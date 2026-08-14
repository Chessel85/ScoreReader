# audio/metronome.py
"""E8/Ref 14: metronome click constants and the one rule deciding whether a
beat position gets a click.

A plain module (constants + one pure function), not a class - same shape as
models/key_signatures.py and models/duration_units.py.

Both audio/sequencer.py (playback) and main_window.py (step navigation) call
click_event_for_beat(), so the two contexts click off one definition.
"""
from typing import Optional, Tuple

# Accent vs regular beat is which SAMPLE plays, not a velocity difference:
# SynthEngine loads soundfonts/recall_score_sounds.sf2 as a second soundfont
# alongside FluidR3_GM and program_selects it on METRONOME_CHANNEL.
# Synthesised clicks (a sawtooth lead, then GM Claves accented by velocity)
# were both tried and rejected as sounds.
METRONOME_CHANNEL = 9  # reserved in MusicData.RESERVED_CHANNELS so no real
                       # part lands here. Nothing depends on channel 10's
                       # GM-percussion behaviour any more - the reservation
                       # is purely collision avoidance.
METRONOME_BANK = 0
METRONOME_PROGRAM = 1  # [preset:click_default] in tools/config.ini
METRONOME_ACCENT_NOTE = 60  # "accent" sample - beat 1 of every bar
METRONOME_OFFBEAT_NOTE = 61  # "offbeat" sample - every other beat
METRONOME_VELOCITY = 100


def click_event_for_beat(beat_position: float) -> Optional[Tuple[int, int, int, int, int]]:
    """(channel, bank, program, pitch, velocity) for a click at this beat
    position, or None if it isn't a whole beat - main beats are always whole
    numbers in the score's own ts-relative units (Ref 18), so this is the
    same "is this a beat" test everywhere it's needed.

    Duration is decided nowhere: each click zone is a one-shot, non-looping
    sample, and FluidSynth retires such a voice by itself once the sample
    data runs out. See SynthEngine.play_click.
    """
    if not float(beat_position).is_integer():
        return None
    pitch = METRONOME_ACCENT_NOTE if beat_position == 1 else METRONOME_OFFBEAT_NOTE
    return METRONOME_CHANNEL, METRONOME_BANK, METRONOME_PROGRAM, pitch, METRONOME_VELOCITY
