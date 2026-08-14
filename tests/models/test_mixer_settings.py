# tests/models/test_mixer_settings.py
"""MixerSettings (wishlist #4/#7) - groundwork, not yet wired to any UI.

The property that matters most here is inertness: an empty MixerSettings has
to leave the synth completely untouched, so that every score without saved
mixer state behaves exactly as it did before the feature existed.
"""
from models.mixer_settings import (
    ANNOUNCER,
    CENTRE_PAN,
    CLICK,
    CUE,
    DEFAULT_VOLUME,
    MixerSettings,
    cc_to_pan_percent,
    cc_to_volume_percent,
    default_pan_for,
    pan_percent_to_cc,
    volume_percent_to_cc,
)
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


def test_copy_is_independent_of_the_original():
    """The Mixer dialog's snapshot-before-edit/working-copy pattern
    (PlaybackController.begin_mixer_edit) relies on volumes/pans being
    genuinely separate dicts, not aliased - a plain dataclasses.replace()
    would still share them."""
    original = MixerSettings()
    original.set_volume("P1", 80)

    copy = original.copy()
    copy.set_volume("P1", 40)
    copy.set_volume("P2", 10)

    assert original.volume_for("P1") == 80
    assert original.volume_for("P2") is None
    assert copy.volume_for("P1") == 40
    assert copy.volume_for("P2") == 10


def test_volume_percent_is_a_perceived_loudness_multiplier_of_the_default():
    """100% must mean "unchanged from today's default" (DEFAULT_VOLUME, the
    engine's own CC7 default of 100) - not the true MIDI maximum of 127, and
    the true 127 ceiling is deliberately unreachable from this dialog - the
    user's own spec has no "louder than default" concept.

    Reported bug, live-tested: a straight linear percent->CC mapping (50%
    -> CC 50) made 25% "barely audible" - far quieter than a quarter of the
    default's loudness - because FluidSynth's own CC7 handling isn't a
    linear amplitude multiplier (like most GM synths it applies an
    audio-taper/power-law response). sqrt() pre-corrects for that assumed
    square-law response, so 50%/25% land close to half/a quarter of
    DEFAULT_VOLUME's CC rather than the much-quieter straight-line value."""
    assert volume_percent_to_cc(0) == 0
    assert volume_percent_to_cc(100) == DEFAULT_VOLUME
    assert volume_percent_to_cc(50) == round(DEFAULT_VOLUME * (0.5 ** 0.5))
    assert cc_to_volume_percent(0) == 0
    assert cc_to_volume_percent(DEFAULT_VOLUME) == 100
    # Round trip at 50%: cc_to_volume_percent inverts volume_percent_to_cc's
    # square-root curve with a square, so the two must agree.
    assert cc_to_volume_percent(volume_percent_to_cc(50)) == 50


def test_pan_percent_round_trips_at_the_boundaries_and_centre():
    assert pan_percent_to_cc(-100) == 0
    assert pan_percent_to_cc(0) == CENTRE_PAN
    assert pan_percent_to_cc(100) == 127
    assert cc_to_pan_percent(0) == -100
    assert cc_to_pan_percent(CENTRE_PAN) == 0
    assert cc_to_pan_percent(127) == 100


def test_default_pan_matches_each_channels_real_hardcoded_default():
    """SynthEngine._load_click_soundfont sets these explicitly at load time
    (hard right for the click, hard left for the announcer, so the two are
    distinguishable) - default_pan_for must agree, since the Mixer dialog
    displays/reverts-to it for a row with no saved override."""
    assert default_pan_for(CLICK) == 127
    assert default_pan_for(ANNOUNCER) == 0
    assert default_pan_for(CUE) == CENTRE_PAN
    assert default_pan_for("P1") == CENTRE_PAN
