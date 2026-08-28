# models/clef_change_mark.py
from dataclasses import dataclass


@dataclass
class ClefChangeMark:
    """P4 (find_feature_plan.md M7): an <attributes>/<clef> for a
    (part, staff) that differs from the one already in force there - a
    mid-part clef change (chopin-etude P1 bars 15-20+, i-see-angels P3/P4).

    Per PART/staff, not first-part-only (D5) - i-see-angels changes clef on
    P3 and P4 but not P1 - so part_id/staff are recorded and the Region 5 /
    report label is part-prefixed only when more than one part contributes a
    clef change. The staff's FIRST clef is never a change; only a later,
    different one produces a mark. Populated by TimelineBuilder._handle_
    attributes as a side effect of build().
    """

    part_id: str
    staff: int
    label: str  # vocabulary.clef_name(...): "bass", "treble 8vb", "alto", ...
    measure: int
    beat_position: float
    quarters_from_start: float
