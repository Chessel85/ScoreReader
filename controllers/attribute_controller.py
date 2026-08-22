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

        # D-15: "stave" is deliberately not dialect-translated here.
        if already_present:
            scopes = [
                ("voice", "Remove for notes in current voice"),
                ("stave", "Remove for notes in current stave"),
                ("part", "Remove for notes in current part"),
                ("score", "Remove for notes in the whole score"),
            ]
        else:
            scopes = [
                ("voice", "Add to notes for this voice"),
                ("stave", "Add to notes in same stave"),
                ("part", "Add to notes in the same part"),
                ("score", "Add to notes in the whole score"),
            ]

        # Reported: a part with no real stave/voice concept underneath it
        # (a MIDI track, a pure Ultimate Guitar import, or one of the
        # synthetic Chords/Lyrics parts a MusicXML file's own <harmony>/
        # <lyric> markup can add - see MusicData.collapsed_part_ids, the
        # same check Region 2 uses to decide whether to show a fake
        # staff/voice tree underneath that part) offered "current voice"/
        # "current stave" scopes that acted on exactly the same notes as
        # "current part" - not wrong, just redundant menu clutter with
        # nothing real behind it. Those two scopes are dropped for such a
        # part; "part" and "score" still apply normally.
        collapsed = self.music_data.collapsed_part_ids
        part_has_no_real_stave_or_voice = collapsed is True or anchor_note.part_id in collapsed
        if part_has_no_real_stave_or_voice:
            scopes = [(scope, label) for scope, label in scopes if scope not in ("voice", "stave")]

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

    def on_order_move(self, dialog, node, attribute_key: str, up: bool) -> None:
        """MusicData owns the reorder; this applies it and pushes the result
        back to Region 3/4 and to the still-open dialog."""
        if not self.music_data:
            return
        voice_tuples = voice_tuples_for_node(node)
        within = self.music_data.attribute_keys_for_voices(voice_tuples)
        if not self.music_data.move_attribute_order(attribute_key, up, within=within):
            return
        self.presenter.refresh_region_3_labels()
        self.presenter.on_region_3_selection_changed()
        dialog.refresh_list(self.order_pairs_for_node(node), preferred_key=attribute_key)
