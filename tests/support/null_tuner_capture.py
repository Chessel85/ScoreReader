# tests/support/null_tuner_capture.py
from typing import List, Optional

from audio.pitch_detector import PitchResult
from audio.tuner_capture import PitchResultCallback


class NullTunerCapture:
    """Recording/injectable stand-in for audio.tuner_capture.TunerCapture.
    Never touches a real microphone. Mirrors that class's public interface
    (set_callback/set_target/list_devices/open/close/is_open/device_name) so
    TunerController and MainWindow(tuner_manager=...) can't tell the
    difference.

    available_devices is settable per test, mirroring
    NullMidiInputManager.available_ports. simulate_result invokes the stored
    callback directly and synchronously - tests don't need real cross-thread
    timing, since TunerController's own Qt.ConnectionType.QueuedConnection
    marshaling is exercised the same way regardless of which thread actually
    called it from."""

    def __init__(self, available_devices: Optional[List[str]] = None):
        self.available_devices: List[str] = list(available_devices or [])
        self._callback: Optional[PitchResultCallback] = None
        self._device_name: Optional[str] = None
        self._is_open: bool = False
        self.expected_hz: Optional[float] = None
        self.search_semitones: Optional[float] = None
        self.open_calls: List[Optional[str]] = []
        self.close_count: int = 0

    def set_callback(self, callback: Optional[PitchResultCallback]) -> None:
        self._callback = callback

    def set_target(self, expected_hz: float, search_semitones: float = 4.0) -> None:
        self.expected_hz = expected_hz
        self.search_semitones = search_semitones

    def list_devices(self) -> List[str]:
        return list(self.available_devices)

    def open(self, device_name: Optional[str]) -> bool:
        self.open_calls.append(device_name)
        if device_name is not None and device_name not in self.available_devices:
            return False
        self._device_name = device_name
        self._is_open = True
        return True

    def close(self) -> None:
        self.close_count += 1
        self._device_name = None
        self._is_open = False

    @property
    def is_open(self) -> bool:
        return self._is_open

    @property
    def device_name(self) -> Optional[str]:
        return self._device_name

    def simulate_result(self, result: Optional[PitchResult], peak_level: float = 0.0) -> None:
        if self._callback is not None:
            self._callback(result, peak_level)
