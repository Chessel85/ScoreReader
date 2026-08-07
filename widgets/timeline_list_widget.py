# timeline_list_widget.py
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget

if TYPE_CHECKING:
    from main_window import MainWindow


class TimelineListWidget(QListWidget):
    """
    Region 3 list widget handling custom timeline traversal (Left/Right)
    and single-note selection collapsing (Up/Down).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # Ref 6 (C4): digits typed while focus is here build up a target bar
        # number, jumped to on Enter and cleared on Escape or any other key
        # that already has its own meaning (arrow keys etc) - stale pending
        # digits silently waiting for a future Enter would be confusing.
        self._pending_digits = ""

    def _main_window(self) -> "MainWindow":
        # This widget is only ever created by MainWindow.setup_ui and added
        # to its central widget, so window() is always the MainWindow - a
        # direct call here fails loudly if that ever stops being true,
        # rather than silently no-op'ing the keystroke the way the old
        # hasattr(main_win, ...) guards did.
        return self.window()  # type: ignore[return-value]

    def keyPressEvent(self, event):
        key = event.key()
        main_win = self._main_window()
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        no_modifiers = event.modifiers() == Qt.KeyboardModifier.NoModifier

        if no_modifiers and Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            self._pending_digits += chr(key)
            main_win.on_pending_digits_changed(self._pending_digits)
            return
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._pending_digits:
                digits = self._pending_digits
                self._pending_digits = ""
                main_win.on_pending_digits_changed(self._pending_digits)
                main_win.navigate_to_typed_measure(digits)
            # else: no digits pending - reserved for E6 (2-bar audition on
            # Enter), not built yet, so this key is currently inert.
            return
        elif key == Qt.Key.Key_Escape:
            if self._pending_digits:
                self._pending_digits = ""
                main_win.on_pending_digits_changed(self._pending_digits)
            return

        if self._pending_digits:
            self._pending_digits = ""
            main_win.on_pending_digits_changed(self._pending_digits)

        if key == Qt.Key.Key_Left:
            if ctrl:
                main_win.navigate_measure_left()
            else:
                main_win.navigate_timeline_left()
        elif key == Qt.Key.Key_Right:
            if ctrl:
                main_win.navigate_measure_right()
            else:
                main_win.navigate_timeline_right()
        elif key == Qt.Key.Key_Home:
            main_win.navigate_timeline_home()
        elif key == Qt.Key.Key_End:
            main_win.navigate_timeline_end()
        elif key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            super().keyPressEvent(event)
            main_win.on_region_3_vertical_move()
        elif key == Qt.Key.Key_Tab:
            main_win.focus_next_region(self)
        elif key == Qt.Key.Key_Backtab:
            main_win.focus_previous_region(self)
        else:
            super().keyPressEvent(event)