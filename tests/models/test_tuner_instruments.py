# tests/models/test_tuner_instruments.py
import pytest

from models.tuner_instruments import (
    NO_SIGNAL_LEVEL_THRESHOLD,
    TUNER_INSTRUMENTS,
    TUNER_INSTRUMENT_NAMES,
    cents_deviation,
    cents_description,
    expected_frequency_hz,
    level_description,
    tuner_instrument_by_name,
)


def test_eight_instruments_are_supported_and_harp_is_excluded():
    assert len(TUNER_INSTRUMENTS) == 8
    assert "Harp" not in TUNER_INSTRUMENT_NAMES


def test_guitar_strings_are_numbered_high_to_low():
    guitar = tuner_instrument_by_name("Guitar")
    assert [(s.number, s.note_name, s.octave) for s in guitar.strings] == [
        (1, "E", 4), (2, "B", 3), (3, "G", 3), (4, "D", 3), (5, "A", 2), (6, "E", 2),
    ]


def test_ukulele_is_re_entrant_string_1_is_not_the_lowest():
    ukulele = tuner_instrument_by_name("Ukulele")
    # As strung (G4 C4 E4 A4), not pitch-ordered - string 4 (A4) is HIGHER
    # than string 1 (G4), the defining feature of re-entrant tuning.
    assert ukulele.strings[0].midi_pitch < ukulele.strings[3].midi_pitch


def test_unknown_instrument_name_falls_back_to_guitar():
    assert tuner_instrument_by_name("Theremin") is TUNER_INSTRUMENTS[0]
    assert tuner_instrument_by_name("Theremin").name == "Guitar"


def test_string_label_includes_octave():
    guitar = tuner_instrument_by_name("Guitar")
    assert guitar.strings[0].label == "String 1 (E4)"


def test_expected_frequency_hz_concert_a4_is_440():
    violin = tuner_instrument_by_name("Violin")
    a4_string = violin.strings[1]  # A4
    assert expected_frequency_hz(a4_string, 0) == pytest.approx(440.0)


def test_expected_frequency_hz_offset_shifts_by_semitones():
    guitar_e2 = tuner_instrument_by_name("Guitar").strings[5]
    base = expected_frequency_hz(guitar_e2, 0)
    up_one = expected_frequency_hz(guitar_e2, 1)
    assert up_one == pytest.approx(base * (2 ** (1 / 12)))


def test_expected_frequency_hz_default_a4_is_440():
    violin = tuner_instrument_by_name("Violin")
    a4_string = violin.strings[1]  # A4
    assert expected_frequency_hz(a4_string) == pytest.approx(440.0)


def test_expected_frequency_hz_non_default_a4_shifts_every_note_proportionally():
    violin = tuner_instrument_by_name("Violin")
    a4_string = violin.strings[1]  # A4
    assert expected_frequency_hz(a4_string, 0, a4_hz=442) == pytest.approx(442.0)
    assert expected_frequency_hz(a4_string, 0, a4_hz=415) == pytest.approx(415.0)

    guitar_e2 = tuner_instrument_by_name("Guitar").strings[5]
    at_440 = expected_frequency_hz(guitar_e2, 0, a4_hz=440)
    at_442 = expected_frequency_hz(guitar_e2, 0, a4_hz=442)
    # A non-A4 string scales by the same ratio as A4 itself did (442/440),
    # since the whole pitch standard moved, not just one note.
    assert at_442 == pytest.approx(at_440 * (442 / 440))


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
