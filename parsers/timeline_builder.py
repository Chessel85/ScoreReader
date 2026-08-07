# parsers/timeline_builder.py
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

from models.duration_units import beat_unit_display_name, beat_unit_quarter_length
from models.event_slice import EventSlice
from models.note_data import NoteData
from models.parts_structure import PartStructureInfo
from models.tempo_change import TempoChange


def _duration_divs(elem) -> int:
    dur_el = elem.find("duration")
    return int(dur_el.text.strip()) if (dur_el is not None and dur_el.text) else 0


def _apply_attributes(
    attrs_elem, divisions: int, ts_num: int, ts_den: int, fifths: int
) -> Tuple[int, int, int, int]:
    """Ref 18: divisions/time signature can change mid-score, so this is
    called every time an <attributes> element is encountered walking in
    document order, not just once for the whole file. Key signature
    (fifths) is tracked the same way (C6/D-11) for the status bar."""
    div_elem = attrs_elem.find("divisions")
    if div_elem is not None and div_elem.text:
        divisions = int(div_elem.text.strip())

    time_elem = attrs_elem.find("time")
    if time_elem is not None:
        b = time_elem.find("beats")
        bt = time_elem.find("beat-type")
        if b is not None and b.text:
            ts_num = int(b.text.strip())
        if bt is not None and bt.text:
            ts_den = int(bt.text.strip())

    fifths_elem = attrs_elem.find("key/fifths")
    if fifths_elem is not None and fifths_elem.text:
        fifths = int(fifths_elem.text.strip())

    return divisions, ts_num, ts_den, fifths


class _MeasureOffsetWalker:
    """Tracks the <backup>/<forward>-adjusted offset (in divisions) through
    one <measure>, updating divisions/time-signature state on every
    <attributes> element along the way.

    Shared by the pickup-bar detection pass and the main per-part parse loop
    in TimelineBuilder.build() (R3) - both used to hand-roll this same walk
    independently, which meant a fix to one would not apply to the other.
    """

    def __init__(self, divisions: int, ts_num: int, ts_den: int, fifths: int = 0):
        self.divisions = divisions
        self.ts_num = ts_num
        self.ts_den = ts_den
        self.fifths = fifths
        self.offset_divs = 0

    def step(self, elem) -> Optional[Tuple[int, bool]]:
        """Advances state for one child of a <measure>.

        Returns (note_offset_divs, is_chord) for a <note> element - the
        offset the note itself starts at, which for a chord note is behind
        the running offset by the chord's own duration since chord notes
        share their predecessor's start time. Returns None for every other
        element (attributes/backup/forward already applied as a side
        effect).
        """
        if elem.tag == "attributes":
            self.divisions, self.ts_num, self.ts_den, self.fifths = _apply_attributes(
                elem, self.divisions, self.ts_num, self.ts_den, self.fifths
            )
            return None
        if elem.tag == "backup":
            self.offset_divs -= _duration_divs(elem)
            return None
        if elem.tag == "forward":
            self.offset_divs += _duration_divs(elem)
            return None
        if elem.tag == "note":
            dur_divs = _duration_divs(elem)
            is_chord = elem.find("chord") is not None
            if is_chord:
                note_offset_divs = self.offset_divs - dur_divs
            else:
                note_offset_divs = self.offset_divs
                self.offset_divs += dur_divs
            return note_offset_divs, is_chord
        return None


