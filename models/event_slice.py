# event_slice.py
from dataclasses import dataclass, field
from typing import List, Tuple
from models.note_data import NoteData


@dataclass
class EventSlice:
    measure: int
    beat_position: float
    quarter_length: float
    notes: List[NoteData] = field(default_factory=list)

    # Time signature (numerator, denominator) and key signature (fifths,
    # MusicXML convention: positive = sharps, negative = flats) in effect at
    # this slice - both can change mid-score, so they're tracked per-event
    # the same way ts_duration already is (D-11, C6). Drives the status bar.
    time_sig: Tuple[int, int] = (4, 4)
    key_fifths: int = 0