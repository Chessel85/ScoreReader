# models/to_coda_mark.py
from dataclasses import dataclass


@dataclass
class ToCodaMark:
    """A "To Coda" direction (<direction>/<direction-type>/<words>"To
    Coda"</words>, or a <sound tocoda="..."> attribute), in measure numbers.
    MuseScore writes this at the END of its measure. Per the MusicXML spec,
    a tocoda mark only takes effect "the second time through" - i.e. only
    after a NavigationJump has already fired once this playback run (see
    MusicData.next_playback_index). label matches a CodaMark.label; "" when
    no label is available (text-only fallback), in which case
    MusicData._resolve_coda_target falls back to the nearest CodaMark whose
    measure comes after this one. Populated by TimelineBuilder._scan_first_part
    as a side effect of build(), the same pattern as TempoChange/tempo_changes."""

    measure: int
    label: str
