# widgets/region_focus_cycle.py
"""R1: the one place Tab/Shift+Tab is turned into a region-cycle move.

Every region widget needs identical behaviour - Tab goes to the next region,
Shift+Tab to the previous, and neither ever leaves the regions area (the
MAA) - so it lives here once rather than being re-implemented per widget.

Two live-tested Qt findings this mixin exists to encode, both originally
discovered while building Region 5 (Ref 29):

1. Interception must happen in event(), NOT keyPressEvent().
   QAbstractItemView consumes Key_Tab/Key_Backtab in its own event()
   handling - its internal cell/item navigation - before keyPressEvent() is
   ever invoked. A keyPressEvent override therefore silently never fires for
   Tab on a QListWidget/QTableWidget. Region 2 and Region 3 carried exactly
   such a dead override for a long time: their Tab still appeared to work,
   but only because Qt's implicit focus chain (built from widget creation
   order in MainWindow.setup_ui, no setTabOrder involved) happened to match
   the intended cycle for every transition except a wrap-around. Region 5
   becoming the last region put a QListWidget at the wrap boundary for the
   first time and exposed it. Confirmed by instrumenting
   MainWindow.focus_next_region: it was never called for a real Tab press on
   Region 2 or Region 3.

2. Both Shift+Tab spellings must be checked. A synthetic Shift+Tab arrives
   as plain Key_Tab with ShiftModifier set, not as Key_Backtab - Qt's key
   dispatch doesn't normalise the two the way some native platform paths do.

Mix in BEFORE the Qt base class (e.g. `class R(RegionFocusCycleMixin,
QListWidget)`) so this event() wins and its super() call still reaches the
widget's own implementation.

Region cycling deliberately does not use setTabOrder/focusNextChild - see
the comment in main_window.py's setup_ui for why Qt's single window-wide
focus ring cannot close an N-widget loop here.
"""
from PySide6.QtCore import QEvent, Qt


class RegionFocusCycleMixin:

    def _region_cycle_window(self):
        """The MainWindow owning this region. Every region widget is only
        ever created by MainWindow.setup_ui and added to its central widget,
        so window() is always the MainWindow - calling straight through
        fails loudly if that ever stops being true, rather than silently
        swallowing the keystroke (the same convention
        TimelineListWidget._main_window already documents)."""
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
