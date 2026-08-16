# note_data.py
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class NoteData:
    step_name: str
    measure: int
    beat_position: float
    ts_duration: float
    quarter_length: float
    part_id: str
    part_name: str
    staff: int
    voice: int
    octave: Optional[int] = None
    midi_pitch: Optional[int] = None
    fret: Optional[int] = None
    string: Optional[int] = None
    dynamic: Optional[str] = None
    articulation: Optional[str] = None
    fingering: Optional[str] = None
    pluck: Optional[str] = None
    duration_name_us: Optional[str] = None
    # Guitar Pro import: strum direction ("down stroke"/"up stroke"), set
    # only on the rare beat where GP records one explicitly - never
    # inferred (see CLAUDE.md / the GP import plan's "leave unstated"
    # decision).
    strum: Optional[str] = None
    # Guitar Pro import: the full set of MIDI pitches sounding at this
    # event, populated only on the synthetic Chords voice's one-note-per-
    # strum events (see parsers/gp_timeline_builder.py). midi_pitch above
    # still holds a single representative pitch (for sort order); this
    # field is what get_playback_events_for_indices/get_midi_notes_for_indices
    # use to sound the whole chord instead of just one note. Never
    # displayed as an attribute.
    chord_pitches: Optional[List[int]] = None
    # S6: the fifths value MidiTimelineBuilder actually spelled this note
    # against (None for MusicXML, whose spelling never depends on key at
    # all). Lets MusicData.apply_key_signature_override re-derive a MIDI
    # note's own original spelling when the override is cleared, with no
    # re-parse and no separate cached "original text" field.
    file_key_fifths: Optional[int] = None
