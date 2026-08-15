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


def _match_duration(quarter_length: float, tolerance: float) -> Optional[tuple]:
    """(type_name, dots) for the first type/dots combination within
    tolerance of quarter_length, or None. Shared by
    quarter_length_to_display_name and is_simple_duration_match so the two
    can never disagree on which combination a given length matched."""
    for type_name, base in QUARTER_LENGTH_BY_TYPE.items():
        for dots in range(4):
            if abs(base * (1.5 ** dots) - quarter_length) < tolerance:
                return type_name, dots
    return None


def quarter_length_to_display_name(quarter_length: float, tolerance: float = 1e-6) -> Optional[str]:
    """Best-effort reverse lookup from a real quarter-length to a display
    name, for the rare note/rest with no <type> element - chiefly a
    whole-measure rest, which MusicXML allows to omit <type> entirely (its
    <duration> alone covers the whole bar). None if no clean type/dots
    combination matches (e.g. an irregular tuplet-fraction rest with no
    <type> of its own), leaving the caller to fall back further."""
    match = _match_duration(quarter_length, tolerance)
    return beat_unit_display_name(*match) if match else None


# Common enough in real notation that naming a duration after one of these
# is trustworthy even from a nearest-match reverse lookup. A single dot is
# routine (dotted quarter/eighth); two or three dots, or anything shorter
# than a 32nd, is rare enough in practice that a non-quantized recording
# landing within tolerance of one is more likely numeric coincidence than a
# real dotted-64th note - see MidiTimelineBuilder's per-track fallback,
# which reverts a whole track to numeric duration display when too many of
# its notes only match a "not simple" combination like this.
SIMPLE_DURATION_TYPES = {"whole", "half", "quarter", "eighth", "16th", "32nd"}


def is_simple_duration_match(quarter_length: float, tolerance: float) -> Optional[bool]:
    """True/False for whether quarter_length's nearest type/dots match (the
    same one quarter_length_to_display_name would name it after) counts as
    "simple" per SIMPLE_DURATION_TYPES above; None if nothing matched at
    all (quarter_length_to_display_name would also return None)."""
    match = _match_duration(quarter_length, tolerance)
    if match is None:
        return None
    type_name, dots = match
    return type_name in SIMPLE_DURATION_TYPES and dots <= 1
