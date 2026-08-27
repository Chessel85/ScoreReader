# tests/test_device_enumeration_worker.py
"""P1: audio settings dialogs enumerate input devices off the Qt main
thread (voice control's scan spawns a subprocess). DeviceEnumerationThread
is the shared worker; main_window._scan_devices_async drives it."""
import threading

from workers.device_enumeration_worker import DeviceEnumerationThread


def test_worker_runs_enumeration_off_the_calling_thread_and_emits_the_result(qtbot):
    calling_thread = threading.get_ident()
    ran_on = {}

    def enumerate_fn():
        ran_on["id"] = threading.get_ident()
        return ["Mic A", "Mic B"]

    thread = DeviceEnumerationThread(enumerate_fn)
    with qtbot.waitSignal(thread.devices_found, timeout=2000) as blocker:
        thread.start()
    thread.wait()

    assert blocker.args == [["Mic A", "Mic B"]]
    assert ran_on["id"] != calling_thread


def test_worker_emits_empty_list_when_enumeration_raises(qtbot):
    def enumerate_fn():
        raise RuntimeError("device query failed")

    thread = DeviceEnumerationThread(enumerate_fn)
    with qtbot.waitSignal(thread.devices_found, timeout=2000) as blocker:
        thread.start()
    thread.wait()

    assert blocker.args == [[]]
