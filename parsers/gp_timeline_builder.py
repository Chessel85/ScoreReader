# parsers/gp_timeline_builder.py
"""Builds the flat, sorted EventSlice timeline for a Guitar Pro (.gp) file -
the GP-native counterpart of TimelineBuilder (MusicXML) and
MidiTimelineBuilder. Unlike MIDI, GP already gives explicit measure/bar
boundaries and exact per-beat rhythm (NoteValue+dots+tuplet), so there is no
tick-based measure-boundary inference to do here - the graph in gp_source.py
already resolves that.

Also builds the synthetic "Chords" voice (see CLAUDE.md / the GP import
plan): one extra NoteData per chord-shaped (2+ note) beat on any track
GpReader already flagged as chord/strum-qualifying (GP_CHORD_VOICE_ID
present in that track's staves_voices), carrying the sticky current chord
name and, only when GP records one, a strum direction - never inferred.

Pickup-bar detection (Ref 17) and repeat/ending/hairpin spans (Ref 29) are
explicitly deferred (see the GP import plan) - repeat_spans/ending_spans/
hairpin_spans stay permanently empty, and measure numbers are never
reindexed, the same way MidiTimelineBuilder starts before Ref 17/29 support
existed there.
"""
from typing import Dict, List, Optional, Tuple

from models.duration_units import beat_unit_display_name, tuplet_word
from models.event_slice import EventSlice
from models.note_data import NoteData
from models.parts_structure import PartStructureInfo
from models.vocabulary import dynamic_name, spell_out_minor_chord
from parsers.gp_source import GpNote, GpSource, GpTrack, iter_track_positions, read_gp_source

# Clearly out of range of GP's real 1-4 <Voices> slots (1-indexed once
# converted - see GpReader), so it can never collide with a real voice
# number even on a score using every slot.
GP_CHORD_VOICE_ID = 1000

# GP's own accidental vocabulary (Property name="ConcertPitch") - mirrors
# MusicXML's acc_words spoken-word convention (never a symbol - see
# CLAUDE.md's key_signatures.py note on the same subject).
_ACCIDENTAL_WORDS = {
    "": "", "#": " sharp", "b": " flat", "##": " double sharp", "bb": " double flat",
}

_STROKE_WORDS = {"Down": "down stroke", "Up": "up stroke"}


