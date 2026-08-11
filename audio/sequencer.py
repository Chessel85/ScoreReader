# audio/sequencer.py
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal

from audio.metronome import click_event_for_beat


class Sequencer(QObject):
    """E4: schedules timeline events over real time from a start index, with
    stop/pause/resume. Foundation for E5 (play/pause/stop from the cursor)
    and E6 (two-bar phrase audition) - E7's chord audition doesn't need
    scheduling at all, it's a single simultaneous chord, so it bypasses this
    class entirely.

    Uses a single QTimer, rescheduled one step at a time rather than N
    timers pre-scheduled up front, so pause/stop/an F/S tempo change (E2)
    mid-playback just cancels and reschedules the next step instead of
    unwinding a queue built with now-stale timing. Timing between two steps
    comes from EventSlice.quarters_from_start (added in this task) and
    MusicData.effective_tempo_bpm() (E1), read fresh on every step rather
    than cached at play_from time.

    timer: injectable like MainWindow's synth parameter (D-7) - defaults to
    a real QTimer, but tests can pass a fake with a synchronous .start()/
    .stop()/.timeout so scheduling can be driven deterministically without
    a real wall-clock wait.
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
        """Start playing from start_index through end_index (inclusive), or
        to the end of the visible timeline if end_index is None (Ref 10
        AC1). update_cursor tells callers (MainWindow) whether this run
        should move active_event_index as it goes (full playback, E5) or
        leave it alone (phrase audition, E6)."""
        self._timer.stop()
        self._current_index = start_index
        self._original_start_index = start_index
        self._end_index = end_index
        self.update_cursor = update_cursor
        self._is_playing = True
        self._is_paused = False
        self._sound_current_step()

    def pause(self) -> None:
        """Ref 10 AC3: stop advancing and silence whatever's sounding right
        now - reported bug, live-tested: an earlier version left the current
        note ringing out on its own natural duration, which for a short note
        meant pausing had no audible effect at all and read as "not
        working". _current_index stays exactly where it is, which AC3 calls
        "the position to restart playback"."""
        if not self._is_playing:
            return
        self._timer.stop()
        self.synth.stop_all_notes()
        self._is_playing = False
        self._is_paused = True

    def resume(self) -> None:
        """Ref 10 AC3: restart playback from the paused position - re-sounds
        the current step (matching the spec's own wording, not a mid-note
        continuation) and carries on forward from there."""
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

        duration_ms = self.music_data.get_duration_ms_for_index(self._current_index)
        events = self.music_data.get_playback_events_at_index(self._current_index)
        if events:
            self.synth.play_chord(events, duration_ms=duration_ms)

        # E8/Ref 14 AC1/AC2: a click layers on top of whatever notes (or
        # nothing) sound at this step, whenever the step lands on a whole
        # beat - accented on beat 1. Fires alongside real notes too, not
        # instead of them, and needs no separate scheduling: this step is
        # only reached at all for a silent beat because
        # next_visible_event_index (Ref 14 AC4) now counts a metronome-only
        # beat marker as a real step to visit.
        if self.music_data.metronome_enabled:
            current_slice = self.music_data.timeline_slices[self._current_index]
            click = click_event_for_beat(current_slice.beat_position)
            if click is not None:
                self.synth.play_click(*click)

        self.step_played.emit(self._current_index)

        next_index = self.music_data.next_visible_event_index(self._current_index, self._end_index)
        if next_index is None:
            # Reported bug, live-tested: this used to flip is_playing False
            # and emit finished() here immediately - before the last note
            # had actually rung out for duration_ms. is_playing being False
            # while the note was still audibly sounding meant Space, pressed
            # right after, took toggle_play_stop()'s "start a new run"
            # branch instead of "stop" - and since the cursor was already on
            # the last note, that played the boundary cue instead of doing
            # anything sensible. Now: stay "playing" and wait out the ring
            # duration via the same timer/_advance path, with
            # _pending_next_index left None as the signal that this wait is
            # the finish, not a further step.
            self._pending_next_index = None
            self._timer.start(duration_ms)
            return

        self._pending_next_index = next_index
        self._timer.start(self._delay_ms_to(next_index))

    def _delay_ms_to(self, next_index: int) -> int:
        """Ref 12 "multi-tempo scope": uses the tempo in effect at the
        *current* step, not the next one - a marking at next_index's own
        position takes effect starting there, so the time it takes to reach
        it is still governed by whatever tempo was active beforehand."""
        current_slice = self.music_data.timeline_slices[self._current_index]
        next_slice = self.music_data.timeline_slices[next_index]
        delta_quarters = next_slice.quarters_from_start - current_slice.quarters_from_start
        bpm = self.music_data.effective_tempo_bpm(self._current_index)
        return max(1, int(delta_quarters * 60000.0 / bpm))

    def _advance(self) -> None:
        if self._pending_next_index is None:
            # The ring-out wait scheduled at the end of _sound_current_step
            # has completed - only now is playback actually finished.
            # Ref 10 AC5's "stopping reverts to the original start position"
            # also applies here, not just to an explicit interrupt (stop()
            # above does the same _original_start_index reset) - user
            # decision, since reaching the end naturally is still "stopping"
            # from the listener's point of view, not a new position to land
            # on and leave the cursor at.
            self._is_playing = False
            self._current_index = self._original_start_index
            self.finished.emit()
            return
        self._current_index = self._pending_next_index
        self._sound_current_step()
