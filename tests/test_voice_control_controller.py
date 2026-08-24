# tests/test_voice_control_controller.py
"""controllers/voice_control_controller.py, exercised entirely with
NullSynth + NullVoiceRecognizer + fake navigation/playback objects - never
touches real audio or a real SAPI COM recognizer (see tests/conftest.py's
_forbid_real_audio/_forbid_real_voice_recognition).

QApplication.processEvents() is needed after simulate_recognition, the same
"a queued signal needs the event loop to actually run before asserting"
convention tests/test_live_midi_input_controller.py already uses - the
controller's _raw_command_recognized signal is connected with
Qt.ConnectionType.QueuedConnection specifically so command dispatch always
happens on the main thread (see the controller's own docstring).
"""
import pytest
from PySide6.QtWidgets import QApplication

from audio import voice_commands
from controllers.voice_control_controller import VoiceControlController
from models.voice_control_settings import VoiceControlSettings
from persistence import app_settings
from tests.support.null_synth import NullSynth
from tests.support.null_voice_recognizer import NullVoiceRecognizer


class _FakeNavigation:
    def __init__(self):
        self.calls = []

    def timeline_right(self):
        self.calls.append("timeline_right")

    def timeline_left(self):
        self.calls.append("timeline_left")

    def measure_right(self):
        self.calls.append("measure_right")

    def measure_left(self):
        self.calls.append("measure_left")

    def timeline_home(self):
        self.calls.append("timeline_home")

    def timeline_end(self):
        self.calls.append("timeline_end")

    def to_typed_measure(self, digits):
        self.calls.append(("to_typed_measure", digits))


class _FakePlayback:
    def __init__(self):
        self.calls = []

    def audition_phrase(self):
        self.calls.append("audition_phrase")

    def play_command(self):
        self.calls.append("play_command")

    def stop(self):
        self.calls.append("stop")

    def pause_command(self):
        self.calls.append("pause_command")

    def tempo_slower(self):
        self.calls.append("tempo_slower")

    def tempo_faster(self):
        self.calls.append("tempo_faster")

    def tempo_reset(self):
        self.calls.append("tempo_reset")


@pytest.fixture
def synth():
    return NullSynth()


@pytest.fixture
def navigation():
    return _FakeNavigation()


@pytest.fixture
def playback():
    return _FakePlayback()


@pytest.fixture
def voice_manager():
    return NullVoiceRecognizer(available_devices=["My Microphone", "Other Device"])


def _controller(synth, navigation, playback, voice_manager, qtbot):
    """qtbot is only depended on to guarantee a QApplication exists (needed
    for the controller's Qt signals/QueuedConnection) - pytest-qt's own
    fixture provides that just by being requested."""
    return VoiceControlController(synth, navigation, playback, voice_manager=voice_manager)


def test_start_does_nothing_when_disabled(synth, navigation, playback, voice_manager, qtbot):
    controller = _controller(synth, navigation, playback, voice_manager, qtbot)
    controller.start()

    assert not controller.is_listening()
    assert voice_manager.start_calls == []


def test_start_auto_starts_when_enabled_and_device_present(
    synth, navigation, playback, voice_manager, qtbot
):
    app_settings.set_voice_control_settings(
        VoiceControlSettings(enabled=True, device_name="My Microphone")
    )
    controller = _controller(synth, navigation, playback, voice_manager, qtbot)

    controller.start()

    assert controller.is_listening()
    assert voice_manager.start_calls == [("My Microphone", controller.settings.confidence_threshold)]


def test_start_degrades_silently_when_device_not_present(
    synth, navigation, playback, voice_manager, qtbot
):
    app_settings.set_voice_control_settings(
        VoiceControlSettings(enabled=True, device_name="Unplugged Microphone")
    )
    controller = _controller(synth, navigation, playback, voice_manager, qtbot)

    controller.start()  # must not raise

    assert not controller.is_listening()


def test_toggle_enabled_starts_and_stops_listening(synth, navigation, playback, voice_manager, qtbot):
    controller = _controller(synth, navigation, playback, voice_manager, qtbot)
    controller.settings.device_name = "My Microphone"

    assert controller.toggle_enabled() is True
    assert controller.is_listening()

    assert controller.toggle_enabled() is False
    assert not controller.is_listening()


@pytest.mark.parametrize("command_name,expected_call", [
    (voice_commands.PREVIEW, "audition_phrase"),
    (voice_commands.PLAY, "play_command"),
    (voice_commands.STOP, "stop"),
    (voice_commands.PAUSE, "pause_command"),
    (voice_commands.SLOWER, "tempo_slower"),
    (voice_commands.FASTER, "tempo_faster"),
    (voice_commands.DEFAULT_SPEED, "tempo_reset"),
])
def test_playback_commands_dispatch_to_the_right_method(
    synth, navigation, playback, voice_manager, qtbot, command_name, expected_call
):
    controller = _controller(synth, navigation, playback, voice_manager, qtbot)
    controller.settings.device_name = "My Microphone"
    controller.toggle_enabled()

    voice_manager.simulate_recognition(command_name, confidence=90.0)
    QApplication.processEvents()

    assert playback.calls == [expected_call]


