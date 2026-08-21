# controllers/live_midi_input_controller.py
from typing import List, Optional

from PySide6.QtCore import QObject, Qt, Signal

from audio.midi_input import LIVE_MIDI_INPUT_CHANNEL, NOTE_ON, MidiInputManager
from models import mixer_settings
from models.live_midi_input_settings import LiveMidiInputSettings
from persistence import app_settings


class LiveMidiInputController(QObject):
    """Play a connected MIDI keyboard/controller live through the app's own
    synth (SynthEngine.live_note_on/live_note_off/live_all_notes_off).

    Constructed ONCE at startup (main_window.py's setup_controllers, next to
    PlaybackController), not per file load - it needs no MusicData and must
    outlive every load, the same lifetime ScoreSession/SynthEngine already
    have. Settings are global (persistence/app_settings.py's AppSettings),
    confirmed with the user, not per-score like models/mixer_settings.py.

    Threading: audio/midi_input.py's MidiInputManager delivers each MIDI
    message on rtmidi's OWN internal thread, not Qt's main thread.
    _on_raw_message (that thread) does nothing but emit _raw_note_on/
    _raw_note_off; both are connected to their handlers with an EXPLICIT
    Qt.ConnectionType.QueuedConnection, which forces the actual handler call
    onto the main thread's event loop (this controller is constructed on,
    and never moved off, the main thread). That keeps "SynthEngine is only
    ever touched from the main thread" true for this feature too, rather
    than adding this codebase's first lock. _connect() applies the
    instrument/volume/pan synchronously before returning, so a queued note-
    on for a fresh connection can only run after that has already happened -
    race-free by construction, not by luck.
    """

    connection_changed = Signal(bool)  # True once a device is actually open
    _raw_note_on = Signal(int, int)    # pitch, velocity - internal, thread-marshaling only
    _raw_note_off = Signal(int)        # pitch

    def __init__(self, synth, parent=None, midi_manager: Optional[MidiInputManager] = None):
        super().__init__(parent)
        self.synth = synth
        self.settings: LiveMidiInputSettings = app_settings.load().live_midi_input
        self._midi = midi_manager if midi_manager is not None else MidiInputManager()
        self._midi.set_callback(self._on_raw_message)
        self._raw_note_on.connect(self._handle_note_on, Qt.ConnectionType.QueuedConnection)
        self._raw_note_off.connect(self._handle_note_off, Qt.ConnectionType.QueuedConnection)
        self._edit_snapshot: Optional[LiveMidiInputSettings] = None

    # --- lifecycle --------------------------------------------------------

    def start(self) -> None:
        """Auto-connect to the last-used device if enabled and it's present
        this session - called once at startup. Silent no-op otherwise (no
        popup, no exception): a device that isn't plugged in, or the feature
        simply never having been enabled, are both ordinary states, not
        errors."""
        if self.settings.enabled and self.settings.device_name:
            self._connect(self.settings.device_name)

    def is_connected(self) -> bool:
        return self._midi.is_open

    def close(self) -> None:
        """App close (main_window.py's closeEvent, before synth.close()) -
        releases the device and force-silences any still-held note."""
        self._midi.close()
        self.synth.live_all_notes_off()

    # --- menu toggle (Ctrl+L) ----------------------------------------------

    def toggle_enabled(self) -> bool:
        """Flips enabled, connects/disconnects to match, persists, and
        returns the new state for the menu action's checked display."""
        if self.settings.enabled:
            self._disconnect()
            self.settings.enabled = False
        else:
            self.settings.enabled = True
            if self.settings.device_name:
                self._connect(self.settings.device_name)
        app_settings.set_live_midi_input_settings(self.settings)
        return self.settings.enabled

    # --- settings dialog (begin/preview/commit/cancel, mirrors           --
    # --- PlaybackController's begin_mixer_edit/set_mixer_*/commit/cancel) --

    def available_devices(self) -> List[str]:
        return self._midi.list_ports()

    def begin_settings_edit(self) -> LiveMidiInputSettings:
        """Snapshots the current settings (for cancel_settings_edit to
        revert to) and returns a separate working copy for the dialog to
        display - the dialog never touches self.settings directly."""
        self._edit_snapshot = self.settings.copy()
        return self.settings.copy()

    def preview_instrument(self, gm_program: int) -> None:
        """Live preview while the dialog is open, only meaningful once a
        device is already connected - GM programs are 1-indexed everywhere
        else in this app (PartStructureInfo.gmidi_program)."""
        if self._midi.is_open:
            self.synth.set_program(LIVE_MIDI_INPUT_CHANNEL, gm_program - 1)

    def preview_volume(self, percent: int) -> None:
        if self._midi.is_open:
            self.synth.set_channel_volume(
                LIVE_MIDI_INPUT_CHANNEL, mixer_settings.volume_percent_to_cc(percent)
            )

    def preview_pan(self, percent: int) -> None:
        if self._midi.is_open:
            self.synth.set_channel_pan(
                LIVE_MIDI_INPUT_CHANNEL, mixer_settings.pan_percent_to_cc(percent)
            )

    def commit_settings_edit(self, new_settings: LiveMidiInputSettings) -> None:
        """OK: adopt the dialog's result. Reconnects only if the device or
        enabled state actually changed - a pure instrument/volume/pan edit
        was already live-previewed onto the existing connection and needs
        nothing further sent. Device selection itself is deliberately never
        live-previewed (see widgets/live_midi_input_dialog.py) - there is
        nothing to preview about a port choice until a note is played
        through it, and reconnecting is heavier than a CC tweak."""
        new_settings = new_settings.copy()
        device_changed = new_settings.device_name != self.settings.device_name
        enabled_changed = new_settings.enabled != self.settings.enabled
        self.settings = new_settings
        if enabled_changed or device_changed:
            if self.settings.enabled and self.settings.device_name:
                self._connect(self.settings.device_name)
            else:
                self._disconnect()
        elif self._midi.is_open:
            self._apply_instrument_and_levels()
        app_settings.set_live_midi_input_settings(self.settings)
        self._edit_snapshot = None

    def cancel_settings_edit(self) -> None:
        """Cancel: put the synth back exactly as it was before the dialog
        opened (instrument/volume/pan only - device/enabled were never
        live-previewed). self.settings is untouched throughout, since
        preview_* never wrote to it - only reverting the synth's CC state
        is needed."""
        if self._edit_snapshot is not None and self._midi.is_open:
            self.settings = self._edit_snapshot
            self._apply_instrument_and_levels()
        self._edit_snapshot = None

    # --- rtmidi callback thread -> Qt main thread --------------------------

    def _on_raw_message(self, status: int, pitch: int, velocity: int) -> None:
        """rtmidi's own thread. Does nothing but emit - see class docstring
        on why."""
        if status == NOTE_ON:
            self._raw_note_on.emit(pitch, velocity)
        else:
            self._raw_note_off.emit(pitch)

    def _handle_note_on(self, pitch: int, velocity: int) -> None:
        """Qt main thread only (see class docstring)."""
        self.synth.live_note_on(pitch, velocity)

    def _handle_note_off(self, pitch: int) -> None:
        """Qt main thread only (see class docstring)."""
        self.synth.live_note_off(pitch)

    # --- internal -----------------------------------------------------

    def _connect(self, device_name: str) -> bool:
        opened = self._midi.open(device_name)
        if opened:
            self._apply_instrument_and_levels()
        self.connection_changed.emit(opened)
        return opened

    def _disconnect(self) -> None:
        was_open = self._midi.is_open
        self._midi.close()
        self.synth.live_all_notes_off()
        if was_open:
            self.connection_changed.emit(False)

    def _apply_instrument_and_levels(self) -> None:
        self.synth.set_program(LIVE_MIDI_INPUT_CHANNEL, self.settings.gm_program - 1)
        self.synth.set_channel_volume(
            LIVE_MIDI_INPUT_CHANNEL, mixer_settings.volume_percent_to_cc(self.settings.volume_percent)
        )
        self.synth.set_channel_pan(
            LIVE_MIDI_INPUT_CHANNEL, mixer_settings.pan_percent_to_cc(self.settings.pan_percent)
        )
