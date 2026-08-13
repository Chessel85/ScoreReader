# models/performance_region_row.py
from dataclasses import dataclass
from typing import Optional


@dataclass
class PerformanceRegionRow:
    """Ref 29: one row of Region 5 (the Performance region) - either the
    start or the end line of a RepeatSpan/EndingSpan/HairpinSpan active at
    the cursor's current position. jump_target_quarters is None for a
    repeat/ending row (resolved via measure lookup only, since those spans
    only ever start/end at a measure boundary) and set for a hairpin row
    (which can start/stop mid-measure, so needs the finer-grained
    quarters_from_start lookup) - MainWindow.jump_to_performance_span_start/
    end branch on this to pick the right MusicData lookup method."""

    label: str
    jump_target_measure: int
    jump_target_quarters: Optional[float] = None