class TimelineBuilder:
    """Builds the flat, sorted EventSlice timeline for a MusicXML file.

    A hand-rolled ElementTree pass, not music21 - it is the source of truth
    for notes because it handles <backup>/<forward> offsets, <chord>
    grouping, and notations/technical string/fret data explicitly, and it is
    ~460x faster than routing through music21.converter.parse.
    """

    def __init__(
        self,
        file_path: str,
        parts_info: List[PartStructureInfo],
        root: Optional[ET.Element] = None,
    ):
        """root: an already-parsed ElementTree root, if the caller (today
        only MusicXMLReader) has one, so this class does not re-parse the
        same file (R2). Falls back to parsing file_path itself when root is
        None - the path timeline tests use via MusicData(file_path=...)."""
        self.file_path = file_path
        self.parts_info = parts_info
        self._root = root
        # Ref 12 "multi-tempo scope": populated by build() as a side effect -
        # every <sound tempo=.../> marking in the piece, not just the first
        # (MusicXMLReader._extract_tempo's job), so callers can look up
        # whichever tempo is actually in effect at a given position.
        self.tempo_changes: List[TempoChange] = []

        # E9/Ref 14 AC4: populated by build() as a side effect, same pattern
        # as tempo_changes above - synthetic, empty-notes EventSlices at
        # every whole beat with no real note. Not part of the returned
        # timeline_slices; see build()'s own comment for why.
        self.beat_markers: List[EventSlice] = []

    def build(self) -> List[EventSlice]:
        root = self._root
        if root is None:
            try:
                root = ET.parse(self.file_path).getroot()
            except Exception as e:
                print(f"[ERROR] Failed to parse XML for timeline: {e}")
                return []

        default_part_name = self.parts_info[0].name if self.parts_info else "Classical Guitar"

        part_names: Dict[str, str] = {}
        for sp in root.findall(".//part-list/score-part"):
            sp_id = sp.attrib.get("id", "")
            name_elem = sp.find("part-name")
            part_names[sp_id] = (
                name_elem.text.strip() if name_elem is not None and name_elem.text else default_part_name
            )

        first_measure_number, needs_reindex, pickup_filled_quarters = self._detect_pickup(root)
        measure_start_quarters, measure_ts_fifths = self._measure_start_quarters(
            root, needs_reindex, pickup_filled_quarters
        )
        self.tempo_changes = self._tempo_changes(root, needs_reindex, measure_start_quarters)

        buckets: Dict[Tuple[int, float], List[NoteData]] = {}
        # Time signature + key fifths in effect at each (measure, offset) key,
        # for stamping the built EventSlice (C6/D-11) - tracked alongside the
        # buckets since a slice's own state isn't known until every part's
        # notes at that key have been visited.
        slice_state: Dict[Tuple[int, float], Tuple[Tuple[int, int], int]] = {}

        for part in root.findall("part"):
            part_id = part.attrib.get("id", "")
            part_name = part_names.get(part_id, default_part_name)

            divisions, time_sig_num, time_sig_den, fifths = 1, 4, 4, 0
            beat_unit_quarter_len = 4.0 / time_sig_den
            full_bar_quarters = time_sig_num * beat_unit_quarter_len

            for m in part.findall("measure"):
                m_attr_num = m.attrib.get("number", "1")
                try:
                    raw_m_num = int(m_attr_num)
                except ValueError:
                    raw_m_num = 1

                m_num = raw_m_num - 1 if needs_reindex else raw_m_num

                walker = _MeasureOffsetWalker(divisions, time_sig_num, time_sig_den, fifths)

                for elem in m:
                    result = walker.step(elem)

                    if elem.tag == "attributes":
                        beat_unit_quarter_len = 4.0 / walker.ts_den
                        full_bar_quarters = walker.ts_num * beat_unit_quarter_len

                    if result is None:
                        continue
                    note_offset_divs, is_chord = result

                    is_rest = elem.find("rest") is not None
                    dur_divs = _duration_divs(elem)

                    staff = int(elem.find("staff").text.strip()) if elem.find("staff") is not None else 1
                    voice = int(elem.find("voice").text.strip()) if elem.find("voice") is not None else 1

                    if is_rest:
                        step_name = "rest"
                        octave = None
                        midi_pitch = None
                        fret = None
                        string_num = None
                    else:
                        pitch_el = elem.find("pitch")
                        if pitch_el is None:
                            continue

                        step = pitch_el.find("step").text.strip() if pitch_el.find("step") is not None else "C"
                        octave = int(pitch_el.find("octave").text.strip()) if pitch_el.find("octave") is not None else 4
                        alter_el = pitch_el.find("alter")
                        alter = int(alter_el.text.strip()) if (alter_el is not None and alter_el.text) else 0

                        acc_words = {1: " sharp", -1: " flat", 2: " double sharp", -2: " double flat", 0: ""}
                        step_name = f"{step}{acc_words.get(alter, '')}"

                        step_offsets = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
                        midi_pitch = (octave + 1) * 12 + step_offsets.get(step, 0) + alter

                        fret = None
                        string_num = None
                        tech_el = elem.find("notations/technical")
                        if tech_el is not None:
                            f_el = tech_el.find("fret")
                            s_el = tech_el.find("string")
                            if f_el is not None and f_el.text:
                                fret = int(f_el.text.strip())
                            if s_el is not None and s_el.text:
                                string_num = int(s_el.text.strip())

                    offset_q = note_offset_divs / walker.divisions
                    quarter_len = dur_divs / walker.divisions
                    ts_duration = round(quarter_len / beat_unit_quarter_len, 2)

                    if m_num == 0:
                        start_beat = self._start_beat(
                            full_bar_quarters, pickup_filled_quarters, beat_unit_quarter_len
                        )
                        beat_pos = start_beat + (offset_q / beat_unit_quarter_len)
                    else:
                        beat_pos = 1.0 + (offset_q / beat_unit_quarter_len)

                    note_obj = NoteData(
                        step_name=step_name,
                        octave=octave,
                        midi_pitch=midi_pitch,
                        measure=m_num,
                        beat_position=round(beat_pos, 2),
                        ts_duration=ts_duration,
                        quarter_length=quarter_len,
                        part_id=part_id,
                        part_name=part_name,
                        staff=staff,
                        voice=voice,
                        fret=fret,
                        string=string_num,
                    )

                    key = (m_num, round(offset_q, 4))
                    if key not in buckets:
                        buckets[key] = []
                    buckets[key].append(note_obj)
                    slice_state[key] = ((walker.ts_num, walker.ts_den), walker.fifths)

                divisions, time_sig_num, time_sig_den, fifths = (
                    walker.divisions, walker.ts_num, walker.ts_den, walker.fifths
                )

        sorted_keys = sorted(buckets.keys(), key=lambda k: (k[0], k[1]))

        slices = []
        for m_num, offset_q in sorted_keys:
            notes = buckets[(m_num, offset_q)]
            q_len = min(n.quarter_length for n in notes) if notes else 1.0
            beat_pos = notes[0].beat_position if notes else 1.0
            time_sig, key_fifths = slice_state.get((m_num, offset_q), ((4, 4), 0))

            slices.append(
                EventSlice(
                    measure=m_num,
                    beat_position=beat_pos,
                    quarter_length=q_len,
                    notes=notes,
                    time_sig=time_sig,
                    key_fifths=key_fifths,
                    quarters_from_start=measure_start_quarters.get(m_num, 0.0) + offset_q,
                )
            )

        # E9/Ref 14 AC4: synthetic, empty-notes markers at every whole beat
        # that has no real note - kept OUT of the returned timeline_slices
        # itself (that list stays exactly "one entry per (measure, offset)
        # with at least one sounding note", the invariant the rest of the
        # codebase - and a good number of existing tests - already assume).
        # Exposed separately as a side effect (mirrors tempo_changes above);
        # MusicData only splices these into its own working timeline when
        # metronome_enabled actually turns on (set_metronome_enabled), so a
        # score with the metronome never touched behaves exactly as before
        # this feature existed.
        self.beat_markers = sorted(
            self._beat_marker_slices(buckets, measure_start_quarters, measure_ts_fifths, pickup_filled_quarters),
            key=lambda s: (s.measure, s.quarters_from_start),
        )

        return slices

    @staticmethod
    def _start_beat(full_bar_quarters: float, pickup_filled_quarters: float, beat_unit_quarter_len: float) -> float:
        """Ref 17/A3: pickup notes are positioned as if placed at the END of
        a notional full bar - e.g. a 6/8 pickup containing only 3 real beats
        starts at beat 4, not beat 1. Shared by real-note beat_position
        construction above and the synthetic beat-marker pass below (E9) so
        the two definitions can't drift apart."""
        return 1.0 + ((full_bar_quarters - pickup_filled_quarters) / beat_unit_quarter_len)

    def _beat_marker_slices(
        self,
        buckets: Dict[Tuple[int, float], List[NoteData]],
        measure_start_quarters: Dict[int, float],
        measure_ts_fifths: Dict[int, Tuple[int, int, int]],
        pickup_filled_quarters: float,
    ) -> List[EventSlice]:
        """E9/Ref 14 AC4: one empty-notes EventSlice per whole beat position
        (1..ts_num) in every measure that doesn't already have a real event
        there. The pickup measure (m_num == 0) only gets markers from its
        own _start_beat onward - beats before that don't correspond to any
        real time before the piece starts, so generating them would make
        silent "beats" reachable before the piece has even begun.
        """
        markers: List[EventSlice] = []
        for m_num, (ts_num, ts_den, fifths) in measure_ts_fifths.items():
            beat_unit_quarter_len = 4.0 / ts_den
            full_bar_quarters = ts_num * beat_unit_quarter_len
            start_beat = (
                self._start_beat(full_bar_quarters, pickup_filled_quarters, beat_unit_quarter_len)
                if m_num == 0
                else 1.0
            )

            beat = start_beat
            while beat <= ts_num + 1e-9:
                offset_q = (beat - start_beat) * beat_unit_quarter_len
                key = (m_num, round(offset_q, 4))
                if key not in buckets:
                    markers.append(
                        EventSlice(
                            measure=m_num,
                            beat_position=round(beat, 2),
                            quarter_length=beat_unit_quarter_len,
                            notes=[],
                            time_sig=(ts_num, ts_den),
                            key_fifths=fifths,
                            quarters_from_start=measure_start_quarters.get(m_num, 0.0) + offset_q,
                        )
                    )
                beat += 1.0
        return markers

    def _measure_start_quarters(
        self, root, needs_reindex: bool, pickup_filled_quarters: float
    ) -> Tuple[Dict[int, float], Dict[int, Tuple[int, int, int]]]:
        """E4: real elapsed quarters-from-piece-start at which each measure
        begins, independent of any part's own note content - notes within a
        measure already carry their own quarter offset from the start of
        that measure (offset_q, the same value used as half the (measure,
        offset) bucket key above), so adding this gives absolute timing.

        Also returns each measure's own (ts_num, ts_den, fifths) as of that
        measure's own <attributes> - the per-measure beat range/key state
        the E9 synthetic beat-marker pass needs, collected in this same walk
        rather than a second one.

        Walked from the first <part> only (mirrors _detect_pickup), on the
        same assumption the main per-part loop above makes when a part
        doesn't redeclare its own <time>: time signature applies uniformly
        across parts within a measure.
        """
        first_part = root.find("part")
        if first_part is None:
            return {}, {}

        starts: Dict[int, float] = {}
        measure_ts_fifths: Dict[int, Tuple[int, int, int]] = {}
        running_total = 0.0
        ts_num, ts_den, fifths = 4, 4, 0

        for m in first_part.findall("measure"):
            m_attr_num = m.attrib.get("number", "1")
            try:
                raw_m_num = int(m_attr_num)
            except ValueError:
                raw_m_num = 1
            m_num = raw_m_num - 1 if needs_reindex else raw_m_num

            starts[m_num] = running_total

            attrs_elem = m.find("attributes")
            if attrs_elem is not None:
                _, ts_num, ts_den, fifths = _apply_attributes(attrs_elem, 1, ts_num, ts_den, fifths)

            measure_ts_fifths[m_num] = (ts_num, ts_den, fifths)

            full_bar_quarters = ts_num * (4.0 / ts_den)
            running_total += pickup_filled_quarters if m_num == 0 else full_bar_quarters

        return starts, measure_ts_fifths

    def _tempo_changes(
        self, root, needs_reindex: bool, measure_start_quarters: Dict[int, float]
    ) -> List[TempoChange]:
        """Ref 12 "multi-tempo scope": every <direction> carrying a
        <sound tempo=.../> + <metronome> marking, at the real elapsed
        position it occurs - not just the score's first one
        (MusicXMLReader._extract_tempo only ever looks at tempos[0]).
        Walked from the first <part> only, same assumption
        _measure_start_quarters makes, using the same _MeasureOffsetWalker
        so a mid-measure marking (not just one at beat 1) lands at the
        right offset.

        MusicXML's <sound tempo="X"> is always quarter notes per minute
        regardless of the marking's own beat unit, so it's used directly as
        TempoChange.tempo_bpm with no conversion - only the beat-unit
        display fields need translating from <beat-unit>/<beat-unit-dot>
        for the status bar/dialog to show the number the way the score
        itself is marked (e.g. "96 eighth notes per minute").
        """
        first_part = root.find("part")
        if first_part is None:
            return []

        changes: List[TempoChange] = []
        divisions, ts_num, ts_den, fifths = 1, 4, 4, 0

        for m in first_part.findall("measure"):
            m_attr_num = m.attrib.get("number", "1")
            try:
                raw_m_num = int(m_attr_num)
            except ValueError:
                raw_m_num = 1
            m_num = raw_m_num - 1 if needs_reindex else raw_m_num

            walker = _MeasureOffsetWalker(divisions, ts_num, ts_den, fifths)

            for elem in m:
                walker.step(elem)

                if elem.tag == "direction":
                    change = self._tempo_change_from_direction(elem, m_num, walker, measure_start_quarters)
                    if change is not None:
                        changes.append(change)

            divisions, ts_num, ts_den, fifths = walker.divisions, walker.ts_num, walker.ts_den, walker.fifths

        changes.sort(key=lambda c: c.quarters_from_start)
        return changes

    @staticmethod
    def _tempo_change_from_direction(
        elem, m_num: int, walker: "_MeasureOffsetWalker", measure_start_quarters: Dict[int, float]
    ) -> Optional[TempoChange]:
        sound_el = elem.find("sound")
        metronome_el = elem.find("direction-type/metronome")
        if sound_el is None or metronome_el is None:
            return None
        tempo_attr = sound_el.attrib.get("tempo")
        beat_unit_el = metronome_el.find("beat-unit")
        per_minute_el = metronome_el.find("per-minute")
        if not tempo_attr or beat_unit_el is None or not beat_unit_el.text or per_minute_el is None or not per_minute_el.text:
            return None

        try:
            tempo_bpm = float(tempo_attr)
            per_minute = float(per_minute_el.text.strip())
        except ValueError:
            return None

        dots = len(metronome_el.findall("beat-unit-dot"))
        beat_unit_ql = beat_unit_quarter_length(beat_unit_el.text.strip(), dots)
        offset_q = walker.offset_divs / walker.divisions

        return TempoChange(
            quarters_from_start=measure_start_quarters.get(m_num, 0.0) + offset_q,
            tempo_bpm=int(round(tempo_bpm)),
            beat_unit_quarter_length=beat_unit_ql,
            beat_unit_name=beat_unit_display_name(beat_unit_el.text.strip(), dots),
            display_number=str(int(per_minute)) if per_minute.is_integer() else str(per_minute),
        )

    def _detect_pickup(self, root) -> Tuple[int, bool, float]:
        """Ref 17: is the first measure a pickup bar, and if so how full is
        it (in quarters)? Walks only the first <measure> across the whole
        file, using staff-1 non-chord notes to measure how much of a full
        bar it actually contains.

        Returns (first_measure_number, needs_reindex, pickup_filled_quarters).
        needs_reindex is False and pickup_filled_quarters is 0.0 when the
        first measure is a full bar, so callers can use them unconditionally.
        """
        first_measure = root.find(".//part/measure")
        is_pickup = False
        pickup_filled_quarters = 0.0
        first_measure_number = 1

        if first_measure is None:
            return first_measure_number, False, pickup_filled_quarters

        try:
            first_measure_number = int(first_measure.attrib.get("number", "1"))
        except ValueError:
            first_measure_number = 1

        if first_measure.attrib.get("implicit") == "yes":
            is_pickup = True

        walker = _MeasureOffsetWalker(divisions=1, ts_num=4, ts_den=4)
        max_offset = 0

        for elem in first_measure:
            result = walker.step(elem)
            if result is None:
                continue
            note_offset_divs, is_chord = result
            if is_chord:
                continue

            staff = elem.find("staff")
            staff_id = int(staff.text.strip()) if staff is not None and staff.text else 1
            if staff_id == 1:
                max_offset = max(max_offset, walker.offset_divs)

        det_full_bar_quarters = walker.ts_num * (4.0 / walker.ts_den)
        pickup_filled_quarters = max_offset / walker.divisions

        if 0 < pickup_filled_quarters < det_full_bar_quarters:
            is_pickup = True

        # Two exporter conventions for the pickup: numbered 1 (re-index
        # every measure down by one so it lands on 0) or already numbered 0
        # (leave numbering alone - subtracting again would land it on -1).
        needs_reindex = is_pickup and first_measure_number != 0

        return first_measure_number, needs_reindex, pickup_filled_quarters
