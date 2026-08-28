# models/direction_mark.py
from dataclasses import dataclass


@dataclass
class DirectionMark:
    """P3 (find_feature_plan.md M1/M3/M5): a point (non-span) <direction>/
    <direction-type> - a rehearsal mark (<rehearsal>), a pedal change
    (<pedal type="change">), or the D6 catch-all for any <direction-type>
    child this parser does not handle explicitly (so a rare or future
    exporter element is still findable rather than vanishing silently).

    Collected per PART like DirectionSpan (D5); part_id/staff recorded so
    the Region 5 / report label can be part-prefixed only when more than
    one part contributes a mark of the same kind. Populated by
    TimelineBuilder._handle_direction as a side effect of build().
    """

    kind: str  # "rehearsal" | "pedal_change" | "other_direction"
    part_id: str
    staff: int
    # rehearsal text; "" for pedal_change; tag with hyphens -> spaces for
    # other_direction (that tag IS the value D6 makes findable).
    label: str
    measure: int
    beat_position: float
    quarters_from_start: float
