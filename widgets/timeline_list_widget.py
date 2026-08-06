# timeline_list_widget.py
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget


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

    def keyPressEvent(self, event):
        key = event.key()
        main_win = self.window()
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        no_modifiers = event.modifiers() == Qt.KeyboardModifier.NoModifier

        if no_modifiers and Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            self._pending_digits += chr(key)
            self._notify_pending_digits_changed(main_win)
            return
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._pending_digits:
                digits = self._pending_digits
                self._pending_digits = ""
                self._notify_pending_digits_changed(main_win)
                if hasattr(main_win, "navigate_to_typed_measure"):
                    main_win.navigate_to_typed_measure(digits)
            # else: no digits pending - reserved for E6 (2-bar audition on
            # Enter), not built yet, so this key is currently inert.
            return
        elif key == Qt.Key.Key_Escape:
            if self._pending_digits:
                self._pending_digits = ""
                self._notify_pending_digits_changed(main_win)
            return

        if self._pending_digits:
            self._pending_digits = ""
            self._notify_pending_digits_changed(main_win)

        if key == Qt.Key.Key_Left:
            if ctrl:
                if hasattr(main_win, "navigate_measure_left"):
                    main_win.navigate_measure_left()
            elif hasattr(main_win, "navigate_timeline_left"):
                main_win.navigate_timeline_left()
        elif key == Qt.Key.Key_Right:
            if ctrl:
                if hasattr(main_win, "navigate_measure_right"):
                    main_win.navigate_measure_right()
            elif hasattr(main_win, "navigate_timeline_right"):
                main_win.navigate_timeline_right()
        elif key == Qt.Key.Key_Home:
            if hasattr(main_win, "navigate_timeline_home"):
                main_win.navigate_timeline_home()
        elif key == Qt.Key.Key_End:
            if hasattr(main_win, "navigate_timeline_end"):
                main_win.navigate_timeline_end()
        elif key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            super().keyPressEvent(event)
            if hasattr(main_win, "on_region_3_vertical_move"):
                main_win.on_region_3_vertical_move()
        elif key == Qt.Key.Key_Tab:
            main_win.focus_next_region(self)
        elif key == Qt.Key.Key_Backtab:
            main_win.focus_previous_region(self)
        else:
            super().keyPressEvent(event)

    def _notify_pending_digits_changed(self, main_win):
        """C6: while digits are pending, the status bar shows "Go to bar:
        {digits}" in place of the measure/beat field - the only feedback
        available on what's been typed before Phase D's screen-reader
        announcements exist."""
        if hasattr(main_win, "on_pending_digits_changed"):
            main_win.on_pending_digits_changed(self._pending_digits)