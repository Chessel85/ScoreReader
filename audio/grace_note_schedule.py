# audio/grace_note_schedule.py
"""The grace-note counterpart of audio/strum_schedule.py: a pure function
for the one piece of real timing math (how long the grace note's own brief
pre-note should ring before the main note starts), so it is directly
unit-testable without a real event loop. SynthEngine.play_chord_with_grace
is the thin QTimer wrapper around it.
"""
from typing import List, Tuple

DEFAULT_GRACE_DURATION_MS = 60
MIN_GRACE_DURATION_MS = 20


def effective_grace_duration_ms(
    main_events: List[Tuple],
    grace_duration_ms: int = DEFAULT_GRACE_DURATION_MS,
) -> int:
    """How long the grace note(s) should ring before the main chord starts.

    Acciaccatura/appoggiatura are both realized the same way here (see
    models/note_data.py's GraceNote docstring): a brief pre-note, not a
    fixed steal-from-the-main-note fraction. Clamped to at most half of the
    SHORTEST main note's own duration_ms (main_events' 4th tuple element) so
    a very fast tempo or a short main note value never has the grace note's
    pre-note outlast (or nearly consume) the note it's meant to decorate -
    an edge case no real file tested so far actually hits, but cheap to
    guard against.
    """
    durations = [event[3] for event in main_events if len(event) > 3]
    if not durations:
        return grace_duration_ms
    shortest_main_ms = min(durations)
    return max(MIN_GRACE_DURATION_MS, min(grace_duration_ms, int(shortest_main_ms * 0.5)))
