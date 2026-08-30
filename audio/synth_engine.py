# audio/synth_engine.py
import os
import ctypes
from typing import List, Optional, Tuple
from PySide6.QtCore import QTimer

from audio.metronome import METRONOME_CHANNEL
from audio.midi_input import LIVE_MIDI_INPUT_CHANNEL
from audio.performance_cue import PERFORMANCE_CUE_CHANNEL
from audio.position_announcer import POSITION_ANNOUNCER_CHANNEL
from audio.voice_confirmation_cue import VOICE_CONTROL_CUE_CHANNEL
from audio.grace_note_schedule import effective_grace_duration_ms
from audio.strum_schedule import build_strum_schedule

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

        # One QTimer per sounding group, so each part rings for its own
        # notated duration rather than the shortest one sounding at that
        # instant (Ref 9 AC2/Ref 13 AC2, see play_chord). Tracked so
        # stop_all_notes()/a retriggering play_chord() can cancel every
        # pending one, not just the most recent.
        self._group_off_timers: List[QTimer] = []

        # A UG import's strummed-bar playback (play_strummed_bar) schedules
        # a whole bar's worth of future note-ONs up front, one QTimer each -
        # unlike _group_off_timers above (which schedule a note-OFF for
        # something already sounding), these are still-pending attacks that
        # haven't happened yet. stop_all_notes() must cancel these too, or a
        # previous audition's still-pending future strokes would fire
        # midway through a new one - the same class of bug
        # _group_off_timers already exists to prevent, one level earlier.
        self._pending_strum_timers: List[QTimer] = []

        # play_chord_with_grace's delayed main-chord attack, scheduled to
        # fire once the grace note's own brief pre-note has had its moment -
        # a still-pending future note-on, same "stop_all_notes() must cancel
        # this or a previous audition's delayed chord fires midway through a
        # new one" reasoning as _pending_strum_timers above.
        self._pending_grace_timers: List[QTimer] = []

        # The click, the spoken position word and the performance cue each
        # get their own slot, separate from _active_notes and from each
        # other. Two reasons, both load-bearing:
        #  - they must not go through play_chord's path, whose retrigger
        #    stop_all_notes() would cut off notes sounding on the same beat;
        #  - each owns a dedicated channel, because FluidSynth's
        #    noteoff(channel, key) releases every voice matching that pair
        #    regardless of preset, and these presets share note numbers (see
        #    audio/position_announcer.py).
        # No timers: a one-shot sample retires itself (see play_click).
        # These slots exist only to interrupt one early on purpose.
        self._active_click: Optional[Tuple[int, int]] = None  # (channel, note)
        self._active_announcement: Optional[Tuple[int, int]] = None
        self._active_performance_cue: Optional[Tuple[int, int]] = None
        self._active_voice_confirmation_cue: Optional[Tuple[int, int]] = None

        # Live MIDI input (audio/midi_input.py, controllers/live_midi_input_
        # controller.py): pitches currently held down on a connected
        # keyboard, all on the one reserved LIVE_MIDI_INPUT_CHANNEL. Just
        # pitches, not (channel, note) pairs, since there is only one
        # channel. Deliberately NOT part of _active_notes and NOT touched by
        # stop_all_notes() below - every score navigation/audition calls
        # stop_all_notes() far too often for a purpose (silence the score's
        # OWN sounding notes before the next one) that has nothing to do
        # with a note the user is physically holding down. A live note's
        # only note-off is the matching live_note_off() call (a real key
        # release) or the explicit live_all_notes_off() panic/teardown path.
        self._live_input_active_notes: set = set()

        if not FLUIDSYNTH_AVAILABLE:
            print("[WARN] pyfluidsynth or DLLs missing. Sound engine disabled.")
            return

        self._init_engine(soundfont_path)

    def _init_engine(self, soundfont_path: Optional[str]):
        try:
            # samplerate MUST be a constructor argument, never set
            # afterwards. Synth.__init__ calls new_fluid_synth(self.settings)
            # - the actual DSP engine creation - using whatever
            # synth.sample-rate holds AT THAT MOMENT (default 44100). A later
            # .setting("synth.sample-rate", ...) updates only the stored
            # value and does not reinitialise the existing engine, so audio
            # renders at 44100 while WASAPI opens the stream at 48000: a
            # 48000/44100 speed-up, heard as everything playing about a
            # semitone sharp. Confirmed by measuring rendered frequency.
            self._fs = fluidsynth.Synth(gain=0.7, samplerate=48000.0)

            # Optimise for low latency using WASAPI
            self._fs.setting("audio.period-size", 128)
            self._fs.setting("audio.periods", 2)

            # Deliberately NOT self._fs.start(driver="wasapi"): pyfluidsynth's
            # Synth.start() unconditionally also creates a native MIDI router
            # AND a MIDI input driver listening on the system's default MIDI
            # input device (whatever "midi.driver" resolves to - "winmidi" on
            # Windows), feeding its raw note-on/note-off straight into THIS
            # SAME synth. This app has no feature that reads external MIDI
            # input - the sequencer and every audition path only ever call
            # noteon/noteoff themselves - so nothing was ever meant to listen
            # there.
            #
            # Reported: with a USB MIDI controller connected (a Native
            # Instruments A49), notes played on it while Preview was running
            # went silent whenever they matched a pitch Preview was also
            # sounding, fixed by transposing an octave away. Root cause: the
            # controller's raw MIDI landed on this same engine on whatever
            # channel it transmits (typically channel 1), which coincides
            # with the channel a part is assigned - and FluidSynth's
            # noteoff(channel, key) releases EVERY voice matching that pair
            # regardless of source (the identical gotcha documented in
            # audio/position_announcer.py for the click/announcer channels).
            # A note played live and a Preview note landing on the same
            # (channel, key) meant Preview's own note-off silenced the still-
            # held live note too.
            #
            # FIRST FIX ATTEMPT, REVERTED: creating it via start() and then
            # immediately calling fluidsynth.delete_fluid_midi_driver()
            # deadlocked the whole app at startup on this machine (confirmed
            # with a standalone repro - new_fluid_midi_driver() itself
            # returns fine, but tearing it down never returns, presumably
            # the driver thread never acknowledging shutdown). So the driver
            # is never created at all instead: this replicates only the
            # audio-half of Synth.start() by calling new_fluid_audio_driver
            # directly (the same call start() makes), and simply never calls
            # new_fluid_midi_router/new_fluid_midi_driver. self._fs.router
            # and .midi_driver stay at Synth.__init__'s own None default, so
            # Synth.delete()'s teardown (`if self.midi_driver: ...`) is a
            # harmless no-op on close - nothing to hang on there either.
            driver = "wasapi"
            device = self._fs.get_setting(f"audio.{driver}.device")
            self._fs.setting("audio.driver", driver)
            self._fs.setting(f"audio.{driver}.device", device)
            self._fs.audio_driver = fluidsynth.new_fluid_audio_driver(self._fs.settings, self._fs.synth)

            # Resolve SoundFont path
            # TEST SWITCH (user-requested, wishlist #4 pan investigation):
            # temporarily pointed at Airfont_380_final.sf2 instead of
            # FluidR3_GM.sf2, to compare whether its instrument patches use
            # the same baked-in dual hard-panned-zone stereo-width trick
            # that defeats the Mixer dialog's channel pan on FluidR3_GM (see
            # audio/synth_engine.py git history / the mixer-dialog pan
            # investigation for the confirmed root cause). Revert to
            # FluidR3_GM.sf2 here if this doesn't turn out better.
            if not soundfont_path:
                soundfont_path = os.path.join(PROJECT_ROOT, "soundfonts", "Airfont_380_final.sf2")

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
        """Loads the small project-authored soundfont (tools/wav_to_sf2.py)
        holding the click, position-announcer and performance-cue samples -
        alongside the main GM soundfont, not instead of it, on its own sfid
        so play_click/play_word/play_performance_cue can program_select it
        without disturbing any other channel. A missing or unloadable file
        is non-fatal (same "warn and no-op" handling as FluidR3_GM): a fresh
        checkout that hasn't run the tool should still run, just silently.

        Panning is set once here, not per call: each of these channels is
        permanently dedicated (MusicData.RESERVED_CHANNELS), and a CC10 pan
        persists on a channel until changed. Announcer hard left and click
        hard right so they're distinguishable from the music and each other
        (verified: CC10=0 gives silence on the right, 127 silence on the
        left); the performance cue centred, having no directional meaning.
        """
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
        self._fs.cc(PERFORMANCE_CUE_CHANNEL, 10, PAN_CENTER)
        self._fs.cc(VOICE_CONTROL_CUE_CHANNEL, 10, PAN_CENTER)

    def set_program(self, channel: int, program: int, bank: int = 0):
        """Pin the channel to the main GM SoundFont explicitly via
        program_select, not the plain program_change MIDI message. The
        click/announcer/cue SoundFont (_load_click_soundfont) is loaded
        after this one and happens to define presets at bank 0 / program
        0-2 (GM's own Acoustic/Bright/Electric Grand Piano programs) -
        program_change does a bank/program lookup across every loaded
        SoundFont, most-recently-loaded first, so an un-pinned piano part
        silently resolved to the click font's spoken-word samples instead
        of the real GM piano preset (reported bug, live-tested: piano parts
        producing no sound at all, since those samples only cover MIDI
        pitches 60-69).

        bank: 128 for a percussion part (wishlist #8, models.gm_percussion_map
        .GM_PERCUSSION_BANK) - verified against soundfonts/Airfont_380_final
        .sf2's own preset headers, which really do carry a bank 128/program 0
        "Hyper Kit". Every other caller leaves this at the default 0."""
        if self._fs is None or self._sfid is None:
            return
        self._fs.program_select(channel & 0x0F, self._sfid, max(0, bank), max(0, min(127, program)))

    # MIDI continuous-controller numbers for the two mixer parameters.
    VOLUME_CC = 7
    PAN_CC = 10

    def set_channel_volume(self, channel: int, value: int):
        """Wishlist #4. Only called for a part the user has actually set a
        level for - a channel with no override is never touched, so it keeps
        the engine's own default."""
        if self._fs is None:
            return
        self._fs.cc(channel & 0x0F, self.VOLUME_CC, max(0, min(127, value)))

    def set_channel_pan(self, channel: int, value: int):
        """Wishlist #4. Same CC the click/announcer/cue channels are panned
        with at load time (see _load_click_soundfont), so a user override of
        those simply replaces the fixed value."""
        if self._fs is None:
            return
        self._fs.cc(channel & 0x0F, self.PAN_CC, max(0, min(127, value)))

    def stop_all_notes(self):
        """Deliberately does NOT touch _live_input_active_notes - see that
        attribute's own comment in __init__. Moving the score cursor must
        never cut off a note the user is physically holding on a connected
        keyboard; only live_all_notes_off() (device disable/close) does
        that."""
        if self._fs is None:
            return

        for timer in self._pending_strum_timers:
            timer.stop()
        self._pending_strum_timers.clear()

        for timer in self._pending_grace_timers:
            timer.stop()
        self._pending_grace_timers.clear()

        for timer in self._group_off_timers:
            timer.stop()
        self._group_off_timers.clear()

        for channel, note in self._active_notes:
            self._fs.noteoff(channel, note)
        self._active_notes.clear()

        self._stop_click()
        self._stop_announcement()
        self._stop_performance_cue()
        self._stop_voice_confirmation_cue()

    def _stop_click(self):
        """Silences a still-ringing click. Called from stop_all_notes() so
        pause/stop leave nothing orphaned, and from play_click() so a fast
        run of clicks cuts the previous one short rather than overlapping."""
        if self._fs is None or self._active_click is None:
            return
        channel, note = self._active_click
        self._fs.noteoff(channel, note)
        self._active_click = None

    def _stop_announcement(self):
        """The announcer counterpart of _stop_click, on its own channel and
        slot so it can't cancel (or be cancelled by) a simultaneous click."""
        if self._fs is None or self._active_announcement is None:
            return
        channel, note = self._active_announcement
        self._fs.noteoff(channel, note)
        self._active_announcement = None

    def _stop_performance_cue(self):
        """The cue counterpart of _stop_click/_stop_announcement, on its own
        channel and slot for the same reason."""
        if self._fs is None or self._active_performance_cue is None:
            return
        channel, note = self._active_performance_cue
        self._fs.noteoff(channel, note)
        self._active_performance_cue = None

    def _stop_voice_confirmation_cue(self):
        """The voice-control ding's counterpart of _stop_click/
        _stop_announcement/_stop_performance_cue, on its own channel and
        slot for the same reason."""
        if self._fs is None or self._active_voice_confirmation_cue is None:
            return
        channel, note = self._active_voice_confirmation_cue
        self._fs.noteoff(channel, note)
        self._active_voice_confirmation_cue = None

    def live_note_on(self, pitch: int, velocity: int) -> None:
        """A key pressed on a connected live-input device (controllers/
        live_midi_input_controller.py, itself called only from the Qt main
        thread after marshaling off rtmidi's own callback thread - see that
        controller's own docstring). Always LIVE_MIDI_INPUT_CHANNEL - the
        instrument/volume/pan for that channel are set once at connect time
        via set_program/set_channel_volume/set_channel_pan, not per note."""
        if self._fs is None:
            return
        self._fs.noteon(LIVE_MIDI_INPUT_CHANNEL, pitch, velocity)
        self._live_input_active_notes.add(pitch)

    def live_note_off(self, pitch: int) -> None:
        """The matching key release. Removes from the tracking set even if
        _fs is None (a torn-down engine has no notes sounding either way)."""
        self._live_input_active_notes.discard(pitch)
        if self._fs is None:
            return
        self._fs.noteoff(LIVE_MIDI_INPUT_CHANNEL, pitch)

    def live_all_notes_off(self) -> None:
        """The one path that DOES force-release every currently-held live-
        input note - explicit device change/disable and app close, never
        ordinary score navigation (see stop_all_notes()'s own comment)."""
        if self._fs is not None:
            for pitch in list(self._live_input_active_notes):
                self._fs.noteoff(LIVE_MIDI_INPUT_CHANNEL, pitch)
        self._live_input_active_notes.clear()

    def play_performance_cue(self, channel: int, bank: int, program: int, pitch: int, velocity: int):
        """Sounds the "check Region 5" cue - same shape and one-shot-sample
        reasoning as play_click below."""
        if self._fs is None or self._click_sfid is None:
            return

        self._stop_performance_cue()

        ch = channel & 0x0F
        self._fs.program_select(ch, self._click_sfid, bank, program)
        self._fs.noteon(ch, pitch, velocity)
        self._active_performance_cue = (ch, pitch)

    def play_voice_confirmation_cue(self, channel: int, bank: int, program: int, pitch: int, velocity: int):
        """Sounds the voice-control "command recognized" ding - same shape
        and one-shot-sample reasoning as play_click/play_performance_cue."""
        if self._fs is None or self._click_sfid is None:
            return

        self._stop_voice_confirmation_cue()

        ch = channel & 0x0F
        self._fs.program_select(ch, self._click_sfid, bank, program)
        self._fs.noteon(ch, pitch, velocity)
        self._active_voice_confirmation_cue = (ch, pitch)

    def play_click(self, channel: int, bank: int, program: int, pitch: int, velocity: int):
        """Sounds a metronome click on its own dedicated channel,
        independent of the melodic pipeline: it never calls stop_all_notes()
        (which would cut off notes on the same beat) and a later play_chord()
        doesn't touch it. Which SAMPLE plays distinguishes the accent, via
        program_select on the dedicated click soundfont.

        Deliberately schedules NO note-off. Each click zone is a one-shot,
        non-looping sample (SampleModes=0), and FluidSynth deactivates such
        a voice once the sample data is exhausted whether or not a note-off
        arrives - so holding it on and never releasing it lets it play to
        its natural end. Verified by rendering both ways: untouched gives
        the full natural length with no hang; an early note-off gives an
        abrupt cutoff through the soundfont's near-instant release envelope.
        _stop_click() stays the deliberate-interrupt path."""
        if self._fs is None or self._click_sfid is None:
            return

        self._stop_click()

        ch = channel & 0x0F
        self._fs.program_select(ch, self._click_sfid, bank, program)
        self._fs.noteon(ch, pitch, velocity)
        self._active_click = (ch, pitch)

    def play_word(self, channel: int, bank: int, program: int, pitch: int, velocity: int):
        """The spoken-word counterpart of play_click - same soundfont (one
        sfid covers every preset in it), same "never schedule a note-off"
        reasoning, own channel and slot so a click and a word on the same
        beat sound together instead of cancelling each other."""
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

        Each part gets its own channel and GM program, so a slice spanning
        two parts sounds both instruments rather than one cutting the other
        off (Ref 8, Ref 9 AC2). Each group's own trailing duration_ms (when
        present; play_notes()'s single-group callers omit it and get the
        outer default) drives its own independent note-off timer, so one
        part is never clamped to another part's shorter note sounding at the
        same instant - Pachelbel's cello minims cut to a crotchet was this.

        retrigger=True (the default) silences everything sounding first,
        which is what discrete audition wants (Ref 8 AC2 - Region 3
        navigation, chord audition). The Sequencer passes retrigger=False
        for its natural step-to-step advance: one part's new attack must not
        cut off other parts' unrelated, still-ringing notes. An explicit
        reposition (Sequencer.play_from/resume) calls stop_all_notes()
        itself, so only the in-run advance is non-destructive.
        """
        if self._fs is None:
            return

        if retrigger:
            self.stop_all_notes()

        for event in events:
            channel, program, midi_notes = event[0], event[1], event[2]
            group_duration_ms = event[3] if len(event) > 3 else duration_ms
            bank = event[4] if len(event) > 4 else 0
            if not midi_notes:
                continue

            ch = channel & 0x0F
            if program is not None:
                self.set_program(ch, program, bank)

            group_notes: List[Tuple[int, int]] = []
            for note in midi_notes:
                self._fs.noteon(ch, note, 90)
                group_notes.append((ch, note))
            self._active_notes.extend(group_notes)

            if group_notes and group_duration_ms > 0:
                self._schedule_group_off(group_notes, group_duration_ms)

    def play_chord_with_grace(
        self,
        main_events: List[Tuple],
        grace_events: List[Tuple],
        retrigger: bool = True,
        grace_duration_ms: Optional[int] = None,
    ):
        """Sounds grace_events briefly, then main_events - the "A grace B"
        note played as two quick successive attacks instead of play_chord's
        default of stacking every pitch into one simultaneous chord (which
        is what made a grace note look and sound like an extra chord tone -
        see models/note_data.py's GraceNote). Used only when
        get_grace_note_events_for_indices found something to schedule; see
        audio/strum_schedule.py's sound_events, the dispatcher that decides
        between this and the plain play_chord path.

        grace_events carries no duration of its own (a grace note has no
        <duration>) - effective_grace_duration_ms (audio/
        grace_note_schedule.py) derives a brief, tempo-aware ring time from
        main_events' own durations, the one piece of real timing math,
        split out as a pure function for the same testability reason
        build_strum_schedule is. Deliberately flat, like play_strum_pattern:
        one QTimer schedules the whole delayed main chord via the ordinary
        play_chord (retrigger=False, since retrigger for the WHOLE call
        already happened above if requested) rather than nesting further
        timers per note.
        """
        if self._fs is None:
            return

        if retrigger:
            self.stop_all_notes()

        if not grace_events:
            self.play_chord(main_events, retrigger=False)
            return

        duration_ms = (
            effective_grace_duration_ms(main_events)
            if grace_duration_ms is None
            else grace_duration_ms
        )

        for channel, program, pitches in grace_events:
            if not pitches:
                continue
            ch = channel & 0x0F
            if program is not None:
                self.set_program(ch, program)
            group_notes: List[Tuple[int, int]] = []
            for note in pitches:
                self._fs.noteon(ch, note, 90)
                group_notes.append((ch, note))
            self._active_notes.extend(group_notes)
            self._schedule_group_off(group_notes, duration_ms)

        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda t=timer: self._fire_delayed_chord(main_events, t))
        self._pending_grace_timers.append(timer)
        timer.start(duration_ms)

    def _fire_delayed_chord(self, main_events: List[Tuple], timer: QTimer):
        if timer in self._pending_grace_timers:
            self._pending_grace_timers.remove(timer)
        if self._fs is None:
            return
        self.play_chord(main_events, retrigger=False)

    def play_strum_pattern(
        self,
        channel: int,
        program: Optional[int],
        midi_pitches: List[int],
        slots: list,
        slot_ms: float,
        note_delay_ms: float = 20.0,
        retrigger: bool = True,
    ):
        """Demo-plays a whole strum pattern (used by the Strumming Patterns
        dialog). build_strum_schedule (audio/strum_schedule.py) does the
        arpeggio + effect math as a pure function; this is just the flat
        QTimer wrapper - every note-on across the pattern is scheduled up
        front from the one list it returns, tracked in _pending_strum_timers
        so stop_all_notes() cancels a still-running demo.
        """
        if self._fs is None:
            return

        if retrigger:
            self.stop_all_notes()

        if program is not None:
            self.set_program(channel & 0x0F, program)

        schedule = build_strum_schedule(slots, midi_pitches, slot_ms, note_delay_ms)
        ch = channel & 0x0F
        for start_ms, pitch, velocity, note_duration_ms in schedule:
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(
                lambda p=pitch, v=velocity, d=note_duration_ms, t=timer: self._fire_strum_note(ch, p, v, d, t)
            )
            self._pending_strum_timers.append(timer)
            timer.start(int(start_ms))

    def _fire_strum_note(self, channel: int, pitch: int, velocity: int, duration_ms: float, timer: QTimer):
        if timer in self._pending_strum_timers:
            self._pending_strum_timers.remove(timer)
        if self._fs is None:
            return

        self._fs.noteon(channel, pitch, velocity)
        group_notes = [(channel, pitch)]
        self._active_notes.extend(group_notes)
        if duration_ms > 0:
            self._schedule_group_off(group_notes, duration_ms)

    def _schedule_group_off(self, group_notes: List[Tuple[int, int]], duration_ms: int):
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._stop_group(group_notes, timer))
        self._group_off_timers.append(timer)
        timer.start(int(duration_ms))

    def _stop_group(self, group_notes: List[Tuple[int, int]], timer: QTimer):
        """A (channel, note) pair can legitimately appear in _active_notes
        more than once: two voices of one part sounding a unison land on
        that part's single channel at the same pitch, each with its own
        duration and timer. So release this group's claim and only send
        noteoff once no other live group still holds the pair - otherwise
        the shorter voice's expiry silences the longer one."""
        if self._fs is None:
            if timer in self._group_off_timers:
                self._group_off_timers.remove(timer)
            return

        for ch, note in group_notes:
            if (ch, note) not in self._active_notes:
                continue
            self._active_notes.remove((ch, note))
            if (ch, note) not in self._active_notes:
                self._fs.noteoff(ch, note)

        if timer in self._group_off_timers:
            self._group_off_timers.remove(timer)

    def close(self):
        if self._fs:
            self.stop_all_notes()
            self.live_all_notes_off()
            self._fs.delete()
            self._fs = None