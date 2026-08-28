# models/direction_span.py
from dataclasses import dataclass


@dataclass
class DirectionSpan:
    """P3 (find_feature_plan.md M1/M2/M4): one <direction>/<direction-type>
    span - a sustain pedal (<pedal>), an octave shift (<octave-shift>), or a
    dashed / bracketed line (<dashes>/<bracket>).

    Unlike RepeatSpan/EndingSpan (measure numbers only) and like
    HairpinSpan, a direction can start or stop mid-measure, so each end
    keeps both the ts-relative beat_position (Ref 18, for display) and the
    monotonic quarters_from_start (for containment comparison against
    EventSlice.quarters_from_start).

    Collected per PART, not first-part-only (D5) - i-see-angels changes
    clef on P3/P4, not P1, and pedal/octave-shift are equally per-part -
    so part_id/staff are recorded and the Region 5 / report label is
    prefixed with the part name only when more than one part contributes a
    span of the same kind. Populated by TimelineBuilder._handle_direction
    as a side effect of build(), the same pattern as HairpinSpan.
    """

    kind: str  # "pedal" | "octave_shift" | "dashes" | "bracket"
    part_id: str
    staff: int
    # "" for pedal/dashes/bracket; "8va"/"8vb"/"15ma"/"15mb" for octave_shift.
    label: str
    start_measure: int
    start_beat_position: float
    start_quarters_from_start: float
    end_measure: int
    end_beat_position: float
    end_quarters_from_start: float
