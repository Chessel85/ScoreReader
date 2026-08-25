# audio/tuner_capture.py
"""Microphone capture + periodic pitch detection for Tools > Tuner
(widgets/tuner_dialog.py). Confirmed in-process compatible with FluidSynth
(no DLL collision, unlike vosk - see the tuner plan's Step 0 spike): a plain
non-Qt class wrapping sounddevice.InputStream, mirroring audio/midi_input.py's
MidiInputManager shape (set_callback/list_devices/open/close/is_open) so a
future test/prod swap is as easy as that module's own. Crossing to Qt's main
thread is the CALLER's job (controllers/tuner_controller.py), the same
"background thread -> QueuedConnection -> main thread" pattern established
there.

Unlike MidiInputManager's raw per-message forwarding, this module holds
real mutable state across two threads (a rolling audio buffer, written by
PortAudio's callback thread and read by a separate detection-cycle thread) -
so, unlike that module, a lock IS needed here to avoid tearing a numpy array
mid-read/mid-write.
"""
import threading
from typing import Callable, List, Optional

import numpy as np

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False

from audio.pitch_detector import PitchResult, detect_pitch

SAMPLE_RATE = 44100

# One detection cycle's worth of audio to analyse - long enough for a low
# string's fundamental to complete several periods (a double bass low B0,
# ~31Hz, needs roughly 100-200ms per cycle - see the tuner plan's forecast),
# short enough to stay reasonably responsive for the highest strings.
BUFFER_SECONDS = 0.25
BUFFER_FRAMES = int(SAMPLE_RATE * BUFFER_SECONDS)

# How often a detection cycle runs - independent of PortAudio's own callback
# block size. Chosen to sit comfortably above the low-string analysis window
# above; expected to need live tuning once audible, like the metronome/
# position-announcer cadence before it (see the tuner plan).
DETECT_INTERVAL_SECONDS = 0.2

# Default search band passed to detect_pitch - matches the reference-pitch
# offset range (models/tuner_instruments.py), so a mistuned string anywhere
# in that range is still inside the searched band.
DEFAULT_SEARCH_SEMITONES = 4.0


def list_input_devices() -> List[str]:
    """Fresh sd.query_devices() every call - never cached, mirrors
    audio/midi_input.py's list_input_ports(). Returns [] (never raises) if
    sounddevice isn't importable or enumeration itself fails, matching that
    module's "warn and no-op" handling for a missing optional resource."""
    if not SOUNDDEVICE_AVAILABLE:
        return []
    try:
        devices = sd.query_devices()
        return [d["name"] for d in devices if d["max_input_channels"] > 0]
    except Exception as e:
        print(f"[WARN] Failed to enumerate audio input devices: {e}")
        return []


# PitchResult|None, peak_level (0.0-1.0, the buffer's own peak absolute
# sample value at this detection cycle) - peak_level is reported
# independently of whether a pitch was confidently detected, so a caller can
# tell "no signal reaching the mic at all" apart from "signal present but no
# clear pitch yet" (reported live: with no target selected yet, the
# controller used to skip feedback entirely, which looked identical to the
# mic not working at all - see controllers/tuner_controller.py).
PitchResultCallback = Callable[[Optional[PitchResult], float], None]


