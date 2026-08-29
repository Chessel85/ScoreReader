"""widgets/play_settings_dialog.py - a pure view over PlaySettings plus the
absolute playback tempo.

Never exec()'d: the dialog is built, driven through its widgets and read
back, the same way test_mixer_dialog.py drives MixerDialog.
"""
from models.music_data import MusicData
from models.play_settings import PlaySettings
from widgets.play_settings_dialog import PlaySettingsDialog


def test_shows_the_settings_it_was_given(qtbot):
    settings = PlaySettings(
        lead_in_enabled=False, lead_in_bars=2, lead_in_beats=3,
        loop_enabled=True, loop_length_bars=4, loop_lead_in=True,
    )
    dialog = PlaySettingsDialog(
        play_settings=settings, current_tempo_display_bpm=88, uk_terms=True
    )
    qtbot.addWidget(dialog)

    assert dialog.tempo_spin.value() == 88
    assert dialog.lead_in_check.isChecked() is False
    assert dialog.lead_in_bars_spin.value() == 2
    assert dialog.lead_in_beats_spin.value() == 3
    assert dialog.loop_check.isChecked() is True
    assert dialog.loop_length_spin.value() == 4
    assert dialog.loop_lead_in_check.isChecked() is True


def test_edits_round_trip_back_out(qtbot):
    dialog = PlaySettingsDialog(
        play_settings=PlaySettings(), current_tempo_display_bpm=120, uk_terms=True
    )
    qtbot.addWidget(dialog)

    dialog.tempo_spin.setValue(60)
    dialog.lead_in_check.setChecked(True)
    dialog.lead_in_bars_spin.setValue(0)
    dialog.lead_in_beats_spin.setValue(2)
    dialog.loop_check.setChecked(True)
    dialog.loop_length_spin.setValue(8)
    dialog.loop_lead_in_check.setChecked(True)

    assert dialog.tempo_display_bpm() == 60
    assert dialog.play_settings() == PlaySettings(
        lead_in_enabled=True, lead_in_bars=0, lead_in_beats=2,
        loop_enabled=True, loop_length_bars=8, loop_lead_in=True,
    )


def test_tempo_field_is_clamped_to_the_hard_bounds(qtbot):
    dialog = PlaySettingsDialog(
        play_settings=PlaySettings(), current_tempo_display_bpm=99999, uk_terms=True
    )
    qtbot.addWidget(dialog)
    assert dialog.tempo_spin.value() == MusicData.MAX_TEMPO_BPM

    dialog.tempo_spin.setValue(0)
    assert dialog.tempo_display_bpm() == MusicData.MIN_TEMPO_BPM


def test_editing_does_not_mutate_the_settings_passed_in(qtbot):
    settings = PlaySettings()
    dialog = PlaySettingsDialog(play_settings=settings, uk_terms=True)
    qtbot.addWidget(dialog)

    dialog.loop_check.setChecked(True)

    assert settings.loop_enabled is False


def test_lead_in_length_fields_follow_the_lead_in_checkbox(qtbot):
    dialog = PlaySettingsDialog(
        play_settings=PlaySettings(lead_in_enabled=False), uk_terms=True
    )
    qtbot.addWidget(dialog)
    assert dialog.lead_in_bars_spin.isEnabled() is False

    dialog.lead_in_check.setChecked(True)
    assert dialog.lead_in_bars_spin.isEnabled() is True
    assert dialog.lead_in_beats_spin.isEnabled() is True


def test_loop_length_follows_the_loop_checkbox(qtbot):
    dialog = PlaySettingsDialog(play_settings=PlaySettings(loop_enabled=False), uk_terms=True)
    qtbot.addWidget(dialog)
    assert dialog.loop_length_spin.isEnabled() is False

    dialog.loop_check.setChecked(True)
    assert dialog.loop_length_spin.isEnabled() is True


def test_repeat_the_lead_in_needs_both_a_loop_and_a_lead_in(qtbot):
    dialog = PlaySettingsDialog(
        play_settings=PlaySettings(loop_enabled=False, lead_in_enabled=True), uk_terms=True
    )
    qtbot.addWidget(dialog)
    assert dialog.loop_lead_in_check.isEnabled() is False

    dialog.loop_check.setChecked(True)
    assert dialog.loop_lead_in_check.isEnabled() is True

    dialog.lead_in_check.setChecked(False)
    assert dialog.loop_lead_in_check.isEnabled() is False


def test_a_loop_can_never_be_zero_bars_long(qtbot):
    dialog = PlaySettingsDialog(play_settings=PlaySettings(), uk_terms=True)
    qtbot.addWidget(dialog)

    dialog.loop_length_spin.setValue(0)

    assert dialog.play_settings().loop_length_bars >= 1


def test_labels_follow_the_uk_us_dialect(qtbot):
    uk = PlaySettingsDialog(play_settings=PlaySettings(), uk_terms=True)
    us = PlaySettingsDialog(play_settings=PlaySettings(), uk_terms=False)
    qtbot.addWidget(uk)
    qtbot.addWidget(us)

    uk_labels = " ".join(_label_texts(uk))
    us_labels = " ".join(_label_texts(us))
    assert "bar" in uk_labels and "measure" not in uk_labels
    assert "measure" in us_labels


def _label_texts(dialog):
    from PySide6.QtWidgets import QLabel

    return [label.text() for label in dialog.findChildren(QLabel)]
