# models/find_target.py
from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class FindTarget:
    """One entry in the Find dialog's list (widgets/find_dialog.py,
    MusicData.available_find_targets) - either an optional note attribute
    ("string", "articulation", ...) or a performance-marking type (one of
    MARKING_KINDS below). `category` is "attribute" or "marking"; `key` is
    the identifier MusicData.find_occurrence scans for; `label` is the
    exact text shown in the dialog and read by a screen reader. Marking
    labels are copied verbatim from MusicData.get_performance_region_rows's
    own wording, so Find and Region 5 never disagree on vocabulary."""

    category: str
    key: str
    label: str


# The closed set of performance-marking types the parser can recognize, in
# the order the Find dialog lists them. Not every score has all of these -
# MusicData.available_find_targets() filters this down per-file to what the
# currently loaded score actually contains, the same presence-based
# philosophy Options > Reorder Attributes... already established for
# attribute keys.
MARKING_KINDS: List[Tuple[str, str]] = [
    ("repeat_start", "Repeat start"),
    ("repeat_end", "Repeat end"),
    ("ending_start", "Ending start"),
    ("ending_end", "Ending end"),
    ("crescendo_start", "Crescendo start"),
    ("crescendo_end", "Crescendo end"),
    ("diminuendo_start", "Diminuendo start"),
    ("diminuendo_end", "Diminuendo end"),
    ("segno", "Segno"),
    ("coda", "Coda"),
    ("to_coda", "To coda"),
    ("fine", "Fine"),
    ("dacapo", "Da capo"),
    ("dalsegno", "Dal segno"),
    ("key_signature_change", "Key signature change"),
    ("time_signature_change", "Time signature change"),
    ("tempo_change", "Tempo change"),
]