class TunerCapture:
    """Owns at most one open sounddevice.InputStream. NOT a QObject - takes
    a plain Python callback, not a Signal (see module docstring). The
    callback fires on a background thread (a self-rescheduling
    threading.Timer chain - see _run_detection - not PortAudio's own audio
    callback thread directly, so a slow detection pass never blocks or
    drops audio callbacks); it is the caller's job to marshal onto whatever
    thread needs the result."""

    def __init__(self):
        self._stream = None
        self._device_name: Optional[str] = None
        self._expected_hz: float = 440.0
        self._search_semitones: float = DEFAULT_SEARCH_SEMITONES
        self._callback: Optional[PitchResultCallback] = None
        self._buffer = np.zeros(BUFFER_FRAMES, dtype=np.float64)
        self._buffer_lock = threading.Lock()
        self._detect_timer: Optional[threading.Timer] = None

    def set_callback(self, callback: Optional[PitchResultCallback]) -> None:
        """Must be called before open() - a detection cycle can fire the
        moment the stream opens, so a callback set afterward could miss an
        early result. Safe to call at any time otherwise."""
        self._callback = callback

    def set_target(self, expected_hz: float, search_semitones: float = DEFAULT_SEARCH_SEMITONES) -> None:
        """Updates the frequency band detect_pitch searches - e.g. when the
        user changes the selected string or reference-pitch offset while the
        dialog is already listening. Takes effect on the next detection
        cycle; no restart needed."""
        self._expected_hz = expected_hz
        self._search_semitones = search_semitones

    def list_devices(self) -> List[str]:
        """Instance wrapper around the module-level list_input_devices(), so
        a test can override per-instance (e.g. a null stand-in) without
        monkeypatching the module function - mirrors
        MidiInputManager.list_ports()."""
        return list_input_devices()

    def open(self, device_name: Optional[str]) -> bool:
        """device_name=None uses the system default input device.
        Re-enumerates fresh each call (a device can be hot-plugged and
        there's no Qt-native signal to invalidate a cache against, the same
        reasoning MidiInputManager.open already has). Returns False (never
        raises) if sounddevice is unavailable or the device can't be
        opened - degrades silently, matching MidiInputManager.open."""
        if not SOUNDDEVICE_AVAILABLE:
            print("[WARN] sounddevice not available; tuner disabled.")
            return False
        self.close()
        try:
            kwargs = {}
            if device_name is not None:
                devices = sd.query_devices()
                matches = [
                    i for i, d in enumerate(devices)
                    if d["name"] == device_name and d["max_input_channels"] > 0
                ]
                if not matches:
                    return False
                kwargs["device"] = matches[0]
            with self._buffer_lock:
                self._buffer[:] = 0.0
            stream = sd.InputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                callback=self._on_audio_block, **kwargs,
            )
            stream.start()
        except Exception as e:
            print(f"[WARN] Failed to open audio input device '{device_name}': {e}")
            return False
        self._stream = stream
        self._device_name = device_name
        self._schedule_detection()
        return True

    def close(self) -> None:
        if self._detect_timer is not None:
            self._detect_timer.cancel()
            self._detect_timer = None
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                print(f"[WARN] Failed to close audio input stream: {e}")
            self._stream = None
        self._device_name = None

    @property
    def is_open(self) -> bool:
        return self._stream is not None

    @property
    def device_name(self) -> Optional[str]:
        return self._device_name

    def _on_audio_block(self, indata, frames, time_info, status) -> None:
        """PortAudio's own callback thread. Only maintains the rolling
        buffer - the detection cycle itself runs on a separate timer thread
        (below), so a slow YIN pass here would otherwise block/drop real
        audio callbacks."""
        mono = np.asarray(indata[:, 0], dtype=np.float64)
        with self._buffer_lock:
            n = len(mono)
            if n >= len(self._buffer):
                self._buffer[:] = mono[-len(self._buffer):]
            else:
                self._buffer[:-n] = self._buffer[n:]
                self._buffer[-n:] = mono

    def _schedule_detection(self) -> None:
        if self._stream is None:
            return
        self._detect_timer = threading.Timer(DETECT_INTERVAL_SECONDS, self._run_detection)
        self._detect_timer.daemon = True
        self._detect_timer.start()

    def _run_detection(self) -> None:
        if self._stream is None:
            return
        with self._buffer_lock:
            snapshot = self._buffer.copy()
        peak_level = float(np.max(np.abs(snapshot))) if len(snapshot) else 0.0
        result = detect_pitch(snapshot, SAMPLE_RATE, self._expected_hz, self._search_semitones)
        if self._callback is not None:
            self._callback(result, peak_level)
        self._schedule_detection()
