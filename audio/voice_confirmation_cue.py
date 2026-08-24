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
# Full MIDI velocity (127, not the more typical 100) - a one-shot UI
# confirmation sound has no expressive reason to hold back, and SF2's default
# velocity-to-attenuation curve measurably quietens anything below max (see
# tools/config.ini's own note on these three sounds needing to be as loud as
# the source recording allows).
VOICE_CONTROL_CUE_VELOCITY = 127

# Toggle-on/off tones (Ctrl+Shift+Enter/Return, or the menu action) - a
# different sound from the per-command confirmation ding above, since that
# one only ever fires once already listening. Share VOICE_CONTROL_CUE_CHANNEL
# and SynthEngine.play_voice_confirmation_cue rather than a dedicated
# channel/method - that call is already generic over (channel, bank,
# program, pitch, velocity), and these are one-shot sounds with the exact
# same "cut off whatever else was ringing on this channel first" reasoning
# the confirmation ding already has, so nothing new was needed to support them.
VOICE_RECOGNITION_STARTED_PROGRAM = 4  # [preset:voice_recognition_started]
VOICE_RECOGNITION_STOPPED_PROGRAM = 5  # [preset:voice_recognition_stopped]


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


def voice_recognition_started_event() -> Tuple[int, int, int, int, int]:
    """(channel, bank, program, pitch, velocity) for the "listening turned
    on" tone."""
    return (
        VOICE_CONTROL_CUE_CHANNEL,
        VOICE_CONTROL_CUE_BANK,
        VOICE_RECOGNITION_STARTED_PROGRAM,
        VOICE_CONTROL_CUE_NOTE,
        VOICE_CONTROL_CUE_VELOCITY,
    )


def voice_recognition_stopped_event() -> Tuple[int, int, int, int, int]:
    """(channel, bank, program, pitch, velocity) for the "listening turned
    off" tone."""
    return (
        VOICE_CONTROL_CUE_CHANNEL,
        VOICE_CONTROL_CUE_BANK,
        VOICE_RECOGNITION_STOPPED_PROGRAM,
        VOICE_CONTROL_CUE_NOTE,
        VOICE_CONTROL_CUE_VELOCITY,
    )
