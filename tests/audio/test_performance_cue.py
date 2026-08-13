# tests/audio/test_performance_cue.py
"""Ref 29: performance_cue_event() is the fixed (channel, bank, program,
pitch, velocity) tuple MainWindow._refresh_region_5 fires whenever the
active Region 5 row set changes - pure function, tested in isolation."""
from audio.metronome import METRONOME_CHANNEL
from audio.performance_cue import (
    PERFORMANCE_CUE_BANK,
    PERFORMANCE_CUE_CHANNEL,
    PERFORMANCE_CUE_NOTE,
    PERFORMANCE_CUE_PROGRAM,
    PERFORMANCE_CUE_VELOCITY,
    performance_cue_event,
)
from audio.position_announcer import POSITION_ANNOUNCER_CHANNEL


def test_performance_cue_event_fields():
    channel, bank, program, pitch, velocity = performance_cue_event()
    assert channel == PERFORMANCE_CUE_CHANNEL
    assert bank == PERFORMANCE_CUE_BANK
    assert program == PERFORMANCE_CUE_PROGRAM
    assert pitch == PERFORMANCE_CUE_NOTE
    assert velocity == PERFORMANCE_CUE_VELOCITY


def test_performance_cue_channel_is_distinct_from_the_other_two_reserved_channels():
    assert PERFORMANCE_CUE_CHANNEL != METRONOME_CHANNEL
    assert PERFORMANCE_CUE_CHANNEL != POSITION_ANNOUNCER_CHANNEL
