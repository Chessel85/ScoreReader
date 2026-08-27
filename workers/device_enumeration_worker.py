# workers/device_enumeration_worker.py
from typing import Callable, List

from PySide6.QtCore import QThread, Signal


class DeviceEnumerationThread(QThread):
    """Runs a device-enumeration callable off the UI thread.

    Enumerating voice-control input devices spawns a whole Python
    subprocess (audio/voice_recognition.list_input_devices, up to a
    multi-second timeout); the Tuner and Live MIDI equivalents call into
    PortAudio / RtMidi host-API scans. All of them block the caller for
    anything from tens of milliseconds to seconds, and every settings
    dialog used to call them synchronously on the Qt main thread while
    building the device combo - a frozen main thread in a screen-reader-
    first app is silence with no cue, indistinguishable from a hang.

    Same shape as ScoreLoadThread / UgImportThread: do the blocking work in
    run(), hand the result back through a queued Signal. `enumerate_fn` is
    whichever controller's `available_devices` (a plain callable returning
    a list of device-name strings); it must not touch Qt objects, since it
    runs on this thread.
    """

    devices_found = Signal(list)

    def __init__(self, enumerate_fn: Callable[[], List[str]], parent=None):
        super().__init__(parent)
        self._enumerate_fn = enumerate_fn

    def run(self):
        try:
            devices = list(self._enumerate_fn())
        except Exception as e:  # never let a scan failure kill the thread
            print(f"[WARN] Device enumeration failed: {e}")
            devices = []
        self.devices_found.emit(devices)
