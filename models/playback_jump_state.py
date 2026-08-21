# models/playback_jump_state.py
from dataclasses import dataclass, field
from typing import Set


@dataclass
class PlaybackJumpState:
    """Per-playback-run state for MusicData.next_playback_index - repeat/
    D.C./D.S./Coda-aware stepping needs to remember what THIS run has already
    done (a repeat is only retaken once; a D.C./D.S. only fires once), unlike
    the plain flat next_visible_event_index, which is pure and stateless.

    Deliberately NOT stored on MusicData - MusicData is a shared, long-lived
    object read by navigation/audition/display code that must stay a stateless
    source of truth (nothing about a single playback run's progress belongs
    there). Instead this is owned by whichever Sequencer.play_from() call is
    driving the run (a fresh instance every call, alongside its other per-run
    resets like _current_index/_end_index), or created as a throwaway instance
    by MusicData.playback_span_ms() for a one-off duration simulation.

    repeats_taken / endings_to_skip hold indices into MusicData.repeat_spans /
    ending_spans (not the spans themselves, so this stays a plain, cheap,
    Qt-free dataclass with no reference back into a particular MusicData
    instance's span objects)."""

    repeats_taken: Set[int] = field(default_factory=set)
    endings_to_skip: Set[int] = field(default_factory=set)
    jump_taken: bool = False

    # Transient, not accumulated like the three fields above: overwritten on
    # every next_playback_index call to say whether THAT call's returned
    # index was reached by a jump (repeat retake, dacapo/dalsegno, to-coda,
    # or an ending-skip redirect) rather than a plain forward step. Read by
    # Sequencer right after each call and used to decide retrigger for the
    # step that follows - a jump is a reposition, not a natural continuation,
    # so the note(s) sounding at the departure point must be silenced first
    # rather than left to ring across the discontinuity (which raced against
    # their own scheduled note-off and could double-sound/stutter).
    last_step_was_jump: bool = False
