# audio/position_announcer.py
"""Ref 28: position announcer (originally "talking metronome") - constants
and the one pure lookup deciding what, if anything, is spoken at a beat
position. Same plain-module shape as audio/metronome.py.

Both audio/sequencer.py (playback) and main_window.py (step navigation) call
announcement_event_for_beat(), so the two contexts speak off one definition.
"""
from typing import Optional, Tuple

# Ref 28 AC3/AC4: the ts-relative beat-position word ("one", "e", "and",
# "a") now lives in models/beat_position_words.py so models/strum_pattern.py
# can share it without importing audio/. Re-exported here for callers/tests
# that import these names from this module.
from models.beat_position_words import (  # noqa: F401
    FRACTIONAL_BEAT_WORDS,
    NUMBER_WORDS,
    spoken_word_for_beat_position,
)

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
