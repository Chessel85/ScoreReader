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
        self.stop_all_notes()

        if not midi_notes:
            return

        if program is not None:
            self.set_program(channel, program)

        self.played.append(
            {
                "midi_notes": list(midi_notes),
                "duration_ms": duration_ms,
                "channel": channel,
                "program": program,
            }
        )

    def close(self) -> None:
        self.closed = True

    @property
    def last_played(self) -> Optional[Dict[str, Any]]:
        return self.played[-1] if self.played else None
