# parsers/timeline_builder.py
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from models.duration_units import beat_unit_display_name, beat_unit_quarter_length
from models.ending_span import EndingSpan
from models.event_slice import EventSlice
from models.hairpin_span import HairpinSpan
from models.note_data import NoteData
from models.parts_structure import PartStructureInfo
from models.repeat_span import RepeatSpan
from models.tempo_change import TempoChange
from models.vocabulary import articulation_name, dynamic_name
from parsers.xml_source import read_musicxml_root


def _duration_divs(elem) -> int:
    dur_el = elem.find("duration")
    return int(dur_el.text.strip()) if (dur_el is not None and dur_el.text) else 0


def _raw_measure_number(measure_elem) -> int:
    """The <measure number="..."> attribute as an int, defaulting to 1 for a
    missing or non-numeric one (MusicXML permits things like "X1" for an
    editorially-added bar)."""
    try:
        return int(measure_elem.attrib.get("number", "1"))
    except ValueError:
        return 1


def _measure_number(measure_elem, needs_reindex: bool) -> int:
    """R4: the measure number this app uses, i.e. the raw one shifted down by
    one when a pickup bar has to become measure 0 (Ref 17).

    This five-line read used to be written out by hand in all five passes
    over the document. They were identical, which meant a change to the
    pickup convention had to be made five times and correctly each time -
    exactly the kind of drift the part-name duplication (R5) had already
    caused a real bug with."""
    return _raw_measure_number(measure_elem) - 1 if needs_reindex else _raw_measure_number(measure_elem)


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


