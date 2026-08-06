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
