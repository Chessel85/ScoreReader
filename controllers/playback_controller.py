# controllers/playback_controller.py
from typing import List, Optional, Tuple

from PySide6.QtCore import QObject, Signal

from audio.metronome import METRONOME_CHANNEL, click_event_for_beat
from audio.performance_cue import PERFORMANCE_CUE_CHANNEL
from audio.position_announcer import POSITION_ANNOUNCER_CHANNEL, announcement_event_for_beat
from audio.sequencer import Sequencer
from models import mixer_settings
from models.mixer_settings import MixerSettings


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

    def __init__(self, session, parent=None):
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
        if self.sequencer is not None:
            self.sequencer.stop()
        self.sequencer = Sequencer(music_data, self.synth, parent=self)
        self.sequencer.step_played.connect(self._on_sequencer_step)
        self.sequencer.finished.connect(self._on_sequencer_finished)
        self.apply_mixer(music_data.mixer)

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
        audition never moved them - but the status field always updates."""
        if self.sequencer is None:
            return
        was_tracking_cursor = self.sequencer.update_cursor
        self.sequencer.stop()
        if was_tracking_cursor and self.music_data:
            self.music_data.active_event_index = self.sequencer.current_index
            self.cursor_moved.emit(False)
        else:
            self.playback_state_changed.emit()

    def audition_phrase(self) -> None:
        """Enter with no pending digits (Ref 11): play from beat 1 of this
        measure through the end of the next. Enter again while anything is
        playing stops it rather than starting an overlapping run."""
        if not self.music_data or self.sequencer is None:
            return
        if self.sequencer.is_playing or self.sequencer.is_paused:
            self.stop()
            return

        current = self.music_data.get_current_slice()
        if current is None:
            return
        start_index = self.music_data.first_visible_event_index_of_measure(current.measure)
        if start_index is None:
            return

        end_index = self.phrase_end_index(current.measure, start_index)
        self.sequencer.play_from(start_index, end_index=end_index, update_cursor=False)
        self.playback_state_changed.emit()

    def phrase_end_index(self, current_measure: int, start_index: int) -> int:
        """Through the end of the NEXT measure, or the last sounding event
        if this is already the final measure - bounded so a phrase can't run
        on into trailing rest-only padding."""
        last_sounding = self.music_data.last_sounding_event_index()
        end_index = last_sounding if last_sounding is not None else self.music_data.last_event_index()

        measures = self.music_data.measure_numbers()
        pos = measures.index(current_measure)
        if pos + 2 < len(measures):
            measure_after_next = measures[pos + 2]
            candidate_end = self.music_data.first_event_index_of_measure(measure_after_next) - 1
            if candidate_end >= start_index:
                end_index = min(end_index, candidate_end)
        return end_index

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
        than leaving them on the last note."""
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

        if events:
            # Each group carries its own duration, so no slice-wide
            # duration_ms is needed here.
            self.synth.play_chord(events)

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
        ]

    def playback_status_text(self) -> str:
        """Playing/Paused/Stopped from the Sequencer - deliberately not a
        MusicData concern, describing UI state rather than the score."""
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
