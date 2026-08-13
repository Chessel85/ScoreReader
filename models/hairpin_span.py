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

    kind: str  # "crescendo" or "diminuendo"
    start_measure: int
    start_beat_position: float
    start_quarters_from_start: float
    end_measure: int
    end_beat_position: float
    end_quarters_from_start: float
