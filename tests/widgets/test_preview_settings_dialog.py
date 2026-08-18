"""widgets/preview_settings_dialog.py - a pure view over PreviewSettings.

Never exec()'d: the dialog is built, driven through its widgets and read
back, the same way test_mixer_dialog.py drives MixerDialog.
"""
from models.preview_settings import PreviewSettings
from widgets.preview_settings_dialog import PreviewSettingsDialog


def test_shows_the_settings_it_was_given(qtbot):
    settings = PreviewSettings(
        lead_in_bars=2, lead_in_beats=3, lead_in_click=False,
        preview_bars=4, loop=True, loop_includes_lead_in=True,
    )
    dialog = PreviewSettingsDialog(settings=settings, uk_terms=True)
    qtbot.addWidget(dialog)

    assert dialog.lead_in_bars_spin.value() == 2
    assert dialog.lead_in_beats_spin.value() == 3
    assert dialog.lead_in_click_check.isChecked() is False
    assert dialog.preview_bars_spin.value() == 4
    assert dialog.loop_check.isChecked() is True
    assert dialog.loop_lead_in_check.isChecked() is True


def test_edits_round_trip_back_out(qtbot):
    dialog = PreviewSettingsDialog(settings=PreviewSettings(), uk_terms=True)
    qtbot.addWidget(dialog)

    dialog.lead_in_bars_spin.setValue(0)
    dialog.lead_in_beats_spin.setValue(2)
    dialog.lead_in_click_check.setChecked(False)
    dialog.preview_bars_spin.setValue(8)
    dialog.loop_check.setChecked(True)
    dialog.loop_lead_in_check.setChecked(True)

    assert dialog.preview_settings() == PreviewSettings(
        lead_in_bars=0, lead_in_beats=2, lead_in_click=False,
        preview_bars=8, loop=True, loop_includes_lead_in=True,
    )


def test_editing_does_not_mutate_the_settings_passed_in(qtbot):
    """A working copy, like MixerDialog's - Cancel has to leave the live
    settings untouched."""
    settings = PreviewSettings()
    dialog = PreviewSettingsDialog(settings=settings, uk_terms=True)
    qtbot.addWidget(dialog)

    dialog.loop_check.setChecked(True)

    assert settings.loop is False


def test_repeat_the_lead_in_follows_the_loop_checkbox(qtbot):
    """It does nothing at all with looping off, so it is disabled rather
    than silently ignored."""
    dialog = PreviewSettingsDialog(settings=PreviewSettings(loop=False), uk_terms=True)
    qtbot.addWidget(dialog)

    assert dialog.loop_lead_in_check.isEnabled() is False

    dialog.loop_check.setChecked(True)
    assert dialog.loop_lead_in_check.isEnabled() is True

    dialog.loop_check.setChecked(False)
    assert dialog.loop_lead_in_check.isEnabled() is False


def test_a_preview_can_never_be_zero_bars_long(qtbot):
    dialog = PreviewSettingsDialog(settings=PreviewSettings(), uk_terms=True)
    qtbot.addWidget(dialog)

    dialog.preview_bars_spin.setValue(0)

    assert dialog.preview_settings().preview_bars >= 1


def test_labels_follow_the_uk_us_dialect(qtbot):
    """F4/D-6: bar vs measure is the user's choice everywhere else too."""
    uk = PreviewSettingsDialog(settings=PreviewSettings(), uk_terms=True)
    us = PreviewSettingsDialog(settings=PreviewSettings(), uk_terms=False)
    qtbot.addWidget(uk)
    qtbot.addWidget(us)

    uk_labels = " ".join(_label_texts(uk))
    us_labels = " ".join(_label_texts(us))
    assert "bar" in uk_labels and "measure" not in uk_labels
    assert "measure" in us_labels


def _label_texts(dialog):
    from PySide6.QtWidgets import QLabel

    return [label.text() for label in dialog.findChildren(QLabel)]
