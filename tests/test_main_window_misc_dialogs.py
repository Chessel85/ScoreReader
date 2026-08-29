# tests/test_main_window_misc_dialogs.py
"""MainWindow-level wiring for hands-free voice control and the Tuner dialog. Split from test_main_window.py (S10).
"""
from PySide6.QtWidgets import QDialog

from main_window import MainWindow
from persistence import app_settings
from widgets.tuner_dialog import TunerDialog
from widgets.tuner_settings_dialog import TunerSettingsDialog
from widgets.voice_control_dialog import VoiceControlDialog
from tests.support.main_window_helpers import load_and_wait


# --- Ref 19: hands-free voice control, MainWindow-level wiring ------------
# (command dispatch/threading is covered in tests/test_voice_control_
# controller.py against a bare VoiceControlController - these confirm only
# the shell's own wiring: construction, the menu toggle, and the
# score-load -> grammar-rebuild hook.)

def test_voice_control_is_constructed_disabled_and_toggle_updates_the_menu_action(
    qtbot, null_synth, null_voice_recognizer,
):
    w = MainWindow(synth=null_synth, uk_terms=False, voice_control_manager=null_voice_recognizer)
    qtbot.addWidget(w)

    assert not w.voice_control.is_listening()
    assert w.voice_control_action.isChecked() is False

    w.voice_control.settings.device_name = "My Microphone"
    null_voice_recognizer.available_devices = ["My Microphone"]
    w.toggle_voice_control()

    assert w.voice_control.is_listening()
    assert w.voice_control_action.isChecked() is True


def test_loading_a_score_rebuilds_the_go_to_bar_grammar(
    qtbot, null_synth, null_voice_recognizer, many_measures_score,
):
    w = MainWindow(synth=null_synth, uk_terms=False, voice_control_manager=null_voice_recognizer)
    qtbot.addWidget(w)

    load_and_wait(w, qtbot, many_measures_score)

    assert null_voice_recognizer.rebuild_calls[-1] == w._music_data.total_measures


def test_voice_control_device_combo_is_filled_off_the_main_thread(
    qtbot, null_synth, null_voice_recognizer,
):
    """P1: the settings dialog must not block the (screen-reader-driving)
    main thread while devices are enumerated. _scan_devices_async shows a
    "Scanning…" placeholder at once and fills the real list from a
    DeviceEnumerationThread, re-selecting the saved device."""
    null_voice_recognizer.available_devices = ["My Microphone", "Other Device"]
    w = MainWindow(synth=null_synth, uk_terms=False, voice_control_manager=null_voice_recognizer)
    qtbot.addWidget(w)

    dialog = VoiceControlDialog(w, devices=[], settings=w.voice_control.begin_settings_edit())
    qtbot.addWidget(dialog)

    w._scan_devices_async(
        dialog, w.voice_control.available_devices, selected="Other Device"
    )
    assert dialog.device_combo.count() == 1
    assert dialog.device_combo.itemText(0) == "Scanning for devices…"

    qtbot.waitUntil(lambda: dialog.device_combo.count() == 3, timeout=2000)
    assert [dialog.device_combo.itemText(i) for i in range(1, 3)] == [
        "My Microphone", "Other Device",
    ]
    assert dialog.device_combo.currentData() == "Other Device"


def test_close_stops_the_voice_control_recognizer(qtbot, null_synth, null_voice_recognizer):
    w = MainWindow(synth=null_synth, uk_terms=False, voice_control_manager=null_voice_recognizer)
    qtbot.addWidget(w)
    w.voice_control.settings.device_name = "My Microphone"
    null_voice_recognizer.available_devices = ["My Microphone"]
    w.toggle_voice_control()

    w.close()

    assert null_voice_recognizer.stop_count >= 1


# --- Tools > Tuner dialog, MainWindow-level wiring -------------------------
# (pitch-detection math is covered in tests/audio/test_pitch_detector.py,
# nearest-note math in tests/models/test_tuner_instruments.py, capture/
# announcement threading in tests/test_tuner_controller.py - these confirm
# only the shell's own wiring: outer dialog construction/signal wiring, and
# the nested Settings dialog's commit/cancel/persistence, mirroring
# _fake_mixer_dialog's shape above. exec() is always faked rather than
# really shown, so showEvent - and the real listening_requested it would
# emit - never fires; no real capture opens. TunerDialog itself has no
# editable settings any more (see controllers/tuner_controller.py's module
# docstring) - only the nested TunerSettingsDialog does.)

