# widgets/region_table_widget.py
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidget, QAbstractItemView


class RegionTableWidget(QTableWidget):
    """
    Plain property-list table used by Region 1 (score info) and Region 4
    (note attributes) via main_window.create_property_list. Only extra
    behaviour needed: forward Tab/Shift+Tab to the region focus cycle instead
    of moving between cells.
    """

    def __init__(self, rows: int = 0, columns: int = 2, parent=None):
        super().__init__(rows, columns, parent)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)

    def keyPressEvent(self, event):
        # Calls MainWindow.focus_next_region/focus_previous_region directly
        # rather than window().focusNextChild()/focusPreviousChild() - Qt's
        # global focus chain can't reliably close a 4-widget loop here (see
        # the comment in main_window.py's setup_ui).
        if event.key() == Qt.Key.Key_Tab:
            self.window().focus_next_region(self)
            return
        elif event.key() == Qt.Key.Key_Backtab:
            self.window().focus_previous_region(self)
            return

        super().keyPressEvent(event)
