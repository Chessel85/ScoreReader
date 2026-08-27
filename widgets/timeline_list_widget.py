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

    Typing a bar number then Enter (Ref 6) is NOT handled here anymore - it
    is global: main_window.py's window-wide digit shortcuts feed
    NavigationController, Enter is the Preview QAction routing through
    audition_phrase, and Escape cancels. Any cursor move cancels a
    half-typed number - NavigationController does that for
    Left/Right/Home/End/Find, and MainWindow.on_region_3_vertical_move for
    an in-slice Up/Down here.
    """

    def _main_window(self) -> "MainWindow":
        # Only ever created by MainWindow.setup_ui, so window() is always it.
        # Calling straight through fails loudly if that stops being true,
        # rather than silently swallowing the keystroke.
        return self.window()  # type: ignore[return-value]

    def keyPressEvent(self, event):
        key = event.key()
        main_win = self._main_window()
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        alt = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)

        if key == Qt.Key.Key_PageUp and alt:
            # Alt avoids QListWidget's own native PageUp (move the current
            # row up a page) - bare PageUp/PageDown would collide with that
            # the same way bare Up/Down would collide with chord-selection
            # handling below, so this is deliberately not bound plain.
            main_win.increase_preview_bars()
            return
        elif key == Qt.Key.Key_PageDown and alt:
            main_win.decrease_preview_bars()
            return
        elif ctrl and Qt.Key.Key_1 <= key <= Qt.Key.Key_9:
            # Quick attribute lookup: speaks Region 4's Nth row without
            # moving focus off Region 3 - see RegionPresenter.
            # announce_attribute_by_number, which silently no-ops if N
            # exceeds the currently displayed attribute list.
            main_win.announce_region_4_attribute(key - Qt.Key.Key_0)
            return

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
