# audio/sequencer.py
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal

from audio.metronome import click_event_for_beat
from audio.position_announcer import announcement_event_for_beat
from audio.strum_schedule import sound_events
from models.playback_jump_state import PlaybackJumpState


class Sequencer(QObject):
    """Schedules timeline events over real time from a start index, with
    stop/pause/resume (Ref 10 playback, Ref 11 phrase audition). Chord
    audition needs no scheduling and bypasses this class entirely.

    One QTimer, rescheduled a step at a time rather than N timers queued up
    front, so a pause/stop or a mid-playback tempo change just cancels and
    reschedules instead of unwinding a queue built on stale timing. Step
    timing reads EventSlice.quarters_from_start and
    MusicData.effective_tempo_bpm() fresh on every step, never cached at
    play_from time.

    timer: injectable (like MainWindow's synth) so tests can drive
    scheduling synchronously with no wall-clock wait.
    """

    step_played = Signal(int)  # emits the timeline index just sounded
    finished = Signal()

    def __init__(self, music_data, synth, timer=None, parent=None):
        super().__init__(parent)
        self.music_data = music_data
        self.synth = synth

        self._timer = timer if timer is not None else QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._advance)

        self._current_index: Optional[int] = None
        self._pending_next_index: Optional[int] = None
        self._end_index: Optional[int] = None
        self._original_start_index: Optional[int] = None
        self.update_cursor: bool = True
        self._is_playing: bool = False
        self._is_paused: bool = False
        # Repeat/ending/Segno/Coda/D.C./D.S./Fine-aware stepping state for
        # THIS run only - see MusicData.next_playback_index. Reset fresh on
        # every play_from(), same as the other per-run fields above.
        self._jump_state: PlaybackJumpState = PlaybackJumpState()
        self._jump_lower_bound: int = 0
        # Whether the step ABOUT TO BE SOUNDED was reached by a jump (see
        # PlaybackJumpState.last_step_was_jump) rather than a natural
        # forward advance - read by _sound_current_step to decide retrigger
        # for THIS step, then overwritten for the NEXT one right after
        # next_playback_index is called. False for the very first step of a
        # run; harmless, since play_from already clears the deck itself.
        self._pending_retrigger: bool = False

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    @property
    def is_paused(self) -> bool:
        return self._is_paused

    @property
    def current_index(self) -> Optional[int]:
        return self._current_index

    @property
    def original_start_index(self) -> Optional[int]:
        return self._original_start_index

    def play_from(
        self,
        start_index: int,
        end_index: Optional[int] = None,
        update_cursor: bool = True,
        jump_lower_bound: int = 0,
    ) -> None:
        """Ref 10 AC1: play from start_index through end_index (inclusive),
        or to the end of the visible timeline. update_cursor tells MainWindow
        whether this run moves active_event_index as it goes (full playback)
        or leaves it alone (phrase audition).

        jump_lower_bound is the lowest index a repeat/D.C./D.S./Coda jump is
        allowed to land on this run (see MusicData.next_playback_index) - 0
        for ordinary full playback (every jump in the piece is reachable),
        or Preview's own start_index (so a jump never lands before Preview's
        own window)."""
        self._timer.stop()
        # An explicit reposition clears the deck; _sound_current_step uses
        # retrigger=False and won't, which is what lets other parts' notes
        # ring across an unrelated part's attack during a normal run.
        self.synth.stop_all_notes()
        self._current_index = start_index
        self._original_start_index = start_index
        self._end_index = end_index
        self._jump_state = PlaybackJumpState()
        self._jump_lower_bound = jump_lower_bound
        self._pending_retrigger = False
        self.update_cursor = update_cursor
        self._is_playing = True
        self._is_paused = False
        self._sound_current_step()

    def pause(self) -> None:
        """Ref 10 AC3: stop advancing AND silence what's sounding - letting
        the current note ring out its natural duration makes pausing on a
        short note inaudible, which reads as "pause doesn't work".
        _current_index stays put, as the position to restart from."""
        if not self._is_playing:
            return
        self._timer.stop()
        self.synth.stop_all_notes()
        self._is_playing = False
        self._is_paused = True

    def resume(self) -> None:
        """Ref 10 AC3: restart from the paused position - re-sounds the
        current step (per the spec's wording, not a mid-note continuation)
        and carries on from there."""
        if not self._is_paused:
            return
        self._is_paused = False
        self._is_playing = True
        self._sound_current_step()

    def stop(self) -> None:
        """Ref 10 AC5: revert to the original start position and silence
        whatever's currently sounding."""
        self._timer.stop()
        self.synth.stop_all_notes()
        self._is_playing = False
        self._is_paused = False
        self._current_index = self._original_start_index

    def _sound_current_step(self) -> None:
        if self._current_index is None:
            return

        events = self.music_data.get_playback_events_at_index(self._current_index)
        grace_events = self.music_data.get_grace_note_events_at_index(self._current_index)
        if events:
            # retrigger=False for a natural advance: it must not silence
            # other parts' still-ringing notes just because this part has a
            # new attack here (play_from/resume clear the deck themselves).
            # But a step reached via a repeat/D.C./D.S./Coda jump
            # (self._pending_retrigger, set after the PREVIOUS step's
            # next_playback_index call - see PlaybackJumpState.
            # last_step_was_jump) is a reposition, not a continuation, and
            # must retrigger: without it, the departing note's own
            # scheduled note-off timer races this step's note-on, which
            # could easily lose the race and briefly double-sound - an
            # audible stutter right at the jump (reported, live-tested).
            # sound_events (audio/strum_schedule.py) routes a UG score's
            # Chords bar through a real strummed pattern when one is
            # available, else falls through to the unchanged play_chord
            # path.
            sound_events(
                self.synth, self.music_data, events, retrigger=self._pending_retrigger, grace_events=grace_events
            )
            # Groups carry their own durations, so the longest is what has
            # to finish ringing before this step is done - which matters
            # below when this is the run's final step.
            ring_out_ms = max(group[3] for group in events)
        else:
            ring_out_ms = self.music_data.get_duration_ms_for_index(self._current_index)

        # Ref 14 AC1/AC2: the click layers on top of whatever sounds here
        # (or nothing), whenever the step is a whole beat. No separate
        # scheduling needed - a silent beat is reached at all only because
        # next_visible_event_index counts metronome-only beat markers.
        if self.music_data.metronome_enabled:
            current_slice = self.music_data.timeline_slices[self._current_index]
            click = click_event_for_beat(current_slice.beat_position)
            if click is not None:
                self.synth.play_click(*click)

        # Ref 28 AC1/AC2: independent of the click - either can be on
        # alone, and they use separate channels so simultaneous ones don't
        # cancel each other (see audio/position_announcer.py).
        if self.music_data.position_announcer_enabled:
            current_slice = self.music_data.timeline_slices[self._current_index]
            announcement = announcement_event_for_beat(current_slice.beat_position)
            if announcement is not None:
                self.synth.play_word(*announcement)

        self.step_played.emit(self._current_index)

        next_index = self.music_data.next_playback_index(
            self._current_index, self._jump_state, self._end_index, self._jump_lower_bound
        )
        # Recorded now for whichever step sounds next (see the retrigger
        # comment above) - next_playback_index has already set it fresh for
        # THIS call by the time it returns.
        self._pending_retrigger = self._jump_state.last_step_was_jump
        if next_index is None:
            # Stay "playing" and wait out the last note's ring via the same
            # timer path, with _pending_next_index None marking this wait as
            # the finish rather than a further step. Flipping is_playing
            # False here instead would make Space (pressed while the note is
            # still audibly sounding) take toggle_play_stop's "start" branch
            # from the last note, i.e. just play the boundary cue.
            self._pending_next_index = None
            self._timer.start(ring_out_ms)
            return

        self._pending_next_index = next_index
        self._timer.start(self._delay_ms_to(next_index))

    def _delay_ms_to(self, next_index: int) -> int:
        """Uses the tempo at the CURRENT step, not the next one: a marking
        at next_index takes effect on arrival, so the time taken to get
        there is governed by the tempo in force beforehand (Ref 12)."""
        if self._pending_retrigger:
            # next_index was reached via a jump - see PlaybackJumpState.
            # last_step_was_jump, read into _pending_retrigger right after
            # the next_playback_index call that produced it (still current
            # here, nothing has touched it since). The departing note rings
            # its own natural duration before the jump; the raw quarters
            # delta below has no real-time meaning for a jump, which can
            # move EITHER backward (a repeat/D.C./D.S. retake, delta <= 0 -
            # the plain formula would collapse to the 1 ms floor) OR forward
            # over unplayed content (an ending-skip/To Coda redirect, delta
            # > 0 - the plain formula would wrongly compute a real-time
            # pause for content that's never actually sounding).
            return self.music_data.get_duration_ms_for_index(self._current_index)
        current_slice = self.music_data.timeline_slices[self._current_index]
        next_slice = self.music_data.timeline_slices[next_index]
        delta_quarters = next_slice.quarters_from_start - current_slice.quarters_from_start
        bpm = self.music_data.effective_tempo_bpm(self._current_index)
        return max(1, int(delta_quarters * 60000.0 / bpm))

    def _advance(self) -> None:
        if self._pending_next_index is None:
            # The ring-out wait has completed, so playback is only now
            # actually finished. Ref 10 AC5's "reverts to the original start
            # position" applies to reaching the end naturally too, not just
            # to an explicit stop (the user's decision: from the listener's
            # point of view both are stopping).
            self._is_playing = False
            self._current_index = self._original_start_index
            self.finished.emit()
            return
        self._current_index = self._pending_next_index
        self._sound_current_step()
