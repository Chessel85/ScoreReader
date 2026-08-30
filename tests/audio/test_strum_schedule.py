# tests/audio/test_strum_schedule.py
from audio.strum_schedule import build_strum_schedule, slots_from_codes, sound_events
from models.strum_codes import StrumSlot


def _slots(*specs):
    return [StrumSlot(stroke, effect) for stroke, effect in specs]


def test_downstroke_fires_pitches_ascending_with_note_delay_gaps():
    schedule = build_strum_schedule(_slots(("down", "none")), [55, 48, 52], slot_ms=1000.0, note_delay_ms=20.0)
    starts_and_pitches = [(s, p) for s, p, v, d in schedule]
    assert starts_and_pitches == [(0.0, 48), (20.0, 52), (40.0, 55)]


def test_upstroke_fires_pitches_descending_with_note_delay_gaps():
    schedule = build_strum_schedule(_slots(("up", "none")), [48, 55, 52], slot_ms=1000.0, note_delay_ms=20.0)
    starts_and_pitches = [(s, p) for s, p, v, d in schedule]
    assert starts_and_pitches == [(0.0, 55), (20.0, 52), (40.0, 48)]


def test_pause_produces_no_events():
    assert build_strum_schedule(_slots(("pause", "none")), [48, 52, 55], slot_ms=1000.0) == []
    assert build_strum_schedule(_slots(("real pause", "none")), [48, 52, 55], slot_ms=1000.0) == []


def test_slots_are_spaced_evenly_across_slot_ms():
    schedule = build_strum_schedule(_slots(*[("down", "none")] * 4), [60], slot_ms=100.0)
    starts = [s for s, p, v, d in schedule]
    assert starts == [0.0, 100.0, 200.0, 300.0]


def test_empty_pattern_or_pitches_returns_nothing():
    assert build_strum_schedule([], [60], 1000.0) == []
    assert build_strum_schedule(_slots(("down", "none")), [], 1000.0) == []


def test_accent_raises_velocity_mute_lowers_it():
    plain = build_strum_schedule(_slots(("down", "none")), [60], slot_ms=200.0)
    accent = build_strum_schedule(_slots(("down", "accent")), [60], slot_ms=200.0)
    muted = build_strum_schedule(_slots(("down", "mute")), [60], slot_ms=200.0)
    assert accent[0][2] > plain[0][2] > muted[0][2]


def test_muted_slot_still_occupies_its_place_in_the_timing():
    schedule = build_strum_schedule(
        _slots(("down", "none"), ("pause", "none"), ("down", "none")), [60], slot_ms=100.0
    )
    starts = [s for s, p, v, d in schedule]
    assert starts == [0.0, 200.0]


def test_palm_mute_reads_as_a_damped_downstroke():
    schedule = build_strum_schedule(_slots(("p.m.", "none")), [48, 55], slot_ms=200.0)
    pitches = [p for s, p, v, d in schedule]
    assert pitches == [48, 55]  # low-to-high, like a downstroke
    assert all(v < 90 for s, p, v, d in schedule)  # quieter than a plain stroke


def test_slots_from_codes_decodes_known_and_unknown():
    slots = slots_from_codes([1, 101, 202, 999])
    assert (slots[0].stroke, slots[1].stroke) == ("down", "up")
    assert slots[2].stroke == "pause"
    assert slots[3].stroke == "pause"  # unknown -> silent pause fallback


def test_sound_events_routes_grace_events_through_play_chord_with_grace(null_synth, timeline, grace_note_score):
    music_data = timeline(grace_note_score)
    events = music_data.get_playback_events_for_indices([0])
    grace_events = music_data.get_grace_note_events_for_indices([0])

    sound_events(null_synth, music_data, events, retrigger=True, grace_events=grace_events)

    assert null_synth.grace_chords, "the grace note must be sounded separately"
    assert null_synth.grace_chords[0]["midi_notes"] == [71]
    assert null_synth.played
    assert null_synth.played[0]["midi_notes"] == [69], "the main note still sounds"


def test_sound_events_falls_through_to_play_chord_with_no_grace_events(null_synth, timeline, minimal_score):
    music_data = timeline(minimal_score)
    events = music_data.get_playback_events_for_indices([0])

    sound_events(null_synth, music_data, events, retrigger=True, grace_events=[])

    assert not null_synth.grace_chords
    assert null_synth.played
