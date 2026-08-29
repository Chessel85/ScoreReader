# tests/test_tuner_settings.py
from models.tuner_settings import TunerSettings


def test_defaults_are_concert_pitch_with_no_device():
    settings = TunerSettings()
    assert settings.a4_reference_hz == 440
    assert settings.signal_threshold_percent == 2
    assert settings.input_device is None


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


def test_copy_is_independent():
    original = TunerSettings(a4_reference_hz=442, input_device="My Mic")
    snapshot = original.copy()
    original.a4_reference_hz = 415
    original.input_device = "Different Mic"
    assert snapshot.a4_reference_hz == 442
    assert snapshot.input_device == "My Mic"


def test_to_dict_from_dict_round_trip():
    original = TunerSettings(
        a4_reference_hz=442, signal_threshold_percent=5, input_device="Interface In 1",
    )
    restored = TunerSettings.from_dict(original.to_dict())
    assert restored == original


def test_from_dict_missing_keys_fall_back_to_defaults():
    restored = TunerSettings.from_dict({"a4_reference_hz": 442})
    assert restored.a4_reference_hz == 442
    assert restored.signal_threshold_percent == 2
    assert restored.input_device is None


def test_from_dict_none_returns_defaults():
    assert TunerSettings.from_dict(None) == TunerSettings()


def test_from_dict_ignores_dead_keys_from_the_old_per_string_tuner():
    """A settings file saved before the chromatic-tuner redesign may still
    carry "instrument"/"last_string_index"/"reference_offset_semitones" -
    these are simply never read, the same silent-drop convention
    ScoreConfig.apply_config already uses for a saved key the current code
    no longer recognises."""
    restored = TunerSettings.from_dict({
        "instrument": "Cello",
        "last_string_index": 2,
        "reference_offset_semitones": -3,
        "a4_reference_hz": 442,
    })
    assert restored.a4_reference_hz == 442
    assert not hasattr(restored, "instrument")
    assert not hasattr(restored, "last_string_index")
    assert not hasattr(restored, "reference_offset_semitones")
