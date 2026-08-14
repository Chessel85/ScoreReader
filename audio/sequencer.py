# audio/sequencer.py
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal

from audio.metronome import click_event_for_beat
from audio.position_announcer import announcement_event_for_beat


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

    def play_from(self, start_index: int, end_index: Optional[int] = None, update_cursor: bool = True) -> None:
        """Ref 10 AC1: play from start_index through end_index (inclusive),
        or to the end of the visible timeline. update_cursor tells MainWindow
        whether this run moves active_event_index as it goes (full playback)
        or leaves it alone (phrase audition)."""
        self._timer.stop()
        # An explicit reposition clears the deck; _sound_current_step uses
        # retrigger=False and won't, which is what lets other parts' notes
        # ring across an unrelated part's attack during a normal run.
        self.synth.stop_all_notes()
        self._current_index = start_index
        self._original_start_index = start_index
        self._end_index = end_index
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
        if events:
            # retrigger=False: a natural advance must not silence other
            # parts' still-ringing notes just because this part has a new
            # attack here. play_from/resume clear the deck themselves.
            self.synth.play_chord(events, retrigger=False)
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

        next_index = self.music_data.next_visible_event_index(self._current_index, self._end_index)
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