@dataclass
class _FirstPartScan:
    """Everything one walk of the first <part> produces (R4).

    Exists so _scan_first_part can return five related results without a
    five-element tuple at the call site - and so the per-element helpers
    (_step_barline/_step_wedge) have somewhere to append to as they go.
    """

    measure_start_quarters: Dict[int, float] = field(default_factory=dict)
    measure_ts_fifths: Dict[int, Tuple[int, int, int]] = field(default_factory=dict)
    tempo_changes: List[TempoChange] = field(default_factory=list)
    repeat_spans: List[RepeatSpan] = field(default_factory=list)
    ending_spans: List[EndingSpan] = field(default_factory=list)
    hairpin_spans: List[HairpinSpan] = field(default_factory=list)


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

        # Ref 29 "Performance region": repeat-barline pairs, 1st/2nd-ending
        # brackets, and crescendo/diminuendo hairpins, each populated by
        # build() as a side effect - same pattern as tempo_changes above.
        self.repeat_spans: List[RepeatSpan] = []
        self.ending_spans: List[EndingSpan] = []
        self.hairpin_spans: List[HairpinSpan] = []
        # Ref 29: total bar count for the Performance Report, sourced from
        # measure_start_quarters (built regardless of note content) rather
        # than timeline_slices, which would undercount a trailing all-rest
        # measure (rests are skipped entirely from timeline_slices).
        self.total_measures: int = 0

    def _part_names(self, root, default_part_name: str) -> Dict[str, str]:
        """part_id -> the name shown against every note of that part.

        R5: taken from parts_info when the caller has it (i.e. every real
        app load, where MusicXMLReader has already read the part list),
        rather than re-reading <part-list>/<score-part>/<part-name> here.
        The two reads used to be independent and were required to agree
        exactly - CLAUDE.md documented that as a standing invariant after
        they diverged once and made the Performance Report show "0 notes"
        for a fully-noted part (a MuseScore export whose <part-name> is
        Korean; one reader filtered non-ASCII names, the other didn't).
        Deriving the names removes the invariant instead of restating it.

        The etree fallback below is still needed for the no-reader path:
        MusicData(file_path=...) built directly (timeline tests, and
        TimelineBuilder's own fast path) has no parts_info at all.
        """
        if self.parts_info:
            return {p.part_id: p.name for p in self.parts_info}

        part_names: Dict[str, str] = {}
        for sp in root.findall(".//part-list/score-part"):
            sp_id = sp.attrib.get("id", "")
            name_elem = sp.find("part-name")
            part_names[sp_id] = (
                name_elem.text.strip()
                if name_elem is not None and name_elem.text
                else default_part_name
            )
        return part_names

    def build(self) -> List[EventSlice]:
        root = self._root
        if root is None:
            try:
                root = read_musicxml_root(self.file_path)
            except Exception as e:
                print(f"[ERROR] Failed to parse XML for timeline: {e}")
                return []

        default_part_name = self.parts_info[0].name if self.parts_info else "Classical Guitar"
        part_names = self._part_names(root, default_part_name)

        first_measure_number, needs_reindex, pickup_filled_quarters = self._detect_pickup(root)
        scan = self._scan_first_part(root, needs_reindex, pickup_filled_quarters)
        measure_start_quarters = scan.measure_start_quarters
        measure_ts_fifths = scan.measure_ts_fifths
        self.tempo_changes = scan.tempo_changes
        self.repeat_spans = scan.repeat_spans
        self.ending_spans = scan.ending_spans
        self.hairpin_spans = scan.hairpin_spans
        self.total_measures = max(measure_start_quarters.keys()) if measure_start_quarters else 0

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
                m_num = _measure_number(m, needs_reindex)

                walker = _MeasureOffsetWalker(divisions, time_sig_num, time_sig_den, fifths)
                # F3/Ref 16 AC3: a MuseScore-style dynamics mark is a
                # <direction> sibling of <note>, not a child of it - keyed by
                # (staff_or_None, offset_divs) so the note landing at that
                # same offset (including every note of a chord, which all
                # share the base note's offset) picks it up below. Reset per
                # measure since a direction's target note is always in the
                # same measure it appears in.
                pending_dynamics: Dict[Tuple[Optional[int], int], str] = {}

                for elem in m:
                    result = walker.step(elem)

                    if elem.tag == "attributes":
                        beat_unit_quarter_len = 4.0 / walker.ts_den
                        full_bar_quarters = walker.ts_num * beat_unit_quarter_len

                    if elem.tag == "direction":
                        dyn_el = elem.find("direction-type/dynamics")
                        if dyn_el is not None and len(dyn_el) > 0:
                            mark_el = dyn_el[0]
                            mark = mark_el.text.strip() if (mark_el.tag == "other-dynamics" and mark_el.text) else mark_el.tag
                            dir_staff_el = elem.find("staff")
                            dir_staff = int(dir_staff_el.text.strip()) if (dir_staff_el is not None and dir_staff_el.text) else None
                            pending_dynamics[(dir_staff, walker.offset_divs)] = dynamic_name(mark)

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
                        dynamic = None
                        articulation = None
                        fingering = None
                        pluck = None
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
                        fingering = None
                        pluck = None
                        tech_el = elem.find("notations/technical")
                        if tech_el is not None:
                            f_el = tech_el.find("fret")
                            s_el = tech_el.find("string")
                            if f_el is not None and f_el.text:
                                fret = int(f_el.text.strip())
                            if s_el is not None and s_el.text:
                                string_num = int(s_el.text.strip())
                            # MusicXML allows more than one <fingering>/
                            # <pluck> per note (e.g. a rasgueado marked with
                            # all of p/i/m/a on one note) - .find() would
                            # silently drop everything after the first, so
                            # every match is joined instead.
                            fing_texts = [e.text.strip() for e in tech_el.findall("fingering") if e.text]
                            pluck_texts = [e.text.strip() for e in tech_el.findall("pluck") if e.text]
                            fingering = ", ".join(fing_texts) or None
                            pluck = ", ".join(pluck_texts) or None

                        # F3/Ref 16 AC3: staccato/accent/tenuto... and
                        # trill/turn/mordent... share the same spoken-word
                        # treatment, so both notations children are merged
                        # into one comma-joined field rather than kept apart.
                        artic_tags = [
                            child.tag
                            for parent_tag in ("articulations", "ornaments")
                            for child in elem.findall(f"notations/{parent_tag}/*")
                        ]
                        articulation = ", ".join(articulation_name(t) for t in artic_tags) or None

                        # A direct notations/dynamics is the rarer form some
                        # exporters use in place of a <direction> sibling;
                        # when present it's more specific than an
                        # offset-matched direction, so it wins.
                        note_dyn_el = elem.find("notations/dynamics")
                        if note_dyn_el is not None and len(note_dyn_el) > 0:
                            note_mark_el = note_dyn_el[0]
                            note_mark = (
                                note_mark_el.text.strip()
                                if (note_mark_el.tag == "other-dynamics" and note_mark_el.text)
                                else note_mark_el.tag
                            )
                            dynamic = dynamic_name(note_mark)
                        else:
                            dynamic = pending_dynamics.get((staff, note_offset_divs))
                            if dynamic is None:
                                dynamic = pending_dynamics.get((None, note_offset_divs))

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
                        dynamic=dynamic,
                        articulation=articulation,
                        fingering=fingering,
                        pluck=pluck,
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

    def _scan_first_part(
        self, root, needs_reindex: bool, pickup_filled_quarters: float
    ) -> "_FirstPartScan":
        """One walk of the first <part>, collecting everything score-wide.

        R4: this was four separate methods (_measure_start_quarters,
        _tempo_changes, _repeat_and_ending_spans, _hairpin_spans), each
        re-walking the same measures with its own copy of the measure-number
        parse and - for three of them - its own _MeasureOffsetWalker. They
        were four chances for the pickup/offset handling to drift apart, and
        four places to update for any change to it.

        Everything here is read from the FIRST <part> only, the established
        "structural, not per-voice" convention (_detect_pickup does the
        same): time signatures, tempo markings, repeat barlines, endings and
        hairpins are all score-wide properties, not something that could
        sensibly vary between parts of the same score.

        R17: measure length is computed from the time signature in effect at
        the START of each measure (snapshotted at its first <attributes>),
        which is what the old _measure_start_quarters did via
        m.find("attributes") and what MusicXML means - a time signature
        change takes effect at a barline. Every other consumer here reads
        the walker's live value, so a mid-measure <attributes> still affects
        offsets for anything after it, exactly as before. The two readings
        used to differ by accident (one method used find(), the others a
        walker); now the difference is explicit and deliberate.
        """
        scan = _FirstPartScan()
        first_part = root.find("part")
        if first_part is None:
            return scan

        running_total = 0.0
        divisions, ts_num, ts_den, fifths = 1, 4, 4, 0
        open_repeat_measure: Optional[int] = None
        open_endings: Dict[int, int] = {}
        # Unlike pending_dynamics in build() (reset per measure), an open
        # wedge must persist ACROSS measures - a hairpin routinely spans
        # several bars.
        # (kind, start_measure, start_beat_position, start_quarters_from_start)
        open_wedge: Optional[Tuple[str, int, float, float]] = None

        for m in first_part.findall("measure"):
            m_num = _measure_number(m, needs_reindex)
            # Set before walking the measure's contents, so the tempo and
            # hairpin handlers below can resolve their own absolute
            # positions against it as they go.
            scan.measure_start_quarters[m_num] = running_total

            walker = _MeasureOffsetWalker(divisions, ts_num, ts_den, fifths)
            measure_ts: Optional[Tuple[int, int, int]] = None

            for elem in m:
                walker.step(elem)

                if elem.tag == "attributes":
                    if measure_ts is None:
                        measure_ts = (walker.ts_num, walker.ts_den, walker.fifths)
                elif elem.tag == "direction":
                    change = self._tempo_change_from_direction(
                        elem, m_num, walker, scan.measure_start_quarters
                    )
                    if change is not None:
                        scan.tempo_changes.append(change)
                    open_wedge = self._step_wedge(
                        elem, m_num, walker, scan, open_wedge, pickup_filled_quarters
                    )
                elif elem.tag == "barline":
                    open_repeat_measure = self._step_barline(
                        elem, m_num, scan, open_repeat_measure, open_endings
                    )

            if measure_ts is None:
                # No <attributes> in this measure, so nothing could have
                # changed the carried-in signature - the walker's values are
                # still exactly those.
                measure_ts = (walker.ts_num, walker.ts_den, walker.fifths)
            scan.measure_ts_fifths[m_num] = measure_ts

            full_bar_quarters = measure_ts[0] * (4.0 / measure_ts[1])
            running_total += pickup_filled_quarters if m_num == 0 else full_bar_quarters

            divisions, ts_num, ts_den, fifths = (
                walker.divisions, walker.ts_num, walker.ts_den, walker.fifths
            )

        scan.tempo_changes.sort(key=lambda c: c.quarters_from_start)
        return scan

    def _step_barline(
        self,
        barline_parent,
        m_num: int,
        scan: "_FirstPartScan",
        open_repeat_measure: Optional[int],
        open_endings: Dict[int, int],
    ) -> Optional[int]:
        """Ref 29: <barline>/<repeat> and <barline>/<ending>, paired by
        simple open/close tracking in document order. Returns the new
        "currently open forward repeat" measure (None once closed).

        A <repeat direction="forward"/> opens a RepeatSpan, closed by the
        next <repeat direction="backward"/> - a second forward before any
        close replaces the open one, since nested repeat barlines aren't a
        real notation concept. A backward repeat with no open forward
        defaults its start to measure 1, the standard reading of an unmarked
        opening repeat. <ending number="N" type="start"> opens EndingSpan N,
        closed by the next stop/discontinue for that SAME number (start and
        close are very often the same measure - a 1st/2nd-ending pair
        typically lives on one bar's left and right barlines).
        """
        repeat_el = barline_parent.find("repeat")
        if repeat_el is not None:
            direction = repeat_el.attrib.get("direction")
            if direction == "forward":
                open_repeat_measure = m_num
            elif direction == "backward":
                start = open_repeat_measure if open_repeat_measure is not None else 1
                scan.repeat_spans.append(RepeatSpan(start_measure=start, end_measure=m_num))
                open_repeat_measure = None

        ending_el = barline_parent.find("ending")
        if ending_el is not None:
            number_attr = ending_el.attrib.get("number", "").strip()
            first_token = number_attr.replace(",", " ").split()[0] if number_attr else ""
            try:
                number = int(first_token)
            except ValueError:
                return open_repeat_measure
            ending_type = ending_el.attrib.get("type")
            if ending_type == "start":
                open_endings[number] = m_num
            elif ending_type in ("stop", "discontinue"):
                start = open_endings.pop(number, m_num)
                scan.ending_spans.append(
                    EndingSpan(number=number, start_measure=start, end_measure=m_num)
                )

        return open_repeat_measure

    def _step_wedge(
        self,
        direction_elem,
        m_num: int,
        walker: "_MeasureOffsetWalker",
        scan: "_FirstPartScan",
        open_wedge: Optional[Tuple[str, int, float, float]],
        pickup_filled_quarters: float,
    ) -> Optional[Tuple[str, int, float, float]]:
        """Ref 29: crescendo/diminuendo hairpins (<direction>/
        <direction-type>/<wedge>). Returns the new open-wedge state.

        MusicXML's wedge `number` attribute (default 1) disambiguates
        overlapping wedges on the same staff - ignored here (a single open
        wedge is tracked), a deliberate v1 simplification since no file this
        app has been tested against has an overlapping wedge.
        """
        wedge_el = direction_elem.find("direction-type/wedge")
        if wedge_el is None:
            return open_wedge

        wedge_type = wedge_el.attrib.get("type")
        beat_unit_quarter_len = 4.0 / walker.ts_den
        full_bar_quarters = walker.ts_num * beat_unit_quarter_len
        offset_q = walker.offset_divs / walker.divisions
        if m_num == 0:
            start_beat = self._start_beat(
                full_bar_quarters, pickup_filled_quarters, beat_unit_quarter_len
            )
            beat_pos = start_beat + (offset_q / beat_unit_quarter_len)
        else:
            beat_pos = 1.0 + (offset_q / beat_unit_quarter_len)
        quarters = scan.measure_start_quarters.get(m_num, 0.0) + offset_q

        if wedge_type in ("crescendo", "diminuendo"):
            return (wedge_type, m_num, round(beat_pos, 2), quarters)
        if wedge_type == "stop" and open_wedge is not None:
            kind, start_m, start_beat_pos, start_quarters = open_wedge
            scan.hairpin_spans.append(
                HairpinSpan(
                    kind=kind,
                    start_measure=start_m,
                    start_beat_position=start_beat_pos,
                    start_quarters_from_start=start_quarters,
                    end_measure=m_num,
                    end_beat_position=round(beat_pos, 2),
                    end_quarters_from_start=quarters,
                )
            )
            return None
        return open_wedge

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

        # Raw, not _measure_number: this pass is what DECIDES needs_reindex,
        # so it has to read the number as the file spells it.
        first_measure_number = _raw_measure_number(first_measure)

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
