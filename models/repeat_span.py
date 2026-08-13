# models/repeat_span.py
from dataclasses import dataclass


@dataclass
class RepeatSpan:
    """Ref 29: one forward-repeat/backward-repeat barline pair
    (<barline>/<repeat direction="forward"|"backward">), in measure numbers.
    Populated by TimelineBuilder._repeat_and_ending_spans as a side effect
    of build(), the same pattern as TempoChange/tempo_changes."""

    start_measure: int
    end_measure: int
