# widgets/region5_list_widget.py
from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from models.performance_region_row import PerformanceRegionRow
from widgets.region_focus_cycle import RegionFocusCycleMixin

if TYPE_CHECKING:
    from main_window import MainWindow


class Region5ListWidget(RegionFocusCycleMixin, QListWidget):
    """
    Region 5 (Ref 29, the "Performance region"): a flat list of whichever
    repeat/ending/hairpin rows are active at the cursor's current position.

    Modeled on Region2ListWidget (thin QListWidget + UserRole-stashed row
    data) rather than the table widgets Region 1/4 use - same "NVDA reads a
    whole row in one keystroke" reasoning. Unlike Region 2, there's no
    user-authored order to preserve across a rebuild (MusicData.
    get_performance_region_rows already returns a stable, deterministic
    order), so refresh_list here is a plain repopulate always landing on row
    0, not an id-based re-anchor.

    Ctrl+Home/Ctrl+End jump the main timeline cursor to the focused row's
    span start/end (MainWindow.jump_to_performance_span_start/end) - a real
    navigation feature scoped only to this region, distinct from the plain
    (unmodified) Home/End that already mean "first/last note of the whole
    piece" globally when Region 3 has focus.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

    def _main_window(self) -> "MainWindow":
        # This widget is only ever created by MainWindow.setup_ui and added
        # to its central widget, so window() is always the MainWindow - same
        # convention as TimelineListWidget._main_window.
        return self.window()  # type: ignore[return-value]

    def refresh_list(self, rows: List[PerformanceRegionRow]) -> None:
        """Clears and repopulates. An empty active set shows a single
        "None" placeholder row (UserRole None, so Ctrl+Home/End on it is a
        no-op) - mirrors get_region_3_data()'s own ["None"] convention for
        "nothing here right now"."""
        self.clear()
        if not rows:
            item = QListWidgetItem("None")
            item.setData(Qt.ItemDataRole.UserRole, None)
            self.addItem(item)
        else:
            for row in rows:
                item = QListWidgetItem(row.label)
                item.setData(Qt.ItemDataRole.UserRole, row)
                self.addItem(item)
        if self.count() > 0:
            self.setCurrentRow(0)

    def current_row_data(self) -> Optional[PerformanceRegionRow]:
        """The PerformanceRegionRow behind the focused row, or None (empty
        list, or the "None" placeholder row) - MainWindow's Ctrl+Home/End
        handlers no-op on None rather than reaching into currentItem()
        directly."""
        item = self.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def keyPressEvent(self, event):
        key = event.key()
        main_win = self._main_window()
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)

        if key == Qt.Key.Key_Home and ctrl:
            main_win.jump_to_performance_span_start()
            return
        elif key == Qt.Key.Key_End and ctrl:
            main_win.jump_to_performance_span_end()
            return

        super().keyPressEvent(event)
