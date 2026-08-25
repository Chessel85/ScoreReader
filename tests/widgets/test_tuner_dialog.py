# tests/widgets/test_tuner_dialog.py
"""Pure widget-state tests for TunerDialog - it never touches
TunerController/TunerCapture itself, only emits signals (or, for announce(),
calls Qt's own accessibility API), so it can be driven directly with no
MainWindow involved - same reasoning tests/widgets/test_mixer_dialog.py
already documents for MixerDialog."""
from widgets import tuner_dialog as tuner_dialog_module
from widgets.tuner_dialog import TunerDialog
from models.tuner_settings import TunerSettings


def test_defaults_to_guitar_string_1(qtbot):
    dialog = TunerDialog()
    qtbot.addWidget(dialog)
    assert dialog.instrument_combo.currentText() == "Guitar"
    assert dialog.string_combo.currentText() == "String 1 (E4)"
    assert dialog.offset_spin.value() == 0
    assert dialog.a4_spin.value() == 440
    assert dialog.threshold_spin.value() == 2


def test_restores_saved_settings(qtbot):
    dialog = TunerDialog(
        devices=["My Mic"],
        settings=TunerSettings(
            instrument="Cello", last_string_index=2, reference_offset_semitones=-3,
            a4_reference_hz=442, signal_threshold_percent=8, input_device="My Mic",
        ),
    )
    qtbot.addWidget(dialog)
    assert dialog.instrument_combo.currentText() == "Cello"
    assert dialog.string_combo.currentText() == "String 3 (G2)"
    assert dialog.offset_spin.value() == -3
    assert dialog.a4_spin.value() == 442
    assert dialog.threshold_spin.value() == 8
    assert dialog.current_device() == "My Mic"


def test_changing_instrument_repopulates_strings_and_emits_target_changed(qtbot):
    dialog = TunerDialog()
    qtbot.addWidget(dialog)
    fired = []
    dialog.target_changed.connect(
        lambda tuner_string, offset, a4_hz: fired.append((tuner_string, offset, a4_hz))
    )

    dialog.instrument_combo.setCurrentText("Violin")

    assert [dialog.string_combo.itemText(i) for i in range(dialog.string_combo.count())] == [
        "String 1 (E5)", "String 2 (A4)", "String 3 (D4)", "String 4 (G3)",
    ]
    assert fired[-1][0].note_name == "E"
    assert fired[-1][0].octave == 5


def test_changing_string_emits_target_changed_with_current_offset(qtbot):
    dialog = TunerDialog()
    qtbot.addWidget(dialog)
    dialog.offset_spin.setValue(2)
    fired = []
    dialog.target_changed.connect(
        lambda tuner_string, offset, a4_hz: fired.append((tuner_string, offset, a4_hz))
    )

    dialog.string_combo.setCurrentIndex(5)  # low E2

    assert fired[-1][0].note_name == "E"
    assert fired[-1][0].octave == 2
    assert fired[-1][1] == 2


def test_changing_a4_reference_emits_target_changed(qtbot):
    dialog = TunerDialog()
    qtbot.addWidget(dialog)
    fired = []
    dialog.target_changed.connect(
        lambda tuner_string, offset, a4_hz: fired.append((tuner_string, offset, a4_hz))
    )

    dialog.a4_spin.setValue(442)

    assert fired[-1][2] == 442


def test_changing_signal_threshold_emits_threshold_changed(qtbot):
    dialog = TunerDialog()
    qtbot.addWidget(dialog)
    fired = []
    dialog.threshold_changed.connect(fired.append)

    dialog.threshold_spin.setValue(10)

    assert fired == [10]


def test_changing_device_emits_device_changed(qtbot):
    dialog = TunerDialog(devices=["Mic A", "Mic B"])
    qtbot.addWidget(dialog)
    fired = []
    dialog.device_changed.connect(fired.append)

    dialog.device_combo.setCurrentIndex(dialog.device_combo.findData("Mic B"))

    assert fired == ["Mic B"]


def test_system_default_device_reports_as_none(qtbot):
    dialog = TunerDialog(devices=["Mic A"])
    qtbot.addWidget(dialog)
    assert dialog.current_device() is None  # "(System Default)" is selected by default


def test_reading_edit_is_read_only_and_starts_with_a_placeholder(qtbot):
    dialog = TunerDialog()
    qtbot.addWidget(dialog)
    assert dialog.reading_edit.isReadOnly()
    assert dialog.reading_edit.text() == "no signal - waiting"


def test_update_pitch_display_shows_no_signal_with_no_target_or_result(qtbot):
    dialog = TunerDialog()
    qtbot.addWidget(dialog)
    dialog.update_pitch_display(None, None, 0.0)
    assert dialog.reading_edit.text() == "no signal - waiting"


def test_update_pitch_display_shows_level_and_note_with_a_result(qtbot):
    dialog = TunerDialog()
    qtbot.addWidget(dialog)
    dialog.update_pitch_display(object(), 3.4, 0.5)
    assert dialog.reading_edit.text() == "signal 50 percent - E: in tune"


def test_update_pitch_display_uses_the_dialogs_own_threshold_control(qtbot):
    """The "no signal" boundary must track threshold_spin live, not the
    models.tuner_instruments module default - see that method's own
    docstring for the live-tested bug this fixes (a below-threshold reading
    used to still show a stray cents figure)."""
    dialog = TunerDialog()
    qtbot.addWidget(dialog)
    dialog.threshold_spin.setValue(20)  # 20% - well above a 5% peak_level

    dialog.update_pitch_display(None, None, 0.05)

    assert dialog.reading_edit.text() == "no signal - waiting"


def test_announce_dispatches_through_the_dialog_itself_as_a_real_widget(qtbot, monkeypatch):
    """The regression test for the actual live-tested bug: an earlier cut
    of this feature had the CONTROLLER call QAccessible.updateAccessibility
    targeting itself (a plain QObject, not a widget) - Qt's accessibility
    bridge had nothing to resolve and silently dropped every announcement.
    announce() must target THIS DIALOG (event.object() is dialog), the real
    widget behind the fix."""
    events = []
    monkeypatch.setattr(
        tuner_dialog_module.QAccessible, "updateAccessibility", events.append
    )
    dialog = TunerDialog()
    qtbot.addWidget(dialog)

    dialog.announce("signal 50 percent. E. in tune")

    assert len(events) == 1
    assert events[0].object() is dialog
    assert events[0].message() == "signal 50 percent. E. in tune"


def test_result_settings_reflects_current_controls(qtbot):
    dialog = TunerDialog(devices=["Mic A"])
    qtbot.addWidget(dialog)
    dialog.instrument_combo.setCurrentText("Ukulele")
    dialog.string_combo.setCurrentIndex(1)
    dialog.offset_spin.setValue(1)
    dialog.device_combo.setCurrentIndex(dialog.device_combo.findData("Mic A"))

    dialog.a4_spin.setValue(415)
    dialog.threshold_spin.setValue(6)

    settings = dialog.result_settings()

    assert settings.instrument == "Ukulele"
    assert settings.last_string_index == 1
    assert settings.reference_offset_semitones == 1
    assert settings.a4_reference_hz == 415
    assert settings.signal_threshold_percent == 6
    assert settings.input_device == "Mic A"
