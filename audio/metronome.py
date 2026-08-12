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

# tasks.txt E11/D-14: the built-in click sound went through two rejected
# attempts (a synthesized sawtooth lead, then GM percussion Claves with
# velocity distinguishing the accent) before landing here - a small
# project-authored soundfont (tools/wav_to_sf2.py, built from
# tools/config.ini, checked into soundfonts/recall_score_sounds.sf2/.json
# despite soundfonts/ otherwise being gitignored - see .gitignore's own
# comment). SynthEngine loads it as a SECOND soundfont alongside
# FluidR3_GM and selects it explicitly via program_select on
# METRONOME_CHANNEL, so accent vs regular is now which SAMPLE plays (two
# distinct recorded sounds), not a velocity difference on one fixed voice
# - unlike the old Claves approach, where only velocity distinguished
# beat 1.
METRONOME_CHANNEL = 9  # same reservation as before - MusicData skips this
                        # channel when assigning real parts (D-5); no
                        # longer relying on channel 10's GM-percussion
                        # bank behaviour, just kept for the same
                        # collision-avoidance reason.
METRONOME_BANK = 0
METRONOME_PROGRAM = 1  # [preset:click_default] in tools/config.ini
METRONOME_ACCENT_NOTE = 60  # "accent" sample - beat 1 of every bar
METRONOME_OFFBEAT_NOTE = 61  # "offbeat" sample - every other beat
METRONOME_VELOCITY = 100  # constant now the accent is a different sample,
                           # not a louder one


def click_event_for_beat(beat_position: float) -> Optional[Tuple[int, int, int, int, int]]:
    """(channel, bank, program, pitch, velocity) for a click at this beat
    position, or None if beat_position isn't a whole beat - main beats are
    always whole numbers in the score's own ts-relative units (Ref 18), so
    this is the same test for "is this a beat" everywhere it's needed.
    Duration isn't decided here: SynthEngine.play_click looks each
    sample's own natural duration up from the sidecar
    soundfonts/recall_score_sounds.sf2.json this module has no need to
    know about (keeps this function a pure lookup, no file I/O)."""
    if not float(beat_position).is_integer():
        return None
    pitch = METRONOME_ACCENT_NOTE if beat_position == 1 else METRONOME_OFFBEAT_NOTE
    return METRONOME_CHANNEL, METRONOME_BANK, METRONOME_PROGRAM, pitch, METRONOME_VELOCITY