def _fake_tuner_dialog(monkeypatch, *, on_exec=None):
    dialog = TunerDialog()

    def fake_exec():
        if on_exec is not None:
            on_exec(dialog)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(dialog, "exec", fake_exec)
    monkeypatch.setattr("main_window.TunerDialog", lambda parent: dialog)
    return dialog


def _fake_tuner_settings_dialog(monkeypatch, window, *, accept: bool, on_exec=None):
    dialog = TunerSettingsDialog(
        window, devices=window.tuner.available_devices(),
        settings=window.tuner.begin_settings_edit(),
    )

    def fake_exec():
        if on_exec is not None:
            on_exec(dialog)
        return QDialog.DialogCode.Accepted if accept else QDialog.DialogCode.Rejected

    monkeypatch.setattr(dialog, "exec", fake_exec)
    monkeypatch.setattr("main_window.TunerSettingsDialog", lambda parent, devices, settings: dialog)
    return dialog


def test_show_tuner_dialog_wires_pitch_updates_live(qtbot, null_synth, null_tuner_capture, monkeypatch):
    """pitch_result_changed is connected before exec() runs, so the reading
    updates the still-open dialog's reading_edit immediately."""
    w = MainWindow(synth=null_synth, uk_terms=False, tuner_manager=null_tuner_capture)
    qtbot.addWidget(w)

    def edit(dialog):
        w.tuner.pitch_result_changed.emit("signal 50 percent - A: in tune")
        assert dialog.reading_edit.text() == "signal 50 percent - A: in tune"

    _fake_tuner_dialog(monkeypatch, on_exec=edit)
    w._show_tuner_dialog()


def test_tuner_settings_dialog_ok_commits_and_persists(
    qtbot, null_synth, null_tuner_capture, monkeypatch
):
    w = MainWindow(synth=null_synth, uk_terms=False, tuner_manager=null_tuner_capture)
    qtbot.addWidget(w)
    parent_dialog = TunerDialog(w)
    qtbot.addWidget(parent_dialog)

    def edit(dialog):
        dialog.a4_spin.setValue(442)
        dialog.threshold_spin.setValue(8)

    _fake_tuner_settings_dialog(monkeypatch, w, accept=True, on_exec=edit)
    w._open_tuner_settings_dialog(parent_dialog)

    assert w.tuner.settings.a4_reference_hz == 442
    assert w.tuner.settings.signal_threshold_percent == 8
    assert app_settings.load().tuner.a4_reference_hz == 442


def test_tuner_settings_dialog_cancel_leaves_settings_unchanged(
    qtbot, null_synth, null_tuner_capture, monkeypatch
):
    w = MainWindow(synth=null_synth, uk_terms=False, tuner_manager=null_tuner_capture)
    qtbot.addWidget(w)
    parent_dialog = TunerDialog(w)
    qtbot.addWidget(parent_dialog)
    original_a4 = w.tuner.settings.a4_reference_hz

    def edit(dialog):
        dialog.a4_spin.setValue(415)

    _fake_tuner_settings_dialog(monkeypatch, w, accept=False, on_exec=edit)
    w._open_tuner_settings_dialog(parent_dialog)

    assert w.tuner.settings.a4_reference_hz == original_a4
    assert app_settings.load().tuner.a4_reference_hz == original_a4


def test_tuner_settings_device_changed_reaches_the_capture_live(
    qtbot, null_synth, null_tuner_capture, monkeypatch
):
    """device_changed is connected before exec() runs - picking a different
    device mid-dialog should immediately reopen capture, without waiting
    for OK."""
    null_tuner_capture.available_devices = ["Mic A", "Mic B"]
    w = MainWindow(synth=null_synth, uk_terms=False, tuner_manager=null_tuner_capture)
    qtbot.addWidget(w)
    parent_dialog = TunerDialog(w)
    qtbot.addWidget(parent_dialog)

    def edit(dialog):
        dialog.device_combo.setCurrentIndex(dialog.device_combo.findData("Mic B"))

    _fake_tuner_settings_dialog(monkeypatch, w, accept=True, on_exec=edit)
    w._open_tuner_settings_dialog(parent_dialog)

    assert null_tuner_capture.open_calls[-1] == "Mic B"
