# tests/test_live_midi_input_settings.py
from models.live_midi_input_settings import DEFAULT_GM_PROGRAM, LiveMidiInputSettings


def test_defaults_are_disabled_with_no_device():
    settings = LiveMidiInputSettings()
    assert settings.enabled is False
    assert settings.device_name is None
    assert settings.gm_program == DEFAULT_GM_PROGRAM
    assert settings.volume_percent == 100
    assert settings.pan_percent == 0


def test_out_of_range_values_are_clamped():
    settings = LiveMidiInputSettings(gm_program=999, volume_percent=-5, pan_percent=500)
    assert settings.gm_program == 128
    assert settings.volume_percent == 0
    assert settings.pan_percent == 100


def test_copy_is_independent():
    original = LiveMidiInputSettings(enabled=True, device_name="My Keyboard")
    snapshot = original.copy()
    original.enabled = False
    original.device_name = "Different Device"
    assert snapshot.enabled is True
    assert snapshot.device_name == "My Keyboard"


def test_to_dict_from_dict_round_trip():
    original = LiveMidiInputSettings(
        enabled=True, device_name="My Keyboard", gm_program=25,
        volume_percent=75, pan_percent=-20,
    )
    restored = LiveMidiInputSettings.from_dict(original.to_dict())
    assert restored == original


def test_from_dict_missing_keys_fall_back_to_defaults():
    restored = LiveMidiInputSettings.from_dict({"enabled": True})
    assert restored.enabled is True
    assert restored.device_name is None
    assert restored.gm_program == DEFAULT_GM_PROGRAM
    assert restored.volume_percent == 100
    assert restored.pan_percent == 0


def test_from_dict_none_returns_defaults():
    assert LiveMidiInputSettings.from_dict(None) == LiveMidiInputSettings()
