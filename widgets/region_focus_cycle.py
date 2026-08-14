# widgets/region_focus_cycle.py
"""The one place Tab/Shift+Tab becomes a region-cycle move.

Every region widget needs the same behaviour - Tab to the next region,
Shift+Tab to the previous, neither ever leaving the regions area - so it
lives here once. Mix in BEFORE the Qt base class (`class R(
RegionFocusCycleMixin, QListWidget)`) so this event() wins while super()
still reaches the widget's own.

Two Qt behaviours this encodes, both verified against real key events:

1. Interception MUST be in event(), not keyPressEvent(). QAbstractItemView
   consumes Key_Tab/Key_Backtab in its own event() handling, for its
   internal item navigation, before keyPressEvent is ever invoked - so a
   keyPressEvent override silently never fires for Tab on a QListWidget or
   QTableWidget. Such an override can still LOOK correct, because Qt's
   implicit focus chain (widget creation order) may happen to match the
   intended cycle; it diverges at the wrap-around.

2. Both Shift+Tab spellings must be checked. It can arrive as plain Key_Tab
   with ShiftModifier set rather than as Key_Backtab; Qt does not normalise
   the two.

Region cycling deliberately avoids setTabOrder/focusNextChild - see
main_window.py's setup_ui for why Qt's single window-wide focus ring cannot
close an N-widget loop.
"""
from PySide6.QtCore import QEvent, Qt


class RegionFocusCycleMixin:

    def _region_cycle_window(self):
        """The MainWindow owning this region. Region widgets are only ever
        created by MainWindow.setup_ui, so window() is always it - calling
        straight through fails loudly if that stops being true, rather than
        silently swallowing the keystroke."""
        return self.window()

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            if key == Qt.Key.Key_Backtab or (key == Qt.Key.Key_Tab and shift):
                self._region_cycle_window().focus_previous_region(self)
                return True
            if key == Qt.Key.Key_Tab:
                self._region_cycle_window().focus_next_region(self)
                return True
        return super().event(event)
