# models/strum_codes.py
"""Ultimate Guitar's undocumented strumming-pattern code vocabulary.

A pure lookup table over a fixed numeric vocabulary - the same category as
models/gm_instruments.py and models/gm_percussion_map.py, which already
live here - so models/ can read it without importing parsers/.

The full 9-code table below is taken verbatim from UG's own front-end
bundle (webpack module 78736, each numeric code -> {stroke, effect}); the
app previously knew only 3 of them and mislabelled 202 (a pause - the
single most common code in every real pattern) as a "muted strum".

parsers/ug_source.py re-exports the names its own callers already import
from there, so those import sites are unchanged.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class StrumSlot:
    """One slot of a decoded strum pattern. `stroke` is one of
    "down"/"up"/"p.m."/"pause"/"real pause"; `effect` is one of
    "none"/"mute"/"accent"."""

    stroke: str
    effect: str


# code -> (stroke, effect), from UG's own bundle. 201 is a palm mute,
# 202/203 are pauses (silent slots that still take up their place in the
# bar's timing).
STRUM_CODES: Dict[int, StrumSlot] = {
    1: StrumSlot("down", "none"),
    2: StrumSlot("down", "mute"),
    3: StrumSlot("down", "accent"),
    101: StrumSlot("up", "none"),
    102: StrumSlot("up", "mute"),
    103: StrumSlot("up", "accent"),
    201: StrumSlot("p.m.", "none"),
    202: StrumSlot("pause", "none"),
    203: StrumSlot("real pause", "none"),
}


def slot_words(code: int) -> str:
    """The spoken form of one code: "down", "down muted", "down accented",
    "up", "up muted", "up accented", "palm mute", "pause", "real pause". An
    unknown code (should one turn up on a different tab) renders as
    "code N" rather than being silently coerced to a stroke."""
    slot = STRUM_CODES.get(code)
    if slot is None:
        return f"code {code}"
    if slot.stroke == "p.m.":
        return "palm mute"
    if slot.stroke in ("pause", "real pause"):
        return slot.stroke
    if slot.effect == "mute":
        return f"{slot.stroke} muted"
    if slot.effect == "accent":
        return f"{slot.stroke} accented"
    return slot.stroke


def strumming_pattern_text(strum_codes: List[int]) -> Optional[str]:
    """Region 1 credits text for a whole-song strum pattern - one fixed
    pattern for the entire song (a score-wide fact like Tempo/Key/Tuning,
    shown once, never repeated per chord note). None when there is no
    pattern. An unrecognised code renders as "code N" via slot_words."""
    if not strum_codes:
        return None
    return ", ".join(slot_words(code) for code in strum_codes)
