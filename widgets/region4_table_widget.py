# widgets/region4_table_widget.py
from PySide6.QtCore import Qt

from widgets.region_table_widget import RegionTableWidget


class Region4TableWidget(RegionTableWidget):
    """
    Region 4 (note attributes) property list. Adds the Ref 15 AC4 context
    menu for appending/removing a Region 4 attribute from Region 3's note
    display, scoped to the current voice/stave/part/score.

    Reachable by right-click (customContextMenuRequested, native Qt) and
    explicitly by the Menu/Application key and Shift+F10 (keyPressEvent
    below) - live-tested finding: Qt's CustomContextMenu policy does not
    reliably synthesize a keyboard contextMenuEvent for a QTableWidget on
    its own, so the keyboard path needs its own handler rather than relying
    on Qt to raise customContextMenuRequested for it unprompted.
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
        """pos is the local click position for a real right-click, or None
        for the explicit keyboard path above. Either way the row and the
        popup's anchor point are resolved from the table's own state
        (rowAt/currentRow and that row's visual rect) rather than trusted
        directly from pos - a keyboard-synthesized contextMenuEvent's pos
        is not reliable enough to place the popup from."""
        row = self.rowAt(pos.y()) if pos is not None else -1
        if row < 0:
            row = self.currentRow()
        if row < 0:
            return
        # Live-tested bug: this used to hard-code column 0, so opening the
        # menu from the value column (1) and coming back afterward always
        # landed back on the key column instead. Preserve whichever column
        # was actually current.
        column = self.currentColumn()
        if column < 0:
            column = 0
        self.setCurrentCell(row, column)

        item = self.item(row, 0)
        anchor = self.visualItemRect(item).center() if item is not None else self.rect().center()

        # self.window() is always MainWindow - this widget is only ever
        # created by MainWindow.setup_ui (same assumption
        # TimelineListWidget/Region2ListWidget already make about their own
        # window()).
        self.window().show_region_4_attribute_menu(row, column, self.viewport().mapToGlobal(anchor))
