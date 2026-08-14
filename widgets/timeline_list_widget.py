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
            # Qt's native ExtendedSelection arrow handling only collapses
            # the multi-row selection down to the newly-current row as a
            # side effect of the current row actually changing - at a
            # boundary (Up already on the top row of a selected chord, or
            # Down already on the bottom) there's nowhere to move to, so it
            # no-ops and leaves every note in the chord still selected.
            # Live-tested bug: landing on a chord then pressing Up did
            # nothing, even though Down correctly narrowed to the next row.
            # Explicitly re-collapsing after every Up/Down (not just at a
            # boundary) is a no-op when the native handling already did it,
            # and fixes the boundary case the same way.
            super().keyPressEvent(event)
            current = self.currentItem()
            if current is not None:
                self.clearSelection()
                current.setSelected(True)
            main_win.on_region_3_vertical_move()
        # Tab/Shift+Tab are handled a level up, in RegionFocusCycleMixin.
        # event() - QAbstractItemView never lets them reach keyPressEvent at
        # all on a single-column view (R1, see that module's docstring).
        else:
            super().keyPressEvent(event)