# models/vocabulary.py
"""UK/US music-terminology word choices for F4/D-6. Purely presentational -
internal identifiers (the "measure" attribute key used for storage and menu
wiring, method names, MusicXML type strings) are never touched by any of
this, only the text actually rendered to the user.

D-15: stave/staff is deliberately EXCLUDED from this toggle - live-tested
feedback was that Region 2's clef names ("Treble stave", "Bass stave") should
stay exactly as the app renders them today regardless of dialect, to keep
this simple for now. See tasks.txt.
"""

UK_BASE_DURATION_NAMES = {
    # Checked longest-key-first by duration_name() so "double whole" isn't
    # matched as a dotted "whole".
    "double whole": "breve",
    "whole": "semibreve",
    "half": "minim",
    "quarter": "crotchet",
    "eighth": "quaver",
    "sixteenth": "semiquaver",
    "thirty-second": "demisemiquaver",
    "sixty-fourth": "hemidemisemiquaver",
    "hundred-twenty-eighth": "semihemidemisemiquaver",
    "two-hundred-fifty-sixth": "demisemihemidemisemiquaver",
}


def bar_word(uk_terms: bool) -> str:
    return "bar" if uk_terms else "measure"


def duration_name(us_display_name: str, uk_terms: bool) -> str:
    """Translates an already-rendered US duration name (e.g. "dotted
    quarter", from models/duration_units.py's beat_unit_display_name) to UK
    terms. Operates on the final string, not the raw MusicXML type/dots, so
    no parser code needs to change - the dotted-prefix words ("dotted ",
    "double-dotted "...) are dialect-neutral, only the base word differs."""
    if not uk_terms:
        return us_display_name
    for us_base in sorted(UK_BASE_DURATION_NAMES, key=len, reverse=True):
        if us_display_name.endswith(us_base):
            prefix = us_display_name[: -len(us_base)]
            return f"{prefix}{UK_BASE_DURATION_NAMES[us_base]}"
    return us_display_name


def attribute_label(attribute_key: str, uk_terms: bool) -> str:
    """Region 3/4's optional-attribute display label for `attribute_key`
    (Ref 15 AC4) - only "measure" differs by dialect (D-15 excludes
    "stave"); every other key (step, octave, duration, part, stave, voice,
    string, fret...) passes through unchanged. The key itself is never
    renamed - callers keep using the raw attribute_key for dict lookups/menu
    wiring, this only affects rendered text."""
    if attribute_key == "measure":
        return bar_word(uk_terms)
    return attribute_key
