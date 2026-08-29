# models/hairpin_span.py
from dataclasses import dataclass


@dataclass
class HairpinSpan:
    """Ref 29: one crescendo/diminuendo hairpin
    (<direction>/<direction-type>/<wedge type="crescendo"|"diminuendo"|
    "stop">). Unlike RepeatSpan/EndingSpan, a wedge can start/stop
    mid-measure, so both the ts-relative beat_position (Ref 18, for
    display) and the monotonic quarters_from_start (for containment
    comparison against EventSlice.quarters_from_start) are kept for each
    end. Populated by TimelineBuilder._hairpin_spans as a side effect of
    build(), the same pattern as TempoChange/tempo_changes."""

    kind: str  # "crescendo" or "diminuendo"; "" for a bare <wedge type="stop">
    #           with no start marked in the file (its kind is unknowable)
    start_measure: int
    start_beat_position: float
    start_quarters_from_start: float
    end_measure: int
    end_beat_position: float
    end_quarters_from_start: float

    # Provenance + completeness, all defaulted so the positional construction
    # in existing tests still works. Hairpins are collected in the per-part
    # walk now (not first-part-only, like tempo/time signature), so a wedge on
    # any staff of any part is reported; part_id is what the Region 5 / report
    # label is part-prefixed with when more than one part contributes.
    part_id: str = ""
    staff: int = 1
    number: int = 1  # the <wedge number="..."> attribute (overlapping wedges)
    # False when the file gives a stop with no matching start (start_* is then
    # the start of the stop's own measure); False when a start never stops
    # before its part ends (end_* is then the end of the part's last measure).
    # The positions are filled only so containment / Ctrl+End still resolve -
    # the *_known flags are what the wording keys off, never the positions.
    start_known: bool = True
    end_known: bool = True
