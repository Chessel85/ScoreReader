# tests/support/fake_timer.py
from typing import Callable, List, Optional


class FakeTimer:
    """Deterministic stand-in for QTimer, injected into Sequencer (E4) the
    same way NullSynth is injected into MainWindow (D-7) - avoids a real
    wall-clock wait in tests. start(ms) just records the interval instead
    of scheduling anything; the test drives time forward explicitly by
    calling fire().
    """

    def __init__(self):
        self.single_shot = False
        self.scheduled_ms: List[int] = []
        self.running = False
        self._callback: Optional[Callable[[], None]] = None
        self.timeout = self  # so `.timeout.connect(cb)` works like the real signal

    def setSingleShot(self, value: bool) -> None:
        self.single_shot = value

    def connect(self, callback: Callable[[], None]) -> None:
        self._callback = callback

    def start(self, ms: int) -> None:
        self.scheduled_ms.append(ms)
        self.running = True

    def stop(self) -> None:
        self.running = False

    def fire(self) -> None:
        """Test helper: simulate the scheduled interval elapsing."""
        if not self.running:
            return
        self.running = False
        self._callback()
