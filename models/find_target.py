# models/find_target.py
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class FindTarget:
    """One entry in the Find dialog's list (widgets/find_dialog.py,
    MusicData.available_find_targets) - either an optional note attribute
    ("string", "articulation", ...) or a performance-marking type (one of
    MARKING_KINDS below). `category` is "attribute" or "marking"; `key` is
    the identifier MusicData.find_occurrence scans for; `label` is the
    exact text shown in the dialog and read by a screen reader. Marking
    labels are copied verbatim from MusicData.get_performance_region_rows's
    own wording, so Find and Region 5 never disagree on vocabulary.

    `value` is the value-level Find refinement (D1): None means "any
    occurrence of this key" and matches on presence; a set value ("staccato",
    "forte") matches only notes whose comma-joined value list for `key`
    contains it. Only keys in VALUE_EXPANDED_KEYS are ever offered with a
    value - see FindIndex.available_targets."""

    category: str
    key: str
    label: str
    value: Optional[str] = None


# The attribute keys whose distinct values each get their own Find target
# (D1/D2, user decision 2026-08-28). An explicit allow-list, not a count
# threshold: the question is whether the value carries musical identity a
# performer would navigate by ("find the next trill", "find the next fff"),
# not how many distinct values there happen to be. Everything not listed
# here - fret, string, fingering, pluck, text (stave text), strum, fermata,
# grace, arpeggio - is offered as a single "any" target only.
#
# Some keys here (chord symbol, other notation) are produced by later
# phases; listing them now is harmless - a key absent from the score simply
# never expands.
VALUE_EXPANDED_KEYS = frozenset({
    "articulation", "technique", "dynamic", "accidental",
    "tie", "slur", "glissando", "tuplet",
    "chord symbol", "other notation",
})


def occurrence_label(count: int) -> str:
    """"1 occurrence" / "N occurrences" - shared by the Find dialog and any
    future caller so the wording stays in one place (D13). An occurrence is
    a timeline position, not a note: a chord whose notes all carry the same
    articulation counts once, matching what one Alt+Right press visits."""
    return f"{count} occurrence" if count == 1 else f"{count} occurrences"


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
    # P3: <direction>/<direction-type> spans and points. Pedal and octave
    # shift are Find + Performance Report only, no Region 5 row (D15 - a
    # pedal-heavy piece would fire the change cue on nearly every bar).
    ("pedal_start", "Pedal start"),
    ("pedal_end", "Pedal end"),
    ("pedal_change", "Pedal change"),
    ("octave_shift_start", "Octave shift start"),
    ("octave_shift_end", "Octave shift end"),
    ("rehearsal", "Rehearsal mark"),
    ("dashed_line_start", "Dashed line start"),
    ("dashed_line_end", "Dashed line end"),
    ("bracket_line_start", "Bracket line start"),
    ("bracket_line_end", "Bracket line end"),
    # D6 catch-all: any <direction-type> child with no explicit handler.
    ("other_direction", "Direction"),
]
