# tests/support/null_synth.py
from typing import Any, Dict, List, Optional


class NullSynth:
    """Records playback calls instead of producing sound.

    Mirrors the SynthEngine interface used by MainWindow, including its
    behaviour of silencing current notes before starting new ones, so
    assertions about ordering stay meaningful.
    """

    def __init__(self):
        self.played: List[Dict[str, Any]] = []
        self.program_changes: List[tuple] = []
        self.stop_count: int = 0
        self.closed: bool = False
        self.clicks: List[Dict[str, Any]] = []
        self.words: List[Dict[str, Any]] = []
        self.performance_cues: List[Dict[str, Any]] = []

    def set_program(self, channel: int, program: int) -> None:
        self.program_changes.append((channel, program))

    def stop_all_notes(self) -> None:
        self.stop_count += 1

    def play_notes(
        self,
        midi_notes: List[int],
        duration_ms: int = 250,
        channel: int = 0,
        program: Optional[int] = None,
    ) -> None:
        self.play_chord([(channel, program, midi_notes)], duration_ms)

    def play_chord(
        self,
        events: List[tuple],
        duration_ms: int = 250,
        retrigger: bool = True,
    ) -> None:
        """Records one entry per (channel, program, midi_notes[, duration_ms]) group.

        Mirrors SynthEngine.play_chord: retrigger=True (the default) calls
        stop_all_notes() for the whole chord first - discrete audition's
        "everything sounding gets silenced before the next thing plays".
        The Sequencer passes retrigger=False for its natural step-to-step
        advance, so real playback layers a new part's notes on top of
        other parts still ringing instead of cutting them off. Every part's
        group is recorded with its OWN duration_ms - falling back to the
        outer duration_ms when a group omits one (play_notes()'s
        single-group callers) - so tests can assert both separate
        channels/programs and separate per-part ring-out durations (Ref 9
        AC2, Ref 13 AC2).
        """
        if retrigger:
            self.stop_all_notes()

        for event in events:
            channel, program, midi_notes = event[0], event[1], event[2]
            group_duration_ms = event[3] if len(event) > 3 else duration_ms
            if not midi_notes:
                continue

            if program is not None:
                self.set_program(channel, program)

            self.played.append(
                {
                    "midi_notes": list(midi_notes),
                    "duration_ms": group_duration_ms,
                    "channel": channel,
                    "program": program,
                }
            )

    def play_click(self, channel: int, bank: int, program: int, pitch: int, velocity: int) -> None:
        """E8: mirrors SynthEngine.play_click - recorded separately from
        `played` (real notes), and deliberately does NOT call
        stop_all_notes(), matching the real engine's independent click path.
        No duration_ms here (unlike the old signature): the real engine now
        looks each click's own duration up internally from a sidecar file
        NullSynth has no equivalent of - tests that care about a specific
        click sound assert on `pitch` (which sample) instead."""
        self.clicks.append(
            {
                "channel": channel,
                "bank": bank,
                "program": program,
                "pitch": pitch,
                "velocity": velocity,
            }
        )

    def play_word(self, channel: int, bank: int, program: int, pitch: int, velocity: int) -> None:
        """Ref 28: mirrors SynthEngine.play_word - recorded separately from
        both `played` and `clicks` so a test can assert the position
        announcer fired independently of (and simultaneously with) a click,
        the whole point of giving it its own channel."""
        self.words.append(
            {
                "channel": channel,
                "bank": bank,
                "program": program,
                "pitch": pitch,
                "velocity": velocity,
            }
        )

    def play_performance_cue(
        self, channel: int, bank: int, program: int, pitch: int, velocity: int
    ) -> None:
        """Ref 29: mirrors SynthEngine.play_performance_cue - recorded
        separately from `played`/`clicks`/`words` so a test can assert the
        Performance region's change cue fired independently of anything
        else."""
        self.performance_cues.append(
            {
                "channel": channel,
                "bank": bank,
                "program": program,
                "pitch": pitch,
                "velocity": velocity,
            }
        )

    def close(self) -> None:
        self.closed = True

    @property
    def last_played(self) -> Optional[Dict[str, Any]]:
        return self.played[-1] if self.played else None
