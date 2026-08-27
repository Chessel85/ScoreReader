# main.py
import os
import sys


def _redirect_stdio_if_headless():
    """A PyInstaller console=False build (required for a GUI app, so no
    console flashes on launch) runs with sys.stdout/sys.stderr set to None,
    not merely closed. This app's error handling is print()-based
    throughout, so any warning - SynthEngine failing to open an audio device
    on a machine with no sound card, say - would otherwise crash with
    "'NoneType' object has no attribute 'write'".

    Must run before any other import that could print."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    log_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Recall Score")
    try:
        os.makedirs(log_dir, exist_ok=True)
        log_file = open(os.path.join(log_dir, "recall_score.log"), "a", encoding="utf-8", buffering=1)
    except OSError:
        log_file = open(os.devnull, "w")
    if sys.stdout is None:
        sys.stdout = log_file
    if sys.stderr is None:
        sys.stderr = log_file


_redirect_stdio_if_headless()

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from main_window import MainWindow
from widgets.accessible_menu_style import AccessibleMenuStyle


def _app_icon_path():
    """RecallScore.ico lives next to main.py in dev, and at the frozen bundle
    root (sys._MEIPASS) once packaging/RecallScore.spec bundles
    packaging/RecallScore.ico - see M2. Returns None until the user supplies
    that file; QIcon(None) would raise, so callers must check first."""
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    icon_path = os.path.join(base_dir, "RecallScore.ico")
    return icon_path if os.path.exists(icon_path) else None


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Recall Score")
    # Let the menu highlight rest on disabled items so a screen reader
    # announces them ("Close, unavailable") instead of skipping them.
    app.setStyle(AccessibleMenuStyle(app.style()))
    icon_path = _app_icon_path()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()