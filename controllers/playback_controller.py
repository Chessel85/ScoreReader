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
from models.preview_settings import PreviewSettings
from models.vocabulary import bar_word


@dataclass
class _PreviewRun:
    """One Preview session: the resolved span, the settings snapshot taken
    when it started, and the schedule of the iteration currently running.

    The session outlives the Sequencer run inside it - it also covers the
    lead-in before any note sounds and the wait to the bar line before a
    loop repeats, neither of which the Sequencer knows about. That is why
    Enter's "stop what's running" test is is_preview_active and not
    sequencer.is_playing.
    """

    settings: PreviewSettings
    start_index: int
    end_index: int
    end_quarters: float
    # True when start_index falls in a pickup bar (Ref 17): a count-in ahead
    # of it must keep counting past the requested lead-in to also complete
    # the pickup's own bar - see _start_preview_iteration.
    is_pickup: bool
    # Silence between the bar line and the first note, for a previewed bar
    # that opens with a rest - kept so a repeat stays in time rather than
    # sliding forward by that gap. 0 for a pickup (its real content starts
    # at the piece's own start, not after some silence) - used as-is for a
    # LOOP repeat with no lead-in of its own; a lead-in ahead of a pickup
    # computes its own play_gap_ms instead (_start_preview_iteration).
    offset_ms: int
    # Bar line to bar line: what one loop iteration lasts.
    iteration_ms: int
    # (offset_ms within the iteration, action) in time order, walked by one
    # chained single-shot timer - the same "reschedule a step at a time so
    # cancelling is one stop()" shape as audio/sequencer.py.
    events: List[Tuple[int, Tuple[Any, ...]]] = field(default_factory=list)
    event_index: int = 0
    elapsed_ms: int = 0
    playing: bool = False


