# controllers/attribute_controller.py
from PySide6.QtWidgets import QMenu

from models.vocabulary import attribute_label
from widgets.region2_manager import voice_tuples_for_node


class AttributeController:
    """Ref 15 AC4's attribute-display system: Region 4's add/remove context
    menu (which attributes show against a note) and the reorder dialog
    (what order they render in).

    Both halves write to MusicData and then ask the presenter to re-render,
    so the two regions can never disagree about which attributes exist or
    in what sequence.

    Dialog construction stays in MainWindow, as it does for every other
    dialog - this owns the logic behind it (which attributes are in scope,
    what a move does), not its lifecycle.
    """

    def __init__(self, session, presenter, window):
        self.session = session
        self.presenter = presenter
        # Needed as the parent for QMenu/QDialog, and for focusWidget().
        self._window = window

    @property
    def music_data(self):
        return self.session.music_data

    # --- shared scope-menu building ------------------------------------

    @staticmethod
    def _scope_action_labels(already_present: bool) -> list:
        """(scope, label) pairs for the four fan-out scopes, worded for
        either direction of the toggle. D-15: "stave" is deliberately not
        dialect-translated here. Shared by Region 4's context menu and the
        Reorder Attributes dialog's Add/Remove button, so the two can't
        drift onto different wording for the same action."""
        if already_present:
            return [
                ("voice", "Remove for notes in current voice"),
                ("stave", "Remove for notes in current stave"),
                ("part", "Remove for notes in current part"),
                ("score", "Remove for notes in the whole score"),
            ]
        return [
            ("voice", "Add to notes for this voice"),
            ("stave", "Add to notes in same stave"),
            ("part", "Add to notes in the same part"),
            ("score", "Add to notes in the whole score"),
        ]

    # Broader-or-equal-to-node-level check for the Reorder Attributes
    # dialog's Add/Remove button (_filter_scopes_for_node_level below) -
    # Region2Node.node_type spells the middle level "staff", the attribute-
    # scope vocabulary spells it "stave" (D-15's own dialect-free choice);
    # these two dicts are the one place that difference has to be bridged.
    _SCOPE_LEVEL = {"voice": 0, "stave": 1, "part": 2, "score": 3}
    _NODE_TYPE_LEVEL = {"voice": 0, "staff": 1, "part": 2}

    def _filter_scopes_for_node_level(self, scopes: list, node_type: str) -> list:
        """Reported: the Reorder Attributes dialog can be opened at any
        Region 2 level (voice/staff/part), but every scope was always
        offered regardless - "Add to notes for this voice" from a STAVE-
        level dialog with two voices underneath is genuinely ambiguous
        (which voice?). Only scopes at or broader than the dialog's own
        node level are unambiguous: a stave-level dialog offers stave/
        part/score; a part-level dialog offers only part/score. A voice-
        level dialog (the common case) is unaffected - every scope is
        still offered, same as before this fix."""
        floor = self._NODE_TYPE_LEVEL.get(node_type, 0)
        return [(scope, label) for scope, label in scopes if self._SCOPE_LEVEL[scope] >= floor]

    def _filter_scopes_for_part(self, scopes: list, part_id: str) -> list:
        """Reported: a part with no real stave/voice concept underneath it
        (a MIDI track, a pure Ultimate Guitar import, or one of the
        synthetic Chords/Lyrics parts a MusicXML file's own <harmony>/
        <lyric> markup can add - see MusicData.collapsed_part_ids, the
        same check Region 2 uses to decide whether to show a fake
        staff/voice tree underneath that part) offered "current voice"/
        "current stave" scopes that acted on exactly the same notes as
        "current part" - not wrong, just redundant menu clutter with
        nothing real behind it. Those two scopes are dropped for such a
        part; "part" and "score" still apply normally."""
        collapsed = self.music_data.collapsed_part_ids
        if collapsed is True or part_id in collapsed:
            return [(scope, label) for scope, label in scopes if scope not in ("voice", "stave")]
        return scopes

    # --- Region 4 context menu ---------------------------------------

    def menu_actions(self, row: int) -> list:
        """(label, callback) pairs for the context menu, empty if there's
        nothing to act on. Split from show_menu so it's testable without
        driving a blocking QMenu.exec()."""
        if not self.music_data:
            return []

        selected_indices = self.presenter.selected_region_3_indices()
        targets = self.music_data.get_region_4_row_targets(selected_indices)
        if not (0 <= row < len(targets)):
            return []

        attribute_key, anchor_note = targets[row]
        selected_notes = self.music_data.notes_for_indices(selected_indices)
        already_present = self.music_data.note_has_display_attribute(anchor_note, attribute_key)

        scopes = self._scope_action_labels(already_present)
        scopes = self._filter_scopes_for_part(scopes, anchor_note.part_id)

        return [
            (
                label,
                # checked=False absorbs the bool QAction.triggered passes
                # to any slot that accepts a positional arg. Without it that
                # bool lands in `scope`'s slot instead, silently replacing
                # e.g. "voice" with False.
                lambda checked=False, scope=scope: self.apply_change(
                    attribute_key, scope, selected_notes, add=not already_present
                ),
            )
            for scope, label in scopes
        ]

    def build_menu(self, row: int):
        """Builds the wired QMenu without exec()ing it, so tests can inspect
        it without a blocking modal loop. The exec() call must be kept OUT
        of the tested method rather than monkeypatched around: QMenu.exec is
        Shiboken-wrapped and overloaded, and patching it hangs indefinitely
        rather than raising."""
        actions = self.menu_actions(row)
        if not actions:
            return None
        menu = QMenu(self._window)
        for label, callback in actions:
            menu.addAction(label).triggered.connect(callback)
        return menu

    def show_menu(self, row: int, global_pos) -> None:
        """Called by Region4ListWidget on right-click or the Menu key.

        Plain exec(), deliberately: pre-highlighting the first action (via
        exec(at=...), with or without a synthetic Key_Down) does move the
        highlight but NVDA still reads "blank" rather than the item text. It
        costs the user one arrow press. Don't re-attempt without a way to
        verify against real NVDA."""
        menu = self.build_menu(row)
        if menu is None:
            return
        menu.exec(global_pos)
        self.restore_focus_after_menu(row)

    def restore_focus_after_menu(self, row: int) -> None:
        """Restores the row the menu was opened from, whether an action
        fired or Escape cancelled.

        Needed because QAction.triggered fires BEFORE exec() returns, so the
        rebuild the callback causes resets the list's current row while the
        menu is still up. (Escape, triggering no callback and no rebuild,
        lands correctly without this; Enter does not.)"""
        region_4 = self.presenter.region_4
        if 0 <= row < region_4.count():
            region_4.setCurrentRow(row)
        region_4.setFocus()

    def apply_change(self, attribute_key: str, scope: str, notes: list, add: bool) -> None:
        self.music_data.set_display_attribute(attribute_key, scope, notes, add)
        self.presenter.refresh_region_3_labels()

    # --- reorder dialog -----------------------------------------------

    def order_pairs_for_node(self, node) -> list:
        """(attribute_key, label) pairs in current order, for every
        attribute present anywhere in the score within `node`'s scope.
        Labels arrive already dialect-translated so the dialog itself stays
        dialect-agnostic."""
        voice_tuples = voice_tuples_for_node(node)
        keys = self.music_data.attribute_keys_for_voices(voice_tuples)
        return [(key, attribute_label(key, self.music_data.uk_terms)) for key in keys]

    def scope_node(self):
        """The Region 2 node the reorder dialog scopes itself to, or None."""
        if not self.music_data:
            return None
        return self.presenter.region_2.current_node()

    def apply_order(self, node, new_order: list) -> None:
        """Commits the Reorder Attributes dialog's staged order (read via
        dialog.ordered_keys() after exec() returns Accepted) into the real
        attribute_order and pushes the result to Region 3/4. `within` is
        recomputed the same way order_pairs_for_node did when the dialog
        was opened, so the commit lands on the same subset of slots."""
        if not self.music_data:
            return
        voice_tuples = voice_tuples_for_node(node)
        within = self.music_data.attribute_keys_for_voices(voice_tuples)
        self.music_data.set_attribute_order_within(new_order, within)
        self.presenter.refresh_region_3_labels()
        self.presenter.on_region_3_selection_changed()

    # --- reorder dialog's Add/Remove button ----------------------------
    # User-requested: Reorder Attributes already lists every attribute
    # present in the dialog's scope regardless of on/off state (below), so
    # a user who spots a rare one there had no way to actually switch it
    # on without first finding a note that already shows it in Region 4.
    # Reuses Region 4's own scope wording/logic (_scope_action_labels/
    # _filter_scopes_for_part above) so the two can't drift onto different
    # behaviour for the same action - the only real difference is that this
    # one fans out from the dialog's own Region 2 node position instead of
    # a selected note, since the dialog has no note selection of its own.

    def order_menu_actions(self, node, attribute_key: str) -> list:
        """(label, callback) pairs for the Add/Remove button's dropdown,
        empty if there's nothing to act on. "Already present" is read off
        one representative voice under `node` (the lowest-sorted one) -
        node is usually a single voice already; for a wider staff/part
        selection this is the same "one anchor decides the wording"
        simplification note_has_display_attribute makes for a chord."""
        if not self.music_data:
            return []
        voice_tuples = voice_tuples_for_node(node)
        if not voice_tuples:
            return []
        part_id, staff, voice = sorted(voice_tuples)[0]
        already_present = self.music_data.display_attribute_present_for_voice(
            attribute_key, part_id, staff, voice
        )

        scopes = self._scope_action_labels(already_present)
        scopes = self._filter_scopes_for_node_level(scopes, node.node_type)
        scopes = self._filter_scopes_for_part(scopes, part_id)

        return [
            (
                label,
                lambda checked=False, scope=scope: self.apply_order_change(
                    attribute_key, scope, part_id, staff, voice, add=not already_present
                ),
            )
            for scope, label in scopes
        ]

    def show_order_menu(self, dialog, node, attribute_key: str) -> None:
        """Called by MainWindow on the Reorder Attributes dialog's Add/
        Remove button. The dialog stays open throughout - toggling on/off
        changes neither which attributes are listed (presence-based) nor
        their order, so unlike an OK-committed Up/Down move there's nothing
        to refresh in the dialog itself, only Region 3."""
        actions = self.order_menu_actions(node, attribute_key)
        if not actions:
            return
        menu = QMenu(self._window)
        for label, callback in actions:
            menu.addAction(label).triggered.connect(callback)
        button = dialog.add_remove_button
        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))
        dialog.attribute_list.setFocus()

    def apply_order_change(
        self, attribute_key: str, scope: str, part_id: str, staff: int, voice: int, add: bool
    ) -> None:
        self.music_data.set_display_attribute_for_voice(attribute_key, scope, part_id, staff, voice, add)
        self.presenter.refresh_region_3_labels()
