# tests/models/test_tuner_instruments.py
import pytest

from models.tuner_instruments import (
    A4_MIDI_PITCH,
    NO_SIGNAL_LEVEL_THRESHOLD,
    cents_deviation,
    cents_description,
    level_description,
    nearest_note,
    nearest_note_name,
)


def test_nearest_note_exact_a4():
    midi_pitch, cents = nearest_note(440.0)
    assert midi_pitch == A4_MIDI_PITCH
    assert cents == pytest.approx(0.0)


def test_nearest_note_a_few_cents_sharp_still_rounds_to_the_same_pitch():
    # A few cents above A4 - well inside the nearest-semitone band, so it
    # should still resolve to A4 itself, with a small positive cents figure.
    midi_pitch, cents = nearest_note(440.0 * (2 ** (10 / 1200)))
    assert midi_pitch == A4_MIDI_PITCH
    assert cents == pytest.approx(10.0, abs=0.5)


def test_nearest_note_a_semitone_up_resolves_to_the_next_chromatic_pitch():
    midi_pitch, cents = nearest_note(440.0 * (2 ** (1 / 12)))
    assert midi_pitch == A4_MIDI_PITCH + 1
    assert cents == pytest.approx(0.0, abs=0.5)


def test_nearest_note_different_a4_shifts_cents_for_the_same_raw_frequency():
    # 440Hz is exactly A4 under the standard reference, but flat of A4 under
    # a 442Hz reference (the whole standard moved up).
    _pitch_440, cents_440 = nearest_note(440.0, a4_hz=440.0)
    _pitch_442, cents_442 = nearest_note(440.0, a4_hz=442.0)
    assert cents_440 == pytest.approx(0.0)
    assert cents_442 < 0


def test_nearest_note_non_positive_frequency_returns_inert_fallback():
    assert nearest_note(0.0) == (A4_MIDI_PITCH, 0.0)
    assert nearest_note(-5.0) == (A4_MIDI_PITCH, 0.0)


def test_nearest_note_name_natural():
    assert nearest_note_name(60) == ("C", 4)  # MIDI 60 = C4


def test_nearest_note_name_is_always_sharp_never_flat_or_symbol():
    name, octave = nearest_note_name(61)  # C#4/Db4
    assert name == "C sharp"
    assert octave == 4
    assert "#" not in name
    assert "flat" not in name


def test_cents_deviation_sign_and_magnitude():
    assert cents_deviation(440.0, 440.0) == pytest.approx(0.0)
    # One octave up is exactly +1200 cents.
    assert cents_deviation(880.0, 440.0) == pytest.approx(1200.0)
    assert cents_deviation(220.0, 440.0) == pytest.approx(-1200.0)


def test_cents_description_in_tune_band():
    assert cents_description(0) == "in tune"
    assert cents_description(4.9) == "in tune"
    assert cents_description(-4.9) == "in tune"


def test_cents_description_sharp_and_flat():
    assert cents_description(12) == "12 cents sharp"
    assert cents_description(-30) == "30 cents flat"


def test_level_description_default_threshold_matches_the_module_constant():
    assert level_description(NO_SIGNAL_LEVEL_THRESHOLD - 0.001) == "no signal"
    assert level_description(NO_SIGNAL_LEVEL_THRESHOLD) == "signal 2 percent"


def test_level_description_accepts_a_custom_threshold():
    """The user-configurable TunerSettings.signal_threshold_percent case -
    a level that would read as "no signal" against the module default reads
    as real signal once a lower threshold is passed explicitly, and vice
    versa."""
    assert level_description(0.01, threshold=0.005) == "signal 1 percent"
    assert level_description(0.01, threshold=0.5) == "no signal"
