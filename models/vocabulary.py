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


# F3/Ref 16 AC3: MusicXML <dynamics> child tag -> spoken word. Marks not in
# this table (including <other-dynamics>, whose own text is arbitrary) fall
# back to their raw text in dynamic_name() below rather than raising.
DYNAMIC_NAMES = {
    "ppppp": "pianississississimo",
    "pppp": "pianississimo",
    "ppp": "pianissississimo",
    "pp": "pianissimo",
    "p": "piano",
    "mp": "mezzo-piano",
    "mf": "mezzo-forte",
    "f": "forte",
    "ff": "fortissimo",
    "fff": "fortississimo",
    "ffff": "fortissississimo",
    "fffff": "fortississississimo",
    "sf": "sforzando",
    "sfp": "sforzando piano",
    "sfpp": "sforzando pianissimo",
    "sfz": "sforzando",
    "sfzp": "sforzando piano",
    "sffz": "sforzato",
    "fz": "forzando",
    "fp": "fortepiano",
    "rf": "rinforzando",
    "rfz": "rinforzando",
    "pf": "poco forte",
    "n": "niente",
}

# F3/Ref 16 AC3: notations/articulations and notations/ornaments child tags
# -> spoken word. Unmapped tags fall back to hyphens-as-spaces in
# articulation_name() below, so an uncommon MuseScore export still renders
# as reasonable text instead of the raw XML tag.
ARTICULATION_NAMES = {
    "staccato": "staccato",
    "staccatissimo": "staccatissimo",
    "accent": "accent",
    "strong-accent": "marcato",
    "tenuto": "tenuto",
    "detached-legato": "detached legato",
    "spiccato": "spiccato",
    "scoop": "scoop",
    "plop": "plop",
    "doit": "doit",
    "falloff": "falloff",
    "stress": "stress",
    "unstress": "unstress",
    "trill-mark": "trill",
    "turn": "turn",
    "inverted-turn": "inverted turn",
    "delayed-turn": "delayed turn",
    "mordent": "mordent",
    "inverted-mordent": "inverted mordent",
    "tremolo": "tremolo",
    "schleifer": "schleifer",
    "shake": "shake",
    "wavy-line": "trill",
}


def dynamic_name(mark: str) -> str:
    """Spoken form of a MusicXML dynamics mark (e.g. "f" -> "forte") for
    F3/Ref 16 AC3. Falls back to the raw mark text for anything not in
    DYNAMIC_NAMES (e.g. <other-dynamics> custom text)."""
    return DYNAMIC_NAMES.get(mark, mark)


def articulation_name(tag: str) -> str:
    """Spoken form of a notations/articulations or notations/ornaments child
    tag (e.g. "strong-accent" -> "marcato") for F3/Ref 16 AC3. Falls back to
    the tag with hyphens replaced by spaces for anything not in
    ARTICULATION_NAMES."""
    return ARTICULATION_NAMES.get(tag, tag.replace("-", " "))


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
