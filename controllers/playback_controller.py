# controllers/playback_controller.py
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

from PySide6.QtCore import QObject, Qt, QTimer, Signal

from audio.lead_in import build_lead_in_schedule
from audio.metronome import METRONOME_CHANNEL, click_event_for_beat
from audio.performance_cue import PERFORMANCE_CUE_CHANNEL
from audio.position_announcer import POSITION_ANNOUNCER_CHANNEL, announcement_event_for_beat
from audio.sequencer import Sequencer
from audio.strum_schedule import sound_events
from models import mixer_settings
from models.mixer_settings import MixerSettings
from models.play_settings import (
    LOOP_REPEAT_MODES,
    PLAY_MODE_LOOP_FOREVER,
    PLAY_MODE_TO_END,
    PLAY_MODES,
    PlaySettings,
)
from models.playback_jump_state import PlaybackJumpState
from models.vocabulary import bar_word


@dataclass
class _PlayRun:
    """One play session that needs more than a bare Sequencer run - i.e.
    one with a lead-in count-in and/or looping. The resolved span, the
    settings snapshot taken when it started, and the schedule of the
    iteration currently running.

    The session outlives the Sequencer run inside it - it also covers the
    lead-in before any note sounds and the wait to the bar line before a
    loop repeats, neither of which the Sequencer knows about. That is why
    the "stop what's running" test is is_play_run_active and not
    sequencer.is_playing.
    """

    settings: PlaySettings
    # True for a looping run (fixed N-bar window, cursor frozen); False for
    # a lead-in-then-play-to-the-end run (cursor follows, ends on its own).
    looping: bool
    start_index: int
    # None for a non-looping run - it plays to the end of the score.
    end_index: Optional[int]
    end_quarters: float
    # True when start_index falls in a pickup bar (Ref 17): a count-in ahead
    # of it must keep counting past the requested lead-in to also complete
    # the pickup's own bar - see _start_play_iteration.
    is_pickup: bool
    # Silence between the bar line and the first note, for a previewed bar
    # that opens with a rest - kept so a repeat stays in time rather than
    # sliding forward by that gap. 0 for a pickup (its real content starts
    # at the piece's own start, not after some silence) - used as-is for a
    # LOOP repeat with no lead-in of its own; a lead-in ahead of a pickup
    # computes its own play_gap_ms instead (_start_play_iteration).
    offset_ms: int
    # Bar line to bar line: what one loop iteration lasts. Still computed
    # (F/S/D tempo tracking, tests), but a "loop until stopped" run no
    # longer schedules its restart off this as a standalone wall-clock
    # timer - see loop_tail_pad_ms and _on_sequencer_finished.
    iteration_ms: int
    # "loop until stopped" only: the restart is driven by the Sequencer's
    # own `finished` signal (which fires only once every chained step has
    # actually run and the last note's ring-out has been waited out), NOT
    # by a monolithic timer armed a whole iteration ahead - that timer
    # raced the Sequencer's chained per-step timers and, at a slow tempo
    # with many steps (heavy per-step region-refresh work between each
    # timer re-arm), drifted early enough to clip the last note (reported,
    # etude 2 bar 3, loop length 3, 44 bpm). loop_tail_pad_ms is the only
    # wait left: the gap between that last note's ring-out and the bar line
    # when the iteration's final bar ends in rests. 0 when the last note
    # itself rings to (or past) the bar line, so the restart is immediate.
    loop_tail_pad_ms: int = 0
    # Looping only: the active_event_index to restore when the run stops.
    # A looping run tracks the playing position in Region 3 as it goes, the
    # same as a non-looping run - but the Sequencer's own update_cursor is
    # left False, so its stop/finish reversion never touches the cursor;
    # this controller moves it per step (_on_sequencer_step) and puts it
    # back here on stop().
    restore_index: Optional[int] = None
    # (offset_ms within the iteration, action) in time order, walked by one
    # chained single-shot timer - the same "reschedule a step at a time so
    # cancelling is one stop()" shape as audio/sequencer.py.
    events: List[Tuple[int, Tuple[Any, ...]]] = field(default_factory=list)
    event_index: int = 0
    elapsed_ms: int = 0
    playing: bool = False
    # Looping on a MusicXML score that actually carries repeat barlines:
    # the iteration follows repeats/endings under a bar-count budget rather
    # than a linear end_index window (see _build_play_run /
    # simulate_loop_iteration). False for every other run - MIDI/GP/UG and
    # repeat-less MusicXML keep the exact linear code path unchanged.
    respect_repeats: bool = False
    # How many times the ("loop",) restart has fired - drives "alternate"
    # mode's per-iteration seed choice (_loop_seed_jump_state).
    iteration_count: int = 0
    # The seed handed to Sequencer.play_from for THIS iteration, recomputed
    # per iteration in _refresh_play_span. None = a fresh first play-through.
    seed_jump_state: Optional[PlaybackJumpState] = None


