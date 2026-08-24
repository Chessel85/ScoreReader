# tests/support/null_voice_recognizer.py
from typing import Callable, List, Optional


class NullVoiceRecognizer:
    """Recording/injectable stand-in for audio.voice_recognition.
    VoiceRecognitionManager. Never touches a real Vosk model or microphone.
    Mirrors that class's public interface (set_callback/
    set_diagnostic_callback/list_devices/start/stop/is_running/
    rebuild_grammar/set_confidence_threshold) so VoiceControlController and
    VoiceControlTestDialog can't tell the difference.

    available_devices is settable per test, so both "device found" (start
    succeeds) and "not present this session, degrade silently" (start
    returns False) auto-start paths are testable without hardware.

    simulate_recognition/simulate_diagnostic invoke the stored callback
    directly and synchronously - tests don't need real cross-thread timing,
    since VoiceControlController's own Qt.ConnectionType.QueuedConnection
    marshaling is exercised the same way regardless of which thread actually
    called it from (mirrors NullMidiInputManager's own reasoning)."""

    def __init__(self, available_devices: Optional[List[str]] = None):
        self.available_devices: List[str] = list(available_devices or [])
        self._callback: Optional[Callable[[str, float, Optional[int]], None]] = None
        self._diagnostic_callback: Optional[Callable[[str, float, bool], None]] = None
        self._running: bool = False
        self.start_calls: List[tuple] = []
        self.stop_count: int = 0
        self.rebuild_calls: List[int] = []
        self.confidence_threshold: float = 0.0

    def set_callback(self, callback) -> None:
        self._callback = callback

    def set_diagnostic_callback(self, callback) -> None:
        self._diagnostic_callback = callback

    def list_devices(self) -> List[str]:
        return list(self.available_devices)

    def start(self, device_name: Optional[str], confidence_threshold: float) -> bool:
        self.start_calls.append((device_name, confidence_threshold))
        self.confidence_threshold = confidence_threshold
        if device_name is not None and device_name not in self.available_devices:
            return False
        self._running = True
        return True

    def stop(self) -> None:
        self.stop_count += 1
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def rebuild_grammar(self, total_measures: int) -> None:
        self.rebuild_calls.append(total_measures)

    def set_confidence_threshold(self, confidence_threshold: float) -> None:
        self.confidence_threshold = confidence_threshold

    def simulate_recognition(
        self, command_name: str, confidence: float = 100.0, measure_number: Optional[int] = None
    ) -> None:
        if self._callback is not None:
            self._callback(command_name, confidence, measure_number)

    def simulate_diagnostic(self, heard_text: str, confidence: float, accepted: bool) -> None:
        if self._diagnostic_callback is not None:
            self._diagnostic_callback(heard_text, confidence, accepted)
