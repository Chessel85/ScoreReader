# tests/test_live_midi_input_controller.py
"""controllers/live_midi_input_controller.py, exercised entirely with
NullSynth + NullMidiInputManager - never touches real audio or a real MIDI
device (see tests/conftest.py's _forbid_real_audio/_forbid_real_midi_input).

QApplication.processEvents() is needed after simulate_note_on/off, the same
"a queued signal needs the event loop to actually run before asserting"
convention tests/test_main_window.py already uses (_focus) - the
controller's _raw_note_on/_raw_note_off signals are connected with
Qt.ConnectionType.QueuedConnection specifically so live-input handling
always happens on the main thread (see the controller's own docstring).
"""
import pytest
from PySide6.QtWidgets import QApplication

from audio.midi_input import LIVE_MIDI_INPUT_CHANNEL
from controllers.live_midi_input_controller import LiveMidiInputController
from models.live_midi_input_settings import LiveMidiInputSettings
from persistence import app_settings
from tests.support.null_live_midi_input import NullMidiInputManager
from tests.support.null_synth import NullSynth


@pytest.fixture
def synth():
    return NullSynth()


@pytest.fixture
def midi_manager():
    return NullMidiInputManager(available_ports=["My Keyboard", "Other Device"])


def _controller(synth, midi_manager, qtbot):
    """qtbot is only depended on to guarantee a QApplication exists (needed
    for the controller's Qt signals/QueuedConnection) - pytest-qt's own
    fixture provides that just by being requested."""
    return LiveMidiInputController(synth, midi_manager=midi_manager)


def test_start_does_nothing_when_disabled(synth, midi_manager, qtbot):
    controller = _controller(synth, midi_manager, qtbot)
    controller.start()

    assert not controller.is_connected()
    assert midi_manager.open_calls == []


def test_start_auto_connects_when_enabled_and_device_present(synth, midi_manager, qtbot):
    app_settings.set_live_midi_input_settings(
        LiveMidiInputSettings(enabled=True, device_name="My Keyboard")
    )
    controller = _controller(synth, midi_manager, qtbot)

    controller.start()

    assert controller.is_connected()
    assert midi_manager.open_calls == ["My Keyboard"]


def test_start_degrades_silently_when_device_not_present(synth, midi_manager, qtbot):
    app_settings.set_live_midi_input_settings(
        LiveMidiInputSettings(enabled=True, device_name="Unplugged Device")
    )
    controller = _controller(synth, midi_manager, qtbot)

    controller.start()  # must not raise

    assert not controller.is_connected()


def test_toggle_enabled_connects_and_disconnects(synth, midi_manager, qtbot):
    controller = _controller(synth, midi_manager, qtbot)
    controller.settings.device_name = "My Keyboard"

    assert controller.toggle_enabled() is True
    assert controller.is_connected()

    assert controller.toggle_enabled() is False
    assert not controller.is_connected()
    assert synth.live_all_off_count >= 1


def test_connecting_applies_instrument_volume_and_pan(synth, midi_manager, qtbot):
    controller = _controller(synth, midi_manager, qtbot)
    controller.settings.device_name = "My Keyboard"
    controller.settings.gm_program = 25  # Acoustic Guitar (nylon)
    controller.settings.volume_percent = 50
    controller.settings.pan_percent = -100

    controller.toggle_enabled()

    assert (LIVE_MIDI_INPUT_CHANNEL, 24, 0) in synth.program_changes
    assert any(ch == LIVE_MIDI_INPUT_CHANNEL for ch, _ in synth.volume_changes)
    assert any(ch == LIVE_MIDI_INPUT_CHANNEL for ch, _ in synth.pan_changes)


def test_note_on_and_off_reach_the_synth_after_the_queued_connection_fires(
    synth, midi_manager, qtbot
):
    controller = _controller(synth, midi_manager, qtbot)
    controller.settings.device_name = "My Keyboard"
    controller.toggle_enabled()

    midi_manager.simulate_note_on(60, 100)
    QApplication.processEvents()

    assert synth.live_notes_on == [(60, 100)]

    midi_manager.simulate_note_off(60)
    QApplication.processEvents()

    assert synth.live_notes_off == [60]


def test_commit_settings_edit_reconnects_only_when_device_or_enabled_changes(
    synth, midi_manager, qtbot
):
    controller = _controller(synth, midi_manager, qtbot)
    controller.settings.device_name = "My Keyboard"
    controller.toggle_enabled()
    midi_manager.open_calls.clear()

    working = controller.begin_settings_edit()
    working.volume_percent = 40  # unchanged device/enabled
    controller.commit_settings_edit(working)

    assert midi_manager.open_calls == [], "a pure volume edit must not reconnect the device"

    working = controller.begin_settings_edit()
    working.device_name = "Other Device"
    controller.commit_settings_edit(working)

    assert midi_manager.open_calls == ["Other Device"]


def test_cancel_settings_edit_reverts_synth_state_but_not_device(synth, midi_manager, qtbot):
    controller = _controller(synth, midi_manager, qtbot)
    controller.settings.device_name = "My Keyboard"
    controller.toggle_enabled()

    working = controller.begin_settings_edit()
    working.volume_percent = 10
    controller.preview_volume(10)
    controller.cancel_settings_edit()

    assert controller.settings.volume_percent == 100, "reverted to the pre-edit value"
    assert controller.is_connected(), "cancel never touches the connection itself"


def test_close_releases_device_and_silences_held_notes(synth, midi_manager, qtbot):
    controller = _controller(synth, midi_manager, qtbot)
    controller.settings.device_name = "My Keyboard"
    controller.toggle_enabled()

    controller.close()

    assert midi_manager.close_count == 1
    assert synth.live_all_off_count >= 1
