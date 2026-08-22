# widgets/region4_list_widget.py
from typing import List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem

from widgets.region_property_list_widget import RegionPropertyListWidget


class Region4ListWidget(RegionPropertyListWidget):
    """
    Region 4 (note attributes) property list. Adds the Ref 15 AC4 context
    menu for appending/removing a Region 4 attribute from Region 3's note
    display, scoped to the current voice/stave/part/score.

    Reachable by right-click (customContextMenuRequested) and explicitly by
    the Menu key and Shift+F10. The keyboard path needs its own handler:
    Qt's CustomContextMenu policy does not reliably synthesise a keyboard
    contextMenuEvent for a QListWidget either.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_attribute_menu)

    def refresh_list(self, rows: List[Tuple[str, str, str]]) -> None:
        """Overrides RegionPropertyListWidget's plain index-clamp: reported,
        moving with Find's Alt+Right/Alt+Left can jump to a note whose
        attribute set/order is entirely different from the one before it
        (unlike ordinary Left/Right between neighbouring notes, which is
        what the index clamp was tuned for), so keeping the same raw row
        index landed on an unrelated attribute - or on row 0 whenever the
        new note simply has fewer rows. Re-anchors on the same
        attribute_key when the new rows still have it (a chord's several
        same-key rows resolve to the first match, the same simplification
        Region2ListWidget's preferred_node_id re-anchoring already makes),
        falling back to the index clamp otherwise. `rows` is (display_key,
        attribute_key, value) triples, MusicData.get_region_4_rows_for_
        indices - attribute_key is stored per item via UserRole so it
        survives the rebuild without keeping a side table."""
        previous_row = self.currentRow()
        previous_key = (
            self.item(previous_row).data(Qt.ItemDataRole.UserRole)
            if 0 <= previous_row < self.count() else None
        )

        self.clear()
        for display_key, attribute_key, value in rows:
            item = QListWidgetItem(f"{display_key}: {value}")
            item.setData(Qt.ItemDataRole.UserRole, attribute_key)
            self.addItem(item)

        if self.count() == 0:
            return

        target_row = min(max(previous_row, 0), self.count() - 1)
        if previous_key:
            for row in range(self.count()):
                if self.item(row).data(Qt.ItemDataRole.UserRole) == previous_key:
                    target_row = row
                    break
        self.setCurrentRow(target_row)

    def keyPressEvent(self, event):
        key = event.key()
        shift_f10 = key == Qt.Key.Key_F10 and bool(
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        )
        if key == Qt.Key.Key_Menu or shift_f10:
            self._show_attribute_menu(None)
            return
        super().keyPressEvent(event)

    def _show_attribute_menu(self, pos):
        """pos is the local click position for a real right-click, None for
        the keyboard path. Either way the item is resolved from the click
        position first, falling back to the current item - no column to
        preserve, unlike the old table."""
        item = self.itemAt(pos) if pos is not None else None
        if item is None:
            item = self.currentItem()
        if item is None:
            return
        row = self.row(item)
        self.setCurrentRow(row)

        anchor = self.visualItemRect(item).center()
        # window() is always MainWindow - only setup_ui creates this.
        self.window().show_region_4_attribute_menu(row, self.viewport().mapToGlobal(anchor))
