# tests/audio/test_metronome.py
"""E8/Ref 14: click_event_for_beat is the one rule both the Sequencer
(playback) and MainWindow (navigation) use to decide whether/how a beat
position clicks - pure function, tested in isolation."""
from audio.metronome import (
    METRONOME_ACCENT_VELOCITY,
    METRONOME_CHANNEL,
    METRONOME_CLAVES_PITCH,
    METRONOME_CLICK_VELOCITY,
    METRONOME_DURATION_MS,
    METRONOME_GM_PROGRAM,
    click_event_for_beat,
)


def test_beat_one_is_accented():
    channel, program, pitch, velocity, duration_ms = click_event_for_beat(1.0)
    assert channel == METRONOME_CHANNEL
    assert program == METRONOME_GM_PROGRAM
    assert pitch == METRONOME_CLAVES_PITCH
    assert velocity == METRONOME_ACCENT_VELOCITY
    assert duration_ms == METRONOME_DURATION_MS


def test_other_whole_beats_are_not_accented():
    _, _, pitch, velocity, _ = click_event_for_beat(3.0)
    assert pitch == METRONOME_CLAVES_PITCH, "same claves voice - only velocity distinguishes the accent"
    assert velocity == METRONOME_CLICK_VELOCITY


def test_non_whole_beat_position_is_not_a_click():
    assert click_event_for_beat(1.5) is None
    assert click_event_for_beat(2.25) is None
