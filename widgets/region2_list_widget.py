# widgets/region2_list_widget.py
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from .region2_manager import Region2HierarchyModel, Region2Node
from .region_focus_cycle import RegionFocusCycleMixin


class Region2ListWidget(RegionFocusCycleMixin, QListWidget):
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
        empty - the attribute-order dialog scopes itself to this."""
        row = self.currentRow()
        if 0 <= row < len(self._current_visible_nodes):
            return self._current_visible_nodes[row]
        return None

    def load_score_structure(self, parts_data: list, collapse_to_parts: bool = False):
        """Populates the list from parsed score metadata. collapse_to_parts
        (Ref 25/S2) is set for a MIDI-loaded score, where staff/voice rows
        would only ever show fake/trivial detail - see
        Region2HierarchyModel.get_visible_nodes."""
        self.model_manager.build_from_score(parts_data, collapse_to_parts=collapse_to_parts)
        self.refresh_list()

    def rename_part(self, part_id: str, new_name: str) -> None:
        """S5: updates one part row's label in place after the instrument
        dialog's OK - see Region2HierarchyModel.rename_part for why this
        isn't a load_score_structure rebuild."""
        self.model_manager.rename_part(part_id, new_name)
        self.refresh_list()

    def apply_off_node_keys(self, parts_off: set, staves_off: set, voices_off: set):
        """Ref 27: restores each node's own on/off state from a saved
        ScoreConfig, after load_score_structure has reset everything to
        enabled. refresh_list()'s filter_changed emission is what propagates
        the result to MusicData and Region 3 - the same signal path a live
        toggle uses, not a separate one."""
        self.model_manager.apply_off_node_keys(parts_off, staves_off, voices_off)
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
            # No per-item UserRole data: current_node() resolves a row via
            # _current_visible_nodes, built from this same list in the same
            # order, so stashing the node_id would be dead weight.
            self.addItem(QListWidgetItem(f"{node.display_name} - {status_text}"))

        if self.count() > 0:
            self.setCurrentRow(target_row)

        active_tuples = self.model_manager.get_active_voice_tuples()
        self.filter_changed.emit(active_tuples)

    def keyPressEvent(self, event):
        # Tab/Shift+Tab are handled in RegionFocusCycleMixin.event() -
        # QAbstractItemView never lets them reach keyPressEvent here.
        if event.key() == Qt.Key.Key_O:
            curr_row = self.currentRow()
            if 0 <= curr_row < len(self._current_visible_nodes):
                focused_node = self._current_visible_nodes[curr_row]
                self.model_manager.toggle_node(focused_node.node_id)
                self.refresh_list(preferred_node_id=focused_node.node_id)
            return

        super().keyPressEvent(event)
