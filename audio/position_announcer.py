# audio/position_announcer.py
"""Ref 28: position announcer (originally "talking metronome") word-
selection constants and the one pure lookup that decides what, if anything,
gets spoken at a beat position - a plain module, not a class, matching
audio/metronome.py's own "small shared lookup" pattern exactly, including
the same channel-reservation trick applied to a second, dedicated channel.

Both audio/sequencer.py (playback, Ref 28 AC1/AC2) and main_window.py
(step navigation) call announcement_event_for_beat() so the two contexts
speak identical words off one definition, the same way the two click call
sites already share click_event_for_beat().
"""
from typing import Optional, Tuple

# Own dedicated channel, separate from METRONOME_CHANNEL (audio/metronome.py,
# also 9) - required, not just tidy: click_default and talking_metronome_
# default both start their note layout at 60 (tools/config.ini), so a click
# accent and a spoken "one" landing on the same beat (AC2: both can be on at
# once) would otherwise noteon two different samples at the SAME
# (channel, key). FluidSynth's noteoff(channel, key) releases every voice
# matching that pair regardless of which preset/program it started under,
# so whichever one-shot's timer fired first would silence both. Two
# channels sidesteps this entirely, no note-numbering convention required.
# MusicData.get_channel_for_part reserves this channel (alongside
# PERCUSSION_CHANNEL) so no real instrument part ever lands on it either.
POSITION_ANNOUNCER_CHANNEL = 8
POSITION_ANNOUNCER_BANK = 0
POSITION_ANNOUNCER_PROGRAM = 0  # [preset:talking_metronome_default] in tools/config.ini
POSITION_ANNOUNCER_VELOCITY = 100

# Matches tools/config.ini's [preset:talking_metronome_default] note layout
# exactly (60=one .. 66=seven, 67=e, 68=and, 69=a) - hardcoded here rather
# than read out of the soundfont itself, the same choice audio/metronome.py
# already made for METRONOME_ACCENT_NOTE/OFFBEAT_NOTE.
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

# Ref 28 AC4: 25/50/75% (a beat split into four, e.g. simple-time
# semiquavers) speak e/and/a; 33/66% (a beat split into three, e.g. a
# triplet) speak and/a. 50% and 33% both map to "and", 75% and 66% both map
# to "a" - deliberate per the AC's own wording, not a collision, since a
# given beat_position's fractional remainder only ever matches one of the
# two subdivision families at a time.
FRACTIONAL_BEAT_WORDS = {
    0.25: "e",
    0.33: "and",
    0.5: "and",
    0.67: "a",
    0.75: "a",
}


def spoken_word_for_beat_position(beat_position: float) -> Optional[str]:
    """The word to speak for this ts-relative beat position (Ref 18), or
    None if nothing in Ref 28 AC3/AC4 covers it - e.g. whole beat 8+ (AC3
    only defines 1-7), or a part-beat fraction outside the fixed AC4 set
    (a demisemiquaver's 12.5%, say). None means the position announcer
    simply stays silent there; it never invents a word to cover a gap.

    beat_position arrives already rounded to 2 decimal places
    (TimelineBuilder), so exact float-key lookups against
    FRACTIONAL_BEAT_WORDS are safe without a tolerance check."""
    whole = int(beat_position)
    fraction = round(beat_position - whole, 2)
    if fraction == 0:
        return NUMBER_WORDS.get(whole)
    return FRACTIONAL_BEAT_WORDS.get(fraction)


def announcement_event_for_beat(beat_position: float) -> Optional[Tuple[int, int, int, int, int]]:
    """(channel, bank, program, pitch, velocity) for the word to speak at
    this beat position, or None if spoken_word_for_beat_position found
    nothing to say. Duration isn't decided here - or anywhere - for the same
    reason as click_event_for_beat: a one-shot sample retires itself when
    its data runs out. (R7: this used to cite a sidecar .sf2.json that no
    longer exists; see SynthEngine.play_click.)"""
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
