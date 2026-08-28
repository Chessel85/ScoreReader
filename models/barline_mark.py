# models/barline_mark.py
from dataclasses import dataclass


@dataclass
class BarlineMark:
    """P4 (find_feature_plan.md M6): one <barline>/<bar-style> that isn't a
    plain barline and isn't a repeat barline (those are RepeatSpan already).

    Score-wide, like RepeatSpan/EndingSpan - so no part_id/staff. Collected
    in TimelineBuilder._scan_first_part alongside the repeat/ending scan.

    D16: every score ends with a <bar-style>light-heavy</bar-style> and the
    End key already goes there, so a light-heavy on the LAST measure is
    dropped rather than recorded. A light-heavy anywhere else (a
    multi-movement score) is real information and is kept as an
    `other_barline`. A `light-light` double bar is the one style with its
    own kind.
    """

    kind: str  # "double_barline" | "other_barline"
    style: str  # spoken: "double", "dashed", "dotted", "heavy light", ...
    measure: int
    location: str  # <barline location=...>: "right" (default) | "left" | "middle"
