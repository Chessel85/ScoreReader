# tests/audio/test_strum_schedule.py
from audio.strum_schedule import build_strum_schedule
from parsers.ug_source import strum_directions


def test_downstroke_fires_pitches_ascending_with_note_delay_gaps():
    schedule = build_strum_schedule(["down"], [55, 48, 52], total_duration_ms=1000.0, note_delay_ms=20.0)
    starts_and_pitches = [(s, p) for s, p, v, d in schedule]
    assert starts_and_pitches == [(0.0, 48), (20.0, 52), (40.0, 55)]


def test_upstroke_fires_pitches_descending_with_note_delay_gaps():
    schedule = build_strum_schedule(["up"], [48, 55, 52], total_duration_ms=1000.0, note_delay_ms=20.0)
    starts_and_pitches = [(s, p) for s, p, v, d in schedule]
    assert starts_and_pitches == [(0.0, 55), (20.0, 52), (40.0, 48)]


def test_mute_produces_no_events():
    """A first attempt played a mute as a short, quiet chunk - live-tested
    and reported as audible stuttering rather than a mute, so a muted slot
    is silent instead."""
    schedule = build_strum_schedule(["mute"], [48, 52, 55], total_duration_ms=1000.0)
    assert schedule == []


def test_slots_are_spaced_evenly_across_total_duration():
    schedule = build_strum_schedule(["down", "down", "down", "down"], [60], total_duration_ms=400.0)
    starts = [s for s, p, v, d in schedule]
    assert starts == [0.0, 100.0, 200.0, 300.0]


def test_empty_pattern_or_pitches_returns_nothing():
    assert build_strum_schedule([], [60], 1000.0) == []
    assert build_strum_schedule(["down"], [], 1000.0) == []


def test_mixed_pattern_preserves_stroke_order_and_skips_mute():
    schedule = build_strum_schedule(["down", "mute", "up"], [48, 55], total_duration_ms=300.0)
    pitches_in_order = [p for s, p, v, d in schedule]
    # down: 48, 55 (ascending) ; mute: silent, contributes nothing ; up: 55, 48 (descending)
    assert pitches_in_order == [48, 55, 55, 48]


def test_mute_slot_still_occupies_its_place_in_the_timing():
    """A muted slot is silent but not absent - the stroke after it must
    still land at its own slot's real offset, not shift earlier to fill
    the gap."""
    schedule = build_strum_schedule(["down", "mute", "down"], [60], total_duration_ms=300.0)
    starts = [s for s, p, v, d in schedule]
    assert starts == [0.0, 200.0]


def test_strum_directions_decodes_known_codes():
    assert strum_directions([1, 101, 202]) == ["down", "up", "mute"]


def test_strum_directions_defaults_unknown_code_to_mute():
    assert strum_directions([1, 999]) == ["down", "mute"]
