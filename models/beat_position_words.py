# models/beat_position_words.py
"""The spoken word for a ts-relative beat position ("1", "1 e", "1 and",
"1 a") - the talking-metronome vocabulary (Ref 28 AC3/AC4).

Extracted here so both audio/position_announcer.py (which turns the word
into a MIDI note on its dedicated channel) and models/strum_pattern.py
(which labels each strum slot) read one definition rather than two that
could drift. A pure lookup over a fixed table, no Qt, no audio - the same
category as models/strum_codes.py. audio/position_announcer.py re-exports
these names, so its own callers and tests are unchanged.
"""
from typing import Optional

NUMBER_WORDS = {
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
}

# Ref 28 AC4: a beat split into four (simple-time semiquavers) speaks
# e/and/a at 25/50/75%; split into three (a triplet) speaks and/a at 33/66%.
# 50% and 33% sharing "and", and 75% and 66% sharing "a", is per the AC and
# not a collision - a given remainder only ever matches one family.
FRACTIONAL_BEAT_WORDS = {
    0.25: "e",
    0.33: "and",
    0.5: "and",
    0.67: "a",
    0.75: "a",
}


def spoken_word_for_beat_position(beat_position: float) -> Optional[str]:
    """The word for this ts-relative beat position (Ref 18), or None if
    nothing in Ref 28 AC3/AC4 covers it - whole beat 8+ (AC3 defines 1-7),
    or a fraction outside the AC4 set (a demisemiquaver's 12.5%, say). None
    means stay silent; the announcer never invents a word to fill a gap.

    beat_position arrives already rounded to 2dp (TimelineBuilder), so exact
    float-key lookups are safe without a tolerance check.
    """
    whole = int(beat_position)
    fraction = round(beat_position - whole, 2)
    if fraction == 0:
        return NUMBER_WORDS.get(whole)
    return FRACTIONAL_BEAT_WORDS.get(fraction)
