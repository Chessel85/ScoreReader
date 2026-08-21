# tests/support/null_live_midi_input.py
from typing import List, Optional

from audio.midi_input import MessageCallback, NOTE_OFF, NOTE_ON


class NullMidiInputManager:
    """Recording/injectable stand-in for audio.midi_input.MidiInputManager.
    Never touches a real MIDI device. Mirrors that class's public interface
    (set_callback/list_ports/open/close/is_open/device_name) so
    LiveMidiInputController and MainWindow(live_midi_manager=...) can't
    tell the difference.

    available_ports is settable per test, so both "device found" (open
    succeeds) and "not present this session, degrade silently" (open
    returns False) auto-connect paths are testable without hardware.

    simulate_note_on/simulate_note_off invoke the stored callback directly
    and synchronously - tests don't need real cross-thread timing, since
    LiveMidiInputController's own Qt.ConnectionType.QueuedConnection
    marshaling is exercised the same way regardless of which thread actually
    called it from."""

    def __init__(self, available_ports: Optional[List[str]] = None):
        self.available_ports: List[str] = list(available_ports or [])
        self._callback: Optional[MessageCallback] = None
        self._device_name: Optional[str] = None
        self.open_calls: List[str] = []
        self.close_count: int = 0

    def set_callback(self, callback: Optional[MessageCallback]) -> None:
        self._callback = callback

    def list_ports(self) -> List[str]:
        return list(self.available_ports)

    def open(self, device_name: str) -> bool:
        self.open_calls.append(device_name)
        if device_name not in self.available_ports:
            return False
        self._device_name = device_name
        return True

    def close(self) -> None:
        self.close_count += 1
        self._device_name = None

    @property
    def is_open(self) -> bool:
        return self._device_name is not None

    @property
    def device_name(self) -> Optional[str]:
        return self._device_name

    def simulate_note_on(self, pitch: int, velocity: int) -> None:
        if self._callback is not None:
            self._callback(NOTE_ON, pitch, velocity)

    def simulate_note_off(self, pitch: int) -> None:
        if self._callback is not None:
            self._callback(NOTE_OFF, pitch, 0)
