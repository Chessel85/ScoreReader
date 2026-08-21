# audio/strum_schedule.py
"""Turns a UG import's decoded strum pattern into an actual note-on
schedule, and dispatches playback events to the right synth call. Split
from audio/synth_engine.py deliberately: build_strum_schedule is a pure
function (no Qt, no timers), so the arpeggio math - the part most worth
getting right and easiest to get wrong - is directly unit-testable without
a real event loop. SynthEngine.play_strummed_bar (audio/synth_engine.py)
is the thin QTimer-driven wrapper around this.
"""
from typing import List, Optional, Tuple


def build_strum_schedule(
    pattern: List[str],
    midi_pitches: List[int],
    total_duration_ms: float,
    note_delay_ms: float = 20.0,
) -> List[Tuple[float, int, int, float]]:
    """Returns (start_offset_ms, pitch, velocity, note_duration_ms) for
    every individual note-on across one bar's strum pattern.

    Strokes are spaced evenly across total_duration_ms - UG's own
    strummings block is "part": "whole", one fixed pattern for the entire
    song, with no further per-bar timing info, so even spacing is the only
    thing there's a basis for. "down" fires the chord low-to-high, "up"
    high-to-low, each note_delay_ms after the previous string (your own
    steer on the timing). "mute" produces no events at all - a first
    attempt played it as a short, quiet chunk (the closest FluidSynth
    approximation to a palm mute without a dedicated sample), but live-
    tested that read as audible stuttering rather than a mute, so a muted
    slot is silent instead: it still occupies its place in the pattern
    (so surrounding strokes keep their real timing), it just sounds
    nothing.
    """
    if not pattern or not midi_pitches:
        return []

    slot_ms = max(1.0, total_duration_ms / len(pattern))
    events: List[Tuple[float, int, int, float]] = []

    for slot_index, direction in enumerate(pattern):
        slot_start = slot_index * slot_ms

        if direction == "mute":
            continue

        ordered = sorted(midi_pitches) if direction == "down" else sorted(midi_pitches, reverse=True)
        for i, pitch in enumerate(ordered):
            start = slot_start + i * note_delay_ms
            # Later strings in the arpeggio get a shorter ring so they stay
            # inside their own slot rather than bleeding into the next
            # stroke's timing.
            duration = max(20.0, slot_ms - i * note_delay_ms)
            events.append((start, pitch, 90, duration))

    return events


def sound_events(
    synth, music_data, events: List[Tuple], retrigger: bool, grace_events: Optional[List[Tuple]] = None
) -> None:
    """The single dispatch point discrete audition (PlaybackController) and
    continuous playback (Sequencer) both route through instead of calling
    synth.play_chord directly. A UG score's Chords part is the only part
    that ever contributes real pitches to `events` (Lyrics never does - see
    parsers/ug_timeline_builder.py), so get_playback_events_for_indices/
    get_playback_events_at_index always return exactly one group for a UG
    score - events[0] is always the right (and only) group to reroute.

    grace_events (from MusicData.get_grace_note_events_for_indices/
    get_grace_note_events_at_index) routes through play_chord_with_grace
    instead when non-empty - a UG score never has any (UG's synthetic
    Chords/Lyrics parts carry no MusicXML <grace> concept), so the two
    routes never need to combine. Every other case falls straight through
    to the unchanged play_chord path."""
    if not events:
        return
    if music_data.is_ug and music_data.ug_strum_pattern:
        channel, program, pitches, duration_ms = events[0]
        synth.play_strummed_bar(
            channel, program, pitches, music_data.ug_strum_pattern, duration_ms, retrigger=retrigger
        )
    elif grace_events:
        synth.play_chord_with_grace(events, grace_events, retrigger=retrigger)
    else:
        synth.play_chord(events, retrigger=retrigger)
