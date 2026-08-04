# widgets/region_table_widget.py
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QAbstractItemView
from .region2_manager import Region2HierarchyModel, Region2Node


class RegionTableWidget(QTableWidget):
    """
    Region Table Widget featuring 2 columns (Item, Status), spacebar toggling,
    collapsing child rows when parents are turned off, focus retention for NVDA,
    and tab key forwarding across regions.
    """
    # Emitted when mute/unmute state changes so Region 3 can filter notes
    filter_changed = Signal(set)

    def __init__(self, rows: int = 0, columns: int = 2, parent=None):
        super().__init__(rows, columns, parent)
        self.model_manager = Region2HierarchyModel()
        self._current_visible_nodes = []

        self.setColumnCount(columns)
        self.setHorizontalHeaderLabels(["Item", "Status"])
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)

    def load_score_structure(self, parts_data: list):
        """Populates the table structure from parsed MusicXML metadata."""
        self.model_manager.build_from_score(parts_data)
        self.refresh_table()

    def refresh_table(self, preferred_node_id: str = None):
        """
        Rebuilds visible table rows based on model state.
        Preserves focus on preferred_node_id for continuous NVDA feedback.
        """
        if preferred_node_id is None:
            curr_row = self.currentRow()
            if 0 <= curr_row < len(self._current_visible_nodes):
                preferred_node_id = self._current_visible_nodes[curr_row].node_id

        self._current_visible_nodes = self.model_manager.get_visible_nodes()
        self.setRowCount(len(self._current_visible_nodes))

        target_row = 0

        for row_idx, node in enumerate(self._current_visible_nodes):
            if preferred_node_id and node.node_id == preferred_node_id:
                target_row = row_idx

            # Column 1: Item Name
            item_name = QTableWidgetItem(node.display_name)
            item_name.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            item_name.setData(Qt.UserRole, node.node_id)
            self.setItem(row_idx, 0, item_name)

            # Column 2: Status ("on" / "off")
            status_text = "on" if node.enabled else "off"
            item_status = QTableWidgetItem(status_text)
            item_status.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.setItem(row_idx, 1, item_status)

        # Re-anchor row focus for NVDA
        if self.rowCount() > 0:
            self.setCurrentCell(target_row, 0)

        # Signal Region 3 with the active voice set
        active_tuples = self.model_manager.get_active_voice_tuples()
        self.filter_changed.emit(active_tuples)

    def keyPressEvent(self, event):
        """
        Custom keyboard handler intercepting Tab/Shift+Tab for global region focus,
        and Spacebar for row toggling.
        """
        if event.key() == Qt.Key.Key_Tab:
            self.window().focusNextChild()
            return
        elif event.key() == Qt.Key.Key_Backtab:
            self.window().focusPreviousChild()
            return
        elif event.key() == Qt.Key.Key_Space:
            curr_row = self.currentRow()
            if 0 <= curr_row < len(self._current_visible_nodes):
                focused_node = self._current_visible_nodes[curr_row]

                # Toggle state
                self.model_manager.toggle_node(focused_node.node_id)

                # Re-render while keeping selection focused on the same node
                self.refresh_table(preferred_node_id=focused_node.node_id)
                return

        super().keyPressEvent(event)