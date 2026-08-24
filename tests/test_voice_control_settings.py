# tests/test_voice_control_settings.py
from models.voice_control_settings import DEFAULT_CONFIDENCE_THRESHOLD, VoiceControlSettings


def test_defaults_are_disabled_with_no_device():
    settings = VoiceControlSettings()
    assert settings.enabled is False
    assert settings.device_name is None
    assert settings.confidence_threshold == DEFAULT_CONFIDENCE_THRESHOLD


def test_out_of_range_values_are_clamped():
    settings = VoiceControlSettings(confidence_threshold=500)
    assert settings.confidence_threshold == 100.0


def test_copy_is_independent():
    original = VoiceControlSettings(enabled=True, device_name="My Microphone")
    snapshot = original.copy()
    original.enabled = False
    original.device_name = "Different Device"
    assert snapshot.enabled is True
    assert snapshot.device_name == "My Microphone"


def test_to_dict_from_dict_round_trip():
    original = VoiceControlSettings(
        enabled=True, device_name="My Microphone", confidence_threshold=85.0,
    )
    restored = VoiceControlSettings.from_dict(original.to_dict())
    assert restored == original


def test_from_dict_missing_keys_fall_back_to_defaults():
    restored = VoiceControlSettings.from_dict({"enabled": True})
    assert restored.enabled is True
    assert restored.device_name is None
    assert restored.confidence_threshold == DEFAULT_CONFIDENCE_THRESHOLD


def test_from_dict_none_returns_defaults():
    assert VoiceControlSettings.from_dict(None) == VoiceControlSettings()
