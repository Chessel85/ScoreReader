# tests/audio/test_metronome.py
"""E8/Ref 14: click_event_for_beat is the one rule both the Sequencer
(playback) and MainWindow (navigation) use to decide whether/how a beat
position clicks - pure function, tested in isolation."""
from audio.metronome import (
    METRONOME_ACCENT_NOTE,
    METRONOME_BANK,
    METRONOME_CHANNEL,
    METRONOME_OFFBEAT_NOTE,
    METRONOME_PROGRAM,
    METRONOME_VELOCITY,
    click_event_for_beat,
)


def test_beat_one_is_accented():
    channel, bank, program, pitch, velocity = click_event_for_beat(1.0)
    assert channel == METRONOME_CHANNEL
    assert bank == METRONOME_BANK
    assert program == METRONOME_PROGRAM
    assert pitch == METRONOME_ACCENT_NOTE
    assert velocity == METRONOME_VELOCITY


def test_other_whole_beats_are_not_accented():
    _, _, _, pitch, velocity = click_event_for_beat(3.0)
    assert pitch == METRONOME_OFFBEAT_NOTE, "a different sample distinguishes the accent, not velocity"
    assert velocity == METRONOME_VELOCITY


def test_non_whole_beat_position_is_not_a_click():
    assert click_event_for_beat(1.5) is None
    assert click_event_for_beat(2.25) is None
