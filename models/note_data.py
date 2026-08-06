# note_data.py
from dataclasses import dataclass
from typing import Optional


@dataclass
class NoteData:
    step_name: str
    octave: int
    midi_pitch: int
    measure: int
    beat_position: float
    ts_duration: float
    quarter_length: float
    part_id: str
    part_name: str
    staff: int
    voice: int
    fret: Optional[int] = None
    string: Optional[int] = None