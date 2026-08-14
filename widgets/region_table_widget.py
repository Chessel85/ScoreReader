# widgets/region_table_widget.py
from PySide6.QtWidgets import QTableWidget, QAbstractItemView

from widgets.region_focus_cycle import RegionFocusCycleMixin


class RegionTableWidget(RegionFocusCycleMixin, QTableWidget):
    """
    Plain property-list table used by Region 1 (score info) and Region 4
    (note attributes) via main_window.create_property_list. The only extra
    behaviour needed is forwarding Tab/Shift+Tab to the region focus cycle
    instead of moving between cells - RegionFocusCycleMixin's job.
    """

    def __init__(self, rows: int = 0, columns: int = 2, parent=None):
        super().__init__(rows, columns, parent)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
