# timeline_list_widget.py
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget

from widgets.region_focus_cycle import RegionFocusCycleMixin

if TYPE_CHECKING:
    from main_window import MainWindow


class TimelineListWidget(RegionFocusCycleMixin, QListWidget):
    """
    Region 3 list widget handling custom timeline traversal (Left/Right)
    and single-note selection collapsing (Up/Down).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # Ref 6: digits typed here build a target bar number, jumped to on
        # Enter and cleared by Escape or any other meaningful key - stale
        # digits waiting for a later Enter would be confusing.
        self._pending_digits = ""

    def _main_window(self) -> "MainWindow":
        # Only ever created by MainWindow.setup_ui, so window() is always it.
        # Calling straight through fails loudly if that stops being true,
        # rather than silently swallowing the keystroke.
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
            else:
                # Ref 11 (E6): no digits pending - two-bar phrase audition.
                main_win.audition_phrase()
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
            # Qt's ExtendedSelection arrow handling collapses a multi-row
            # selection only as a side effect of the current row CHANGING.
            # At a boundary (Up on the top row of a selected chord) there is
            # nowhere to move, so it no-ops and leaves the whole chord
            # selected. Re-collapsing unconditionally is harmless when the
            # native handling already did it, and fixes the boundary case.
            super().keyPressEvent(event)
            current = self.currentItem()
            if current is not None:
                self.clearSelection()
                current.setSelected(True)
            main_win.on_region_3_vertical_move()
        # Tab/Shift+Tab are handled in RegionFocusCycleMixin.event() -
        # QAbstractItemView never lets them reach keyPressEvent here.
        else:
            super().keyPressEvent(event)