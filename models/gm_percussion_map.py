# models/gm_percussion_map.py
"""The General MIDI Level 1 Percussion Key Map (notes 27-87 on the GM
percussion channel), used by parsers/midi_timeline_builder.py to give a
percussion note a spoken name ("Closed Hi-Hat", "Acoustic Snare") the same
way models/gm_instruments.py names a pitched part's program.

Unlike a pitched instrument, percussion has no single GM program to look
up - each drum/cymbal is its own note number on a dedicated bank. There is
no MusicXML counterpart to this table: a MusicXML percussion part (e.g.
Hit It.mxl) already carries its own real <instrument-name> text per note
via <score-instrument>, read directly by parsers/timeline_builder.py - this
table exists only for formats (MIDI) that have nothing but a bare note
number.

Stdlib-only, like every other models/ module - see
test_models_package_does_not_import_qt.
"""
from typing import Dict, List, Optional, Tuple

# The standard GM bank/program a synth's percussion kit lives at (verified
# against soundfonts/Airfont_380_final.sf2's own preset headers: bank 128,
# program 0 = "Hyper Kit"). audio/synth_engine.py program_selects this
# instead of a part's own gmidi_program whenever MusicData says the part
# is_percussion.
GM_PERCUSSION_BANK = 128
GM_PERCUSSION_PROGRAM = 0

GM_PERCUSSION_NAMES: Dict[int, str] = {
    27: "High Q",
    28: "Slap",
    29: "Scratch Push",
    30: "Scratch Pull",
    31: "Sticks",
    32: "Square Click",
    33: "Metronome Click",
    34: "Metronome Bell",
    35: "Acoustic Bass Drum",
    36: "Bass Drum 1",
    37: "Side Stick",
    38: "Acoustic Snare",
    39: "Hand Clap",
    40: "Electric Snare",
    41: "Low Floor Tom",
    42: "Closed Hi-Hat",
    43: "High Floor Tom",
    44: "Pedal Hi-Hat",
    45: "Low Tom",
    46: "Open Hi-Hat",
    47: "Low-Mid Tom",
    48: "Hi-Mid Tom",
    49: "Crash Cymbal 1",
    50: "High Tom",
    51: "Ride Cymbal 1",
    52: "Chinese Cymbal",
    53: "Ride Bell",
    54: "Tambourine",
    55: "Splash Cymbal",
    56: "Cowbell",
    57: "Crash Cymbal 2",
    58: "Vibraslap",
    59: "Ride Cymbal 2",
    60: "Hi Bongo",
    61: "Low Bongo",
    62: "Mute Hi Conga",
    63: "Open Hi Conga",
    64: "Low Conga",
    65: "High Timbale",
    66: "Low Timbale",
    67: "High Agogo",
    68: "Low Agogo",
    69: "Cabasa",
    70: "Maracas",
    71: "Short Whistle",
    72: "Long Whistle",
    73: "Short Guiro",
    74: "Long Guiro",
    75: "Claves",
    76: "Hi Wood Block",
    77: "Low Wood Block",
    78: "Mute Cuica",
    79: "Open Cuica",
    80: "Mute Triangle",
    81: "Open Triangle",
    82: "Shaker",
    83: "Jingle Bell",
    84: "Belltree",
    85: "Castanets",
    86: "Mute Surdo",
    87: "Open Surdo",
}


def gm_percussion_name(note: int) -> str:
    """Note number -> spoken name, degrading to a plain "Percussion note N"
    for anything outside the standard map rather than raising - a
    non-standard kit mapping or an out-of-range value shouldn't crash the
    loader (same "degrade gracefully" convention as gm_instrument_name)."""
    return GM_PERCUSSION_NAMES.get(note, f"Percussion note {note}")


# Ordered by key, for the Instruments dialog's percussion combo box - the
# percussion counterpart of gm_instruments.GM_INSTRUMENT_NAMES.
GM_PERCUSSION_SOUND_NAMES: List[str] = [
    GM_PERCUSSION_NAMES[key] for key in sorted(GM_PERCUSSION_NAMES)
]

# Reverse lookup (name -> key), case/whitespace-insensitive - a real MuseScore
# export's own <instrument-name> text is what "Apply MusicXML offset for
# percussion" cross-references against (wishlist #8 follow-up, confirmed
# against Hit It.mxl: MuseScore 4.7.4 exported every percussion instrument's
# <midi-unpitched> one key higher than the GM key its own <instrument-name>
# actually names - "Closed Hi-Hat" declared at 43, GM's real Closed Hi-Hat is
# 42). Keyed lowercase/stripped since nothing guarantees an exporter's
# instrument-name text matches this table's capitalisation exactly.
_GM_PERCUSSION_KEY_BY_NORMALISED_NAME: Dict[str, int] = {
    name.strip().lower(): key for key, name in GM_PERCUSSION_NAMES.items()
}


def gm_percussion_key_for_name(name: str) -> Optional[int]:
    """The file's own instrument-name text -> the GM key that name actually
    belongs to, or None for a name this table doesn't recognise (a custom
    kit's own invented name, e.g.) - degrades to "nothing to cross-reference
    against" rather than guessing. Exact match only (after normalising case/
    whitespace) - see detect_percussion_key_shift for why a fuzzy per-name
    match isn't used here."""
    return _GM_PERCUSSION_KEY_BY_NORMALISED_NAME.get(name.strip().lower())


def detect_percussion_key_shift(items: List[Tuple[str, int]]) -> Optional[int]:
    """Wishlist #8 follow-up: infers ONE consistent correction for a whole
    percussion part, from whichever of its items exactly name-match a GM
    sound, rather than guessing per item independently.

    `items` is [(declared_name, declared_key), ...] for every item in one
    part. Returns `declared_key - real_gm_key` when every exactly-matching
    item agrees on that same difference, else None (no exact match at all,
    or they disagree - not safe to guess a single correction).

    Why not just fuzzy-match every item's name on its own (e.g. "Snare"
    against GM's "Acoustic Snare"/"Electric Snare")? Tried against a real
    file (Hit It.mxl) and rejected: a short name like "Snare" or "Bass Drum"
    is genuinely ambiguous against GM's own longer names, and picking the
    "closest" one by word count landed on the wrong candidate for "Bass
    Drum" (GM's actual default is key 36 "Bass Drum 1", not the
    equally-plausible-by-word-count 35 "Acoustic Bass Drum"). A whole
    exporter's shift is far more reliable: Hit It.mxl's own
    unambiguous exact matches ("Closed Hi-Hat"->42 vs declared 43,
    "Tambourine"->54 vs declared 55) agree on a uniform -1, which is
    guaranteed correct to apply to "Snare"/"Bass Drum" too - the export
    quirk is per-file, not per-instrument.
    """
    shifts = {
        declared_key - real_key
        for name, declared_key in items
        for real_key in [gm_percussion_key_for_name(name)]
        if real_key is not None
    }
    if len(shifts) == 1:
        return next(iter(shifts))
    return None
