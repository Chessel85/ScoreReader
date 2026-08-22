# widgets/region4_list_widget.py
from PySide6.QtCore import Qt

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
