# models/segno_mark.py
from dataclasses import dataclass


@dataclass
class SegnoMark:
    """A segno sign location (<direction>/<direction-type>/<segno/>), in
    measure numbers. MuseScore writes this at the START of its measure.
    label matches a NavigationJump(kind="dalsegno").target_label, from the
    sibling <sound segno="..."> attribute - defaults to "1" when the file's
    own author never set an explicit label (MuseScore's own default), or ""
    when this mark came from the text-only fallback (no <sound> at all, so
    no label is available - see TimelineBuilder._step_direction_jump_marks).
    Populated by TimelineBuilder._scan_first_part as a side effect of
    build(), the same pattern as TempoChange/tempo_changes."""

    measure: int
    label: str
