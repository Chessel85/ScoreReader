# models/duration_units.py
"""MusicXML <beat-unit>/<type> vocabulary <-> quarter-length ratio and
screen-reader-friendly display name. Shared by MusicXMLReader's initial
tempo extraction (via music21 Duration objects) and TimelineBuilder's
mid-score tempo-change scan (via raw <metronome> elements, Ref 12
"multi-tempo scope") so both describe a beat unit the same way."""

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


def beat_unit_quarter_length(type_name: str, dots: int = 0) -> float:
    base = QUARTER_LENGTH_BY_TYPE.get(type_name, 1.0)
    return base * (1.5 ** dots) if dots else base


def beat_unit_display_name(type_name: str, dots: int = 0) -> str:
    base = DURATION_TYPE_NAMES.get(type_name, type_name)
    prefix = DOTS_PREFIX.get(dots, f"{dots}x-dotted ")
    return f"{prefix}{base}"
