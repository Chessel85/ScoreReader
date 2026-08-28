# models/measure_style_mark.py
from dataclasses import dataclass


@dataclass
class MeasureStyleMark:
    """P4 (find_feature_plan.md M8): an <attributes>/<measure-style> child -
    a multi-measure rest (<multiple-rest>) or a measure/beat repeat or slash
    region (<measure-repeat>/<beat-repeat>/<slash>).

    Per PART/staff like ClefChangeMark (D5). A simple presence point - no
    span, no value expansion (D2 expands attribute values only, not marking
    kinds), so the slash family collapses to one `measure_repeat` kind.
    Populated by TimelineBuilder._handle_attributes as a side effect of
    build(). None of the sample-set files carry one; covered by a hand
    fixture.
    """

    kind: str  # "multi_measure_rest" | "measure_repeat"
    part_id: str
    staff: int
    label: str  # "8-bar rest", "measure repeat", "beat repeat", "slash"
    measure: int
