# models/coda_mark.py
from dataclasses import dataclass


@dataclass
class CodaMark:
    """A coda sign location (<direction>/<direction-type>/<coda/>), in
    measure numbers. MuseScore writes this at the START of its measure.
    label matches a ToCodaMark.label, from the sibling <sound coda="...">
    attribute - defaults to "1" when unset, or "" when this mark came from
    the text-only fallback (no <sound> at all - MusicData._resolve_coda_target
    falls back to nearest-following-measure matching in that case, since an
    empty label can't be matched by equality). Populated by
    TimelineBuilder._scan_first_part as a side effect of build(), the same
    pattern as TempoChange/tempo_changes."""

    measure: int
    label: str
