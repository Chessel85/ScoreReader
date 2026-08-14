# widgets/region4_table_widget.py
from PySide6.QtCore import Qt

from widgets.region_table_widget import RegionTableWidget


class Region4TableWidget(RegionTableWidget):
    """
    Region 4 (note attributes) property list. Adds the Ref 15 AC4 context
    menu for appending/removing a Region 4 attribute from Region 3's note
    display, scoped to the current voice/stave/part/score.

    Reachable by right-click (customContextMenuRequested) and explicitly by
    the Menu key and Shift+F10. The keyboard path needs its own handler:
    Qt's CustomContextMenu policy does not reliably synthesise a keyboard
    contextMenuEvent for a QTableWidget.
    """

    def __init__(self, rows: int = 0, columns: int = 2, parent=None):
        super().__init__(rows, columns, parent)
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
        the keyboard path. Either way the row and anchor are resolved from
        the table's own state rather than from pos, which is not reliable
        enough to place the popup when keyboard-synthesised."""
        row = self.rowAt(pos.y()) if pos is not None else -1
        if row < 0:
            row = self.currentRow()
        if row < 0:
            return
        # Preserve the current column: hard-coding 0 sends a menu opened
        # from the value column back to the key column afterwards.
        column = self.currentColumn()
        if column < 0:
            column = 0
        self.setCurrentCell(row, column)

        item = self.item(row, 0)
        anchor = self.visualItemRect(item).center() if item is not None else self.rect().center()

        # window() is always MainWindow - only setup_ui creates this.
        self.window().show_region_4_attribute_menu(row, column, self.viewport().mapToGlobal(anchor))
