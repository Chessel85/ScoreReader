# controllers/voice_control_controller.py
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import QObject, Qt, Signal

from audio import voice_commands
from audio.voice_confirmation_cue import (
    VOICE_CONTROL_CUE_CHANNEL,
    voice_confirmation_cue_event,
    voice_recognition_started_event,
    voice_recognition_stopped_event,
)
from audio.voice_recognition import VoiceRecognitionManager
from models import mixer_settings
from models.voice_control_settings import VoiceControlSettings
from persistence import app_settings


class VoiceControlController(QObject):
    """Hands-free voice control (feature/voice-control, Ref 19): recognized
    spoken commands call straight into NavigationController/
    PlaybackController, the same entry points every keyboard shortcut, menu
    action and dialog already use - no widget focus dependency at all (see
    the project plan's own note that this is what makes voice commands
    correct regardless of which region currently has keyboard focus).

    Constructed ONCE at startup (main_window.py's setup_controllers, next to
    LiveMidiInputController), not per file load - it needs no MusicData
    itself beyond total_measures (see rebuild_grammar) and must outlive
    every load. Settings are global (persistence/app_settings.py's
    AppSettings), the same reasoning as live_midi_input.

    Threading: audio/voice_recognition.py's VoiceRecognitionManager delivers
    a recognized command on its OWN background thread, not Qt's main thread
    (see that module's docstring). _on_raw_recognition (that thread) does
    nothing but emit _raw_command_recognized; it is connected to its handler
    with an EXPLICIT Qt.ConnectionType.QueuedConnection, which forces the
    actual dispatch onto the main thread's event loop - the same "keep
    SynthEngine/the controllers only ever touched from the main thread"
    reasoning LiveMidiInputController already established for live MIDI
    input.
    """

    connection_changed = Signal(bool)  # True once the recognizer is actually listening
    # command_name, confidence_percent, measure_number (object: Optional[int]
    # - internal, thread-marshaling only, same shape as LiveMidiInputController's
    # _raw_note_on/_raw_note_off.
    _raw_command_recognized = Signal(str, float, object)
    # True once the worker actually finished loading the model and opened
    # the microphone (or failed to) - internal, thread-marshaling only, same
    # reasoning as _raw_command_recognized. See VoiceRecognitionManager.
    # set_ready_callback for why this is async rather than a return value.
    _raw_ready = Signal(bool)

    # Suppressing the ding for individual commands (e.g. "play", where it
    # might interfere with noticing playback has actually started) is a
    # deliberately cheap future edit - add the command name here. Empty
    # today: the ding plays for every recognized command.
    _SUPPRESSED_CUE_COMMANDS: set = set()

    def __init__(self, synth, navigation, playback, parent=None, voice_manager=None):
        super().__init__(parent)
        self.synth = synth
        self.navigation = navigation
        self.playback = playback
        self.settings: VoiceControlSettings = app_settings.load().voice_control
        self._manager = voice_manager if voice_manager is not None else VoiceRecognitionManager()
        self._manager.set_callback(self._on_raw_recognition)
        self._manager.set_ready_callback(self._on_raw_ready)
        self._raw_command_recognized.connect(
            self._handle_command_recognized, Qt.ConnectionType.QueuedConnection
        )
        self._raw_ready.connect(self._handle_ready, Qt.ConnectionType.QueuedConnection)
        self._edit_snapshot: Optional[VoiceControlSettings] = None

        # command_name -> zero-arg callable. GO_TO_BAR is handled separately
        # in _dispatch (it carries a measure number, unlike every other
        # command) and is deliberately NOT a key here.
        self._command_table: Dict[str, Callable[[], None]] = {
            voice_commands.PREVIEW: self.playback.audition_phrase,
            voice_commands.PLAY: self.playback.play_command,
            voice_commands.STOP: self.playback.stop,
            voice_commands.PAUSE: self.playback.pause_command,
            voice_commands.FORWARD: self.navigation.timeline_right,
            voice_commands.BACK: self.navigation.timeline_left,
            voice_commands.NEXT_BAR: self.navigation.measure_right,
            voice_commands.PREVIOUS_BAR: self.navigation.measure_left,
            voice_commands.HOME: self.navigation.timeline_home,
            voice_commands.END: self.navigation.timeline_end,
            voice_commands.SLOWER: self.playback.tempo_slower,
            voice_commands.FASTER: self.playback.tempo_faster,
            voice_commands.DEFAULT_SPEED: self.playback.tempo_reset,
        }
        self._apply_cue_levels()

    # --- lifecycle ---------------------------------------------------

    def start(self) -> None:
        """Auto-start listening if enabled and a device was saved - called
        once at startup. Silent no-op otherwise (no popup, no exception):
        the feature never having been enabled, or pywin32/SAPI not being
        available, are both ordinary states, not errors."""
        if self.settings.enabled:
            self._connect(self.settings.device_name)

    def is_listening(self) -> bool:
        return self._manager.is_running

    def close(self) -> None:
        """App close (main_window.py's closeEvent) - stops the recognizer
        thread."""
        self._manager.stop()

    def stop_listening(self) -> None:
        """Pauses listening WITHOUT touching settings.enabled or persisting
        anything - used by the settings dialog's Test... flow (main_window.
        py's _show_voice_control_test_dialog) to free the microphone for
        VoiceControlTestDialog's own isolated recognizer session. Pair with
        resume_listening() once that dialog closes."""
        self._disconnect()

    def resume_listening(self) -> None:
        """Counterpart of stop_listening() - resumes with the CURRENT
        settings, only if they say to (a no-op if the user disabled voice
        control, or changed the device, while the test dialog was open)."""
        if self.settings.enabled:
            self._connect(self.settings.device_name)

    def rebuild_grammar(self, total_measures: int) -> None:
        """Called on every score load (main_window.py's _on_score_loaded,
        after the saved config is applied) so "go to bar N"'s numeric
        vocabulary is always bounded to the CURRENT score's real measure
        numbers - see audio/voice_commands.go_to_bar_phrases."""
        self._manager.rebuild_grammar(total_measures)

    # --- menu toggle (Ctrl+Shift+Return) ------------------------------

    def toggle_enabled(self) -> bool:
        """Flips enabled, starts/stops listening to match, persists, and
        returns the new state for the menu action's checked display.

        Plays a distinct tone for each direction (reported: the user could
        not otherwise tell by ear whether the toggle had actually taken
        effect). "Stopped" plays right here, unconditionally, since stopping
        never fails and is fast (no model to load). "Started" does NOT play
        here - starting is asynchronous (see VoiceRecognitionManager.start),
        so it plays from _handle_ready once listening has actually begun,
        never claiming success before it's true."""
        if self.settings.enabled:
            self._disconnect()
            self.settings.enabled = False
            self.synth.play_voice_confirmation_cue(*voice_recognition_stopped_event())
        else:
            self.settings.enabled = True
            self._connect(self.settings.device_name)
        app_settings.set_voice_control_settings(self.settings)
        return self.settings.enabled

    # --- settings dialog (begin/commit/cancel) ------------------------

    def available_devices(self) -> List[str]:
        return self._manager.list_devices()

    def begin_settings_edit(self) -> VoiceControlSettings:
        """Snapshots the current settings (for cancel_settings_edit to
        revert to, though there is nothing live to revert here - unlike
        LiveMidiInputController there is no per-CC live preview) and returns
        a separate working copy for the dialog to display."""
        self._edit_snapshot = self.settings.copy()
        return self.settings.copy()

    def commit_settings_edit(self, new_settings: VoiceControlSettings) -> None:
        """OK: adopt the dialog's result. Restarts listening only if the
        device or enabled state actually changed - a pure confidence-
        threshold edit is pushed to the already-running recognizer instead
        of forcing a reconnect, mirroring LiveMidiInputController.
        commit_settings_edit's "reconnect only when it matters" reasoning."""
        new_settings = new_settings.copy()
        device_changed = new_settings.device_name != self.settings.device_name
        enabled_changed = new_settings.enabled != self.settings.enabled
        self.settings = new_settings
        if enabled_changed or device_changed:
            if self.settings.enabled:
                self._connect(self.settings.device_name)
            else:
                self._disconnect()
        elif self._manager.is_running:
            self._manager.set_confidence_threshold(self.settings.confidence_threshold)
        self._apply_cue_levels()
        app_settings.set_voice_control_settings(self.settings)
        self._edit_snapshot = None

    def cancel_settings_edit(self) -> None:
        """Cancel: nothing was live-previewed onto the recognizer itself
        (self.settings was never touched), but the cue's volume/pan WAS
        live-previewed straight onto the synth channel (see preview_cue_
        volume/preview_cue_pan) - put that back exactly as it was before the
        dialog opened, mirroring LiveMidiInputController.cancel_settings_edit."""
        if self._edit_snapshot is not None:
            self.settings = self._edit_snapshot
            self._apply_cue_levels()
        self._edit_snapshot = None

    def preview_cue_volume(self, percent: int) -> None:
        """Live preview while the dialog is open: sets the cue channel's
        volume AND plays the cue once, since it's a one-shot sound rather
        than a held note - there is nothing already ringing to hear the new
        level change on, unlike LiveMidiInputController's preview_volume."""
        self.synth.set_channel_volume(
            VOICE_CONTROL_CUE_CHANNEL, mixer_settings.volume_percent_to_cc(percent)
        )
        self.synth.play_voice_confirmation_cue(*voice_confirmation_cue_event())

    def preview_cue_pan(self, percent: int) -> None:
        self.synth.set_channel_pan(
            VOICE_CONTROL_CUE_CHANNEL, mixer_settings.pan_percent_to_cc(percent)
        )
        self.synth.play_voice_confirmation_cue(*voice_confirmation_cue_event())

    # --- recognizer callback thread -> Qt main thread -----------------

    def _on_raw_recognition(
        self, command_name: str, confidence: float, measure_number: Optional[int]
    ) -> None:
        """VoiceRecognitionManager's own background thread. Does nothing but
        emit - see class docstring on why."""
        self._raw_command_recognized.emit(command_name, confidence, measure_number)

    def _handle_command_recognized(
        self, command_name: str, confidence: float, measure_number
    ) -> None:
        """Qt main thread only (see class docstring)."""
        self._dispatch(command_name, measure_number)

    def _on_raw_ready(self, started: bool) -> None:
        """VoiceRecognitionManager's own background thread. Does nothing but
        emit - see class docstring on why."""
        self._raw_ready.emit(started)

    def _handle_ready(self, started: bool) -> None:
        """Qt main thread only. Fires once the worker has actually finished
        loading the model and opened the microphone (or failed to) - see
        toggle_enabled's own note on why the "started" tone lives here
        rather than right after requesting a connect."""
        self.connection_changed.emit(started)
        if started:
            self.synth.play_voice_confirmation_cue(*voice_recognition_started_event())

    def _dispatch(self, command_name: str, measure_number: Optional[int]) -> None:
        """The single point every recognized command passes through -
        exactly one place to add per-command cue suppression later (see
        _SUPPRESSED_CUE_COMMANDS)."""
        if command_name == voice_commands.GO_TO_BAR:
            if measure_number is None:
                return
            self.navigation.to_typed_measure(str(measure_number))
        else:
            handler = self._command_table.get(command_name)
            if handler is None:
                return
            handler()
        if command_name not in self._SUPPRESSED_CUE_COMMANDS:
            self.synth.play_voice_confirmation_cue(*voice_confirmation_cue_event())

    # --- internal -----------------------------------------------------

    def _connect(self, device_name: Optional[str]) -> bool:
        """Returns whether the worker was LAUNCHED, not whether it is
        actually listening yet - that arrives asynchronously via
        _handle_ready (see VoiceRecognitionManager.start). Only a launch
        failure is reported synchronously here; a real success/failure is
        reported once, later, from _handle_ready."""
        launched = self._manager.start(device_name, self.settings.confidence_threshold)
        if not launched:
            self.connection_changed.emit(False)
        return launched

    def _disconnect(self) -> None:
        was_running = self._manager.is_running
        self._manager.stop()
        if was_running:
            self.connection_changed.emit(False)

    def _apply_cue_levels(self) -> None:
        """Sends the saved cue volume/pan to the synth - called at
        construction (SynthEngine._load_click_soundfont otherwise leaves the
        channel at its own fixed centre-pan/full-volume default) and after a
        settings commit/cancel. The cue is a one-shot sound, so this only
        needs to run when the settings actually change, never per-play -
        MIDI channel CC state persists on its own until next changed."""
        self.synth.set_channel_volume(
            VOICE_CONTROL_CUE_CHANNEL, mixer_settings.volume_percent_to_cc(self.settings.cue_volume_percent)
        )
        self.synth.set_channel_pan(
            VOICE_CONTROL_CUE_CHANNEL, mixer_settings.pan_percent_to_cc(self.settings.cue_pan_percent)
        )
