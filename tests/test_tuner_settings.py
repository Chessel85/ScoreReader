# tests/test_tuner_settings.py
from models.tuner_settings import DEFAULT_INSTRUMENT, TunerSettings


def test_defaults_are_guitar_at_string_zero_with_no_offset_or_device():
    settings = TunerSettings()
    assert settings.instrument == DEFAULT_INSTRUMENT == "Guitar"
    assert settings.last_string_index == 0
    assert settings.reference_offset_semitones == 0
    assert settings.a4_reference_hz == 440
    assert settings.signal_threshold_percent == 2
    assert settings.input_device is None


def test_out_of_range_offset_is_clamped():
    settings = TunerSettings(reference_offset_semitones=99)
    assert settings.reference_offset_semitones == 4
    settings = TunerSettings(reference_offset_semitones=-99)
    assert settings.reference_offset_semitones == -4


def test_out_of_range_a4_reference_is_clamped():
    settings = TunerSettings(a4_reference_hz=999)
    assert settings.a4_reference_hz == 446
    settings = TunerSettings(a4_reference_hz=1)
    assert settings.a4_reference_hz == 415


def test_out_of_range_signal_threshold_is_clamped():
    settings = TunerSettings(signal_threshold_percent=999)
    assert settings.signal_threshold_percent == 50
    settings = TunerSettings(signal_threshold_percent=0)
    assert settings.signal_threshold_percent == 1


def test_empty_instrument_falls_back_to_default():
    settings = TunerSettings(instrument="")
    assert settings.instrument == DEFAULT_INSTRUMENT


def test_copy_is_independent():
    original = TunerSettings(instrument="Cello", last_string_index=2, input_device="My Mic")
    snapshot = original.copy()
    original.instrument = "Violin"
    original.input_device = "Different Mic"
    assert snapshot.instrument == "Cello"
    assert snapshot.input_device == "My Mic"


def test_to_dict_from_dict_round_trip():
    original = TunerSettings(
        instrument="Double Bass", last_string_index=3,
        reference_offset_semitones=-3, a4_reference_hz=442, signal_threshold_percent=5,
        input_device="Interface In 1",
    )
    restored = TunerSettings.from_dict(original.to_dict())
    assert restored == original


def test_from_dict_missing_keys_fall_back_to_defaults():
    restored = TunerSettings.from_dict({"instrument": "Viola"})
    assert restored.instrument == "Viola"
    assert restored.last_string_index == 0
    assert restored.reference_offset_semitones == 0
    assert restored.a4_reference_hz == 440
    assert restored.signal_threshold_percent == 2
    assert restored.input_device is None


def test_from_dict_none_returns_defaults():
    assert TunerSettings.from_dict(None) == TunerSettings()
