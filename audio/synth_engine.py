# audio/synth_engine.py
import os
import sys
import ctypes
from typing import List, Optional
from PySide6.QtCore import QTimer

# --- DLL RESOLUTION FROM SUBFOLDER ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN_DIR = os.path.join(PROJECT_ROOT, "bin")

if os.path.exists(BIN_DIR):
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(BIN_DIR)

    os.environ["PATH"] = BIN_DIR + os.pathsep + os.environ.get("PATH", "")

    deps = [
        "libglib-2.0-0.dll",
        "libgobject-2.0-0.dll",
        "libgthread-2.0-0.dll",
        "libfluidsynth-3.dll",
        "libfluidsynth.dll"
    ]
    for dll in deps:
        dll_path = os.path.join(BIN_DIR, dll)
        if os.path.exists(dll_path):
            try:
                ctypes.CDLL(dll_path)
            except Exception:
                pass

try:
    import fluidsynth
    FLUIDSYNTH_AVAILABLE = True
except ImportError:
    FLUIDSYNTH_AVAILABLE = False


class SynthEngine:
    """In-process FluidSynth engine for low-latency WASAPI audio playback."""

    def __init__(self, soundfont_path: Optional[str] = None):
        self._fs = None
        self._sfid = None
        self._active_midi_notes: List[int] = []
        self._active_channel: int = 0

        # Off timer for scheduling note stops
        self._off_timer = QTimer()
        self._off_timer.setSingleShot(True)
        self._off_timer.timeout.connect(self.stop_all_notes)

        if not FLUIDSYNTH_AVAILABLE:
            print("[WARN] pyfluidsynth or DLLs missing. Sound engine disabled.")
            return

        self._init_engine(soundfont_path)

    def _init_engine(self, soundfont_path: Optional[str]):
        try:
            self._fs = fluidsynth.Synth(gain=0.7)

            # Optimise for low latency using WASAPI
            self._fs.setting("synth.sample-rate", 48000.0)
            self._fs.setting("audio.period-size", 128)
            self._fs.setting("audio.periods", 2)
            self._fs.start(driver="wasapi")

            # Resolve SoundFont path
            if not soundfont_path:
                soundfont_path = os.path.join(PROJECT_ROOT, "soundfonts", "FluidR3_GM.sf2")

            if os.path.exists(soundfont_path):
                self._sfid = self._fs.sfload(soundfont_path)
                self._fs.program_select(0, self._sfid, 0, 0)
            else:
                print(f"[WARN] SoundFont not found: {soundfont_path}")

        except Exception as e:
            print(f"[ERROR] Failed to initialize FluidSynth: {e}")
            self._fs = None

    def set_program(self, channel: int, program: int):
        if self._fs is None or self._sfid is None:
            return
        self._fs.program_change(channel & 0x0F, max(0, min(127, program)))

    def stop_all_notes(self):
        if self._fs is None:
            return
        
        self._off_timer.stop()

        for note in self._active_midi_notes:
            self._fs.noteoff(self._active_channel, note)
        self._active_midi_notes.clear()

    def play_notes(
        self,
        midi_notes: List[int],
        duration_ms: int = 250,
        channel: int = 0,
        program: Optional[int] = None
    ):
        if self._fs is None or not midi_notes:
            return

        self.stop_all_notes()
        self._active_channel = channel & 0x0F

        if program is not None:
            self.set_program(self._active_channel, program)

        self._active_midi_notes = list(midi_notes)
        for note in self._active_midi_notes:
            self._fs.noteon(self._active_channel, note, 90)

        # Schedule Note Off after duration_ms
        if duration_ms > 0:
            self._off_timer.start(int(duration_ms))

    def close(self):
        if self._fs:
            self.stop_all_notes()
            self._fs.delete()
            self._fs = None