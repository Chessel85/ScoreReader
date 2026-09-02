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

    A list, not a table, for the same "NVDA reads a whole row in one
    keystroke" reasoning as Region 2. Unlike Region 2 there is no
    user-authored order to preserve across a rebuild, so refresh_list is a
    plain repopulate landing on row 0 rather than an id-based re-anchor.

    Ctrl+Home/Ctrl+End jump the timeline cursor to the focused row's span
    start/end - scoped to this region only, distinct from plain Home/End,
    which mean "first/last note of the piece" when Region 3 has focus.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # P2: how many of the leading items are live "context" rows (Section
        # / Chord / Lyric), so update_context_rows knows which ones it may
        # relabel in place.
        self._context_row_count = 0

    def _main_window(self) -> "MainWindow":
        # Only ever created by MainWindow.setup_ui, so window() is always it.
        return self.window()  # type: ignore[return-value]

    def refresh_list(
        self,
        context_rows: List[PerformanceRegionRow],
        structural_rows: List[PerformanceRegionRow],
    ) -> None:
        """Clears and repopulates: the P2 context rows first, then the Ref
        29 structural rows. Both empty shows a single "None" placeholder
        (UserRole None, so Ctrl+Home/End no-ops on it), matching
        get_region_3_data()'s own ["None"] convention."""
        self.clear()
        self._context_row_count = len(context_rows)
        all_rows = list(context_rows) + list(structural_rows)
        if not all_rows:
            item = QListWidgetItem("None")
            item.setData(Qt.ItemDataRole.UserRole, None)
            self.addItem(item)
        else:
            for row in all_rows:
                item = QListWidgetItem(row.label)
                item.setData(Qt.ItemDataRole.UserRole, row)
                self.addItem(item)
        if self.count() > 0:
            self.setCurrentRow(0)

    def update_context_rows(self, context_rows: List[PerformanceRegionRow]) -> bool:
        """Relabels the leading context rows in place (text + UserRole),
        never clearing or moving focus - mirrors
        RegionPresenter.refresh_region_3_labels. Returns False (caller falls
        back to a full refresh_list) when the row count changed, so a
        Section/Chord/Lyric row appearing or disappearing still rebuilds."""
        if len(context_rows) != self._context_row_count:
            return False
        for i, row in enumerate(context_rows):
            item = self.item(i)
            if item is None:
                return False
            item.setText(row.label)
            item.setData(Qt.ItemDataRole.UserRole, row)
        return True

    def current_row_data(self) -> Optional[PerformanceRegionRow]:
        """The row behind the focused item, or None (empty list or the
        placeholder), so callers never reach into currentItem() themselves."""
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
