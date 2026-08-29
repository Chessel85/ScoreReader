# tests/widgets/test_tuner_settings_dialog.py
"""Pure widget-state tests for TunerSettingsDialog - it never touches
TunerController itself, only emits signals, so it can be driven directly
with no MainWindow involved - same reasoning
tests/widgets/test_mixer_dialog.py already documents for MixerDialog.
Holds the set-once values split out of TunerDialog (widgets/tuner_dialog.py)
once that dialog stopped needing an Instrument/String picker: A4 reference,
signal threshold, input device."""
from models.tuner_settings import TunerSettings
from widgets.tuner_settings_dialog import TunerSettingsDialog


def test_defaults_reflect_a_fresh_settings_object(qtbot):
    dialog = TunerSettingsDialog()
    qtbot.addWidget(dialog)
    assert dialog.a4_spin.value() == 440
    assert dialog.threshold_spin.value() == 2
    assert dialog.current_device() is None


def test_restores_saved_settings(qtbot):
    dialog = TunerSettingsDialog(
        devices=["My Mic"],
        settings=TunerSettings(a4_reference_hz=442, signal_threshold_percent=8, input_device="My Mic"),
    )
    qtbot.addWidget(dialog)
    assert dialog.a4_spin.value() == 442
    assert dialog.threshold_spin.value() == 8
    assert dialog.current_device() == "My Mic"


def test_changing_a4_emits_a4_changed(qtbot):
    dialog = TunerSettingsDialog()
    qtbot.addWidget(dialog)
    fired = []
    dialog.a4_changed.connect(fired.append)

    dialog.a4_spin.setValue(442)

    assert fired == [442]


def test_changing_signal_threshold_emits_threshold_changed(qtbot):
    dialog = TunerSettingsDialog()
    qtbot.addWidget(dialog)
    fired = []
    dialog.threshold_changed.connect(fired.append)

    dialog.threshold_spin.setValue(10)

    assert fired == [10]


def test_changing_device_emits_device_changed(qtbot):
    dialog = TunerSettingsDialog(devices=["Mic A", "Mic B"])
    qtbot.addWidget(dialog)
    fired = []
    dialog.device_changed.connect(fired.append)

    dialog.device_combo.setCurrentIndex(dialog.device_combo.findData("Mic B"))

    assert fired == ["Mic B"]


def test_system_default_device_reports_as_none(qtbot):
    dialog = TunerSettingsDialog(devices=["Mic A"])
    qtbot.addWidget(dialog)
    assert dialog.current_device() is None  # "(System Default)" is selected by default


def test_refresh_button_emits_refresh_requested(qtbot):
    dialog = TunerSettingsDialog()
    qtbot.addWidget(dialog)
    fired = []
    dialog.refresh_requested.connect(lambda: fired.append(True))

    dialog.refresh_button.click()

    assert fired == [True]


def test_set_devices_preserves_the_selected_device_across_a_refresh(qtbot):
    dialog = TunerSettingsDialog(devices=["Mic A"], settings=TunerSettings(input_device="Mic A"))
    qtbot.addWidget(dialog)

    dialog.set_devices(["Mic A", "Mic B"])

    assert dialog.current_device() == "Mic A"


def test_result_settings_reflects_current_controls(qtbot):
    dialog = TunerSettingsDialog(devices=["Mic A"])
    qtbot.addWidget(dialog)
    dialog.a4_spin.setValue(415)
    dialog.threshold_spin.setValue(6)
    dialog.device_combo.setCurrentIndex(dialog.device_combo.findData("Mic A"))

    settings = dialog.result_settings()

    assert settings.a4_reference_hz == 415
    assert settings.signal_threshold_percent == 6
    assert settings.input_device == "Mic A"