class PlaybackController(QObject):
    """Everything that makes sound, and the transport state around it:
    Sequencer lifecycle, play/pause/stop, phrase audition, tempo offset,
    chord audition, the boundary cue, and the metronome/announcer toggles.

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
        # Preview (Enter/Playback > Preview): lead-in, length and looping.
        # Global settings, pushed in by MainWindow from AppSettings on
        # startup and again whenever the dialog is accepted.
        self.preview_settings = PreviewSettings()
        self._preview: Optional[_PreviewRun] = None
        # timer: injectable like Sequencer's, so tests can drive the
        # count-in and the loop without waiting on the clock.
        if timer is None:
            timer = QTimer(self)
            # See Sequencer.__init__'s own comment - the same fast-tempo
            # drift applies to the count-in/loop-restart chain here.
            timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._preview_timer = timer
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._on_preview_timer)

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
        self.cancel_preview()
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
        self.cancel_preview()
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

        `is_preview_active` as well as the Sequencer's own flags: a preview
        can have a count-in or a loop pending that `is_playing`/`is_paused`
        cannot see, so checking the Sequencer alone would leave it running
        after the dialog closed.
        """
        if accepted:
            self.commit_mixer_edit()
        else:
            self.cancel_mixer_edit()
        sequencer_running = self.sequencer is not None and (
            self.sequencer.is_playing or self.sequencer.is_paused
        )
        if self.is_preview_active or sequencer_running:
            self.stop()

    # --- transport ---------------------------------------------------

    def toggle_play_stop(self) -> None:
        """Space (Ref 10): not playing -> start from the cursor; playing ->
        stop, silence and revert to the start; paused -> resume. Space owns
        both starting and resuming; Ctrl+Space only pauses.

        From the last note it sounds the boundary cue instead of playing:
        there is nothing ahead to play, the same "can't go further" signal
        Left/Right give."""
        if not self.music_data or self.sequencer is None:
            return
        if self._preview is not None:
            # A preview may be mid-count-in with nothing sounding yet, which
            # is_playing cannot see - without this, Space would start a
            # second, overlapping run underneath the count-in.
            self.stop()
            return
        if self.sequencer.is_paused:
            self.sequencer.resume()
            self.playback_state_changed.emit()
        elif self.sequencer.is_playing:
            self.stop()
        else:
            start_index = self.music_data.active_event_index
            if self.music_data.next_visible_event_index(start_index) is None:
                self.play_boundary_cue()
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
        if self._preview is not None:
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
        """Shared by Space and Enter, which both stop whatever is running
        before starting anything new. Only a cursor-tracking run syncs
        active_event_index and the regions back afterwards - a phrase
        audition never moved them - but the status field always updates.

        Cancelling the preview session first is what makes Enter (or Space)
        stop a count-in that has not sounded a note yet."""
        self.cancel_preview()
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
        else:
            self.playback_state_changed.emit()

    def audition_phrase(self) -> None:
        """Enter with no pending digits (Ref 11): preview from beat 1 of
        this measure, after the count-in and for as many bars as
        preview_settings asks for, repeating if it says to. Enter again
        while a preview is running stops it - including during the count-in
        and between loop repeats - rather than starting an overlapping run.
        """
        if not self.music_data or self.sequencer is None:
            return
        if self._preview is not None or self.sequencer.is_playing or self.sequencer.is_paused:
            self.stop()
            return

        run = self._build_preview_run()
        if run is None:
            return
        self._preview = run
        self._start_preview_iteration(with_lead_in=run.settings.has_lead_in())

    def phrase_end_index(self, current_measure: int, start_index: int, bars: int = 2) -> int:
        """Through the end of the (bars-1)th measure after this one, or the
        last sounding event if the piece ends first - bounded so a preview
        can't run on into trailing rest-only padding, and so a preview
        length reaching past the end of the piece simply ends there."""
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

    # --- preview session ---------------------------------------------

    @property
    def is_preview_active(self) -> bool:
        """True from the first tick of the count-in until the preview stops
        - the check callers need instead of sequencer.is_playing, which is
        False during the lead-in and between loop repeats."""
        return self._preview is not None

    def set_preview_settings(self, settings: PreviewSettings) -> None:
        """Applied to the NEXT preview: a running session keeps its own
        snapshot, so accepting the dialog can't change what a loop is doing
        half way through."""
        self.preview_settings = settings.copy()

    def adjust_preview_bars(self, delta: int) -> None:
        """Alt+PageUp/PageDown in the Note region: lengthen/shorten the
        preview span by one bar per press (reported from real practice use
        - the fixed length the Preview Settings dialog sets was awkward to
        retune mid-session). Alt avoids the native PageUp/PageDown paging
        QListWidget already gives Region 3 - the same reason Ctrl is used
        for measure-at-a-time Left/Right there.

        Applies to the NEXT preview, exactly like the dialog's OK - a
        running preview keeps its own already-started snapshot. Clamped at
        MIN_PREVIEW_BARS only; there is no practical upper bound the user
        asked for (see MAX_PREVIEW_BARS's own comment for why a very high
        one still exists internally)."""
        self.preview_settings = self.preview_settings.with_preview_bars(
            self.preview_settings.preview_bars + delta
        )
        self.status_text_changed.emit()

    def set_preview_length_bars(self, bars: int) -> None:
        """The voice command "loop length N" (Ref 19, audio/voice_commands.
        LOOP_LENGTH) - sets the NEXT preview's length directly, unlike
        adjust_preview_bars' relative +/-1 nudge. Clamped by PreviewSettings
        itself, same as every other entry point (the dialog, Alt+PageUp/
        PageDown)."""
        self.preview_settings = self.preview_settings.with_preview_bars(bars)
        self.status_text_changed.emit()

    def _build_preview_run(self) -> Optional["_PreviewRun"]:
        """Resolve where the preview starts and ends, in both index and
        real-time terms. Returns None when there is nothing to play."""
        current = self.music_data.get_current_slice()
        if current is None:
            return None
        start_index = self.music_data.first_visible_event_index_of_measure(current.measure)
        if start_index is None:
            return None

        settings = self.preview_settings.copy()
        end_index = self.phrase_end_index(current.measure, start_index, settings.preview_bars)

        # The loop repeats on the BAR LINE after the last previewed bar, not
        # when the last note stops ringing: a bar ending in rests would
        # otherwise restart early and out of time, which is useless to play
        # along to. bar_bounds_quarters derives that from the slice itself
        # (see MusicData). A preview length running past the end of the
        # piece is already clamped by phrase_end_index, so the last bar of
        # the piece becomes the end of the loop.
        start_slice = self.music_data.timeline_slices[start_index]
        start_bar = self.music_data.bar_bounds_quarters(start_index)
        end_bar = self.music_data.bar_bounds_quarters(end_index)
        # A pickup bar's (Ref 17) NOTIONAL start is before the piece begins,
        # so its unclamped bar start comes back negative - that is the
        # signal is_pickup keys off. The matching clamp lives in
        # _refresh_preview_span, which needs it to derive offset_ms and
        # recomputes it per loop iteration; a duplicate sat here unused
        # from the commit that moved that calculation out (5eb1101), and
        # was removed rather than kept in sync with nothing reading it.
        is_pickup = bool(start_bar and start_bar[0] < 0)
        end_quarters = end_bar[1] if end_bar else start_slice.quarters_from_start

        run = _PreviewRun(
            settings=settings,
            start_index=start_index,
            end_index=end_index,
            end_quarters=end_quarters,
            is_pickup=is_pickup,
            offset_ms=0,
            iteration_ms=0,
        )
        self._refresh_preview_span(run)
        return run

    def _refresh_preview_span(self, run: "_PreviewRun") -> None:
        """(Re)computes offset_ms/iteration_ms from the CURRENT tempo -
        called both when a run is first built and again at the top of every
        _start_preview_iteration call (including a loop repeat), so an
        F/S/D tempo change made while Preview is already looping is
        reflected in the very next loop-restart's timing rather than
        replaying a stale span computed at whatever tempo was in force when
        Enter was first pressed. Reported live: speeding up ~40bpm while a
        repeat-containing passage was already looping left the loop-restart
        (and the lead-in count-in it schedules) drifting out of time -
        _start_preview_iteration's own bpm (used for the count-in clicks)
        was already re-derived per iteration (see its own comment below),
        but iteration_ms/offset_ms - the loop-restart's own timing - were
        computed once in _build_preview_run and never touched again."""
        start_slice = self.music_data.timeline_slices[run.start_index]
        start_bar = self.music_data.bar_bounds_quarters(run.start_index)
        # Clamped at 0 for a pickup bar, whose NOTIONAL start is before the
        # piece begins - see is_pickup/_build_preview_run's own comment.
        bar_start_quarters = max(0.0, start_bar[0]) if start_bar else start_slice.quarters_from_start
        lead_quarters = max(0.0, start_slice.quarters_from_start - bar_start_quarters)
        bpm = self.music_data.effective_tempo_bpm(run.start_index)
        run.offset_ms = int(round(lead_quarters * 60000.0 / float(bpm)))
        # Jump-aware, not span_ms_to_quarters's flat walk - a repeat fully
        # inside the preview window makes the real Sequencer run take longer
        # than a naive linear walk would predict, and this drives the
        # loop-restart timer below (iteration_ms), so it must know about it
        # too or a contained repeat gets truncated mid-replay.
        span_ms = self.music_data.playback_span_ms(run.start_index, run.end_index, run.end_quarters)
        run.iteration_ms = run.offset_ms + span_ms

    def _start_preview_iteration(self, with_lead_in: bool) -> None:
        """Build one iteration's event schedule - count-in clicks, the
        moment the notes start, and (looping only) the bar line where the
        next repeat begins - then walk it with the chained timer."""
        run = self._preview
        if run is None or not self.music_data:
            return
        # See _refresh_preview_span's own docstring: keeps a loop repeat's
        # own restart timing current, not just the count-in's bpm below.
        self._refresh_preview_span(run)

        start_slice = self.music_data.timeline_slices[run.start_index]
        ts_num, ts_den = start_slice.time_sig
        # Re-derived per iteration, so an F/S/D tempo change during a loop
        # takes effect from the next repeat rather than never.
        bpm = self.music_data.effective_tempo_bpm(run.start_index)

        events: List[Tuple[int, Tuple[Any, ...]]] = []
        lead_in_ms = 0
        # The silent gap between the last count-in click and the note
        # itself. Ordinarily that is just run.offset_ms (the bar-line-to-
        # first-note gap, 0 for a pickup - see _build_preview_run). A pickup
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
        if run.settings.loop and run.iteration_ms > run.offset_ms:
            events.append((lead_in_ms + run.iteration_ms, ("loop",)))

        run.events = sorted(events, key=lambda event: event[0])
        run.event_index = 0
        run.elapsed_ms = 0
        if with_lead_in:
            # Nothing sounds for a whole count-in, so the status field is
            # the only sign Enter was heard at all - update it now rather
            # than at the first note.
            self.playback_state_changed.emit()
        self._advance_preview()

    def _advance_preview(self) -> None:
        """Fire every event due at the current position, then arm the timer
        for the next one. Events due at 0 fire synchronously, so a preview
        with no lead-in still starts sounding within the keypress that asked
        for it, exactly as it did before this feature existed."""
        run = self._preview
        if run is None:
            return
        while run.event_index < len(run.events):
            due_ms, action = run.events[run.event_index]
            if due_ms > run.elapsed_ms:
                self._preview_timer.start(due_ms - run.elapsed_ms)
                return
            run.event_index += 1
            self._fire_preview_event(action)
            # A loop repeat rebuilds run.events and re-arms the timer from
            # scratch, and a stop drops the session entirely - either way
            # this walk is finished with the schedule it was reading.
            if self._preview is not run or run.event_index == 0:
                return
        # Nothing further scheduled: a non-looping preview is now just the
        # Sequencer running to its own end, which ends the session (see
        # _on_sequencer_finished).

    def _on_preview_timer(self) -> None:
        run = self._preview
        if run is None:
            return
        run.elapsed_ms = run.events[run.event_index][0]
        self._advance_preview()

    def _fire_preview_event(self, action: Tuple[Any, ...]) -> None:
        run = self._preview
        if run is None or not self.music_data:
            return
        kind = action[0]
        if kind == "count":
            self._sound_count_in_beat(action[1], run.settings.lead_in_click)
        elif kind == "play":
            run.playing = True
            if self.sequencer is not None:
                self.sequencer.play_from(
                    run.start_index,
                    end_index=run.end_index,
                    update_cursor=False,
                    jump_lower_bound=run.start_index,
                )
            self.playback_state_changed.emit()
        elif kind == "loop":
            self._start_preview_iteration(
                with_lead_in=run.settings.loop_includes_lead_in and run.settings.has_lead_in()
            )

    def _sound_count_in_beat(self, beat_position: float, click_enabled: bool) -> None:
        """One beat of the count-in. The click follows the preview's own
        setting rather than the Ctrl+M metronome toggle (a count-in is
        wanted whether or not the piece itself is being clicked), while the
        spoken beat number follows Ctrl+P - the user's decision: with the
        announcer on, hearing "three, four" is the clearest signal of where
        the downbeat lands. Muting (wishlist #7) silences both without
        changing the timing."""
        if self._muted:
            return
        if click_enabled:
            click = click_event_for_beat(beat_position)
            if click is not None:
                self.synth.play_click(*click)
        if self.music_data and self.music_data.position_announcer_enabled:
            announcement = announcement_event_for_beat(beat_position)
            if announcement is not None:
                self.synth.play_word(*announcement)

    def cancel_preview(self) -> None:
        """Drop the session and its pending schedule. Silencing and stopping
        the Sequencer stays with the callers that need it - stop() and
        attach_score both do that themselves."""
        self._preview_timer.stop()
        self._preview = None

    def _on_sequencer_step(self, index: int) -> None:
        """Ref 10 AC4: a cursor-tracking run moves active_event_index and
        refreshes the regions as it goes. That is what makes "pause
        refreshes the regions" true for free - they already track the live
        position throughout, not just at the moment of pausing."""
        if self.sequencer is None or not self.sequencer.update_cursor or not self.music_data:
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

        A one-shot preview ends here too. A LOOPING one does not: its own
        timer is still counting down to the bar line, and the Sequencer
        finishing simply means the last note of this repeat has rung out."""
        if self._preview is not None and not self._preview.settings.loop:
            self.cancel_preview()
        if self.sequencer.update_cursor and self.music_data:
            self.music_data.active_event_index = self.sequencer.current_index
            self.cursor_moved.emit(False)
        self.playback_state_changed.emit()

    # --- tempo -------------------------------------------------------

    def tempo_faster(self) -> None:
        """F (Ref 12 AC3): +10bpm, clamped to the 30-300bpm bounds. Does not
        move the timeline or re-audition."""
        if not self.music_data:
            return
        self.music_data.set_playback_tempo_offset(self.music_data.playback_tempo_offset + 10)
        self.status_text_changed.emit()

    def tempo_slower(self) -> None:
        """S (Ref 12 AC3): -10bpm to the playback tempo offset."""
        if not self.music_data:
            return
        self.music_data.set_playback_tempo_offset(self.music_data.playback_tempo_offset - 10)
        self.status_text_changed.emit()

    def tempo_reset(self) -> None:
        """D (Ref 12 AC4): reset playback tempo to the score's own tempo."""
        if not self.music_data:
            return
        self.music_data.reset_playback_tempo()
        self.status_text_changed.emit()

    def set_tempo_offset(self, offset: float) -> None:
        if not self.music_data:
            return
        self.music_data.set_playback_tempo_offset(offset)
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

    def audition_selection(self, selected_indices: List[int]) -> None:
        """Sound the given Region 3 rows, plus the click and spoken position
        if they are on. Indices are passed in rather than read off the
        widget, so this stays widget-free."""
        if not self.music_data or self._muted:
            return

        events = self.music_data.get_playback_events_for_indices(selected_indices)
        grace_events = self.music_data.get_grace_note_events_for_indices(selected_indices)

        # sound_events (audio/strum_schedule.py) routes a UG score's Chords
        # bar through a real strummed pattern (play_strummed_bar) when one
        # is available, a selection with a MusicXML grace note through
        # play_chord_with_grace, else falls straight through to the
        # unchanged play_chord path used by every other format - each group
        # still carries its own duration, so no slice-wide duration_ms is
        # needed here.
        sound_events(self.synth, self.music_data, events, retrigger=True, grace_events=grace_events)

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
            self.preview_length_status_text(),
        ]

    def playback_status_text(self) -> str:
        """Playing/Paused/Stopped from the Sequencer - deliberately not a
        MusicData concern, describing UI state rather than the score.

        A preview reports its own phase first: during the count-in nothing
        is sounding yet and the Sequencer would say "Stopped", which reads
        as "Enter did nothing". Looping is called out because it is the one
        state that will not end on its own."""
        if self._preview is not None:
            if not self._preview.playing:
                return "Playback: Lead-in"
            if self._preview.settings.loop:
                return "Playback: Preview (looping)"
            return "Playback: Preview"
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

    def preview_length_status_text(self) -> str:
        """Alt+PageUp/PageDown (adjust_preview_bars) has no visible control
        to read the current value off, unlike a spin box in the dialog - so
        the count is announced here the same way the metronome/announcer
        toggles are, rather than only being discoverable by starting a
        preview and counting bars."""
        bar = bar_word(self.session.uk_terms) if self.session else "bar"
        return f"Preview length: {self.preview_settings.preview_bars} {bar}s"
