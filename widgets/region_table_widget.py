# widgets/region_table_widget.py
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidget, QAbstractItemView


class RegionTableWidget(QTableWidget):
    """
    Plain property-list table used by Region 1 (score info) and Region 4
    (note attributes) via main_window.create_property_list. Only extra
    behaviour needed: forward Tab/Shift+Tab to the global region focus cycle
    instead of moving between cells.
    """

    def __init__(self, rows: int = 0, columns: int = 2, parent=None):
        super().__init__(rows, columns, parent)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Tab:
            self.window().focusNextChild()
            return
        elif event.key() == Qt.Key.Key_Backtab:
            self.window().focusPreviousChild()
            return

        super().keyPressEvent(event)
