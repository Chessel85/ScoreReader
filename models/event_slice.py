# event_slice.py
from dataclasses import dataclass, field
from typing import List
from models.note_data import NoteData


@dataclass
class EventSlice:
    measure: int
    beat_position: float
    quarter_length: float
    notes: List[NoteData] = field(default_factory=list)