"""models/preview_settings.py - the shape the Preview Settings dialog edits
and persistence/app_settings.py stores globally."""
from models.preview_settings import (
    MAX_LEAD_IN_BARS,
    MAX_PREVIEW_BARS,
    PreviewSettings,
)


def test_shipped_defaults_are_one_bar_of_clicks_then_two_bars_once():
    """The user's own choice: enough count-in to get hands to the guitar,
    today's two-bar preview length, no looping until asked for."""
    settings = PreviewSettings()

    assert settings.lead_in_bars == 1
    assert settings.lead_in_beats == 0
    assert settings.lead_in_click is True
    assert settings.preview_bars == 2
    assert settings.loop is False
    assert settings.loop_includes_lead_in is False


def test_has_lead_in_is_false_only_when_both_parts_are_zero():
    assert PreviewSettings(lead_in_bars=0, lead_in_beats=0).has_lead_in() is False
    assert PreviewSettings(lead_in_bars=0, lead_in_beats=2).has_lead_in() is True
    assert PreviewSettings(lead_in_bars=1, lead_in_beats=0).has_lead_in() is True


def test_out_of_range_values_are_clamped_rather_than_rejected():
    """A hand-edited settings.json must not be able to produce a preview
    with no bars in it, or a count-in that looks like a hang."""
    settings = PreviewSettings(lead_in_bars=99, lead_in_beats=-3, preview_bars=0)

    assert settings.lead_in_bars == MAX_LEAD_IN_BARS
    assert settings.lead_in_beats == 0
    assert settings.preview_bars == 1

    assert PreviewSettings(preview_bars=1000).preview_bars == MAX_PREVIEW_BARS


def test_round_trips_through_a_dict():
    original = PreviewSettings(
        lead_in_bars=2, lead_in_beats=3, lead_in_click=False,
        preview_bars=4, loop=True, loop_includes_lead_in=True,
    )

    assert PreviewSettings.from_dict(original.to_dict()) == original


def test_a_settings_file_written_before_this_feature_gets_the_defaults():
    assert PreviewSettings.from_dict(None) == PreviewSettings()
    assert PreviewSettings.from_dict({}) == PreviewSettings()
    assert PreviewSettings.from_dict({"loop": True}) == PreviewSettings(loop=True)


def test_copy_is_independent_of_the_original():
    """A running preview snapshots its settings, so editing them mid-loop
    must not change what the loop is already doing."""
    original = PreviewSettings()
    snapshot = original.copy()
    original.loop = True

    assert snapshot.loop is False