class GpTimelineBuilder:
    def __init__(
        self,
        file_path: str,
        parts_info: List[PartStructureInfo],
        source: Optional[GpSource] = None,
    ):
        """source: an already-parsed GpSource if the caller has one (from
        GpReader), so the file isn't parsed twice - mirrors
        MidiTimelineBuilder's source= parameter. Falls back to parsing
        file_path itself, the path MusicData(file_path=...) takes directly
        (tests)."""
        self.file_path = file_path
        self.parts_info = parts_info
        self._source = source

        self.tempo_changes: List = []
        self.beat_markers: List[EventSlice] = []
        self.repeat_spans: List = []
        self.ending_spans: List = []
        self.hairpin_spans: List = []
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
                source = read_gp_source(self.file_path)
            except Exception as e:
                print(f"[ERROR] Failed to parse Guitar Pro file for timeline: {e}")
                return []

        if not source.master_bars or not source.tracks:
            return []

        self.total_measures = len(source.master_bars)

        start_quarters: Dict[int, float] = {}
        offset = 0.0
        for m_index, master_bar in enumerate(source.master_bars):
            m_num = m_index + 1
            start_quarters[m_num] = offset
            ts_num, ts_den = master_bar.time_sig
            offset += ts_num * (4.0 / ts_den)

        part_by_id = {p.part_id: p for p in self.parts_info}
        buckets: Dict[Tuple[int, float], List[NoteData]] = {}
        slice_state: Dict[Tuple[int, float], Tuple[Tuple[int, int], int]] = {}

        for track in source.tracks:
            part_id = f"P{track.index}"
            part = part_by_id.get(part_id)
            part_name = part.name if part is not None else track.name
            qualifies_for_chords = (
                part is not None and GP_CHORD_VOICE_ID in part.staves_voices.get(1, [])
            )
            self._build_track(
                source, track, part_id, part_name, qualifies_for_chords,
                start_quarters, buckets, slice_state,
            )

        part_order = {f"P{t.index}": i for i, t in enumerate(source.tracks)}

        def pitch_sort_key(note: NoteData) -> Tuple[int, int, float]:
            # The synthetic Chords-voice note carries a representative
            # pitch (max(chord_pitches), for this key's own tie-breaking
            # only) that would otherwise interleave it among the real
            # fretted notes by pitch. It's a different kind of entry, not
            # another note in the voicing, so it always sorts after every
            # real note in the instrument's list regardless of pitch.
            is_chord_voice = 1 if note.voice == GP_CHORD_VOICE_ID else 0
            pitch_component = -note.midi_pitch if note.midi_pitch is not None else float("inf")
            return (part_order.get(note.part_id, 0), is_chord_voice, pitch_component)

        for bucket_notes in buckets.values():
            bucket_notes.sort(key=pitch_sort_key)

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
        return slices

    def _build_track(
        self,
        source: GpSource,
        track: GpTrack,
        part_id: str,
        part_name: str,
        qualifies_for_chords: bool,
        start_quarters: Dict[int, float],
        buckets: Dict[Tuple[int, float], List[NoteData]],
        slice_state: Dict[Tuple[int, float], Tuple[Tuple[int, int], int]],
    ) -> None:
        offsets: Dict[Tuple[int, int], float] = {}  # (measure_index, voice_slot) -> running offset
        current_chord_name: Optional[str] = None

        for measure_index, voice_slot, beat_id in iter_track_positions(source, track.index):
            beat = source.beats.get(beat_id)
            if beat is None:
                continue
            master_bar = source.master_bars[measure_index]
            ts_num, ts_den = master_bar.time_sig
            beat_unit_quarter_len = 4.0 / ts_den
            m_num = measure_index + 1

            key = (measure_index, voice_slot)
            offset_q = offsets.get(key, 0.0)
            offsets[key] = offset_q + beat.quarter_length

            if beat.chord_index is not None:
                # track.chord_names holds GP's own raw chord diagram name
                # ("Am") - the same bare-"m" expansion MusicXML/UG chords
                # need (see models/vocabulary.py). Idempotent: re-applying it
                # to an already-expanded sticky value (the fallback default
                # here) is a no-op, since "A minor" itself doesn't match.
                raw_chord_name = track.chord_names.get(beat.chord_index)
                if raw_chord_name is not None:
                    current_chord_name = spell_out_minor_chord(raw_chord_name)

            if not beat.note_ids:
                continue  # a rest - still advances offset above, produces no event

            beat_pos = 1.0 + (offset_q / beat_unit_quarter_len)
            ts_duration = round(beat.quarter_length / beat_unit_quarter_len, 2)
            duration_name_us = beat_unit_display_name(beat.duration_type, beat.duration_dots)
            if beat.tuplet_actual is not None:
                word = tuplet_word(beat.tuplet_actual)
                if word is not None:
                    duration_name_us = f"{duration_name_us} {word}"
            dynamic = dynamic_name(beat.dynamic.lower()) if beat.dynamic else None

            bucket_key = (m_num, round(offset_q, 4))
            slice_state[bucket_key] = ((ts_num, ts_den), master_bar.key_fifths)

            for note_id in beat.note_ids:
                gp_note = source.notes.get(note_id)
                if gp_note is None or gp_note.midi_pitch is None:
                    continue
                step_name = self._spell_note(gp_note)
                articulation_bits = []
                if gp_note.slide:
                    articulation_bits.append("slide")
                if gp_note.muted:
                    articulation_bits.append("muted")
                if gp_note.tie_origin:
                    articulation_bits.append("tied")
                articulation = ", ".join(articulation_bits) or None

                note_obj = NoteData(
                    step_name=step_name,
                    octave=gp_note.octave,
                    midi_pitch=gp_note.midi_pitch,
                    measure=m_num,
                    beat_position=round(beat_pos, 2),
                    ts_duration=ts_duration,
                    quarter_length=beat.quarter_length,
                    part_id=part_id,
                    part_name=part_name,
                    staff=1,
                    voice=voice_slot + 1,
                    fret=gp_note.fret,
                    string=gp_note.string,
                    dynamic=dynamic,
                    articulation=articulation,
                    duration_name_us=duration_name_us,
                )
                buckets.setdefault(bucket_key, []).append(note_obj)

            if qualifies_for_chords and len(beat.note_ids) >= 2:
                chord_pitches = [
                    source.notes[n].midi_pitch for n in beat.note_ids
                    if n in source.notes and source.notes[n].midi_pitch is not None
                ]
                if not chord_pitches:
                    continue
                strum = None
                if beat.brush_direction is not None:
                    strum = _STROKE_WORDS.get(beat.brush_direction, f"{beat.brush_direction.lower()} stroke")

                chord_note = NoteData(
                    step_name=current_chord_name or "Strum",
                    octave=None,
                    midi_pitch=max(chord_pitches),
                    measure=m_num,
                    beat_position=round(beat_pos, 2),
                    ts_duration=ts_duration,
                    quarter_length=beat.quarter_length,
                    part_id=part_id,
                    part_name=part_name,
                    staff=1,
                    voice=GP_CHORD_VOICE_ID,
                    dynamic=dynamic,
                    duration_name_us=duration_name_us,
                    strum=strum,
                    chord_pitches=chord_pitches,
                )
                buckets.setdefault(bucket_key, []).append(chord_note)

    @staticmethod
    def _spell_note(gp_note: GpNote) -> str:
        """Prefer GP's own notated spelling (ConcertPitch) over deriving one
        from the raw MIDI pitch - GP already did that work. Falls back to a
        bare step-less label only in the pathological case of a note with a
        MIDI pitch but no ConcertPitch at all (not seen in any real file
        tested)."""
        if gp_note.step is None:
            return f"MIDI {gp_note.midi_pitch}"
        return f"{gp_note.step}{_ACCIDENTAL_WORDS.get(gp_note.accidental, ' ' + gp_note.accidental)}"
