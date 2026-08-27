# tests/test_main_window_misc_dialogs.py
"""MainWindow-level wiring for hands-free voice control and the Tuner dialog. Split from test_main_window.py (S10).
"""
import pytest
from PySide6.QtWidgets import QDialog

from main_window import MainWindow
from persistence import app_settings
from widgets.tuner_dialog import TunerDialog
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
# capture/announcement threading in tests/test_tuner_controller.py - these
# confirm only the shell's own wiring: dialog construction, commit/cancel,
# and persistence, mirroring _fake_mixer_dialog's shape above. exec() is
# always faked rather than really shown, so showEvent - and the real
# listening_requested it would emit - never fires; no real capture opens.)

def _fake_tuner_dialog(monkeypatch, window, *, accept: bool, on_exec=None):
    dialog = TunerDialog(
        window, devices=window.tuner.available_devices(),
        settings=window.tuner.begin_settings_edit(),
    )

    def fake_exec():
        if on_exec is not None:
            on_exec(dialog)
        return QDialog.DialogCode.Accepted if accept else QDialog.DialogCode.Rejected

    monkeypatch.setattr(dialog, "exec", fake_exec)
    monkeypatch.setattr("main_window.TunerDialog", lambda parent, devices, settings: dialog)
    return dialog


def test_tuner_dialog_ok_commits_and_persists_the_selection(
    qtbot, null_synth, null_tuner_capture, monkeypatch
):
    w = MainWindow(synth=null_synth, uk_terms=False, tuner_manager=null_tuner_capture)
    qtbot.addWidget(w)

    def edit(dialog):
        dialog.instrument_combo.setCurrentText("Violin")
        dialog.string_combo.setCurrentIndex(2)
        dialog.offset_spin.setValue(-2)

    _fake_tuner_dialog(monkeypatch, w, accept=True, on_exec=edit)
    w._show_tuner_dialog()

    assert w.tuner.settings.instrument == "Violin"
    assert w.tuner.settings.last_string_index == 2
    assert w.tuner.settings.reference_offset_semitones == -2
    assert app_settings.load().tuner.instrument == "Violin"


def test_tuner_dialog_cancel_leaves_settings_unchanged(
    qtbot, null_synth, null_tuner_capture, monkeypatch
):
    w = MainWindow(synth=null_synth, uk_terms=False, tuner_manager=null_tuner_capture)
    qtbot.addWidget(w)
    original_instrument = w.tuner.settings.instrument

    def edit(dialog):
        dialog.instrument_combo.setCurrentText("Cello")

    _fake_tuner_dialog(monkeypatch, w, accept=False, on_exec=edit)
    w._show_tuner_dialog()

    assert w.tuner.settings.instrument == original_instrument
    assert app_settings.load().tuner.instrument == original_instrument


def test_tuner_target_changed_reaches_the_capture_live(qtbot, null_synth, null_tuner_capture, monkeypatch):
    """target_changed is connected before exec() runs - selecting a
    different string mid-dialog should immediately update the capture's
    search band, without waiting for OK."""
    w = MainWindow(synth=null_synth, uk_terms=False, tuner_manager=null_tuner_capture)
    qtbot.addWidget(w)

    def edit(dialog):
        dialog.string_combo.setCurrentIndex(1)

    _fake_tuner_dialog(monkeypatch, w, accept=True, on_exec=edit)
    w._show_tuner_dialog()

    # Guitar string 2 (B3) - see models/tuner_instruments.py.
    from models.tuner_instruments import expected_frequency_hz, tuner_instrument_by_name

    expected = expected_frequency_hz(tuner_instrument_by_name("Guitar").strings[1], 0)
    assert null_tuner_capture.expected_hz == pytest.approx(expected)
