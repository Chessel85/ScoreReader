# models/strum_codes.py
"""S2: Ultimate Guitar's undocumented strumming-pattern code vocabulary,
and the two ways this app reads it.

A pure lookup table over a fixed numeric vocabulary - the same category as
models/gm_instruments.py and models/gm_percussion_map.py, which already
live here - so models/ can read it without importing parsers/. It was
previously in parsers/ug_source.py, which made MusicData.ug_strum_pattern a
models -> parsers dependency for what is really just a decode table.

parsers/ug_source.py re-exports all four names, so its own callers (and the
tests that import them from there) are unchanged.

The codes themselves were confirmed by the user against a real UG page; no
public documentation exists for them. The two decodes are two different
interpretations of the same tab_view.strummings[0].measures[] field:
words for Region 1's display text (parsers/ug_reader.py), directions for
actual playback (audio/strum_schedule.py, via MusicData.ug_strum_pattern).
"""
from typing import List, Optional

STRUM_CODE_WORDS = {1: "downstroke", 101: "upstroke", 202: "muted strum"}
STRUM_CODE_DIRECTIONS = {1: "down", 101: "up", 202: "mute"}


def strumming_pattern_text(strum_codes: List[int]) -> Optional[str]:
    """Region 1 credits text for a whole-song strum pattern (UG's own
    strummings block is "part": "whole" - one fixed pattern for the entire
    song, not per-bar/per-section - so this is a score-wide fact like
    Tempo/Key/Tuning, shown once, never repeated per chord note). An
    unrecognised code (should one turn up on a different tab) renders as
    its own raw number rather than raising."""
    if not strum_codes:
        return None
    words = [STRUM_CODE_WORDS.get(code, str(code)) for code in strum_codes]
    return ", ".join(words)


def strum_directions(strum_codes: List[int]) -> List[str]:
    """The same codes, decoded into audio/strum_schedule.py's compact
    direction vocabulary ("down"/"up"/"mute") instead of display words. An
    unrecognised code defaults to "mute" - the quietest, safest fallback
    for a code outside the three the user confirmed, rather than guessing a
    stroke direction."""
    return [STRUM_CODE_DIRECTIONS.get(code, "mute") for code in strum_codes]
