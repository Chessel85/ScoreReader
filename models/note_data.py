# note_data.py
from dataclasses import dataclass
from typing import Optional


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
    # S6: the fifths value MidiTimelineBuilder actually spelled this note
    # against (None for MusicXML, whose spelling never depends on key at
    # all). Lets MusicData.apply_key_signature_override re-derive a MIDI
    # note's own original spelling when the override is cleared, with no
    # re-parse and no separate cached "original text" field.
    file_key_fifths: Optional[int] = None
