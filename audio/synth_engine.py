# audio/synth_engine.py
import os
import ctypes
from typing import List, Optional, Tuple
from PySide6.QtCore import QTimer

from audio.metronome import METRONOME_CHANNEL
from audio.performance_cue import PERFORMANCE_CUE_CHANNEL
from audio.position_announcer import POSITION_ANNOUNCER_CHANNEL

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
        self._click_sfid: Optional[int] = None
        self._active_notes: List[Tuple[int, int]] = []  # (channel, note) pairs

        # One QTimer per sounding group (Ref 9 AC2/Ref 13 AC2: each part
        # rings for its own notated duration, not the shortest duration of
        # any part sounding at the same instant - see play_chord). Tracked
        # here so stop_all_notes()/a retriggering play_chord() can cancel
        # every pending one, not just the most recent.
        self._group_off_timers: List[QTimer] = []

        # E8: the metronome click gets its own tiny parallel state, entirely
        # separate from _active_notes/_group_off_timers above - a click must
        # not cut off a note sounding at the same beat (play_chord's
        # stop_all_notes() would do exactly that if the click went through
        # the same path). No timer here (see play_click's own comment for
        # why not) - just enough bookkeeping to silence an in-progress click
        # early if something needs to interrupt it (stop_all_notes, or a
        # new click retriggering before the old one has finished).
        self._active_click: Optional[Tuple[int, int]] = None  # (channel, note)

        # Ref 28: the position announcer gets its own parallel slot, entirely
        # separate from _active_click above despite sharing the same click
        # soundfont/sfid - it plays on its own dedicated channel
        # (audio/position_announcer.py's POSITION_ANNOUNCER_CHANNEL)
        # specifically so a click and a spoken word landing on the same beat
        # (AC2: both can be on at once) don't fight over one shared
        # active-note slot the way they would on a single channel - see
        # that module's own comment for why a shared channel can't work
        # here (FluidSynth releases by channel+key, not by preset).
        self._active_announcement: Optional[Tuple[int, int]] = None  # (channel, note)

        # Ref 29: the Performance region's change cue gets its own parallel
        # slot too, same reasoning as _active_click/_active_announcement
        # above - its own dedicated channel (PERFORMANCE_CUE_CHANNEL) so it
        # can't collide with either of them or with a note ringing at the
        # same instant.
        self._active_performance_cue: Optional[Tuple[int, int]] = None  # (channel, note)

        if not FLUIDSYNTH_AVAILABLE:
            print("[WARN] pyfluidsynth or DLLs missing. Sound engine disabled.")
            return

        self._init_engine(soundfont_path)

    def _init_engine(self, soundfont_path: Optional[str]):
        try:
            # samplerate MUST be passed to the constructor, not set
            # afterward: pyfluidsynth's Synth.__init__ calls
            # new_fluid_synth(self.settings) - the actual DSP engine
            # creation - using whatever synth.sample-rate is in the
            # settings object AT THAT MOMENT (default 44100, since it's
            # a constructor kwarg with that default). A later
            # self._fs.setting("synth.sample-rate", ...) call only updates
            # the stored settings value; it does not reinitialize the
            # already-created engine. Reported bug, live-tested and
            # confirmed by direct measurement: with the old code (rate set
            # only via .setting() after construction, as it used to be
            # here), audio was actually generated at 44100 Hz while WASAPI
            # opened the output stream at 48000 Hz (matching the real
            # device rate) - a 48000/44100 speed-up, audible as everything
            # playing about a semitone sharp (and, less obviously without
            # A/B comparison, slightly fast) - not a soundfont, MIDI
            # number, or audio-device problem.
            self._fs = fluidsynth.Synth(gain=0.7, samplerate=48000.0)

            # Optimise for low latency using WASAPI
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

            self._load_click_soundfont()

        except Exception as e:
            print(f"[ERROR] Failed to initialize FluidSynth: {e}")
            self._fs = None

    def _load_click_soundfont(self):
        """E8/Ref 14, tasks.txt E11/D-14/E12: a second, small,
        project-authored soundfont (tools/wav_to_sf2.py) for the click
        metronome and the Ref 28 position announcer - loaded alongside the
        main GM soundfont, not instead of it, on its own sfid so
        play_click/play_word can select it explicitly via program_select
        without disturbing whatever's program_select'd on any other
        channel. Missing/failing to load is non-fatal - matches
        FluidR3_GM's own "warn and become a no-op" handling above - since a
        fresh checkout that hasn't run the tool yet should still run, just
        without a click/announcer sound.

        No per-note duration lookup needed here (there used to be one, read
        from a sidecar .sf2.json) - see play_click's own comment for why a
        one-shot sample doesn't need its duration known in code at all.

        Ref 28 (user-requested): pans the click and the position announcer
        to opposite sides so they're easier to tell apart from the music
        and from each other - the announcer full left, the click full
        right. Set once here rather than per-call in play_click/play_word,
        since each has a permanently dedicated channel (MusicData.
        RESERVED_CHANNELS keeps real instrument parts off both) - a MIDI
        pan (CC10) setting persists on a channel until changed, so there's
        nothing to re-apply on every note. Verified against real
        FluidSynth (fluidsynth.Synth.get_samples(), no audio device
        needed): CC10=0 produced silence on the right channel, CC10=127
        silence on the left, confirming real hard-left/hard-right
        separation rather than a partial/no-op pan."""
        click_sf_path = os.path.join(PROJECT_ROOT, "soundfonts", "recall_score_sounds.sf2")
        if not os.path.exists(click_sf_path):
            print(f"[WARN] Click/announcer SoundFont not found: {click_sf_path}")
            return
        self._click_sfid = self._fs.sfload(click_sf_path)

        PAN_FULL_LEFT = 0
        PAN_FULL_RIGHT = 127
        PAN_CENTER = 64
        self._fs.cc(POSITION_ANNOUNCER_CHANNEL, 10, PAN_FULL_LEFT)
        self._fs.cc(METRONOME_CHANNEL, 10, PAN_FULL_RIGHT)
        # Ref 29: center pan - unlike the click/announcer pair, this cue has
        # no directional meaning to preserve, it just needs its own channel
        # (see PERFORMANCE_CUE_CHANNEL's own comment).
        self._fs.cc(PERFORMANCE_CUE_CHANNEL, 10, PAN_CENTER)

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
        self._stop_announcement()
        self._stop_performance_cue()

    def _stop_click(self):
        """Silences a still-ringing metronome click, if any (E8). Separate
        from the main note-off path above - see _active_click's own comment
        - but folded into stop_all_notes() too, so pause/stop (Ref 10 AC3/
        AC5) leave nothing orphaned. Also called from play_click() itself
        before a new click, so a fast run of clicks cuts the previous one
        short rather than overlapping."""
        if self._fs is None or self._active_click is None:
            return
        channel, note = self._active_click
        self._fs.noteoff(channel, note)
        self._active_click = None

    def _stop_announcement(self):
        """Silences a still-ringing position-announcer word, if any (Ref
        28) - the announcement counterpart of _stop_click above, on its own
        channel/active-note slot so it can't cancel (or be cancelled by) a
        click sounding at the same instant."""
        if self._fs is None or self._active_announcement is None:
            return
        channel, note = self._active_announcement
        self._fs.noteoff(channel, note)
        self._active_announcement = None

    def _stop_performance_cue(self):
        """Silences a still-ringing performance-region cue, if any (Ref 29)
        - the cue counterpart of _stop_click/_stop_announcement above, on
        its own channel/active-note slot for the same reason."""
        if self._fs is None or self._active_performance_cue is None:
            return
        channel, note = self._active_performance_cue
        self._fs.noteoff(channel, note)
        self._active_performance_cue = None

    def play_performance_cue(self, channel: int, bank: int, program: int, pitch: int, velocity: int):
        """Ref 29: sounds the "check Region 5" cue - same shape and
        one-shot-sample reasoning as play_click/play_word above (see
        play_click's own comment for why no note-off scheduling is needed).
        Its own channel/active-note bookkeeping (_active_performance_cue) so
        it can't collide with a click, a spoken word, or a note ringing at
        the same instant."""
        if self._fs is None or self._click_sfid is None:
            return

        self._stop_performance_cue()

        ch = channel & 0x0F
        self._fs.program_select(ch, self._click_sfid, bank, program)
        self._fs.noteon(ch, pitch, velocity)
        self._active_performance_cue = (ch, pitch)

    def play_click(self, channel: int, bank: int, program: int, pitch: int, velocity: int):
        """E8/Ref 14: sounds a metronome click on its own dedicated channel,
        independent of the melodic note pipeline above - does not call
        stop_all_notes() (so it doesn't cut off notes sounding at the same
        beat) and is not touched by a later play_chord() call. Which SAMPLE
        plays (via program_select's explicit bank on the dedicated click
        soundfont, self._click_sfid - see _load_click_soundfont) now
        distinguishes the accented beat, not velocity - tasks.txt E11/D-14's
        Claves attempt used one fixed percussion voice with velocity as the
        only accent signal; this plays two different recorded sounds
        instead.

        No explicit note-off scheduling (there used to be one, timed from a
        per-sample duration read from a sidecar .sf2.json): each click zone
        in soundfonts/recall_score_sounds.sf2 is a one-shot, non-looping
        sample (SampleModes=0, tools/wav_to_sf2.py), and FluidSynth
        deactivates a voice on its own once such a sample's data is
        exhausted, regardless of whether a note-off was ever sent - holding
        the note "on" and simply never releasing it early is enough to let
        it play to its natural end. Verified against real FluidSynth
        (fluidsynth.Synth.get_samples(), no audio device needed): rendering
        with no note-off at all reproduced the sample's full natural
        length with no hang and no glitch; rendering with an early
        note-off reproduced the original problem (abrupt cutoff via the
        soundfont's default near-instant release envelope) - confirming
        both that letting a one-shot finish untouched is safe and why an
        early note-off must still be avoided. _stop_click() (called just
        below, and from stop_all_notes()) remains the deliberate-interrupt
        path - a fast run of clicks or an explicit stop still cuts a
        still-ringing one short, which is the wanted behaviour there."""
        if self._fs is None or self._click_sfid is None:
            return

        self._stop_click()

        ch = channel & 0x0F
        self._fs.program_select(ch, self._click_sfid, bank, program)
        self._fs.noteon(ch, pitch, velocity)
        self._active_click = (ch, pitch)

    def play_word(self, channel: int, bank: int, program: int, pitch: int, velocity: int):
        """Ref 28: sounds a position-announcer spoken-word sample - the
        word counterpart of play_click above, same soundfont (self.
        _click_sfid loads every preset in soundfonts/recall_score_sounds.sf2,
        talking_metronome_default included, not just click_default) and the
        same "let a one-shot finish on its own, never schedule an early
        note-off" reasoning - see play_click's own comment. Its own
        channel/active-note bookkeeping (_active_announcement) so a click
        and a word landing on the same beat (Ref 28 AC2) sound together
        instead of one cancelling the other - see
        audio/position_announcer.py's POSITION_ANNOUNCER_CHANNEL comment
        for why they can't share a channel."""
        if self._fs is None or self._click_sfid is None:
            return

        self._stop_announcement()

        ch = channel & 0x0F
        self._fs.program_select(ch, self._click_sfid, bank, program)
        self._fs.noteon(ch, pitch, velocity)
        self._active_announcement = (ch, pitch)

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