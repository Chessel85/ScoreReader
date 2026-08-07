# audio/metronome.py
"""E8/Ref 14: metronome click constants and the one rule that decides
whether a beat position gets a click - a plain module (constants + one pure
function), not a class, matching models/key_signatures.py and
models/duration_units.py's existing "plain module-level, not a class"
pattern for the same kind of small shared lookup.

Both audio/sequencer.py (playback, Ref 14 AC1/AC2) and main_window.py
(step navigation, Ref 14 AC3) call click_event_for_beat() so the two
contexts trigger identical clicks off one definition.
"""
from typing import Optional, Tuple

# GM percussion channel - live-tested feedback: a synthesized sawtooth lead
# "was awful" as a click sound. Claves (below) is a GM PERCUSSION voice,
# which General MIDI only maps correctly on channel 10 (0-indexed 9) - the
# same channel MusicData.PERCUSSION_CHANNEL reserves for a score's own
# percussion part (D-5). That's not a collision: multiple percussion note
# numbers (a drum kit's kick/snare/hihat, or this click) can sound
# simultaneously on channel 10 same as real drum kit voicing - each note
# number is its own independent drum voice.
METRONOME_CHANNEL = 9

# "Standard Kit" - channel 10 in a GM-conformant soundfont is hardwired to
# the percussion bank regardless of program, but selecting the standard kit
# explicitly keeps this from depending on that convention silently holding.
METRONOME_GM_PROGRAM = 0

# GM percussion key map note 75 - Claves. A fixed-pitch percussion voice
# (unlike a melodic instrument, GM percussion notes select a specific drum
# sound, not a pitch), so beat 1's accent (Ref 14 AC2) is distinguished by
# velocity (louder), not a different note number.
METRONOME_CLAVES_PITCH = 75
METRONOME_ACCENT_VELOCITY = 127  # beat 1 of every bar
METRONOME_CLICK_VELOCITY = 100  # every other beat

METRONOME_DURATION_MS = 40  # short and fixed, independent of note/score tempo


def click_event_for_beat(beat_position: float) -> Optional[Tuple[int, int, int, int, int]]:
    """(channel, program, pitch, velocity, duration_ms) for a click at this
    beat position, or None if beat_position isn't a whole beat - main beats
    are always whole numbers in the score's own ts-relative units (Ref 18),
    so this is the same test for "is this a beat" everywhere it's needed.
    Accented (louder) on beat 1 of the bar (Ref 14 AC2)."""
    if not float(beat_position).is_integer():
        return None
    velocity = METRONOME_ACCENT_VELOCITY if beat_position == 1 else METRONOME_CLICK_VELOCITY
    return METRONOME_CHANNEL, METRONOME_GM_PROGRAM, METRONOME_CLAVES_PITCH, velocity, METRONOME_DURATION_MS
