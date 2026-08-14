# audio/position_announcer.py
"""Ref 28: position announcer (originally "talking metronome") - constants
and the one pure lookup deciding what, if anything, is spoken at a beat
position. Same plain-module shape as audio/metronome.py.

Both audio/sequencer.py (playback) and main_window.py (step navigation) call
announcement_event_for_beat(), so the two contexts speak off one definition.
"""
from typing import Optional, Tuple

# A dedicated channel is REQUIRED, not just tidy. click_default and
# talking_metronome_default both start their note layout at 60
# (tools/config.ini), so a click and a spoken word on the same beat (AC2
# allows both at once) would noteon two different samples at the same
# (channel, key). FluidSynth's noteoff(channel, key) releases every voice
# matching that pair regardless of preset, so silencing one would silence
# both. Two channels sidesteps it with no note-numbering convention to
# remember. MusicData.RESERVED_CHANNELS keeps real parts off this one.
POSITION_ANNOUNCER_CHANNEL = 8
POSITION_ANNOUNCER_BANK = 0
POSITION_ANNOUNCER_PROGRAM = 0  # [preset:talking_metronome_default]
POSITION_ANNOUNCER_VELOCITY = 100

# Mirrors tools/config.ini's [preset:talking_metronome_default] note layout.
WORD_NOTES = {
    "one": 60,
    "two": 61,
    "three": 62,
    "four": 63,
    "five": 64,
    "six": 65,
    "seven": 66,
    "e": 67,
    "and": 68,
    "a": 69,
}

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


def announcement_event_for_beat(beat_position: float) -> Optional[Tuple[int, int, int, int, int]]:
    """(channel, bank, program, pitch, velocity) for the word to speak here,
    or None if there's nothing to say. Duration is decided nowhere, same as
    click_event_for_beat - a one-shot sample retires itself."""
    word = spoken_word_for_beat_position(beat_position)
    if word is None:
        return None
    pitch = WORD_NOTES[word]
    return (
        POSITION_ANNOUNCER_CHANNEL,
        POSITION_ANNOUNCER_BANK,
        POSITION_ANNOUNCER_PROGRAM,
        pitch,
        POSITION_ANNOUNCER_VELOCITY,
    )
