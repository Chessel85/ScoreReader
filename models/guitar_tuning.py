# models/guitar_tuning.py
"""Turning a tab row + fret number into a MIDI pitch, for the Ultimate
Guitar *Tab* import (parsers/ug_timeline_builder.py).

stdlib-only, like every other models/ module (models/gm_instruments.py states
the rule): this is fixed-table pitch arithmetic, not parsing. Octave
assignment is deliberately a simplification in the same spirit as
models/pitch_spelling.py - a tab carries no key signature and UG's own
tuning text gives only note letters, so octaves are inferred from the
conventional low-string-up layout, which is right for standard tuning and
every "drop"/"down a step" variant seen in practice.
"""
from typing import List, Optional

# UG prints ASCII tablature with the highest string on top, so tab row index
# 0 is the highest-pitched string. NoteData.string is 1-indexed with string
# 1 = the highest (the MusicXML / Guitar Pro convention), i.e.
# NoteData.string == row_index + 1. Standard 6-string guitar, high to low:
# E4 B3 G3 D3 A2 E2.
STANDARD_TUNING_HIGH_TO_LOW = [64, 59, 55, 50, 45, 40]

_LOW_STRING_ANCHOR_MIDI = 40  # E2 - where the lowest string is assumed to sit

_PITCH_CLASS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _token_to_pitch_class(token: str) -> Optional[int]:
    """'E' -> 4, 'D#' -> 3, 'Eb' -> 3, 'e|' -> 4 (trailing junk ignored).
    None when the leading character isn't a note letter."""
    token = token.strip()
    if not token:
        return None
    letter = token[0].upper()
    if letter not in _PITCH_CLASS:
        return None
    pc = _PITCH_CLASS[letter]
    for ch in token[1:]:
        if ch in ("#", "s", "S"):
            pc += 1
        elif ch == "b":
            pc -= 1
        else:
            break
    return pc % 12


def _assign_octaves_low_to_high(pitch_classes: List[int]) -> List[int]:
    """Given pitch classes ordered low string -> high string, pick an octave
    for each so the lowest string lands near E2 and every subsequent string
    is the nearest pitch of its class at or above the previous one. Handles
    standard tuning, drop tunings (low string below string 5) and uniform
    step-down tunings."""
    if not pitch_classes:
        return []
    first = pitch_classes[0]
    candidates = [first + 12 * octave for octave in range(1, 7)]
    low = min(candidates, key=lambda m: abs(m - _LOW_STRING_ANCHOR_MIDI))
    midis = [low]
    for pc in pitch_classes[1:]:
        prev = midis[-1]
        nxt = prev + ((pc - prev) % 12)
        if nxt == prev:
            nxt += 12  # never stack two strings on the exact same pitch
        midis.append(nxt)
    return midis


def parse_tuning_text(text: str) -> Optional[List[int]]:
    """Parse UgSource.tuning free text ('E A D G B E', drop-D 'D A D G B E',
    'E A D G B D', ...) into a MIDI pitch list ordered HIGH-TO-LOW, to match
    UG's tab-row order. UG writes tuning low string first, so the result is
    reversed before returning. None when the text can't be parsed or the
    string count isn't a plausible 4-8."""
    if not text:
        return None
    tokens = text.replace(",", " ").split()
    if not (4 <= len(tokens) <= 8):
        return None
    pcs: List[int] = []
    for tok in tokens:
        pc = _token_to_pitch_class(tok)
        if pc is None:
            return None
        pcs.append(pc)
    return list(reversed(_assign_octaves_low_to_high(pcs)))


def open_string_midis_from_rows(row_labels: List[str]) -> Optional[List[int]]:
    """The most reliable source: each tab row's own leading label ('e', 'B',
    'G', 'D', 'A', 'E') names that string. `row_labels` is top row -> bottom
    row (high string -> low string). Returns MIDI pitches HIGH-TO-LOW to
    match, or None when a label isn't a note letter or the count is
    implausible."""
    if not (4 <= len(row_labels) <= 8):
        return None
    pcs_high_to_low: List[int] = []
    for label in row_labels:
        pc = _token_to_pitch_class(label)
        if pc is None:
            return None
        pcs_high_to_low.append(pc)
    midis_low_to_high = _assign_octaves_low_to_high(list(reversed(pcs_high_to_low)))
    return list(reversed(midis_low_to_high))


def midi_for(open_midi: int, fret: int, capo: int) -> int:
    """Sounding MIDI pitch of a fretted note. capo raises every open string
    uniformly, so it simply adds to the fret offset."""
    return open_midi + fret + capo