@pytest.mark.parametrize("command_name,expected_call", [
    (voice_commands.FORWARD, "timeline_right"),
    (voice_commands.BACK, "timeline_left"),
    (voice_commands.NEXT_BAR, "measure_right"),
    (voice_commands.PREVIOUS_BAR, "measure_left"),
    (voice_commands.HOME, "timeline_home"),
    (voice_commands.END, "timeline_end"),
])
def test_navigation_commands_dispatch_to_the_right_method(
    synth, navigation, playback, voice_manager, qtbot, command_name, expected_call
):
    controller = _controller(synth, navigation, playback, voice_manager, qtbot)
    controller.settings.device_name = "My Microphone"
    controller.toggle_enabled()

    voice_manager.simulate_recognition(command_name, confidence=90.0)
    QApplication.processEvents()

    assert navigation.calls == [expected_call]


def test_go_to_bar_dispatches_with_the_measure_number(
    synth, navigation, playback, voice_manager, qtbot
):
    controller = _controller(synth, navigation, playback, voice_manager, qtbot)
    controller.settings.device_name = "My Microphone"
    controller.toggle_enabled()

    voice_manager.simulate_recognition(voice_commands.GO_TO_BAR, confidence=90.0, measure_number=12)
    QApplication.processEvents()

    assert navigation.calls == [("to_typed_measure", "12")]


def test_go_to_bar_with_no_measure_number_is_ignored(
    synth, navigation, playback, voice_manager, qtbot
):
    """Defensive: a real recognized GO_TO_BAR always carries a measure
    number (see audio/voice_commands.parse_command) - this only guards
    against a malformed injected event."""
    controller = _controller(synth, navigation, playback, voice_manager, qtbot)
    controller.settings.device_name = "My Microphone"
    controller.toggle_enabled()

    voice_manager.simulate_recognition(voice_commands.GO_TO_BAR, confidence=90.0, measure_number=None)
    QApplication.processEvents()

    assert navigation.calls == []


def test_recognized_command_plays_the_confirmation_cue(
    synth, navigation, playback, voice_manager, qtbot
):
    controller = _controller(synth, navigation, playback, voice_manager, qtbot)
    controller.settings.device_name = "My Microphone"
    controller.toggle_enabled()

    voice_manager.simulate_recognition(voice_commands.STOP, confidence=90.0)
    QApplication.processEvents()

    assert len(synth.voice_confirmation_cues) == 1


def test_unknown_command_name_is_ignored_and_plays_no_cue(
    synth, navigation, playback, voice_manager, qtbot
):
    controller = _controller(synth, navigation, playback, voice_manager, qtbot)
    controller.settings.device_name = "My Microphone"
    controller.toggle_enabled()

    voice_manager.simulate_recognition("not_a_real_command", confidence=90.0)
    QApplication.processEvents()

    assert navigation.calls == []
    assert playback.calls == []
    assert synth.voice_confirmation_cues == []


def test_suppressed_cue_commands_skip_the_ding(synth, navigation, playback, voice_manager, qtbot):
    """The one-line future extension point the user explicitly asked for -
    confirms suppressing a single command's cue works without touching
    dispatch at all."""
    controller = _controller(synth, navigation, playback, voice_manager, qtbot)
    controller.settings.device_name = "My Microphone"
    controller.toggle_enabled()
    controller._SUPPRESSED_CUE_COMMANDS.add(voice_commands.PLAY)
    try:
        voice_manager.simulate_recognition(voice_commands.PLAY, confidence=90.0)
        QApplication.processEvents()

        assert playback.calls == ["play_command"]
        assert synth.voice_confirmation_cues == []
    finally:
        controller._SUPPRESSED_CUE_COMMANDS.discard(voice_commands.PLAY)


def test_commit_settings_edit_restarts_only_when_device_or_enabled_changes(
    synth, navigation, playback, voice_manager, qtbot
):
    controller = _controller(synth, navigation, playback, voice_manager, qtbot)
    controller.settings.device_name = "My Microphone"
    controller.toggle_enabled()
    voice_manager.start_calls.clear()

    working = controller.begin_settings_edit()
    working.confidence_threshold = 40.0  # unchanged device/enabled
    controller.commit_settings_edit(working)

    assert voice_manager.start_calls == [], "a pure threshold edit must not restart the recognizer"
    assert voice_manager.confidence_threshold == 40.0

    working = controller.begin_settings_edit()
    working.device_name = "Other Device"
    controller.commit_settings_edit(working)

    assert voice_manager.start_calls == [("Other Device", 40.0)]


def test_rebuild_grammar_forwards_to_the_manager(synth, navigation, playback, voice_manager, qtbot):
    controller = _controller(synth, navigation, playback, voice_manager, qtbot)

    controller.rebuild_grammar(42)

    assert voice_manager.rebuild_calls == [42]


def test_close_stops_the_manager(synth, navigation, playback, voice_manager, qtbot):
    controller = _controller(synth, navigation, playback, voice_manager, qtbot)
    controller.settings.device_name = "My Microphone"
    controller.toggle_enabled()

    controller.close()

    assert voice_manager.stop_count == 1
