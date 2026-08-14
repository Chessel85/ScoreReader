# models/duration_units.py
"""MusicXML <beat-unit>/<type> vocabulary <-> quarter-length ratio and
screen-reader-friendly display name. Shared by MusicXMLReader's initial
tempo extraction (via music21 Duration objects) and TimelineBuilder's
mid-score tempo-change scan (via raw <metronome> elements, Ref 12
"multi-tempo scope") so both describe a beat unit the same way."""

from typing import Optional

QUARTER_LENGTH_BY_TYPE = {
    "maxima": 32.0,
    "longa": 16.0,
    "breve": 8.0,
    "whole": 4.0,
    "half": 2.0,
    "quarter": 1.0,
    "eighth": 0.5,
    "16th": 0.25,
    "32nd": 0.125,
    "64th": 0.0625,
    "128th": 0.03125,
    "256th": 0.015625,
}

DURATION_TYPE_NAMES = {
    "maxima": "maxima",
    "longa": "longa",
    "breve": "double whole",
    "whole": "whole",
    "half": "half",
    "quarter": "quarter",
    "eighth": "eighth",
    "16th": "sixteenth",
    "32nd": "thirty-second",
    "64th": "sixty-fourth",
    "128th": "hundred-twenty-eighth",
    "256th": "two-hundred-fifty-sixth",
}

DOTS_PREFIX = {0: "", 1: "dotted ", 2: "double-dotted ", 3: "triple-dotted "}

# Standard tuplet names, keyed by the <time-modification>/<actual-notes>
# count (a "triplet" packs 3 notes into the time of 2, a "quintuplet" 5 into
# the time of 4, etc.) - appended as a suffix to the base note name, e.g.
# "eighth triplet"/"quaver triplet": a tuplet member's <type> already reads
# as its plain notated shape (see TimelineBuilder.build), so a triplet
# eighth needs this suffix to say what makes its actual duration different
# from a plain eighth.
TUPLET_WORDS = {
    2: "duplet",
    3: "triplet",
    4: "quadruplet",
    5: "quintuplet",
    6: "sextuplet",
    7: "septuplet",
    8: "octuplet",
    9: "nonuplet",
}


def beat_unit_quarter_length(type_name: str, dots: int = 0) -> float:
    base = QUARTER_LENGTH_BY_TYPE.get(type_name, 1.0)
    return base * (1.5 ** dots) if dots else base


def beat_unit_display_name(type_name: str, dots: int = 0) -> str:
    base = DURATION_TYPE_NAMES.get(type_name, type_name)
    prefix = DOTS_PREFIX.get(dots, f"{dots}x-dotted ")
    return f"{prefix}{base}"


def tuplet_word(actual_notes: int) -> Optional[str]:
    """None for a ratio with no standard English name (uncommon in
    practice) rather than a made-up word - the caller falls back to the
    base duration name with no tuplet suffix at all."""
    return TUPLET_WORDS.get(actual_notes)


def quarter_length_to_display_name(quarter_length: float, tolerance: float = 1e-6) -> Optional[str]:
    """Best-effort reverse lookup from a real quarter-length to a display
    name, for the rare note/rest with no <type> element - chiefly a
    whole-measure rest, which MusicXML allows to omit <type> entirely (its
    <duration> alone covers the whole bar). None if no clean type/dots
    combination matches (e.g. an irregular tuplet-fraction rest with no
    <type> of its own), leaving the caller to fall back further."""
    for type_name, base in QUARTER_LENGTH_BY_TYPE.items():
        for dots in range(4):
            if abs(base * (1.5 ** dots) - quarter_length) < tolerance:
                return beat_unit_display_name(type_name, dots)
    return None
