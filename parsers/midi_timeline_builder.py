# parsers/midi_timeline_builder.py
"""Builds the flat, sorted EventSlice timeline for a Standard MIDI File - the
MIDI-native counterpart of TimelineBuilder (MusicXML). A different
hand-rolled walk, not a shared implementation: raw MIDI has no notations/
tie/<chord>-tag/repeat-barline structure at all, so the two builders only
share a return shape (EventSlice/NoteData), not code. repeat_spans/
ending_spans/hairpin_spans stay permanently empty for a MIDI-loaded score -
there is nothing in a Standard MIDI File that encodes them."""
import bisect
from typing import Dict, List, Optional, Tuple

from models.event_slice import EventSlice
from models.gm_percussion_map import gm_percussion_name
from models.note_data import NoteData
from models.duration_units import is_simple_duration_match, quarter_length_to_display_name
from models.parts_structure import PartStructureInfo
from models.pitch_spelling import spell_pitch
from models.tempo_change import TempoChange
from parsers.midi_source import PERCUSSION_CHANNEL, MidiSource, read_midi_source
from parsers.timeline_builder import TimelineBuilder



class MidiTimelineBuilder:
    def __init__(
        self,
        file_path: str,
        parts_info: List[PartStructureInfo],
        source: Optional[MidiSource] = None,
    ):
        """source: an already-parsed MidiSource if the caller has one (from
        MidiReader), so the file isn't parsed twice - mirrors
        TimelineBuilder's root= parameter. Falls back to parsing file_path
        itself, the path MusicData(file_path=...) takes directly (tests)."""
        self.file_path = file_path
        self.parts_info = parts_info
        self._source = source

        self.tempo_changes: List[TempoChange] = []
        self.beat_markers: List[EventSlice] = []
        self.repeat_spans: List = []
        self.ending_spans: List = []
        self.hairpin_spans: List = []
        # P3: MusicXML-only, like the span lists above.
        self.direction_spans: List = []
        self.direction_marks: List = []
        # P4: MusicXML-only (bar-style / mid-part clef / measure-style).
        self.barline_marks: List = []
        self.clef_change_marks: List = []
        self.measure_style_marks: List = []
        self.segno_marks: List = []
        self.coda_marks: List = []
        self.to_coda_marks: List = []
        self.fine_marks: List = []
        self.navigation_jumps: List = []
        self.total_measures: int = 0

    def build(self) -> List[EventSlice]:
        source = self._source
        if source is None:
            try:
                source = read_midi_source(self.file_path)
            except Exception as e:
                print(f"[ERROR] Failed to parse MIDI for timeline: {e}")
                return []

        if not source.tracks:
            return []

        division = source.division
        total_ticks = max(
            (ev.end_tick for t in source.tracks for ev in t.note_events), default=0
        )

        raw_start, raw_ts, last_raw = self._build_raw_measure_map(
            source.time_signature_changes, division, total_ticks
        )
        needs_reindex, pickup_filled_quarters, governing_ts = self._detect_pickup(raw_ts, last_raw)

        def final_measure(raw_m: int) -> int:
            return raw_m - 1 if needs_reindex else raw_m

        start_quarters = {final_measure(m): t / division for m, t in raw_start.items()}
        time_sig_by_measure = {final_measure(m): ts for m, ts in raw_ts.items()}
        if needs_reindex:
            # The pickup's OWN declared time signature is a fake, shortened
            # one the exporter writes just to size that one bar (see
            # _detect_pickup) - real MusicXML pickups instead declare the
            # true governing signature on the pickup measure itself, so
            # anything reading this measure's time signature (the status
            # bar, _start_beat below) should see the real one too, not the
            # exporter artifact.
            time_sig_by_measure[0] = governing_ts
        self.total_measures = max(start_quarters.keys()) if start_quarters else 0

        boundaries = sorted(raw_start.items(), key=lambda kv: kv[1])
        boundary_ticks = [t for _, t in boundaries]
        boundary_measures = [m for m, _ in boundaries]

        def locate_raw(tick: int) -> int:
            idx = bisect.bisect_right(boundary_ticks, tick) - 1
            idx = max(0, idx)
            return boundary_measures[idx]

        key_changes = sorted(source.key_signature_changes)

        def fifths_at(tick: int) -> int:
            fifths = 0
            for change_tick, sharps in key_changes:
                if change_tick > tick:
                    break
                fifths = sharps
            return fifths

        self.tempo_changes = self._build_tempo_changes(source.tempo_changes, division)

        buckets: Dict[Tuple[int, float], List[NoteData]] = {}
        slice_state: Dict[Tuple[int, float], Tuple[Tuple[int, int], int]] = {}
        part_names = {p.part_id: p.name for p in self.parts_info}

        # Ref 25/S3: a non-quantized (human-performed) recording's real
        # durations are numerically close to SOME type/dots combination
        # almost everywhere, since maxima..256th with 0-3 dots densely
        # covers the range - "close" often lands on a rare one (a
        # double-dotted 32nd) that isn't a trustworthy name just because the
        # numbers happen to line up. Tracked per part/track, not globally: a
        # cleanly quantized part should still get named durations even in a
        # score where another part was played freehand. notes_by_part holds
        # every note built below so the ones needing reverting can be found
        # again after the fact, without a second, separate walk of the
        # source data.
        notes_by_part: Dict[str, List[NoteData]] = {}
        weird_count_by_part: Dict[str, int] = {}

        for track in source.tracks:
            part_name = part_names.get(track.part_id, track.name or track.part_id)
            voice_by_channel = {ch: i + 1 for i, ch in enumerate(track.channels_used)}
            # Wishlist #8: derived straight from the track's own channel
            # usage, not parts_info - MidiReader's is_percussion flag agrees
            # (same check), but the timeline must build correctly even via
            # the no-reader MusicData(file_path=...) path timeline tests use,
            # which has no parts_info at all (see _part_names above).
            is_percussion = track.channels_used == [PERCUSSION_CHANNEL]

            for ev in track.note_events:
                raw_m = locate_raw(ev.start_tick)
                m_num = final_measure(raw_m)
                ts_num, ts_den = time_sig_by_measure[m_num]
                beat_unit_quarter_len = 4.0 / ts_den
                offset_q = (ev.start_tick - raw_start[raw_m]) / division

                if m_num == 0:
                    full_bar_quarters = ts_num * beat_unit_quarter_len
                    start_beat = TimelineBuilder._start_beat(
                        full_bar_quarters, pickup_filled_quarters, beat_unit_quarter_len
                    )
                    beat_pos = start_beat + (offset_q / beat_unit_quarter_len)
                else:
                    beat_pos = 1.0 + (offset_q / beat_unit_quarter_len)

                quarter_len = (ev.end_tick - ev.start_tick) / division
                if quarter_len <= 0:
                    continue
                ts_duration = round(quarter_len / beat_unit_quarter_len, 2)
                fifths = fifths_at(ev.start_tick)
                if is_percussion:
                    # Wishlist #8: a percussion note's key number IS the
                    # sound to play (GM percussion key map), not a pitch to
                    # spell against a key signature - file_key_fifths stays
                    # None so apply_key_signature_override's re-spell loop
                    # (which skips any note with file_key_fifths is None)
                    # leaves these notes alone, the same way it already
                    # leaves MusicXML notes alone.
                    step_name, octave, note_file_key_fifths = gm_percussion_name(ev.pitch), None, None
                else:
                    step_name, octave = spell_pitch(ev.pitch, fifths)
                    note_file_key_fifths = fifths
                # Tolerance of 1%: loose enough to still call a
                # programmatically-quantized file's durations by name
                # (test1.MID/test2.mid), tight enough to reject a note a
                # couple of percent off a clean fraction - which should fall
                # through to _note_attribute_pairs' existing numeric
                # fallback (models/music_data.py) instead of being
                # mis-named. 0.03 (3%) previously called a note at 0.98 of a
                # crotchet "quarter"/"crotchet"; reported, live-tested.
                duration_name_us = quarter_length_to_display_name(quarter_len, tolerance=0.01)
                is_simple = is_simple_duration_match(quarter_len, tolerance=0.01)

                note_obj = NoteData(
                    step_name=step_name,
                    octave=octave,
                    midi_pitch=ev.pitch,
                    measure=m_num,
                    beat_position=round(beat_pos, 2),
                    ts_duration=ts_duration,
                    quarter_length=quarter_len,
                    part_id=track.part_id,
                    part_name=part_name,
                    staff=1,
                    # Region 2 follow-up: a percussion note's voice is its
                    # own note number, not the channel-derived voice every
                    # other track uses - MIDI's percussion channel is
                    # always singular, so voice_by_channel would otherwise
                    # collapse every distinct drum/cymbal onto voice 1. Same
                    # substitution TimelineBuilder makes for MusicXML.
                    voice=ev.pitch if is_percussion else voice_by_channel.get(ev.channel, 1),
                    duration_name_us=duration_name_us,
                    file_key_fifths=note_file_key_fifths,
                    percussion_source_key=ev.pitch if is_percussion else None,
                )

                key = (m_num, round(offset_q, 4))
                buckets.setdefault(key, []).append(note_obj)
                slice_state[key] = ((ts_num, ts_den), fifths)

                notes_by_part.setdefault(track.part_id, []).append(note_obj)
                if duration_name_us is not None and is_simple is False:
                    weird_count_by_part[track.part_id] = weird_count_by_part.get(track.part_id, 0) + 1

        # A track with too many "weird" duration names (over 5%) reverts to
        # numeric display for ALL of its notes, not just the weird ones -
        # reported: a mix of named and numbered durations within one part
        # read as unsatisfactory/inconsistent, even though each individual
        # value was technically defensible on its own.
        for part_id, notes in notes_by_part.items():
            weird = weird_count_by_part.get(part_id, 0)
            if notes and weird / len(notes) > 0.05:
                for n in notes:
                    n.duration_name_us = None

        part_order = {t.part_id: i for i, t in enumerate(source.tracks)}

        def _pitch_sort_key(note: NoteData) -> Tuple[int, float]:
            pitch_component = -note.midi_pitch if note.midi_pitch is not None else float("inf")
            return (part_order.get(note.part_id, 0), pitch_component)

        for bucket_notes in buckets.values():
            bucket_notes.sort(key=_pitch_sort_key)

        slices: List[EventSlice] = []
        for (m_num, offset_q), notes in buckets.items():
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
                    quarters_from_start=start_quarters.get(m_num, 0.0) + offset_q,
                )
            )
        slices.sort(key=lambda s: (s.measure, s.quarters_from_start))

        self.beat_markers = self._beat_marker_slices(
            buckets, start_quarters, time_sig_by_measure, pickup_filled_quarters, fifths_at, division
        )

        return slices

    @staticmethod
    def _build_raw_measure_map(
        time_signature_changes: List[Tuple[int, int, int]], division: int, total_ticks: int
    ) -> Tuple[Dict[int, int], Dict[int, Tuple[int, int]], int]:
        """Raw (un-reindexed) measure number -> start tick / (num, den),
        derived purely from the time-signature meta-event timeline - MIDI has
        no explicit barlines, so a measure's length is however many ticks its
        governing time signature implies, repeated until the next change."""
        raw_start: Dict[int, int] = {}
        raw_ts: Dict[int, Tuple[int, int]] = {}
        m = 1
        for i, (tick, num, den) in enumerate(time_signature_changes):
            # For the last segment, stop once every note's start tick is
            # covered rather than padding to total_ticks + 1 - every note's
            # start is strictly less than total_ticks (the max END tick), so
            # this is exact coverage. Using total_ticks + 1 here previously
            # built one phantom empty trailing measure whenever the last
            # note happened to end exactly on a bar boundary (real bug,
            # caught against files/midi/test1.MID: 5 measures reported for
            # 4 measures of real content).
            next_tick = (
                time_signature_changes[i + 1][0]
                if i + 1 < len(time_signature_changes)
                else total_ticks
            )
            bar_ticks = max(1, round(division * num * 4.0 / den))
            t = tick
            first = True
            while t < next_tick or first:
                raw_start[m] = t
                raw_ts[m] = (num, den)
                t += bar_ticks
                m += 1
                first = False
        return raw_start, raw_ts, m - 1

    @staticmethod
    def _detect_pickup(
        raw_ts: Dict[int, Tuple[int, int]],
        last_raw: int,
    ) -> Tuple[bool, float, Optional[Tuple[int, int]]]:
        """Ref 17, MIDI-native version - detects only the pattern a real
        MuseScore MIDI export of a pickup bar produces: the file's own first
        time-signature span lasts exactly one measure before changing to a
        genuinely longer one (confirmed against
        files/midi/bach-bourree-tab.mid: a real 1/4 span for bar 1 reverting
        to 4/4 at bar 2).

        A content-based fallback (comparing the first bar's actual note
        content to its declared length, mirroring MusicXML's
        implicit="yes"-less fallback) was tried and dropped: unlike
        MusicXML, where a measure's notated notes+rests always sum to
        exactly the declared bar length by construction, raw MIDI has no
        explicit rests, so "content falls short of the barline" fires on any
        ordinary bar whose last note doesn't ring to the literal last tick -
        confirmed as a real false positive on
        pachelbels-canon-in-d-string-quartet.mid, whose staggered canon
        entries and human note-off timing both trip it. A MIDI pickup with
        no time-signature hint (no fixture for this yet) is consequently not
        detected by this version - a known, accepted gap.
        """
        if last_raw < 2:
            return False, 0.0, None

        def bar_quarters(ts: Tuple[int, int]) -> float:
            return ts[0] * 4.0 / ts[1]

        ts1, ts2 = raw_ts[1], raw_ts[2]
        if ts1 != ts2 and bar_quarters(ts1) < bar_quarters(ts2):
            return True, bar_quarters(ts1), ts2
        return False, 0.0, None

    @staticmethod
    def _build_tempo_changes(
        tempo_events: List[Tuple[int, int]], division: int
    ) -> List[TempoChange]:
        changes = []
        for tick, usec_per_quarter in tempo_events:
            bpm = round(60000000 / usec_per_quarter) if usec_per_quarter > 0 else 120
            changes.append(
                TempoChange(
                    quarters_from_start=tick / division,
                    tempo_bpm=bpm,
                    beat_unit_quarter_length=1.0,
                    beat_unit_name="quarter",
                    display_number=str(bpm),
                )
            )
        return changes

    @staticmethod
    def _beat_marker_slices(
        buckets: Dict[Tuple[int, float], List[NoteData]],
        start_quarters: Dict[int, float],
        time_sig_by_measure: Dict[int, Tuple[int, int]],
        pickup_filled_quarters: float,
        fifths_at,
        division: int,
    ) -> List[EventSlice]:
        """Ref 14 AC4, MIDI-native version - see TimelineBuilder's own
        _beat_marker_slices for the shared rationale (one synthetic,
        empty-notes EventSlice per whole beat with no real event)."""
        markers: List[EventSlice] = []
        for m_num, (ts_num, ts_den) in time_sig_by_measure.items():
            beat_unit_quarter_len = 4.0 / ts_den
            full_bar_quarters = ts_num * beat_unit_quarter_len
            start_beat = (
                TimelineBuilder._start_beat(full_bar_quarters, pickup_filled_quarters, beat_unit_quarter_len)
                if m_num == 0
                else 1.0
            )

            beat = start_beat
            while beat <= ts_num + 1e-9:
                offset_q = (beat - start_beat) * beat_unit_quarter_len
                key = (m_num, round(offset_q, 4))
                if key not in buckets:
                    quarters_from_start = start_quarters.get(m_num, 0.0) + offset_q
                    markers.append(
                        EventSlice(
                            measure=m_num,
                            beat_position=round(beat, 2),
                            quarter_length=beat_unit_quarter_len,
                            notes=[],
                            time_sig=(ts_num, ts_den),
                            key_fifths=fifths_at(round(quarters_from_start * division)),
                            quarters_from_start=quarters_from_start,
                        )
                    )
                beat += 1.0
        return markers
