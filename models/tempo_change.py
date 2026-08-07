# models/tempo_change.py
from dataclasses import dataclass


@dataclass
class TempoChange:
    """One <sound tempo=.../>+<metronome> marking's position and value
    (Ref 12 "multi-tempo scope"), in the same units as MusicData.tempo_bpm/
    tempo_beat_unit_* (A9) - lets playback (Sequencer) and the status bar
    look up whichever tempo is actually in effect at a given position
    instead of always the score's first marking."""

    quarters_from_start: float
    tempo_bpm: int
    beat_unit_quarter_length: float
    beat_unit_name: str
    display_number: str