class PlaybackController(QObject):
    """Everything that makes sound, and the transport state around it:
    Sequencer lifecycle, play/pause/stop, the lead-in/looping play session,
    absolute tempo, chord audition, the boundary cue, and the metronome/
    announcer toggles.

    Touches no widgets. Where a widget-derived value is needed it is passed
    in - audition_selection(indices) rather than reading Region 3's
    selection - which is what keeps the transport logic testable without a
    window.

    Signals rather than direct calls into the view, so the refresh ordering
    stays owned by MainWindow (see its _on_cursor_moved):
      cursor_moved(play_all)   - the timeline position changed
      status_text_changed()    - the whole status bar needs rebuilding
      playback_state_changed() - only the Playing/Paused/Stopped field
    """

    cursor_moved = Signal(bool)
    status_text_changed = Signal()
    playback_state_changed = Signal()

    # Boundary cue (Ref 2 AC4/Ref 3 AC4): a short, quiet, low note played
    # INSTEAD of moving, deliberately unlike anything in the score so it
    # isn't mistaken for one. Channel 15 because parts are allocated from
    # the low end, making it the last to collide (only on a 15+ part score).
    BOUNDARY_CHANNEL = 15
    BOUNDARY_GM_PROGRAM = 43  # GM 44 Contrabass, 0-indexed on the wire
    BOUNDARY_MIDI_PITCH = 37  # C#2 - low
    BOUNDARY_DURATION_MS = 100  # roughly a semiquaver; independent of score tempo

    def __init__(self, session, timer=None, parent=None):
        super().__init__(parent)
        self.session = session
        # One Sequencer per loaded score - it holds a reference to that
        # score's MusicData, so it is recreated in attach_score().
        self.sequencer: Optional[Sequencer] = None
        # Groundwork for wishlist #7 (mute): consulted before anything
        # sounds. False throughout today, so every path is unchanged.
        self._muted = False
        # Mixer dialog edit-session state (begin/set/commit/cancel_mixer_edit
        # below) - None outside of an open dialog.
        self._mixer_edit_original: Optional[MixerSettings] = None
        self._mixer_edit_working: Optional[MixerSettings] = None
        # Play Settings (Space/Playback > Play Settings): lead-in and
        # looping. Global settings, pushed in by MainWindow from AppSettings
        # on startup and again whenever the dialog is accepted.
        self.play_settings = PlaySettings()
        self._play_run: Optional[_PlayRun] = None
        # timer: injectable like Sequencer's, so tests can drive the
        # count-in and the loop without waiting on the clock.
        if timer is None:
            timer = QTimer(self)
            # See Sequencer.__init__'s own comment - the same fast-tempo
            # drift applies to the count-in/loop-restart chain here.
            timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._play_timer = timer
        self._play_timer.setSingleShot(True)
        self._play_timer.timeout.connect(self._on_play_timer)

        # Play Metronome (Ctrl+Alt+Space): a free-running click track at the
        # current playback tempo that never moves the timeline - for playing
        # along by ear. Independent of the Ctrl+M score metronome (which
        # only clicks as the cursor steps over a beat during real playback)
        # and of the transport. One chained single-shot timer, re-armed each
        # beat so an F/S/D tempo change takes effect on the very next click.
        self._play_metronome_timer = QTimer(self)
        self._play_metronome_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._play_metronome_timer.setSingleShot(True)
        self._play_metronome_timer.timeout.connect(self._sound_play_metronome_beat)
        self._play_metronome_beat = 1

    @property
    def music_data(self):
        return self.session.music_data

    @property
    def synth(self):
        return self.session.synth

    @property
    def muted(self) -> bool:
        return self._muted

    def set_muted(self, muted: bool) -> None:
        """Wishlist #7. Silences anything ringing on the way in, so muting
        mid-note takes effect immediately rather than at the next note-off."""
        self._muted = muted
        if muted:
            self.synth.stop_all_notes()

    def attach_score(self, music_data) -> None:
        """Called on every load: stop whatever the previous score was doing,
        build that score's own Sequencer, and push the score's own saved
        mixer state (music_data.mixer - already populated by apply_config()
        before this runs, see main_window.py's _on_score_loaded)."""
        self.cancel_play_run()
        self.stop_play_metronome()
        if self.sequencer is not None:
            self.sequencer.stop()
        self.sequencer = Sequencer(music_data, self.synth, parent=self)
        self.sequencer.step_played.connect(self._on_sequencer_step)
        self.sequencer.finished.connect(self._on_sequencer_finished)
        self.apply_mixer(music_data.mixer)

    def detach_score(self) -> None:
        """File > Close: the inverse of attach_score. Silence anything
        sounding or scheduled and drop the score's Sequencer, so the
        controller is back to its pre-load state. The synth stays alive
        (it is a process-long singleton), so an explicit stop_all_notes()
        is needed here where closeEvent can rely on synth.close()."""
        self.cancel_play_run()
        self.stop_play_metronome()
        if self.sequencer is not None:
            self.sequencer.stop()
        self.sequencer = None
        self._muted = False
        self.synth.stop_all_notes()

    def apply_mixer(self, mixer) -> None:
        """Wishlist #4: push a score's saved volume/pan overrides onto their
        channels.

        Every mixer-controllable channel is resent UNCONDITIONALLY - an
        override where one exists, else the real default (DEFAULT_VOLUME /
        default_pan_for(key), same values cancel_mixer_edit already reverts
        to) - not just the channels this score happens to override.

        Reported bug, live-tested: the synth is a long-lived singleton
        across file loads (one in-process FluidSynth session for the whole
        run - audio/synth_engine.py), so a channel's CC7/CC10 value from
        whatever score was open PREVIOUSLY survives untouched into a new
        load. A part on the same channel number in both scores (channel
        assignment is deterministic per get_channel_for_part) silently
        inherited the old score's override - the user's own repro: a cello
        set to 0% volume in a MusicXML score's Mixer stayed silent after
        switching to the MIDI version of the same piece, which had no
        override of its own. Sending nothing for a channel with no override,
        as this method used to, only leaves the engine "as it would be
        without this feature" on a script's very first load - not on every
        later one, since by then the engine already has a past.
        """
        if mixer is None or not self.music_data:
            return
        self._muted = mixer.muted
        for part in self.music_data.parts_info:
            channel = self.music_data.get_channel_for_part(part.part_id)
            volume = mixer.volume_for(part.part_id)
            self.synth.set_channel_volume(
                channel, volume if volume is not None else mixer_settings.DEFAULT_VOLUME
            )
            pan = mixer.pan_for(part.part_id)
            self.synth.set_channel_pan(
                channel, pan if pan is not None else mixer_settings.default_pan_for(part.part_id)
            )
        for key, channel in (
            (mixer_settings.CLICK, METRONOME_CHANNEL),
            (mixer_settings.ANNOUNCER, POSITION_ANNOUNCER_CHANNEL),
            (mixer_settings.CUE, PERFORMANCE_CUE_CHANNEL),
        ):
            volume = mixer.volume_for(key)
            self.synth.set_channel_volume(
                channel, volume if volume is not None else mixer_settings.DEFAULT_VOLUME
            )
            pan = mixer.pan_for(key)
            self.synth.set_channel_pan(
                channel, pan if pan is not None else mixer_settings.default_pan_for(key)
            )

    # --- mixer dialog (wishlist #4) -----------------------------------

    def mixer_rows(self) -> List[Tuple[str, str, int]]:
        """(key, label, channel) for every mixer-controllable channel: each
        real instrument part, in parts_info order, plus the click, position
        announcer and performance-cue channels. The Mixer dialog's list is
        built from this."""
        rows: List[Tuple[str, str, int]] = []
        if self.music_data:
            for part in self.music_data.parts_info:
                rows.append((part.part_id, part.name, self.music_data.get_channel_for_part(part.part_id)))
        rows.append((mixer_settings.CLICK, "Metronome", METRONOME_CHANNEL))
        rows.append((mixer_settings.ANNOUNCER, "Position Announcer", POSITION_ANNOUNCER_CHANNEL))
        rows.append((mixer_settings.CUE, "Performance Cue", PERFORMANCE_CUE_CHANNEL))
        return rows

    def _mixer_channel(self, key: str) -> Optional[int]:
        for row_key, _, channel in self.mixer_rows():
            if row_key == key:
                return channel
        return None

    def begin_mixer_edit(self) -> List[Tuple[str, str, int, int]]:
        """Opens a Mixer dialog edit session: snapshots the score's current
        mixer twice - once untouched (for cancel_mixer_edit to revert to),
        once as the working copy set_mixer_volume/set_mixer_pan mutate -
        and returns (key, label, volume_percent, pan_percent) per row for
        MixerDialog to display. A row with no override shows the channel's
        REAL current default (100% volume everywhere; 0% pan for a part,
        but the click/announcer's own hard-right/hard-left pan - see
        mixer_settings.default_pan_for), not an arbitrary placeholder."""
        if not self.music_data:
            return []
        self._mixer_edit_original = self.music_data.mixer.copy()
        self._mixer_edit_working = self.music_data.mixer.copy()
        rows = []
        for key, label, _ in self.mixer_rows():
            volume_cc = self._mixer_edit_working.volume_for(key)
            if volume_cc is None:
                volume_cc = mixer_settings.DEFAULT_VOLUME
            pan_cc = self._mixer_edit_working.pan_for(key)
            if pan_cc is None:
                pan_cc = mixer_settings.default_pan_for(key)
            rows.append((
                key, label,
                mixer_settings.cc_to_volume_percent(volume_cc),
                mixer_settings.cc_to_pan_percent(pan_cc),
            ))
        return rows

    def set_mixer_volume(self, key: str, percent: int) -> None:
        """Live preview: pushed to the synth immediately, and recorded on
        the working copy - music_data.mixer itself isn't touched until
        commit_mixer_edit (OK)."""
        if self._mixer_edit_working is None:
            return
        cc = mixer_settings.volume_percent_to_cc(percent)
        self._mixer_edit_working.set_volume(key, cc)
        channel = self._mixer_channel(key)
        if channel is not None:
            self.synth.set_channel_volume(channel, cc)

    def set_mixer_pan(self, key: str, percent: int) -> None:
        """Pan counterpart of set_mixer_volume - same live-preview shape."""
        if self._mixer_edit_working is None:
            return
        cc = mixer_settings.pan_percent_to_cc(percent)
        self._mixer_edit_working.set_pan(key, cc)
        channel = self._mixer_channel(key)
        if channel is not None:
            self.synth.set_channel_pan(channel, cc)

    def commit_mixer_edit(self) -> None:
        """OK: the working copy becomes the score's real mixer - already
        fully live on the synth from set_mixer_volume/set_mixer_pan's
        incremental pushes, so there is nothing further to send."""
        if self.music_data and self._mixer_edit_working is not None:
            self.music_data.mixer = self._mixer_edit_working
        self._mixer_edit_original = None
        self._mixer_edit_working = None

    def cancel_mixer_edit(self) -> None:
        """Cancel: put the synth back exactly as it was before the dialog
        opened. Every mixer-controllable channel is resent unconditionally,
        not just ones touched this session - a live preview may have pushed
        CC to a channel that had no prior override at all, and apply_mixer()
        alone would skip resending anything for such a channel. music_data.
        mixer is left untouched throughout."""
        if self.music_data and self._mixer_edit_original is not None:
            original = self._mixer_edit_original
            for key, _, channel in self.mixer_rows():
                volume_cc = original.volume_for(key)
                self.synth.set_channel_volume(
                    channel, volume_cc if volume_cc is not None else mixer_settings.DEFAULT_VOLUME
                )
                pan_cc = original.pan_for(key)
                self.synth.set_channel_pan(
                    channel, pan_cc if pan_cc is not None else mixer_settings.default_pan_for(key)
                )
        self._mixer_edit_original = None
        self._mixer_edit_working = None

    def end_mixer_edit(self, accepted: bool) -> None:
        """S5: close out a mixer edit session - commit or revert, then
        silence anything the dialog's own Preview button (Alt+W) left
        running.

        `is_play_run_active` as well as the Sequencer's own flags: a play
        run can have a count-in or a loop pending that `is_playing`/
        `is_paused` cannot see, so checking the Sequencer alone would leave
        it running after the dialog closed.
        """
        if accepted:
            self.commit_mixer_edit()
        else:
            self.cancel_mixer_edit()
        sequencer_running = self.sequencer is not None and (
            self.sequencer.is_playing or self.sequencer.is_paused
        )
        if self.is_play_run_active or sequencer_running:
            self.stop()

    # --- transport ---------------------------------------------------

    def toggle_play_stop(self) -> None:
        """Space (Ref 10): the single play control. Not playing -> start from
        the cursor (looping the loop-length window when looping is on, else
        playing to the end and stopping); playing -> stop, silence and
        revert; paused -> resume. Space owns both starting and resuming;
        Ctrl+Space only pauses.

        From the last note it sounds the boundary cue instead of playing:
        there is nothing ahead to play, the same "can't go further" signal
        Left/Right give."""
        if not self.music_data or self.sequencer is None:
            return
        if self.is_play_metronome_running:
            # Space is the "stop everything sounding" key - a running
            # free-metronome click track is what it stops here, the same as
            # it would stop real playback.
            self.stop_play_metronome()
            return
        if self._play_run is not None:
            # A play run may be mid-count-in with nothing sounding yet, which
            # is_playing cannot see - without this, Space would start a
            # second, overlapping run underneath the count-in.
            self.stop()
            return
        if self.sequencer.is_paused:
            self.sequencer.resume()
            self.playback_state_changed.emit()
            return
        if self.sequencer.is_playing:
            self.stop()
            return

        start_index = self.music_data.active_event_index
        if self.music_data.next_visible_event_index(start_index) is None:
            self.play_boundary_cue()
            return

        if self.play_settings.loop_enabled or self.play_settings.lead_in_enabled:
            run = self._build_play_run(looping=self.play_settings.loop_enabled)
            if run is None:
                return
            self._play_run = run
            self._start_play_iteration(with_lead_in=run.settings.has_lead_in())
        else:
            self.sequencer.play_from(start_index, update_cursor=True)
            self.playback_state_changed.emit()

    def play_command(self) -> None:
        """Hands-free voice control's directional "play" (Ref 19): resumes
        if paused, starts from the cursor if stopped, no-ops if already
        playing. Unlike toggle_play_stop, never stops what's already
        running - a spoken "play" heard while music is already playing
        should not silence it, the way pressing Space a second time
        deliberately does."""
        if not self.music_data or self.sequencer is None:
            return
        self.stop_play_metronome()
        if self._play_run is not None:
            self.stop()
        if self.sequencer.is_paused:
            self.sequencer.resume()
            self.playback_state_changed.emit()
        elif not self.sequencer.is_playing:
            start_index = self.music_data.active_event_index
            if self.music_data.next_visible_event_index(start_index) is None:
                self.play_boundary_cue()
            else:
                self.sequencer.play_from(start_index, update_cursor=True)
                self.playback_state_changed.emit()

    def pause_command(self) -> None:
        """Hands-free voice control's directional "pause" (Ref 19): pauses
        if playing, no-ops otherwise - never resumes, unlike a spoken "pause"
        heard while already paused, which should just stay paused. Body is
        identical to toggle_pause_resume today, kept as its own named method
        since the two commands mean different things even where they
        currently coincide."""
        if self.sequencer is None:
            return
        if self.sequencer.is_playing:
            self.sequencer.pause()
            self.playback_state_changed.emit()

    def toggle_pause_resume(self) -> None:
        """Ctrl+Space (Ref 10 AC3): pauses only. Resuming is Space's job -
        having both resume collides and leaves users pressing Space twice."""
        if self.sequencer is None:
            return
        if self.sequencer.is_playing:
            self.sequencer.pause()
            self.playback_state_changed.emit()

    def stop(self) -> None:
        """Stops whatever is running before anything new starts. Only a
        cursor-tracking run syncs active_event_index and the regions back
        afterwards - a looping run never moved the cursor - but the status
        field always updates.

        Cancelling the play session first is what makes Space stop a
        count-in that has not sounded a note yet."""
        # A looping run tracks the playing position in Region 3 as it runs
        # (_on_sequencer_step) but leaves the Sequencer's own update_cursor
        # False, so stopping it must put the cursor back to where the loop
        # was started from - captured before cancel_play_run() drops the run.
        looping_restore_index = None
        if self._play_run is not None and self._play_run.looping:
            looping_restore_index = self._play_run.restore_index
        self.cancel_play_run()
        self.stop_play_metronome()
        if self.sequencer is None:
            return
        was_tracking_cursor = self.sequencer.update_cursor
        self.sequencer.stop()
        # current_index is None on a Sequencer that has never been played
        # from - which stopping a preview during its count-in reaches, since
        # nothing has started the Sequencer yet. Syncing the cursor to it
        # would set active_event_index to None and break every later read.
        if was_tracking_cursor and self.music_data and self.sequencer.current_index is not None:
            self.music_data.active_event_index = self.sequencer.current_index
            self.cursor_moved.emit(False)
        elif looping_restore_index is not None and self.music_data:
            self.music_data.active_event_index = looping_restore_index
            self.cursor_moved.emit(False)
        else:
            self.playback_state_changed.emit()

    def phrase_end_index(self, current_measure: int, start_index: int, bars: int = 2) -> int:
        """Through the end of the (bars-1)th measure after this one, or the
        last sounding event if the piece ends first - bounded so a loop
        can't run on into trailing rest-only padding, and so a loop length
        reaching past the end of the piece simply ends there."""
        last_sounding = self.music_data.last_sounding_event_index()
        end_index = last_sounding if last_sounding is not None else self.music_data.last_event_index()

        measures = self.music_data.measure_numbers()
        pos = measures.index(current_measure)
        bars = max(1, int(bars))
        if pos + bars < len(measures):
            measure_after_last = measures[pos + bars]
            candidate_end = self.music_data.first_event_index_of_measure(measure_after_last) - 1
            if candidate_end >= start_index:
                end_index = min(end_index, candidate_end)
        return end_index

    # --- play session ----------------------------------------------------

    @property
    def is_play_run_active(self) -> bool:
        """True from the first tick of the count-in until the play run stops
        - the check callers need instead of sequencer.is_playing, which is
        False during the lead-in and between loop repeats."""
        return self._play_run is not None

    def set_play_settings(self, settings: PlaySettings) -> None:
        """Applied to the NEXT play run: a running session keeps its own
        snapshot, so accepting the dialog can't change what a loop is doing
        half way through."""
        self.play_settings = settings.copy()

    def adjust_loop_length_bars(self, delta: int) -> None:
        """Alt+PageUp/PageDown in the Note region: lengthen/shorten the loop
        window by one bar per press. Alt avoids the native PageUp/PageDown
        paging QListWidget already gives Region 3 - the same reason Ctrl is
        used for measure-at-a-time Left/Right there.

        Applies to the NEXT play run, exactly like the dialog's OK - a
        running loop keeps its own already-started snapshot. Clamped to
        [MIN_LOOP_LENGTH_BARS, MAX_LOOP_LENGTH_BARS] by PlaySettings."""
        self.play_settings = self.play_settings.with_loop_length_bars(
            self.play_settings.loop_length_bars + delta
        )
        self.status_text_changed.emit()

    def set_loop_length_bars(self, bars: int) -> None:
        """Typed Ctrl+Enter buffer / the voice command "loop length N" (Ref
        19) - sets the loop length directly, unlike adjust_loop_length_bars'
        relative +/-1 nudge. Clamped by PlaySettings itself, same as every
        other entry point (the dialog, Alt+PageUp/PageDown)."""
        self.play_settings = self.play_settings.with_loop_length_bars(bars)
        self.status_text_changed.emit()

    def cycle_play_mode(self) -> str:
        """Ctrl+L: rotate the play mode "play to end" -> "play loop once" ->
        "play loop until stopped" -> "play to end". Returns the new mode.
        Replaces the old toggle_loop (a plain loop on/off)."""
        try:
            i = PLAY_MODES.index(self.play_settings.play_mode)
        except ValueError:
            i = 0
        return self.set_play_mode(PLAY_MODES[(i + 1) % len(PLAY_MODES)])

    def set_play_mode(self, mode: str) -> str:
        """The deterministic target for cycle_play_mode and the Play
        Settings dialog. Persists globally and refreshes the status bar; an
        unknown value coerces to "play to end" in PlaySettings.__post_init__.
        Returns the mode actually stored."""
        updated = self.play_settings.copy()
        updated.play_mode = mode
        updated.__post_init__()
        self.play_settings = updated
        from persistence import app_settings

        app_settings.set_play_settings(self.play_settings)
        self.status_text_changed.emit()
        return self.play_settings.play_mode

    def toggle_lead_in(self) -> bool:
        """Ctrl+I. Returns the new state, like cycle_play_mode."""
        return self.set_lead_in_enabled(not self.play_settings.lead_in_enabled)

    def set_loop_enabled(self, enabled: bool) -> bool:
        """The deterministic on/off target the voice "looping on/off"
        commands still use (Ref 19). Maps onto the three-way play mode: on
        -> "play loop until stopped", off -> "play to end". Returns the
        resulting loop_enabled bool."""
        self.set_play_mode(PLAY_MODE_LOOP_FOREVER if enabled else PLAY_MODE_TO_END)
        return self.play_settings.loop_enabled

    def set_lead_in_enabled(self, enabled: bool) -> bool:
        """Counterpart of set_loop_enabled for "lead in on/off"."""
        updated = self.play_settings.copy()
        updated.lead_in_enabled = bool(enabled)
        updated.__post_init__()
        self.play_settings = updated
        from persistence import app_settings

        app_settings.set_play_settings(self.play_settings)
        self.status_text_changed.emit()
        return self.play_settings.lead_in_enabled

    def set_loop_repeat_mode(self, mode: str) -> str:
        """"Repeat handling while looping" - how a repeat barline clipped by
        the loop window is read (see models/play_settings.py's
        LOOP_REPEAT_MODES). Global, like loop_enabled; an unknown value
        coerces to "first" in PlaySettings.__post_init__. Returns the mode
        actually stored."""
        updated = self.play_settings.copy()
        updated.loop_repeat_mode = mode
        updated.__post_init__()
        self.play_settings = updated
        from persistence import app_settings

        app_settings.set_play_settings(self.play_settings)
        self.status_text_changed.emit()
        return self.play_settings.loop_repeat_mode

    def cycle_loop_repeat_mode(self) -> str:
        """Ctrl+R: rotate first -> second -> alternate -> first."""
        try:
            i = LOOP_REPEAT_MODES.index(self.play_settings.loop_repeat_mode)
        except ValueError:
            i = 0
        return self.set_loop_repeat_mode(LOOP_REPEAT_MODES[(i + 1) % len(LOOP_REPEAT_MODES)])

    def _build_play_run(self, looping: bool) -> Optional["_PlayRun"]:
        """Resolve where the play run starts and (for a looping run) ends,
        in both index and real-time terms. Returns None when there is
        nothing to play.

        A looping run snaps its start to the bar line of the cursor's
        measure and runs a fixed loop_length_bars window; a non-looping run
        (lead-in only) starts on the exact cursor and plays to the end."""
        current = self.music_data.get_current_slice()
        if current is None:
            return None

        settings = self.play_settings.copy()

        if not looping:
            start_index = self.music_data.active_event_index
            start_slice = self.music_data.timeline_slices[start_index]
            start_bar = self.music_data.bar_bounds_quarters(start_index)
            is_pickup = bool(start_bar and start_bar[0] < 0)
            run = _PlayRun(
                settings=settings,
                looping=False,
                start_index=start_index,
                end_index=None,
                end_quarters=start_slice.quarters_from_start,
                is_pickup=is_pickup,
                offset_ms=0,
                iteration_ms=0,
            )
            self._refresh_play_span(run)
            return run

        start_index = self.music_data.first_visible_event_index_of_measure(current.measure)
        if start_index is None:
            return None

        end_index = self.phrase_end_index(current.measure, start_index, settings.loop_length_bars)

        # The loop repeats on the BAR LINE after the last looped bar, not
        # when the last note stops ringing: a bar ending in rests would
        # otherwise restart early and out of time, which is useless to play
        # along to. bar_bounds_quarters derives that from the slice itself
        # (see MusicData). A loop length running past the end of the piece
        # is already clamped by phrase_end_index, so the last bar of the
        # piece becomes the end of the loop.
        start_slice = self.music_data.timeline_slices[start_index]
        start_bar = self.music_data.bar_bounds_quarters(start_index)
        end_bar = self.music_data.bar_bounds_quarters(end_index)
        # A pickup bar's (Ref 17) NOTIONAL start is before the piece begins,
        # so its unclamped bar start comes back negative - that is the
        # signal is_pickup keys off. The matching clamp lives in
        # _refresh_play_span, which needs it to derive offset_ms and
        # recomputes it per loop iteration; a duplicate sat here unused
        # from the commit that moved that calculation out (5eb1101), and
        # was removed rather than kept in sync with nothing reading it.
        is_pickup = bool(start_bar and start_bar[0] < 0)
        end_quarters = end_bar[1] if end_bar else start_slice.quarters_from_start

        # Only MusicXML scores that actually carry repeat barlines take the
        # repeat-aware looped path; everything else (MIDI/GP/UG always have
        # an empty repeat_spans, as does a repeat-less MusicXML score) keeps
        # the linear end_index window verbatim, so fingerprints and every
        # existing loop stay unchanged. When respected, there is no linear
        # end_index - a backward repeat can send the iteration to a bar
        # before the window - so it is None and _refresh_play_span derives
        # end_quarters/iteration_ms from simulate_loop_iteration instead.
        respect_repeats = bool(self.music_data.repeat_spans)

        run = _PlayRun(
            settings=settings,
            looping=True,
            start_index=start_index,
            end_index=None if respect_repeats else end_index,
            end_quarters=end_quarters,
            is_pickup=is_pickup,
            offset_ms=0,
            iteration_ms=0,
            restore_index=self.music_data.active_event_index,
            respect_repeats=respect_repeats,
        )
        self._refresh_play_span(run)
        return run

    def _refresh_play_span(self, run: "_PlayRun") -> None:
        """(Re)computes offset_ms/iteration_ms/loop_tail_pad_ms from the
        CURRENT tempo - called both when a run is first built and at the top of every
        _start_play_iteration call (including a loop repeat), so an
        F/S/D tempo change made while Preview is already looping is
        reflected in the very next loop-restart's timing rather than
        replaying a stale span computed at whatever tempo was in force when
        Enter was first pressed. Reported live: speeding up ~40bpm while a
        repeat-containing passage was already looping left the loop-restart
        (and the lead-in count-in it schedules) drifting out of time -
        _start_play_iteration's own bpm (used for the count-in clicks)
        was already re-derived per iteration (see its own comment below),
        but iteration_ms/offset_ms - the loop-restart's own timing - were
        computed once in _build_play_run and never touched again.

        A non-looping run starts on the exact cursor and has no bar-line
        gap or loop iteration of its own - the pickup count-in padding in
        _start_play_iteration handles the one case (a pickup) where a gap
        after the count-in is still wanted."""
        if not run.looping:
            run.offset_ms = 0
            run.iteration_ms = 0
            return
        start_slice = self.music_data.timeline_slices[run.start_index]
        start_bar = self.music_data.bar_bounds_quarters(run.start_index)
        # Clamped at 0 for a pickup bar, whose NOTIONAL start is before the
        # piece begins - see is_pickup/_build_play_run's own comment.
        bar_start_quarters = max(0.0, start_bar[0]) if start_bar else start_slice.quarters_from_start
        lead_quarters = max(0.0, start_slice.quarters_from_start - bar_start_quarters)
        bpm = self.music_data.effective_tempo_bpm(run.start_index)
        run.offset_ms = int(round(lead_quarters * 60000.0 / float(bpm)))
        if run.respect_repeats:
            # A backward repeat can send this iteration to a bar BEFORE the
            # window, so there is no linear end_index to time against;
            # simulate_loop_iteration walks the repeat-aware path under a
            # bar-count budget and returns its real elapsed span and the
            # bar line the ("loop",) restart fires on. The seed selects
            # which play-through of a clipped repeat is looped - recomputed
            # here per iteration so "alternate" gets the right length each
            # time and an F/S/D tempo change lands on the next restart.
            run.seed_jump_state = self._loop_seed_jump_state(
                run.settings.loop_repeat_mode, run.iteration_count
            )
            iter_indices, span_ms, end_quarters = self.music_data.simulate_loop_iteration(
                run.start_index, run.settings.loop_length_bars, run.seed_jump_state
            )
            run.end_quarters = end_quarters
            last_index = iter_indices[-1] if iter_indices else run.start_index
        else:
            # Jump-aware, not span_ms_to_quarters's flat walk - a repeat
            # fully inside the preview window makes the real Sequencer run
            # take longer than a naive linear walk would predict, and this
            # drives the loop-restart timer below (iteration_ms), so it must
            # know about it too or a contained repeat gets truncated
            # mid-replay.
            span_ms = self.music_data.playback_span_ms(
                run.start_index, run.end_index, run.end_quarters
            )
            last_measure = self.music_data.timeline_slices[run.end_index].measure
            last_index = self.music_data.last_visible_event_index_of_measure(last_measure)
            if last_index is None:
                last_index = run.end_index
        run.iteration_ms = run.offset_ms + span_ms

        # The one wait the Sequencer's own `finished` signal does NOT already
        # cover: when the iteration's last note is shorter than the run to
        # the bar line (final bar ends in rests), the loop must still restart
        # on the bar line, not when that note stops ringing. Mirrors
        # playback_event_builder._tail_ms exactly (max(bar_line, ring_out)),
        # minus the ring_out the Sequencer waits out itself - so 0 whenever
        # the last note rings to or past the bar line.
        last_slice = self.music_data.timeline_slices[last_index]
        bar_line_ms = int(
            max(0.0, run.end_quarters - last_slice.quarters_from_start) * 60000.0 / float(bpm)
        )
        ring_out_ms = self.music_data.get_ring_out_ms_for_index(last_index)
        run.loop_tail_pad_ms = max(0, bar_line_ms - ring_out_ms)

    def _loop_seed_jump_state(
        self, mode: str, iteration_count: int
    ) -> Optional[PlaybackJumpState]:
        """The PlaybackJumpState a looped iteration is seeded with, per the
        "Repeat handling while looping" mode (models/play_settings.py's
        LOOP_REPEAT_MODES):

          first     - None (a fresh run): the clipped repeat is taken once
                      and its first-time ending played; once a loop window
                      is long enough that the repeat's target lies inside
                      it, this reproduces normal repeat playback for free.
          second    - pre-marked as if one full pass already happened: every
                      repeat consumed, every first-time ending skipped, so
                      the iteration runs linearly through the second
                      play-through (first-time endings skipped, final
                      endings played).
          alternate - the "first" seed on an even iteration_count, the
                      "second" seed on an odd one.

        The "first-time ending" is the one whose measure range spans a
        repeat's backward barline - the exact condition
        PlaybackEventBuilder._jump_from_measure_end uses to mark an ending
        skipped when a real repeat retake happens, so a long-window "second"
        loop and a normal second pass agree on which endings vanish.
        """
        if not self.music_data:
            return None
        if mode == "alternate":
            mode = "first" if iteration_count % 2 == 0 else "second"
        if mode != "second":
            return None
        repeats = self.music_data.repeat_spans
        endings = self.music_data.ending_spans
        endings_to_skip = {
            j
            for rs in repeats
            for j, es in enumerate(endings)
            if es.start_measure <= rs.end_measure <= es.end_measure
        }
        return PlaybackJumpState(
            repeats_taken=set(range(len(repeats))),
            endings_to_skip=endings_to_skip,
            jump_taken=True,
        )

    def _start_play_iteration(self, with_lead_in: bool) -> None:
        """Build one iteration's event schedule - count-in clicks, the
        moment the notes start, and (looping only) the bar line where the
        next repeat begins - then walk it with the chained timer."""
        run = self._play_run
        if run is None or not self.music_data:
            return
        # See _refresh_play_span's own docstring: keeps a loop repeat's
        # own restart timing current, not just the count-in's bpm below.
        self._refresh_play_span(run)

        start_slice = self.music_data.timeline_slices[run.start_index]
        ts_num, ts_den = start_slice.time_sig
        # Re-derived per iteration, so an F/S/D tempo change during a loop
        # takes effect from the next repeat rather than never.
        bpm = self.music_data.effective_tempo_bpm(run.start_index)

        events: List[Tuple[int, Tuple[Any, ...]]] = []
        lead_in_ms = 0
        # The silent gap between the last count-in click and the note
        # itself. Ordinarily that is just run.offset_ms (the bar-line-to-
        # first-note gap, 0 for a pickup - see _build_play_run). A pickup
        # gets a different value here: see the pickup padding below.
        play_gap_ms = run.offset_ms
        if with_lead_in:
            # Back to the count-in phase, which the status field reports as
            # Lead-in rather than Preview - true on a loop repeat too.
            run.playing = False
            lead_in_beats = run.settings.lead_in_beats
            if run.is_pickup:
                # Reported from real practice use: a pickup's own notated
                # beat position (e.g. beat 4 of a 4/4 bar) is not where the
                # requested lead-in should end - counting only "1, 2, 3, 4"
                # and landing exactly on the pickup's own beat leaves the
                # anacrusis itself uncounted. The user's ask: play the
                # requested lead-in in full, THEN keep counting through
                # whatever beats are needed to complete the anacrusis into a
                # whole bar, so the pickup sounds exactly where a real beat
                # 1 would follow - e.g. one bar of lead-in ahead of a
                # one-beat pickup in 4/4 counts "1, 2, 3, 4, 1, 2, 3", not
                # "4, 1, 2, 3". The count-in's own anchor (start_beat_position,
                # below) already lands the LAST click one beat before the
                # pickup's real notated position, so padding total_beats
                # with the pickup's own missing whole beats is all that is
                # needed - build_lead_in_schedule's backward-counting keeps
                # every click correctly numbered.
                #
                # A pickup that starts mid-beat (e.g. a beat 2.5 anacrusis -
                # 1.5 beats of real content in 4/4) leaves a fractional
                # leftover after the last WHOLE beat is counted - clicks
                # only ever land on whole beats (audio/metronome.py's
                # click_event_for_beat), so that remainder is a silent wait
                # after the count-in rather than another click.
                gap_beats = max(0.0, start_slice.beat_position - 1.0)
                whole_gap_beats = int(gap_beats + 1e-6)
                fractional_beats = max(0.0, gap_beats - whole_gap_beats)
                lead_in_beats += whole_gap_beats
                beat_ms = (4.0 / float(ts_den or 4)) * 60000.0 / bpm
                play_gap_ms = int(round(fractional_beats * beat_ms))
            clicks, lead_in_ms = build_lead_in_schedule(
                run.settings.lead_in_bars,
                lead_in_beats,
                ts_num,
                ts_den,
                bpm,
                start_beat_position=start_slice.beat_position,
            )
            events.extend((offset, ("count", beat)) for offset, beat in clicks)

        events.append((lead_in_ms + play_gap_ms, ("play",)))
        # No ("loop",) event is scheduled here any more, for EITHER loop
        # mode. "loop once" ends via _on_sequencer_finished; "loop until
        # stopped" restarts from there too, off the Sequencer's own
        # `finished` signal plus loop_tail_pad_ms - anchored to the
        # Sequencer's real progress so per-step timer drift can't
        # accumulate into an early restart that clips the last note
        # (reported: etude 2, bar 3, loop length 3, 44 bpm).

        run.events = sorted(events, key=lambda event: event[0])
        run.event_index = 0
        run.elapsed_ms = 0
        if with_lead_in:
            # Nothing sounds for a whole count-in, so the status field is
            # the only sign Enter was heard at all - update it now rather
            # than at the first note.
            self.playback_state_changed.emit()
        self._advance_play()

    def _advance_play(self) -> None:
        """Fire every event due at the current position, then arm the timer
        for the next one. Events due at 0 fire synchronously, so a preview
        with no lead-in still starts sounding within the keypress that asked
        for it, exactly as it did before this feature existed."""
        run = self._play_run
        if run is None:
            return
        while run.event_index < len(run.events):
            due_ms, action = run.events[run.event_index]
            if due_ms > run.elapsed_ms:
                self._play_timer.start(due_ms - run.elapsed_ms)
                return
            run.event_index += 1
            self._fire_play_event(action)
            # A loop repeat rebuilds run.events and re-arms the timer from
            # scratch, and a stop drops the session entirely - either way
            # this walk is finished with the schedule it was reading.
            if self._play_run is not run or run.event_index == 0:
                return
        # Nothing further scheduled: a non-looping preview is now just the
        # Sequencer running to its own end, which ends the session (see
        # _on_sequencer_finished).

    def _on_play_timer(self) -> None:
        run = self._play_run
        if run is None:
            return
        run.elapsed_ms = run.events[run.event_index][0]
        self._advance_play()

    def _fire_play_event(self, action: Tuple[Any, ...]) -> None:
        run = self._play_run
        if run is None or not self.music_data:
            return
        kind = action[0]
        if kind == "count":
            self._sound_count_in_beat(action[1])
        elif kind == "play":
            run.playing = True
            if self.sequencer is not None:
                if run.looping and run.respect_repeats:
                    # No linear end_index - the iteration follows
                    # repeats/endings and stops on a bar-count budget, and
                    # jump_lower_bound=0 lets a backward repeat land before
                    # the window. The seed picks which play-through of a
                    # clipped repeat this iteration loops.
                    self.sequencer.play_from(
                        run.start_index,
                        end_index=None,
                        update_cursor=False,
                        jump_lower_bound=0,
                        initial_jump_state=run.seed_jump_state,
                        measure_budget=run.settings.loop_length_bars,
                    )
                elif run.looping:
                    self.sequencer.play_from(
                        run.start_index,
                        end_index=run.end_index,
                        update_cursor=False,
                        jump_lower_bound=run.start_index,
                    )
                else:
                    # Lead-in only: play to the end of the score, cursor
                    # following, ending on its own via _on_sequencer_finished.
                    self.sequencer.play_from(run.start_index, update_cursor=True)
            self.playback_state_changed.emit()
        elif kind == "loop":
            # Advance the iteration counter BEFORE the next iteration is
            # built, so "alternate" mode's _loop_seed_jump_state (called
            # from _start_play_iteration -> _refresh_play_span) sees the new
            # count.
            run.iteration_count += 1
            self._start_play_iteration(
                with_lead_in=run.settings.loop_lead_in and run.settings.has_lead_in()
            )

    def _sound_count_in_beat(self, beat_position: float) -> None:
        """One beat of the count-in. The click always sounds during a
        lead-in (the lead-in tickbox IS "play the count-in click"; there is
        no silent-numbers-only count-in any more), independent of the Ctrl+M
        metronome toggle. The spoken beat number follows Ctrl+P - the user's
        decision: with the announcer on, hearing "three, four" is the
        clearest signal of where the downbeat lands. Muting (wishlist #7)
        silences both without changing the timing."""
        if self._muted:
            return
        click = click_event_for_beat(beat_position)
        if click is not None:
            self.synth.play_click(*click)
        if self.music_data and self.music_data.position_announcer_enabled:
            announcement = announcement_event_for_beat(beat_position)
            if announcement is not None:
                self.synth.play_word(*announcement)

    def cancel_play_run(self) -> None:
        """Drop the session and its pending schedule. Silencing and stopping
        the Sequencer stays with the callers that need it - stop() and
        attach_score both do that themselves."""
        self._play_timer.stop()
        self._play_run = None

    def _on_sequencer_step(self, index: int) -> None:
        """Ref 10 AC4: a cursor-tracking run moves active_event_index and
        refreshes the regions as it goes. That is what makes "pause
        refreshes the regions" true for free - they already track the live
        position throughout, not just at the moment of pausing.

        A looping run also tracks here even though the Sequencer's own
        update_cursor is False for it (so the Sequencer's stop/finish
        reversion can't move the cursor): the Note region should follow the
        loop just as it follows a plain lead-in run. stop() puts the cursor
        back to the loop's start (run.restore_index) afterwards."""
        if self.sequencer is None or not self.music_data:
            return
        looping_run = self._play_run is not None and self._play_run.looping
        if not self.sequencer.update_cursor and not looping_run:
            return
        self.music_data.active_event_index = index
        self.cursor_moved.emit(False)

    def _on_sequencer_finished(self) -> None:
        """A run ending on its own flips is_playing without anyone calling
        stop(). The Sequencer reverts to the original start position when
        that happens (AC5's "stopping reverts" applies to reaching the end
        too - the user's decision), so a cursor-tracking run must sync the
        regions to that reverted position exactly as stop() does, rather
        than leaving them on the last note.

        A non-looping play run (lead-in only) AND a "loop once" run both end
        for good here. A "loop until stopped" run does NOT end - it restarts
        the next iteration off THIS signal (plus loop_tail_pad_ms), which is
        the whole point: `finished` fires only once every chained Sequencer
        step has actually run and the last note's ring-out has been waited
        out, so any accumulated per-step timer drift is already absorbed and
        the restart can't land early and clip the last note."""
        run = self._play_run
        # "loop once" (looping window, but loop_forever False) terminates
        # like a lead-in run - and, having tracked the Note region through
        # the single pass with update_cursor False, it restores the cursor
        # to where the loop started, exactly as stop() does for a stopped
        # "loop until stopped" run.
        ends_now = run is not None and (not run.looping or not run.settings.loop_forever)
        loop_once_restore = (
            run.restore_index if (ends_now and run is not None and run.looping) else None
        )
        if ends_now:
            self.cancel_play_run()
        if self.sequencer.update_cursor and self.music_data:
            self.music_data.active_event_index = self.sequencer.current_index
            self.cursor_moved.emit(False)
        elif loop_once_restore is not None and self.music_data:
            self.music_data.active_event_index = loop_once_restore
            self.cursor_moved.emit(False)
        elif run is not None and run.looping and not ends_now and self.music_data:
            # "loop until stopped", between iterations: snap the Note region
            # back to the loop's start so it matches what the next iteration
            # is about to sound rather than sitting on the last note through
            # the bar-line gap, then arm the restart. loop_tail_pad_ms is 0
            # in the common case, so _advance_play fires ("loop",)
            # synchronously and the next iteration starts right here.
            self.music_data.active_event_index = run.start_index
            self.cursor_moved.emit(False)
            self.playback_state_changed.emit()
            # Arm the restart through _play_timer (never synchronously from
            # inside this `finished` slot): _on_play_timer -> _advance_play
            # fires the ("loop",) event, which rebuilds the next iteration.
            # A 0ms pad still defers to the next event-loop turn, keeping the
            # Sequencer out of a re-entrant play_from.
            run.events = [(max(0, run.loop_tail_pad_ms), ("loop",))]
            run.event_index = 0
            run.elapsed_ms = 0
            self._play_timer.start(max(0, run.loop_tail_pad_ms))
            return
        self.playback_state_changed.emit()

    # --- tempo -------------------------------------------------------

    def tempo_faster(self) -> None:
        """F (Ref 12 AC3): +10 on the absolute playback tempo (in
        time-signature-denominator beats), clamped to the 5-300 bounds.
        Does not move the timeline or re-audition."""
        if not self.music_data:
            return
        self.music_data.nudge_playback_tempo(10)
        self.status_text_changed.emit()

    def tempo_slower(self) -> None:
        """S (Ref 12 AC3): -10 on the absolute playback tempo."""
        if not self.music_data:
            return
        self.music_data.nudge_playback_tempo(-10)
        self.status_text_changed.emit()

    def tempo_reset(self) -> None:
        """D (Ref 12 AC4): reset playback tempo to the score's own tempo."""
        if not self.music_data:
            return
        self.music_data.reset_playback_tempo()
        self.status_text_changed.emit()

    def set_playback_tempo(self, display_bpm: float) -> None:
        """The Play Settings dialog's absolute tempo field. display_bpm is
        in the time-signature denominator beat at the cursor; MusicData
        clamps and converts to its stored quarter-note BPM."""
        if not self.music_data:
            return
        self.music_data.set_playback_tempo_display_bpm(display_bpm)
        self.status_text_changed.emit()

    # --- toggles -----------------------------------------------------

    def toggle_metronome(self) -> bool:
        """Ctrl+M (Ref 14). Returns the new state so the caller can keep the
        menu action checked in sync."""
        if not self.music_data:
            return False
        self.music_data.toggle_metronome()
        self.status_text_changed.emit()
        return self.music_data.metronome_enabled

    def toggle_position_announcer(self) -> bool:
        """Ctrl+P (Ref 28): mirrors toggle_metronome, but needs no timeline
        rebuild (see MusicData.position_announcer_enabled)."""
        if not self.music_data:
            return False
        self.music_data.toggle_position_announcer()
        self.status_text_changed.emit()
        return self.music_data.position_announcer_enabled

    # --- play metronome (Alt+Space) --------------------------------------

    @property
    def is_play_metronome_running(self) -> bool:
        return self._play_metronome_timer.isActive()

    def toggle_play_metronome(self) -> bool:
        """Ctrl+Alt+Space: start/stop a free-running metronome click. It
        sounds at the current playback tempo (F/S/D adjustments included)
        and the time signature at the cursor, never moves the timeline, and
        is separate from the Ctrl+M score metronome. Returns the new on/off
        state."""
        if self.is_play_metronome_running:
            self.stop_play_metronome()
            return False
        if not self.music_data:
            return False
        self._play_metronome_beat = 1
        self._sound_play_metronome_beat()
        return True

    def stop_play_metronome(self) -> None:
        self._play_metronome_timer.stop()

    def _sound_play_metronome_beat(self) -> None:
        """Sound the current beat's click and arm the timer for the next.
        Tempo and time signature are re-read every beat, so a tempo change
        or a cursor move to a differently-metred bar is picked up on the
        next click rather than needing a restart."""
        if not self.music_data:
            self._play_metronome_timer.stop()
            return
        ts_num, ts_den = 4, 4
        current = self.music_data.get_current_slice()
        if current is not None and current.time_sig:
            ts_num, ts_den = current.time_sig
        beat = self._play_metronome_beat
        if not self._muted:
            click = click_event_for_beat(float(beat))
            if click is not None:
                self.synth.play_click(*click)
        self._play_metronome_beat = beat + 1 if beat < max(1, ts_num) else 1
        quarter_bpm = self.music_data.effective_tempo_bpm()
        beat_ms = (4.0 / float(ts_den or 4)) * 60000.0 / float(quarter_bpm)
        self._play_metronome_timer.start(max(1, int(round(beat_ms))))

    # --- sounding ----------------------------------------------------

    def play_boundary_cue(self) -> None:
        """Sounds INSTEAD of moving, when a navigation key would go past a
        boundary of the active timeline (Ref 2 AC4/Ref 3 AC4)."""
        if self._muted:
            return
        self.synth.play_notes(
            midi_notes=[self.BOUNDARY_MIDI_PITCH],
            duration_ms=self.BOUNDARY_DURATION_MS,
            channel=self.BOUNDARY_CHANNEL,
            program=self.BOUNDARY_GM_PROGRAM,
        )

    def audition_selection(
        self, selected_indices: List[int], with_position_cues: bool = True
    ) -> None:
        """Sound the given Region 3 rows, plus the click and spoken position
        if they are on. Indices are passed in rather than read off the
        widget, so this stays widget-free.

        `with_position_cues=False` sounds only the notes: an Up/Down move
        within the current slice (e.g. stepping through a chord's notes)
        stays on the same timeline position and beat, so re-firing the
        metronome click and the spoken beat position there is just noise -
        those cues belong to real timeline movement (arrow / Ctrl+arrow /
        Alt+arrow / go-to-bar), which always passes the default True."""
        if not self.music_data or self._muted:
            return

        events = self.music_data.get_playback_events_for_indices(selected_indices)
        grace_events = self.music_data.get_grace_note_events_for_indices(selected_indices)

        # sound_events (audio/strum_schedule.py) routes a selection with a
        # MusicXML grace note through play_chord_with_grace, else falls
        # straight through to the unchanged play_chord path used by every
        # format (UG chords included - per-chord strumming was removed) -
        # each group still carries its own duration, so no slice-wide
        # duration_ms is needed here.
        sound_events(self.synth, self.music_data, events, retrigger=True, grace_events=grace_events)

        if not with_position_cues:
            return

        # Ref 14 AC3: fires even with no events at all (a metronome-only
        # beat marker), which is why it isn't folded into `if events`.
        if self.music_data.metronome_enabled:
            current = self.music_data.get_current_slice()
            if current is not None:
                click = click_event_for_beat(current.beat_position)
                if click is not None:
                    self.synth.play_click(*click)

        # Ref 28 AC1/AC2: independent of the click, same "fires with no
        # notes here" reasoning.
        if self.music_data.position_announcer_enabled:
            current = self.music_data.get_current_slice()
            if current is not None:
                announcement = announcement_event_for_beat(current.beat_position)
                if announcement is not None:
                    self.synth.play_word(*announcement)

    # --- status text -------------------------------------------------

    def status_fields(self) -> List[str]:
        """The three status-bar fields describing playback state, appended
        after MusicData's own position/key/time/tempo fields."""
        return [
            self.playback_status_text(),
            self.metronome_status_text(),
            self.position_announcer_status_text(),
            self.loop_length_status_text(),
        ]

    def playback_status_text(self) -> str:
        """Playing/Paused/Stopped from the Sequencer - deliberately not a
        MusicData concern, describing UI state rather than the score.

        A play run reports its own phase first: during the count-in nothing
        is sounding yet and the Sequencer would say "Stopped", which reads
        as "Space did nothing". Looping is called out because it is the one
        state that will not end on its own."""
        if self._play_run is not None:
            if not self._play_run.playing:
                return "Playback: Lead-in"
            if self._play_run.looping:
                if self._play_run.settings.loop_forever:
                    return "Playback: Playing (looping)"
                return "Playback: Playing (loop once)"
            return "Playback: Playing"
        if self.sequencer is not None and self.sequencer.is_paused:
            return "Playback: Paused"
        if self.sequencer is not None and self.sequencer.is_playing:
            return "Playback: Playing"
        return "Playback: Stopped"

    def metronome_status_text(self) -> str:
        """Ref 14: On/Off, since there is otherwise no way to check the
        metronome without listening for a click."""
        if self.music_data and self.music_data.metronome_enabled:
            return "Metronome: On"
        return "Metronome: Off"

    def position_announcer_status_text(self) -> str:
        """Ref 28: same discoverability reasoning as the metronome field."""
        if self.music_data and self.music_data.position_announcer_enabled:
            return "Position Announcer: On"
        return "Position Announcer: Off"

    def loop_length_status_text(self) -> str:
        """Alt+PageUp/PageDown (adjust_loop_length_bars) and the typed
        Ctrl+Enter buffer have no visible control to read the current value
        off, unlike a spin box in the dialog - so the count is shown here
        the same way the metronome/announcer toggles are."""
        bar = bar_word(self.session.uk_terms) if self.session else "bar"
        return f"Loop length: {self.play_settings.loop_length_bars} {bar}s"
