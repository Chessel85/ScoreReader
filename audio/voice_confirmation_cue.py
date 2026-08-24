# audio/voice_confirmation_cue.py
"""Hands-free voice control (feature/voice-control): the short "ding" that
confirms a spoken command was recognized and acted upon. Same plain-module
shape as audio/performance_cue.py.

Fires unconditionally today for every recognized command - see
controllers/voice_control_controller.py's _SUPPRESSED_CUE_COMMANDS for the
extension point the user explicitly asked to have in place before suppressing
it for individual commands (e.g. "play", where it might interfere with
noticing playback has started) or dropping the cue feature altogether.
"""
from typing import Tuple

# Fifth reserved channel, alongside METRONOME_CLICK_CHANNEL (9),
# POSITION_ANNOUNCER_CHANNEL (8), PERFORMANCE_CUE_CHANNEL (7) and
# LIVE_MIDI_INPUT_CHANNEL (6), for the same reason spelled out in
# position_announcer.py: FluidSynth releases a ringing one-shot by
# channel+key, not by preset, so unrelated sounds sharing a channel can cut
# each other off. MusicData.VOICE_CONTROL_CUE_CHANNEL duplicates this value
# (models/ doesn't import audio/).
VOICE_CONTROL_CUE_CHANNEL = 5
VOICE_CONTROL_CUE_BANK = 0
VOICE_CONTROL_CUE_PROGRAM = 3  # [preset:voice_command_confirmation]
VOICE_CONTROL_CUE_NOTE = 60
VOICE_CONTROL_CUE_VELOCITY = 100


def voice_confirmation_cue_event() -> Tuple[int, int, int, int, int]:
    """(channel, bank, program, pitch, velocity) for the ding - one generic
    sound for every command, not one per command (mirrors
    performance_cue_event's own "one generic sound" reasoning)."""
    return (
        VOICE_CONTROL_CUE_CHANNEL,
        VOICE_CONTROL_CUE_BANK,
        VOICE_CONTROL_CUE_PROGRAM,
        VOICE_CONTROL_CUE_NOTE,
        VOICE_CONTROL_CUE_VELOCITY,
    )
