# models/key_signatures.py
# Shared by parsers/musicXML_reader.py (Region 1's opening-of-score key) and
# music_data.py (the status bar's live-position key, C6/D-11) - moved here
# from musicXML_reader.py so music_data.py can read it without a
# parsers->models reverse import.
from typing import List, Optional, Tuple

# Accidentals are spelled out as words ("F sharp"), never as symbols ("F#")
# or a bare letter suffix ("Bb") - the same spoken-friendly convention the
# rest of the app already uses for note names (CLAUDE.md: "F sharp", "B
# double flat", never a symbol). Reported, live-tested: NVDA read "Bb
# major" as "b major" - the second "b" (meant to be read as "flat") was
# just silently dropped/misread as a letter, not spoken as an accidental at
# all - and "F# minor" similarly lost the "#" to "number"/nothing rather
# than "sharp". This FIFTHS_MAP was the one place in the codebase that had
# never picked up that convention.
FIFTHS_MAP = {
    0: "C major / A minor",
    1: "G major / E minor",
    2: "D major / B minor",
    3: "A major / F sharp minor",
    4: "E major / C sharp minor",
    5: "B major / G sharp minor",
    6: "F sharp major / D sharp minor",
    7: "C sharp major / A sharp minor",
    -1: "F major / D minor",
    -2: "B flat major / G minor",
    -3: "E flat major / C minor",
    -4: "A flat major / F minor",
    -5: "D flat major / B flat minor",
    -6: "G flat major / E flat minor",
    -7: "C flat major / A flat minor",
}

# S6: no-override sentinel for key_override_options() below - a fifths of
# None means "nothing selected/no override", never a real key.
NO_KEY_OVERRIDE_LABEL = "Use the file's own key"


def key_signature_display_name(fifths: int, mode: Optional[str] = None) -> str:
    """S6. mode=None keeps today's joined "X major / Y minor" text (every
    call site that predates the key override, and the no-override case) -
    mode="major"/"minor" splits FIFTHS_MAP's own string on " / " and
    returns just that half, so the 15 key names are never duplicated
    anywhere else."""
    joined = FIFTHS_MAP.get(fifths, f"{fifths} sharps/flats")
    if mode is None or " / " not in joined:
        return joined
    major, minor = joined.split(" / ", 1)
    return major if mode == "major" else minor


def key_override_options() -> List[Tuple[str, Optional[int], Optional[str]]]:
    """(label, fifths, mode) for every selectable entry in the key-override
    picker (widgets/key_signature_dialog.py): the no-override sentinel
    first, then every major key in fifths order, then every minor key in
    fifths order - 31 entries. Kept here, not in the widget, so it stays
    testable without Qt."""
    options: List[Tuple[str, Optional[int], Optional[str]]] = [
        (NO_KEY_OVERRIDE_LABEL, None, None)
    ]
    for fifths in sorted(FIFTHS_MAP):
        options.append((key_signature_display_name(fifths, "major"), fifths, "major"))
    for fifths in sorted(FIFTHS_MAP):
        options.append((key_signature_display_name(fifths, "minor"), fifths, "minor"))
    return options
