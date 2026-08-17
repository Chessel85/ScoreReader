# widgets/region2_list_widget.py
from typing import Dict, List, Optional, Set, Union

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QTreeWidget, QTreeWidgetItem

from .region2_manager import Region2HierarchyModel, Region2Node, node_status_label
from .region_focus_cycle import RegionFocusCycleMixin


class Region2ListWidget(RegionFocusCycleMixin, QTreeWidget):
    """
    Region 2: parts/staves/voices as a real tree.

    Left/Right collapse/expand, Up/Down move between rows, indentation
    reflects depth - all standard, accessible tree-view interaction.
    Expand/collapse is a pure navigation convenience: every node starts
    COLLAPSED on every score load (the user's own preference, confirmed
    live: "all the nodes are closed to start with... I think that is
    better") and expand state is never persisted to the .rsc.

    Collapsing a node forgets its children's own expand state too - live-
    tested and reverted after a "remember each descendant's own state"
    version turned out to depend on the same missing setExpanded(True)
    call below and behaved oddly; the user's own call was simplicity over
    memory ("I'll live with the child nodes collapsing when the parent is
    collapsed"). Re-expanding a node always rebuilds its immediate
    children fresh, themselves collapsed. Tab/Shift+Tab forward to the
    region focus cycle like every other region widget.

    Reported, live-tested against NVDA (real hardware, Pachelbel's Canon):
    collapsing via Qt's native isExpanded()/setExpanded() only visually
    hides child rows, it doesn't remove them - and NVDA's own browse-mode
    buffer over the accessible tree did not reliably pick up the resulting
    "these children are now hidden" state change, so arrowing down past a
    freshly-collapsed node kept announcing its now-invisible children as
    blank rows (the count matched exactly: a 2-child part left 2 blank
    presses), compounding with every further collapse in the session.
    Left/Right are therefore handled here explicitly instead of relying on
    Qt's native collapse: collapsing REMOVES the child QTreeWidgetItems
    outright (a real child-count change, which is the well-tested
    accessibility notification path every screen reader relies on) rather
    than just hiding them, and re-expanding rebuilds that subtree fresh
    from the model. setChildIndicatorPolicy keeps the expand arrow showing
    on a collapsed-but-not-actually-childless row so it still reads as
    expandable.
    """
    # Emitted after every rebuild/mute/solo change so Region 3 can filter
    # notes (Ref 7).
    filter_changed = Signal(set)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model_manager = Region2HierarchyModel()
        self._item_by_node_id: Dict[str, QTreeWidgetItem] = {}
        self.setColumnCount(1)
        self.setHeaderHidden(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

    def current_node(self) -> Optional[Region2Node]:
        """The Region2Node behind the focused row, or None if the tree is
        empty - the attribute-order dialog scopes itself to this."""
        item = self.currentItem()
        if item is None:
            return None
        node_id = item.data(0, Qt.ItemDataRole.UserRole)
        return self.model_manager.node(node_id)

    def select_node(self, node_id: str) -> None:
        """Moves focus/current-item to a specific node by id, regardless of
        depth - expands any collapsed ancestor along the way so the row
        actually exists to select (nodes start collapsed, so a deep node's
        row may not be built yet), same as a sighted user would have to
        arrow/Right their way down to it. A no-op if the id is unknown."""
        node = self.model_manager.node(node_id)
        if node is None:
            return
        ancestors = []
        current = node.parent
        while current is not None:
            ancestors.append(current)
            current = current.parent
        for ancestor in reversed(ancestors):
            ancestor_item = self._item_by_node_id.get(ancestor.node_id)
            if ancestor_item is not None and ancestor_item.childCount() == 0:
                self._expand_item(ancestor_item)
        item = self._item_by_node_id.get(node_id)
        if item is not None:
            self.setCurrentItem(item)

    def visible_item_texts(self) -> List[str]:
        """Every currently-rendered row's text, in the same top-to-bottom
        order the tree displays them - the tree-widget counterpart of
        Region2HierarchyModel.get_visible_nodes()."""
        return [
            self._item_by_node_id[node.node_id].text(0)
            for node in self.model_manager.get_visible_nodes()
            if node.node_id in self._item_by_node_id
        ]

    def load_score_structure(self, parts_data: list, collapse_to_parts: Union[bool, Set[str]] = False):
        """Populates the tree from parsed score metadata. collapse_to_parts
        (Ref 25/S2) is True for a MIDI-loaded score or pure Ultimate Guitar
        import, where every part's staff/voice rows would only ever show
        fake/trivial detail, or a set of specific part_ids for a mixed score
        (real notated parts alongside synthetic Chords/Lyrics parts) - see
        Region2HierarchyModel.get_visible_nodes."""
        self.model_manager.build_from_score(parts_data, collapse_to_parts=collapse_to_parts)
        self._rebuild_tree()

    def _rebuild_tree(self) -> None:
        """Builds every top-level part row only, collapsed - every node
        starts collapsed, so nothing beneath a part is built until it's
        expanded (see _populate_children)."""
        self.clear()
        self._item_by_node_id = {}
        for part in self.model_manager.roots:
            item = self._make_item(part)
            self.addTopLevelItem(item)
            self._mark_expandable_if_real(item, part)

        if self.topLevelItemCount() > 0:
            self.setCurrentItem(self.topLevelItem(0))

        self._emit_filter_changed()

    def _make_item(self, node: Region2Node) -> QTreeWidgetItem:
        item = QTreeWidgetItem([node_status_label(node)])
        item.setData(0, Qt.ItemDataRole.UserRole, node.node_id)
        self._item_by_node_id[node.node_id] = item
        return item

    def _mark_expandable_if_real(self, item: QTreeWidgetItem, node: Region2Node) -> None:
        """Shows the expand arrow on a still-childless item, but only if
        `node` actually has real children to reveal later - a
        collapsed_to_parts part (MIDI/UG/synthetic Chords-Lyrics) never
        gets one, since there's no real staff/voice concept underneath it."""
        if node.node_type == "part" and self.model_manager.part_is_collapsed(node.part_id):
            return
        if node.children:
            item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)

    def _populate_children(self, item: QTreeWidgetItem, node: Region2Node) -> None:
        """Builds `node`'s immediate children under `item`, one level deep
        - each new child starts collapsed itself (an expand indicator only,
        no grandchildren built yet, and no memory of any earlier expanded
        state - collapsing a node forgets what was open underneath it). In
        practice never reached for a collapsed_to_parts part (it never gets
        an expand indicator to trigger this from), but guarded again here
        defensively rather than relying solely on that."""
        if node.node_type == "part" and self.model_manager.part_is_collapsed(node.part_id):
            return
        for child in node.children:
            child_item = self._make_item(child)
            item.addChild(child_item)
            self._mark_expandable_if_real(child_item, child)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        item = self.currentItem()
        if key == Qt.Key.Key_Left and item is not None and item.childCount() > 0:
            self._collapse_item(item)
            return
        if key == Qt.Key.Key_Right and item is not None and item.childCount() == 0 and (
            item.childIndicatorPolicy() == QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
        ):
            self._expand_item(item)
            return
        super().keyPressEvent(event)

    def _collapse_item(self, item: QTreeWidgetItem) -> None:
        node = self._node_for_item(item)
        if node is not None:
            for child in node.children:
                self._forget_item(child)
        item.takeChildren()
        item.setExpanded(False)
        item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)

    def _expand_item(self, item: QTreeWidgetItem) -> None:
        """Reported bug, live-tested: this used to add the child items
        without ever calling setExpanded(True) - QTreeWidget keeps a
        SEPARATE native "is this item expanded" flag from whatever children
        it actually has, and Down-arrow navigation skips a non-expanded
        item's children even when they're really there, so the newly
        revealed row(s) were silently unreachable by keyboard until you
        happened to jump straight to one (e.g. via select_node)."""
        node = self._node_for_item(item)
        if node is None:
            return
        self._populate_children(item, node)
        item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicatorWhenChildless)
        item.setExpanded(True)

    def _node_for_item(self, item: QTreeWidgetItem) -> Optional[Region2Node]:
        node_id = item.data(0, Qt.ItemDataRole.UserRole)
        return self.model_manager.node(node_id)

    def _forget_item(self, node: Region2Node) -> None:
        """Drops a removed-from-the-widget node (and its descendants, in
        case it was itself still expanded) from _item_by_node_id, so a
        later lookup can't return a stale QTreeWidgetItem no longer parented
        anywhere."""
        self._item_by_node_id.pop(node.node_id, None)
        for child in node.children:
            self._forget_item(child)

    def rename_part(self, part_id: str, new_name: str) -> None:
        """S5: updates one part row's label in place after the instrument
        dialog's OK - see Region2HierarchyModel.rename_part for why this
        isn't a load_score_structure rebuild (it would also reset expand
        state)."""
        self.model_manager.rename_part(part_id, new_name)
        for part in self.model_manager.roots:
            if part.part_id == part_id:
                item = self._item_by_node_id.get(part.node_id)
                if item is not None:
                    item.setText(0, node_status_label(part))
                return

    def rename_voice(self, part_id: str, staff_id: int, voice_id: int, new_label: str) -> None:
        """Wishlist #8 follow-up: updates one voice row's label in place
        after a percussion item is renamed via the Instruments dialog - see
        Region2HierarchyModel.rename_voice / rename_part above."""
        self.model_manager.rename_voice(part_id, staff_id, voice_id, new_label)
        node_id = f"voice_{part_id}_{staff_id}_{voice_id}"
        node = self.model_manager.node(node_id)
        if node is None:
            return
        item = self._item_by_node_id.get(node_id)
        if item is not None:
            item.setText(0, node_status_label(node))

    def reorder_parts(self, part_id_order: list) -> None:
        """Options > Reorder Parts... - reflects a live part reorder onto
        the already-built tree in place, same "not a load_score_structure
        rebuild" reasoning as rename_part above (a rebuild would reset
        every mute/solo toggle and expand state)."""
        self.model_manager.reorder_roots(part_id_order)
        items = [self._item_by_node_id[p.node_id] for p in self.model_manager.roots
                 if p.node_id in self._item_by_node_id]
        for item in items:
            self.takeTopLevelItem(self.indexOfTopLevelItem(item))
        for item in items:
            self.addTopLevelItem(item)

    def apply_muted_node_keys(self, parts_muted: set, staves_muted: set, voices_muted: set) -> None:
        """Ref 27: restores each node's own mute state from a saved
        ScoreConfig, after load_score_structure has reset everything to
        unmuted. Never rebuilds the tree, so the fresh-load collapsed
        state this always runs right after is left untouched."""
        self.model_manager.apply_muted_node_keys(parts_muted, staves_muted, voices_muted)
        self._refresh_all_item_texts()

    def apply_soloed_node_keys(self, parts_soloed: set, staves_soloed: set, voices_soloed: set) -> None:
        """The soloed counterpart to apply_muted_node_keys."""
        self.model_manager.apply_soloed_node_keys(parts_soloed, staves_soloed, voices_soloed)
        self._refresh_all_item_texts()

    def toggle_mute_current(self) -> None:
        """F8 (via the Playback menu's Mute action) - mutes/unmutes the
        focused row only."""
        node = self.current_node()
        if node is None:
            return
        self.model_manager.toggle_mute(node.node_id)
        self._refresh_item_text(node)
        self._emit_filter_changed()

    def toggle_solo_current(self) -> None:
        """F9 (via the Playback menu's Solo action) - solos/unsolos the
        focused row only."""
        node = self.current_node()
        if node is None:
            return
        self.model_manager.toggle_solo(node.node_id)
        self._refresh_item_text(node)
        self._emit_filter_changed()

    def unmute_all(self) -> None:
        """Alt+F8 (via the Playback menu's Unmute All action)."""
        self.model_manager.clear_all_mute()
        self._refresh_all_item_texts()

    def unsolo_all(self) -> None:
        """Alt+F9 (via the Playback menu's Unsolo All action)."""
        self.model_manager.clear_all_solo()
        self._refresh_all_item_texts()

    def _refresh_item_text(self, node: Region2Node) -> None:
        item = self._item_by_node_id.get(node.node_id)
        if item is not None:
            item.setText(0, node_status_label(node))

    def _refresh_all_item_texts(self) -> None:
        for node_id, item in self._item_by_node_id.items():
            node = self.model_manager.node(node_id)
            if node is not None:
                item.setText(0, node_status_label(node))
        self._emit_filter_changed()

    def _emit_filter_changed(self) -> None:
        self.filter_changed.emit(self.model_manager.get_active_voice_tuples())
