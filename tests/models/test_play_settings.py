"""models/play_settings.py - the shape the Play Settings dialog edits and
persistence/app_settings.py stores globally."""
from models.play_settings import (
    DEFAULT_LOOP_REPEAT_MODE,
    LOOP_REPEAT_MODES,
    MAX_LEAD_IN_BARS,
    MAX_LOOP_LENGTH_BARS,
    MIN_LOOP_LENGTH_BARS,
    PlaySettings,
)


def test_shipped_defaults_are_lead_in_on_one_bar_looping_off():
    """The user's own choice: lead-in on with enough count-in to get hands
    to the guitar, looping off until asked for, a two-bar window when it
    is."""
    settings = PlaySettings()

    assert settings.lead_in_enabled is True
    assert settings.lead_in_bars == 1
    assert settings.lead_in_beats == 0
    assert settings.loop_enabled is False
    assert settings.loop_length_bars == 2
    assert settings.loop_lead_in is False


def test_has_lead_in_needs_the_master_toggle_and_at_least_one_beat():
    assert PlaySettings(lead_in_enabled=False, lead_in_bars=2).has_lead_in() is False
    assert PlaySettings(lead_in_enabled=True, lead_in_bars=0, lead_in_beats=0).has_lead_in() is False
    assert PlaySettings(lead_in_enabled=True, lead_in_bars=0, lead_in_beats=2).has_lead_in() is True
    assert PlaySettings(lead_in_enabled=True, lead_in_bars=1).has_lead_in() is True


def test_out_of_range_values_are_clamped_rather_than_rejected():
    settings = PlaySettings(lead_in_bars=99, lead_in_beats=-3, loop_length_bars=0)

    assert settings.lead_in_bars == MAX_LEAD_IN_BARS
    assert settings.lead_in_beats == 0
    assert settings.loop_length_bars == MIN_LOOP_LENGTH_BARS

    assert PlaySettings(loop_length_bars=1000).loop_length_bars == MAX_LOOP_LENGTH_BARS


def test_round_trips_through_a_dict():
    original = PlaySettings(
        lead_in_enabled=False, lead_in_bars=2, lead_in_beats=3,
        loop_enabled=True, loop_length_bars=4, loop_lead_in=True,
    )

    assert PlaySettings.from_dict(original.to_dict()) == original


def test_a_settings_file_written_before_this_feature_gets_the_defaults():
    assert PlaySettings.from_dict(None) == PlaySettings()
    assert PlaySettings.from_dict({}) == PlaySettings()
    assert PlaySettings.from_dict({"loop_enabled": True}) == PlaySettings(loop_enabled=True)


def test_from_dict_reads_the_pre_rename_preview_keys():
    """An existing settings.json written by the Preview era carries over."""
    old = {
        "lead_in_bars": 2, "lead_in_beats": 1, "lead_in_click": True,
        "preview_bars": 5, "loop": True, "loop_includes_lead_in": True,
    }
    settings = PlaySettings.from_dict(old)

    assert settings.lead_in_bars == 2
    assert settings.lead_in_beats == 1
    assert settings.lead_in_enabled is True
    assert settings.loop_length_bars == 5
    assert settings.loop_enabled is True
    assert settings.loop_lead_in is True


def test_from_dict_infers_lead_in_off_from_a_zero_length_old_count_in():
    settings = PlaySettings.from_dict({"lead_in_bars": 0, "lead_in_beats": 0})
    assert settings.lead_in_enabled is False


def test_with_loop_length_bars_returns_an_independent_copy():
    original = PlaySettings(lead_in_bars=3, loop_length_bars=2, loop_enabled=True)

    changed = original.with_loop_length_bars(5)

    assert changed.loop_length_bars == 5
    assert changed.lead_in_bars == 3
    assert changed.loop_enabled is True
    assert original.loop_length_bars == 2, "the original is untouched"


def test_with_loop_length_bars_clamps_the_bounds():
    assert PlaySettings().with_loop_length_bars(0).loop_length_bars == MIN_LOOP_LENGTH_BARS
    assert PlaySettings().with_loop_length_bars(999).loop_length_bars == MAX_LOOP_LENGTH_BARS


def test_copy_is_independent_of_the_original():
    original = PlaySettings()
    snapshot = original.copy()
    original.loop_enabled = True

    assert snapshot.loop_enabled is False


def test_loop_repeat_mode_defaults_to_first():
    assert PlaySettings().loop_repeat_mode == "first"
    assert DEFAULT_LOOP_REPEAT_MODE == "first"
    assert LOOP_REPEAT_MODES == ("first", "second", "alternate")


def test_loop_repeat_mode_round_trips_and_an_unknown_value_coerces():
    for mode in LOOP_REPEAT_MODES:
        settings = PlaySettings(loop_repeat_mode=mode)
        assert settings.loop_repeat_mode == mode
        assert PlaySettings.from_dict(settings.to_dict()).loop_repeat_mode == mode
        assert settings.copy().loop_repeat_mode == mode

    assert PlaySettings(loop_repeat_mode="nonsense").loop_repeat_mode == "first"


def test_loop_repeat_mode_absent_from_an_older_settings_file_gets_first():
    assert PlaySettings.from_dict({"loop_enabled": True}).loop_repeat_mode == "first"
    assert PlaySettings.from_dict({}).loop_repeat_mode == "first"
