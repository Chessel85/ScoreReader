# tests/models/test_mixer_settings.py
"""MixerSettings (wishlist #4/#7) - groundwork, not yet wired to any UI.

The property that matters most here is inertness: an empty MixerSettings has
to leave the synth completely untouched, so that every score without saved
mixer state behaves exactly as it did before the feature existed.
"""
from models.mixer_settings import ANNOUNCER, CLICK, CUE, MixerSettings
from models.score_config_data import ScoreConfig


def test_a_fresh_mixer_overrides_nothing():
    """None, not a default value: callers must be able to tell "no setting"
    from "set to the default", because only the former means "send no CC"."""
    mixer = MixerSettings()

    assert mixer.is_empty()
    assert mixer.muted is False
    assert mixer.volume_for("P1") is None
    assert mixer.pan_for("P1") is None


def test_a_score_config_defaults_to_an_empty_mixer():
    assert ScoreConfig().mixer.is_empty()


def test_setting_and_clearing_one_part_leaves_others_alone():
    mixer = MixerSettings()
    mixer.set_volume("P1", 80)
    mixer.set_pan("P1", 20)

    assert mixer.volume_for("P1") == 80
    assert mixer.pan_for("P1") == 20
    assert mixer.volume_for("P2") is None

    mixer.clear("P1")
    assert mixer.is_empty()


def test_levels_are_clamped_to_the_midi_range():
    mixer = MixerSettings()
    mixer.set_volume("P1", 999)
    mixer.set_pan("P1", -5)

    assert mixer.volume_for("P1") == 127
    assert mixer.pan_for("P1") == 0


def test_round_trips_through_a_dict():
    """ScoreConfig is persisted as JSON, so the mixer has to survive the
    trip - including the three non-instrument channels, which are keyed by
    name rather than by part_id."""
    mixer = MixerSettings(muted=True)
    mixer.set_volume("P1", 80)
    mixer.set_pan(CLICK, 127)
    mixer.set_volume(ANNOUNCER, 90)
    mixer.set_pan(CUE, 64)

    restored = MixerSettings.from_dict(mixer.to_dict())

    assert restored == mixer
    assert restored.muted is True
    assert restored.pan_for(CLICK) == 127


def test_missing_or_empty_data_restores_an_empty_mixer():
    """A .rsc written before the mixer existed has no "mixer" key at all."""
    assert MixerSettings.from_dict(None).is_empty()
    assert MixerSettings.from_dict({}).is_empty()
