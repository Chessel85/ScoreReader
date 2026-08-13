# audio/performance_cue.py
"""Ref 29: the Performance region's "something changed, check Region 5" cue
- a plain module (constants + one pure function), matching audio/
metronome.py and audio/position_announcer.py's existing "plain module-level,
not a class" pattern for this kind of small shared lookup.

Unlike click_event_for_beat()/announcement_event_for_beat(), this cue isn't
tied to a beat position - it fires whenever MainWindow detects the active
set of Region 5 rows has changed (see MainWindow._refresh_region_5), so
performance_cue_event() takes no argument and always returns the same fixed
event.
"""
from typing import Tuple

# Third reserved channel, alongside METRONOME_CHANNEL (9) and
# POSITION_ANNOUNCER_CHANNEL (8) - same reservation pattern (see both
# modules' own comments on why a shared channel/note-numbering scheme was
# rejected: FluidSynth releases a still-ringing one-shot by channel+key, not
# by preset, so two unrelated sounds sharing one would risk cutting each
# other off). MusicData.PERFORMANCE_CUE_CHANNEL duplicates this value, same
# as MusicData.POSITION_ANNOUNCER_CHANNEL already duplicates this module's
# sibling constant.
PERFORMANCE_CUE_CHANNEL = 7
PERFORMANCE_CUE_BANK = 0
PERFORMANCE_CUE_PROGRAM = 2  # [preset:performance_cue_default] in tools/config.ini
PERFORMANCE_CUE_NOTE = 60
PERFORMANCE_CUE_VELOCITY = 100


def performance_cue_event() -> Tuple[int, int, int, int, int]:
    """(channel, bank, program, pitch, velocity) for the performance-region
    change cue - always the same fixed event (one generic cue sound, not a
    per-marker-type one, per the user's own explicit choice)."""
    return (
        PERFORMANCE_CUE_CHANNEL,
        PERFORMANCE_CUE_BANK,
        PERFORMANCE_CUE_PROGRAM,
        PERFORMANCE_CUE_NOTE,
        PERFORMANCE_CUE_VELOCITY,
    )
