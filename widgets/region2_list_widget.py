# widgets/region2_list_widget.py
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from .region2_manager import Region2HierarchyModel, Region2Node


class Region2ListWidget(QListWidget):
    """
    Region 2: parts/staves/voices hierarchy as a flat navigable list.

    Up/Down move between rows natively (no override needed). O toggles the
    focused row on/off - toggling a part or staff off hides its descendants
    from the list without touching their own enabled state, so they come
    back with whatever on/off status they had before (Region2HierarchyModel
    already guarantees this). Tab/Shift+Tab forward to the region focus
    cycle like every other region widget.
    """
    # Emitted after every rebuild so Region 3 can filter notes (Ref 7)
    filter_changed = Signal(set)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model_manager = Region2HierarchyModel()
        self._current_visible_nodes = []

    def current_node(self) -> Optional[Region2Node]:
        """The Region2Node behind the focused row, or None if the list is
        empty/no score is loaded - powers F2's attribute-order dialog, which
        scopes itself to whatever part/staff/voice the user was on in Region
        2 when they opened it."""
        row = self.currentRow()
        if 0 <= row < len(self._current_visible_nodes):
            return self._current_visible_nodes[row]
        return None

    def load_score_structure(self, parts_data: list):
        """Populates the list from parsed MusicXML metadata."""
        self.model_manager.build_from_score(parts_data)
        self.refresh_list()

    def apply_active_voice_tuples(self, active_tuples: set):
        """Ref 27: restores on/off state from a saved ScoreConfig, after
        load_score_structure has already reset every node to its default
        enabled=True. refresh_list()'s filter_changed emission at the end is
        what actually propagates the restored state back to MusicData and
        Region 3 (MainWindow._on_region_2_filter_changed) - the same signal
        path a live toggle already uses, not a separate one."""
        self.model_manager.set_active_voice_tuples(active_tuples)
        self.refresh_list()

    def refresh_list(self, preferred_node_id: str = None):
        """
        Rebuilds the visible rows from model state. Preserves focus on
        preferred_node_id for continuous NVDA feedback across a toggle.
        """
        if preferred_node_id is None:
            curr_row = self.currentRow()
            if 0 <= curr_row < len(self._current_visible_nodes):
                preferred_node_id = self._current_visible_nodes[curr_row].node_id

        self._current_visible_nodes = self.model_manager.get_visible_nodes()

        self.clear()
        target_row = 0
        for row_idx, node in enumerate(self._current_visible_nodes):
            if preferred_node_id and node.node_id == preferred_node_id:
                target_row = row_idx

            status_text = "on" if node.enabled else "off"
            item = QListWidgetItem(f"{node.display_name} - {status_text}")
            item.setData(Qt.UserRole, node.node_id)
            self.addItem(item)

        if self.count() > 0:
            self.setCurrentRow(target_row)

        active_tuples = self.model_manager.get_active_voice_tuples()
        self.filter_changed.emit(active_tuples)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Tab:
            self.window().focus_next_region(self)
            return
        elif event.key() == Qt.Key.Key_Backtab:
            self.window().focus_previous_region(self)
            return
        elif event.key() == Qt.Key.Key_O:
            curr_row = self.currentRow()
            if 0 <= curr_row < len(self._current_visible_nodes):
                focused_node = self._current_visible_nodes[curr_row]
                self.model_manager.toggle_node(focused_node.node_id)
                self.refresh_list(preferred_node_id=focused_node.node_id)
            return

        super().keyPressEvent(event)
