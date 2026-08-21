# tests/audio/test_grace_note_schedule.py
from audio.grace_note_schedule import (
    DEFAULT_GRACE_DURATION_MS,
    MIN_GRACE_DURATION_MS,
    effective_grace_duration_ms,
)


def test_default_duration_used_when_main_note_is_long_enough():
    main_events = [(0, 0, [69], 500)]
    assert effective_grace_duration_ms(main_events) == DEFAULT_GRACE_DURATION_MS


def test_duration_clamped_to_half_the_shortest_main_note():
    """A very short main note (fast tempo, small note value) must not have
    the grace note's own pre-note outlast it."""
    main_events = [(0, 0, [69], 50)]
    assert effective_grace_duration_ms(main_events) == 25


def test_duration_uses_the_shortest_of_several_parts():
    main_events = [(0, 0, [69], 500), (1, 24, [60], 40)]
    assert effective_grace_duration_ms(main_events) == 20  # half of 40, but floored at MIN


def test_duration_never_drops_below_the_minimum():
    main_events = [(0, 0, [69], 10)]
    assert effective_grace_duration_ms(main_events) == MIN_GRACE_DURATION_MS


def test_no_durations_falls_back_to_the_default():
    assert effective_grace_duration_ms([]) == DEFAULT_GRACE_DURATION_MS
