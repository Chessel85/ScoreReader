# audio/strum_schedule.py
"""Turns a decoded strum pattern into an actual note-on schedule, and
dispatches playback events to the right synth call.

build_strum_schedule is a pure function (no Qt, no timers) so the arpeggio
math is directly unit-testable without a real event loop.
SynthEngine.play_strum_pattern (audio/synth_engine.py) is the thin
QTimer-driven wrapper around it, used only by the Strumming Patterns dialog
for demo playback - per-chord strummed audition was removed (a
multi-pattern song's per-bar choice was arbitrary, and the audio was
unreadable anyway), so ordinary UG chord navigation now auditions as a
plain chord through the unchanged play_chord path.
"""
from typing import List, Optional, Tuple

from models.strum_codes import STRUM_CODES, StrumSlot

_BASE_VELOCITY = 90
_ACCENT_VELOCITY = 116
_MUTED_VELOCITY = 42


def build_strum_schedule(
    slots: List[StrumSlot],
    midi_pitches: List[int],
    slot_ms: float,
    note_delay_ms: float = 20.0,
) -> List[Tuple[float, int, int, float]]:
    """Returns (start_offset_ms, pitch, velocity, note_duration_ms) for
    every individual note-on across a strum pattern.

    Each slot occupies `slot_ms` (derived by the caller from the pattern's
    own bpm/denominator/is_triplet - see models/strum_pattern.slot_ms), so
    a 32-slot two-bar sixteenth pattern plays across two bars, not squeezed
    into one chord. A "down" stroke fires the chord low-to-high, "up"
    high-to-low, each `note_delay_ms` after the previous string.

    Effects:
    - "pause" / "real pause": nothing sounds, but the slot still takes up
      its `slot_ms` so surrounding strokes keep their real timing.
    - "mute" and "p.m." (palm mute): a short, quiet damped stroke.
    - "accent": the same stroke at a higher velocity.
    """
    if not slots or not midi_pitches:
        return []

    events: List[Tuple[float, int, int, float]] = []
    for slot_index, slot in enumerate(slots):
        slot_start = slot_index * slot_ms
        if slot.stroke in ("pause", "real pause"):
            continue

        damped = slot.effect == "mute" or slot.stroke == "p.m."
        if slot.effect == "accent":
            velocity = _ACCENT_VELOCITY
        elif damped:
            velocity = _MUTED_VELOCITY
        else:
            velocity = _BASE_VELOCITY

        # p.m. reads as a downstroke in practice; otherwise honour the mark.
        low_to_high = slot.stroke in ("down", "p.m.")
        ordered = sorted(midi_pitches) if low_to_high else sorted(midi_pitches, reverse=True)
        for i, pitch in enumerate(ordered):
            start = slot_start + i * note_delay_ms
            full = max(20.0, slot_ms - i * note_delay_ms)
            duration = min(full, slot_ms * 0.35) if damped else full
            events.append((start, pitch, velocity, duration))
    return events


def slots_from_codes(codes: List[int]) -> List[StrumSlot]:
    """Decode raw UG codes to StrumSlots, unknown codes as a silent pause
    (the safest fallback - see models/strum_codes)."""
    return [STRUM_CODES.get(code, StrumSlot("pause", "none")) for code in codes]


def sound_events(
    synth, music_data, events: List[Tuple], retrigger: bool, grace_events: Optional[List[Tuple]] = None
) -> None:
    """The single dispatch point discrete audition (PlaybackController) and
    continuous playback (Sequencer) both route through instead of calling
    synth.play_chord directly.

    grace_events (from MusicData.get_grace_note_events_for_indices/
    get_grace_note_events_at_index) routes through play_chord_with_grace
    when non-empty; every other case falls straight through to play_chord.
    """
    if not events:
        return
    if grace_events:
        synth.play_chord_with_grace(events, grace_events, retrigger=retrigger)
    else:
        synth.play_chord(events, retrigger=retrigger)
