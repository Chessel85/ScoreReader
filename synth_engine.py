# synth_engine.py
from typing import List, Optional
import mido
from PySide6.QtCore import QTimer


class SynthEngine:
    """Cross-platform MIDI playback abstraction wrapper using mido."""

    def __init__(self):
        self._outport = None
        self._off_timer = QTimer()
        self._off_timer.setSingleShot(True)
        self._off_timer.timeout.connect(self.stop_all_notes)
        self._active_midi_notes: List[int] = []
        self._initialize_port()

    def _initialize_port(self):
        """Attempts to open the default system MIDI output port."""
        try:
            # mido.open_output() opens the OS default virtual/hardware MIDI port
            self._outport = mido.open_output()
        except Exception as e:
            print(f"[WARN] Could not open default MIDI output port: {e}")
            self._outport = None

    def set_program(self, channel: int, program: int):
        """
        Sets the General MIDI instrument program (0-127) for a specific channel.
        Note: Expects a 0-indexed program value (0 = Piano, 24 = Nylon Guitar).
        """
        if self._outport is None:
            return

        clamped_program = max(0, min(127, program))
        msg = mido.Message(
            "program_change", channel=channel & 0x0F, program=clamped_program
        )
        self._outport.send(msg)

    def stop_all_notes(self):
        """Sends All Notes Off / Reset Controller commands across all standard channels."""
        if self._outport is None:
            return

        self._off_timer.stop()

        # Send Note-Off for any specific tracked active notes
        for note in self._active_midi_notes:
            for channel in range(16):
                msg = mido.Message(
                    "note_off", note=note, velocity=0, channel=channel
                )
                self._outport.send(msg)
        self._active_midi_notes.clear()

        # Control Change 123 = All Notes Off
        for channel in range(16):
            msg = mido.Message(
                "control_change", channel=channel, control=123, value=0
            )
            self._outport.send(msg)

    def play_notes(
        self,
        midi_notes: List[int],
        duration_ms: int,
        channel: int = 0,
        program: Optional[int] = None,
    ):
        """
        Stops running notes, updates the instrument program (if provided), 
        and triggers active MIDI pitch values for duration_ms.
        """
        # Always silence existing sound before starting new notes
        self.stop_all_notes()

        if self._outport is None or not midi_notes:
            return

        # Issue program change if provided
        if program is not None:
            self.set_program(channel=channel, program=program)

        self._active_midi_notes = list(midi_notes)

        # Trigger Note On for all active pitches
        for note in self._active_midi_notes:
            msg = mido.Message(
                "note_on", note=note, velocity=90, channel=channel & 0x0F
            )
            self._outport.send(msg)

        # Schedule Note Off after duration_ms
        self._off_timer.start(duration_ms)

    def close(self):
        """Silences audio and closes the output port cleanly."""
        self.stop_all_notes()
        if self._outport:
            self._outport.close()
            self._outport = None