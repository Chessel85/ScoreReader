# audio/midi_input.py
"""Live MIDI input: a standalone python-rtmidi wrapper, NOT layered on
FluidSynth's own MIDI driver.

audio/synth_engine.py's _init_engine deliberately never calls
fluidsynth.Synth.start()/new_fluid_midi_driver - that auto-created driver
both caused the original bug this feature grew out of (a connected USB
controller's raw input collided on (channel, key) with the app's own
scripted note-offs, silencing notes the user was still physically holding -
see _init_engine's own history of that) AND has a documented deadlock when
torn down via fluidsynth.delete_fluid_midi_driver(). This module never
touches either of those calls: it opens its own independent RtMidi input
session via python-rtmidi and hands raw (status, pitch, velocity) tuples to
a caller-supplied callback, which is free to feed them into the SAME
fluidsynth.Synth instance the audio driver is already rendering, via plain
noteon/noteoff calls - exactly the "direct API calls into one shared engine"
approach every other playback path in this app already uses (SynthEngine.
play_chord etc.), just triggered by hardware input instead of a QTimer.

Deliberately Qt-free (no PySide6 import anywhere in this file), the same
reason audio/metronome.py / audio/position_announcer.py / audio/
performance_cue.py are bare stdlib modules despite living in audio/:
models/music_data.py imports LIVE_MIDI_INPUT_CHANNEL from here to fold it
into MusicData.RESERVED_CHANNELS, and models/ must stay importable with zero
Qt in the chain (test_models_package_does_not_import_qt). Crossing to Qt's
main thread from rtmidi's own callback thread is the CALLER's job -
controllers/live_midi_input_controller.py is where that happens, via a
Signal connected with Qt.ConnectionType.QueuedConnection.

Phase 1 scope: only note-on/note-off are recognised. Sustain pedal (CC64),
pitch bend, and aftertouch are deliberately ignored, not a bug to later
"discover" - a future phase can add them if wanted.
"""
from typing import Callable, List, Optional

try:
    import rtmidi
    RTMIDI_AVAILABLE = True
except ImportError:
    RTMIDI_AVAILABLE = False

# Reserved in MusicData.RESERVED_CHANNELS alongside the click/announcer/cue
# channels, so no real score part ever lands here (models/music_data.py
# mirrors this constant the same way it already mirrors METRONOME_CLICK_
# CHANNEL/POSITION_ANNOUNCER_CHANNEL/PERFORMANCE_CUE_CHANNEL from their own
# audio/ modules).
LIVE_MIDI_INPUT_CHANNEL = 6

# Raw MIDI status-byte nibbles (channel is the low nibble, ignored here -
# python-rtmidi's callback already delivers only the channel the port sends
# on, and this app only ever opens one port at a time). Public: callers
# (controllers/live_midi_input_controller.py) compare against these rather
# than duplicating the literals.
NOTE_OFF = 0x80
NOTE_ON = 0x90

# (status, pitch, velocity) - the normalised, channel-stripped shape this
# module hands to its callback.
MessageCallback = Callable[[int, int, int], None]


def list_input_ports() -> List[str]:
    """Fresh rtmidi.MidiIn().get_ports() every call - never cached, since a
    device can be hot-plugged and there is no Qt-native signal to invalidate
    a cache against. Returns [] (never raises) if rtmidi isn't importable or
    enumeration itself fails, matching the rest of this app's "warn and
    no-op" handling for a missing optional resource (e.g. SynthEngine's
    missing-soundfont handling)."""
    if not RTMIDI_AVAILABLE:
        return []
    try:
        midi_in = rtmidi.MidiIn()
        try:
            return list(midi_in.get_ports())
        finally:
            del midi_in
    except Exception as e:
        print(f"[WARN] Failed to enumerate MIDI input ports: {e}")
        return []


class MidiInputManager:
    """Owns at most one open rtmidi.MidiIn port. NOT a QObject - takes a
    plain Python callback, not a Signal (see module docstring). The callback
    fires on rtmidi's OWN internal thread, not the caller's - it is the
    caller's job to marshal onto whatever thread needs the result."""

    def __init__(self):
        self._midi_in = None
        self._device_name: Optional[str] = None
        self._callback: Optional[MessageCallback] = None

    def set_callback(self, callback: Optional[MessageCallback]) -> None:
        """Must be called before open() - rtmidi delivers input starting the
        moment the port opens, so a callback set afterward could miss an
        immediate message. Safe to call at any time otherwise; only takes
        effect on the next open()."""
        self._callback = callback

    def list_ports(self) -> List[str]:
        """Instance wrapper around the module-level list_input_ports(), so
        a test can override per-instance (e.g. NullMidiInputManager) without
        monkeypatching the module function."""
        return list_input_ports()

    def open(self, device_name: str) -> bool:
        """Opens device_name if it's currently enumerated, returns False
        (never raises) otherwise - the "degrade silently" behaviour an
        auto-connect needs when the last-used device isn't plugged in this
        session. Re-enumerates fresh each call, since a cached port list
        could be stale by the time this runs."""
        if not RTMIDI_AVAILABLE:
            print("[WARN] python-rtmidi not available; live MIDI input disabled.")
            return False
        self.close()
        ports = list_input_ports()
        if device_name not in ports:
            return False
        try:
            midi_in = rtmidi.MidiIn()
            midi_in.ignore_types(sysex=True, timing=True, active_sense=True)
            midi_in.open_port(ports.index(device_name))
            midi_in.set_callback(self._on_raw_message)
        except Exception as e:
            print(f"[WARN] Failed to open MIDI input device '{device_name}': {e}")
            return False
        self._midi_in = midi_in
        self._device_name = device_name
        return True

    def close(self) -> None:
        if self._midi_in is not None:
            try:
                self._midi_in.cancel_callback()
                self._midi_in.close_port()
            except Exception as e:
                print(f"[WARN] Failed to close MIDI input device: {e}")
            self._midi_in = None
        self._device_name = None

    @property
    def is_open(self) -> bool:
        return self._midi_in is not None

    @property
    def device_name(self) -> Optional[str]:
        return self._device_name

    def _on_raw_message(self, event, data=None) -> None:
        """rtmidi's own callback thread, NOT the caller's. Fires with
        event = ([status, data1, data2, ...], delta_time). Normalises a
        note-on with velocity 0 to a note-off (a common MIDI convention for
        running-status note-off), and drops anything that isn't a note-on/
        note-off (CC/pitch-bend/aftertouch/sysex etc - phase 1 scope, see
        module docstring)."""
        if self._callback is None:
            return
        message = event[0] if event else None
        if not message or len(message) < 3:
            return
        status = message[0] & 0xF0
        pitch, velocity = message[1], message[2]
        if status == NOTE_ON and velocity > 0:
            self._callback(NOTE_ON, pitch, velocity)
        elif status == NOTE_ON or status == NOTE_OFF:
            self._callback(NOTE_OFF, pitch, 0)
