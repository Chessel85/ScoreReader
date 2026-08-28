# models/vocabulary.py
"""UK/US music-terminology word choices for F4/D-6. Purely presentational -
internal identifiers (the "measure" attribute key used for storage and menu
wiring, method names, MusicXML type strings) are never touched by any of
this, only the text actually rendered to the user.

D-15: stave/staff is deliberately EXCLUDED from this toggle - Region 2's
clef names ("Treble stave", "Bass stave") stay as they are regardless of
dialect, a simplification the user asked for.
"""

import re

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
    quarter", "eighth triplet", from models/duration_units.py's
    beat_unit_display_name/quarter_length_to_display_name plus
    TimelineBuilder's tuplet-word suffix) to UK terms. Operates on the final
    string, not the raw MusicXML type/dots, so no parser code needs to
    change - the dotted-prefix words ("dotted ", "double-dotted "...) and
    tuplet-suffix words ("triplet", "quintuplet"...) are dialect-neutral,
    only the base word differs.

    The base word is matched as a whole space-bounded token/phrase, not
    just a suffix (a plain str.endswith used to be enough when the base
    word was always last, but a tuplet suffix now often follows it, e.g.
    "eighth" in "eighth triplet") - (?<!\\S)/(?!\\S) require the match to
    start/end at a space or string boundary, so "eighth" doesn't
    accidentally match inside some unrelated longer word."""
    if not uk_terms:
        return us_display_name
    for us_base in sorted(UK_BASE_DURATION_NAMES, key=len, reverse=True):
        match = re.search(r"(?<!\S)" + re.escape(us_base) + r"(?!\S)", us_display_name)
        if match:
            uk_base = UK_BASE_DURATION_NAMES[us_base]
            return us_display_name[: match.start()] + uk_base + us_display_name[match.end():]
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


# A minor chord's usual written abbreviation is a bare trailing "m" ("Am",
# "Am7") - reported: NVDA reads that as the letter "m", not the word
# "minor", while every other abbreviation seen in practice (Cmaj7, Dsus4,
# C7, a bare G for G major) already reads correctly as-is and must be left
# untouched. Matches root + accidental, "m" NOT followed by "aj" (so
# "Amaj7" is never touched), optional trailing extension digits (the
# "7"/"9"/"11" of an extended minor chord), and an optional /bass suffix.
# Deliberately narrow - "AmM7" (minor-major-seventh) doesn't match and is
# left as-is, an untested rarity nobody asked about.
#
# Shared by every chord-symbol source in the app - parsers/timeline_builder.py
# (MusicXML <harmony>, via music21's ChordSymbol.figure), parsers/
# ug_timeline_builder.py (an Ultimate Guitar page's own raw [ch] markup
# text) and parsers/gp_timeline_builder.py (a Guitar Pro chord diagram's own
# name) - so a fix here fixes the "Am" chord in Half the World Away's UG
# import and any GP chord track the same way it fixes a MusicXML <harmony>
# chord, rather than needing three separate regexes to stay in sync.
_MINOR_CHORD_RE = re.compile(r"^([A-G][#b-]*)m(?!aj)(\d*)((?:/.*)?)$")


def spell_out_minor_chord(label: str) -> str:
    """"Am" -> "A minor", "Am7" -> "A minor 7". Any label the regex above
    doesn't match (already-spoken-friendly abbreviations, or GP's "Strum"
    placeholder for a chordless strum event) passes through unchanged."""
    match = _MINOR_CHORD_RE.match(label)
    if not match:
        return label
    root, extension, bass = match.groups()
    words = [root, "minor"]
    if extension:
        words.append(extension)
    return " ".join(words) + bass


def attribute_label(attribute_key: str, uk_terms: bool) -> str:
    """Region 3/4's optional-attribute display label for `attribute_key`
    (Ref 15 AC4) - only "measure" differs by dialect (D-15 excludes
    "stave"); every other key (step, octave, duration, part, stave, voice,
    string, fret...) passes through unchanged. The key itself is never
    renamed - callers keep using the raw attribute_key for dict lookups/menu
    wiring, this only affects rendered text."""
    if attribute_key == "measure":
        return bar_word(uk_terms)
    # P1 (find_feature_plan.md): the attribute key is "grace" (one token),
    # but it reads as "grace note" everywhere it's shown. Every other new
    # P1 key ("tie", "slur", "tuplet", "fermata", "arpeggio", "accidental",
    # "glissando", "technique", "other notation") already reads correctly
    # as-is and passes straight through - as do P2's "chord symbol" and
    # "chord diagram".
    if attribute_key == "grace":
        return "grace note"
    return attribute_key
