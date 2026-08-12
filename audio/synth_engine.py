# audio/synth_engine.py
import os
import ctypes
from typing import List, Optional, Tuple
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
        self._active_notes: List[Tuple[int, int]] = []  # (channel, note) pairs

        # One QTimer per sounding group (Ref 9 AC2/Ref 13 AC2: each part
        # rings for its own notated duration, not the shortest duration of
        # any part sounding at the same instant - see play_chord). Tracked
        # here so stop_all_notes()/a retriggering play_chord() can cancel
        # every pending one, not just the most recent.
        self._group_off_timers: List[QTimer] = []

        # E8: the metronome click gets its own tiny parallel state, entirely
        # separate from _active_notes/_group_off_timers above. A click must not cut
        # off a note sounding at the same beat (play_chord's stop_all_notes()
        # would do exactly that if the click went through the same path),
        # and it rings for its own short fixed duration independent of
        # whatever duration_ms a note at that beat is using.
        self._active_click: Optional[Tuple[int, int]] = None  # (channel, note)
        self._click_off_timer = QTimer()
        self._click_off_timer.setSingleShot(True)
        self._click_off_timer.timeout.connect(self._stop_click)

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

        for timer in self._group_off_timers:
            timer.stop()
        self._group_off_timers.clear()

        for channel, note in self._active_notes:
            self._fs.noteoff(channel, note)
        self._active_notes.clear()

        self._stop_click()

    def _stop_click(self):
        """Silences a still-ringing metronome click, if any (E8). Separate
        from the main note-off path above - see _active_click's own comment
        - but folded into stop_all_notes() too, so pause/stop (Ref 10 AC3/
        AC5) leave nothing orphaned."""
        if self._fs is None or self._active_click is None:
            return
        self._click_off_timer.stop()
        channel, note = self._active_click
        self._fs.noteoff(channel, note)
        self._active_click = None

    def play_click(self, channel: int, program: int, pitch: int, velocity: int, duration_ms: int):
        """E8/Ref 14: sounds a metronome click on its own dedicated channel,
        independent of the melodic note pipeline above - does not call
        stop_all_notes() (so it doesn't cut off notes sounding at the same
        beat) and is not touched by a later play_chord() call (so a click
        rings for its own short duration_ms regardless of the next note's
        own timing). velocity (not pitch) distinguishes the accented beat -
        the click is a GM percussion voice (Claves), which has a fixed
        pitch per note number rather than a tunable one."""
        if self._fs is None:
            return

        self._stop_click()

        ch = channel & 0x0F
        self.set_program(ch, program)
        self._fs.noteon(ch, pitch, velocity)
        self._active_click = (ch, pitch)

        if duration_ms > 0:
            self._click_off_timer.start(int(duration_ms))

    def play_notes(
        self,
        midi_notes: List[int],
        duration_ms: int = 250,
        channel: int = 0,
        program: Optional[int] = None
    ):
        """Play one group of notes on a single channel/program.

        Kept for callers that only ever need one instrument at a time; see
        play_chord for multi-part simultaneous playback (Ref 8, D-5).
        """
        self.play_chord([(channel, program, midi_notes)], duration_ms)

    def play_chord(
        self,
        events: List[Tuple],
        duration_ms: int = 250,
        retrigger: bool = True,
    ):
        """Play several (channel, program, midi_notes[, duration_ms]) groups
        together.

        Each part gets its own channel and GM program, so a slice with
        notes from two parts sounds both instruments at once instead of
        one group cutting the other off (Ref 8, Ref 9 AC2, D-5). Each
        group's own trailing duration_ms (when present - MusicData supplies
        it; play_notes()'s single-group callers don't) governs its own
        note-off timer independently, so one part isn't clamped to another
        part's shorter note sounding at the same instant (Ref 9 AC2, Ref 13
        AC2 - reported bug: Pachelbel's Canon cello minims cut short to
        match faster upper parts). Falls back to the outer duration_ms for
        any group that omits its own.

        retrigger=True (the default) silences everything currently sounding
        first - correct for discrete audition (Ref 8 AC2's "moving through
        the timeline stops all notes currently sounding before playing new
        notes", used by Region 3 navigation and chord audition). The
        Sequencer (E4/Ref 10) passes retrigger=False for its natural
        step-to-step advance during real playback: a new part's note
        starting (e.g. Violin I entering on beat 2 while Violin II/Viola/
        Cello are mid-minim from beat 1) must NOT cut off other parts'
        still-ringing, unrelated notes - reported bug, live-tested, second
        occurrence of the same underlying "one group's timing clobbers
        another's" class of bug this method already had for duration.
        Sequencer.play_from()/resume() still call stop_all_notes() directly
        first, so an explicit reposition (not a natural advance) does clear
        the deck.
        """
        if self._fs is None:
            return

        if retrigger:
            self.stop_all_notes()

        for event in events:
            channel, program, midi_notes = event[0], event[1], event[2]
            group_duration_ms = event[3] if len(event) > 3 else duration_ms
            if not midi_notes:
                continue

            ch = channel & 0x0F
            if program is not None:
                self.set_program(ch, program)

            group_notes: List[Tuple[int, int]] = []
            for note in midi_notes:
                self._fs.noteon(ch, note, 90)
                group_notes.append((ch, note))
            self._active_notes.extend(group_notes)

            if group_notes and group_duration_ms > 0:
                self._schedule_group_off(group_notes, group_duration_ms)

    def _schedule_group_off(self, group_notes: List[Tuple[int, int]], duration_ms: int):
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._stop_group(group_notes, timer))
        self._group_off_timers.append(timer)
        timer.start(int(duration_ms))

    def _stop_group(self, group_notes: List[Tuple[int, int]], timer: QTimer):
        if self._fs is not None:
            for ch, note in group_notes:
                if (ch, note) in self._active_notes:
                    self._fs.noteoff(ch, note)
                    self._active_notes.remove((ch, note))
        if timer in self._group_off_timers:
            self._group_off_timers.remove(timer)

    def close(self):
        if self._fs:
            self.stop_all_notes()
            self._fs.delete()
            self._fs = None