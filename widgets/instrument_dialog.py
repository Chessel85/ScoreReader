# widgets/instrument_dialog.py
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QStringListModel, Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QCompleter,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from models.gm_instruments import GM_INSTRUMENT_NAMES, GM_PROGRAM_BY_NAME, gm_instrument_name
from models.gm_percussion_map import (
    GM_PERCUSSION_SOUND_NAMES,
    gm_percussion_key_for_name,
    gm_percussion_name,
)
from widgets.list_focus_helper import focus_list_and_reannounce_current_row

# A percussion item's row list entry: (item_key, current display name,
# current effective sounding key) - exactly MusicData.get_percussion_items_
# for_part's own return shape, so main_window.py can pass it straight
# through with no reshaping.
PercussionItemRow = Tuple[Tuple[str, int], str, int]


class InstrumentDialog(QDialog):
    """Edit > Instruments... (S5) - rename a part and/or change what it
    plays back as, for both MusicXML and MIDI scores. "Piano may not always
    be a suitable default" (MIDI parts default to Acoustic Grand Piano when
    a file gives no program at all) and MIDI tracks are sometimes unnamed
    entirely (BluePeter.mid, a real internet-sourced file: every track just
    "Track 1"/"Track 2"/etc).

    S6 (the key signature override) briefly lived as a second control in
    this same dialog, but the user found renaming/reprogramming a part and
    overriding the score's key too different a pair of actions to share one
    dialog - reverted, key override now lives in its own
    widgets/key_signature_dialog.py (Edit > Key Signature...).

    Deliberately no live audio preview, unlike MixerDialog - a name/program
    change has nothing to preview live the way a volume/pan slider does,
    and the user asked to keep this UI simple. Pure view like every other
    dialog here: main_window.py's _show_instrument_dialog reads
    self.overrides() after exec() and applies it through
    MusicData.apply_part_overrides - this class never touches MusicData.

    Instrument choice is a combo box, never a raw program number (the user
    explicitly does not want program numbers surfaced) - editable with a
    contains-anywhere QCompleter so 128 entries stay searchable ("type
    'guit' to find every guitar") without adding a separate search box,
    per the user's "keep the UI design simple" request; confirmed working
    well by the user (native combo-box keyboard search, not a custom
    control). setInsertPolicy NoInsert stops a typed-but-unmatched string
    from becoming a bogus new item; an unresolved edit is simply ignored at
    commit time (see _commit_current_row) rather than corrupting the
    part's program.

    Wishlist #8 follow-up: the SAME list/name-field/combo layout also
    carries one row per PERCUSSION ITEM (e.g. "Closed Hi-Hat") right after
    its owning percussion part's own row - selecting one swaps the combo's
    contents to GM's percussion sound names instead of the 128 GM
    instruments, and edits go through overrides()' extra two dicts instead
    of the part-level ones. A percussion part's OWN row keeps just its name
    field - there's no single "instrument" concept for a whole kit, so its
    combo is disabled rather than the layout changing shape. One dialog-
    level checkbox, "Apply MusicXML offset for percussion", is the auto-
    correct toggle (MusicData.percussion_auto_correct_enabled) - shown only
    when the score has at least one percussion part, since it does nothing
    otherwise.
    """

    ROW_PART = "part"
    ROW_ITEM = "item"

    def __init__(
        self,
        parent=None,
        rows: Optional[List[Tuple[str, str, int]]] = None,
        percussion_part_ids: Optional[List[str]] = None,
        percussion_rows: Optional[Dict[str, List[PercussionItemRow]]] = None,
        auto_correct_enabled: bool = False,
    ):
        super().__init__(parent)
        self.setWindowTitle("Instruments")

        self._percussion_part_ids = set(percussion_part_ids or [])
        percussion_rows = percussion_rows or {}

        # part_id -> (name, gmidi_program) - unused/ignored for a
        # percussion part (its row never shows the instrument combo).
        self._part_values: Dict[str, Tuple[str, int]] = {
            part_id: (name, program) for part_id, name, program in (rows or [])
        }
        self._original_part_values: Dict[str, Tuple[str, int]] = dict(self._part_values)

        # (part_id, source_key) -> (name, sounding_key).
        self._item_values: Dict[Tuple[str, int], Tuple[str, int]] = {
            item_key: (name, key)
            for items in percussion_rows.values()
            for item_key, name, key in items
        }
        self._original_item_values: Dict[Tuple[str, int], Tuple[str, int]] = dict(self._item_values)

        # ("part", part_id) or ("item", part_id, source_key) - the row
        # list's UserRole, so _on_row_changed knows which kind it's showing.
        self._current_row_id: Optional[tuple] = None

        self.row_list = QListWidget(self)
        for part_id, name, _ in (rows or []):
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, (self.ROW_PART, part_id))
            self.row_list.addItem(item)
            if part_id in self._percussion_part_ids:
                for item_key, item_name, _ in percussion_rows.get(part_id, []):
                    row = QListWidgetItem(item_name)
                    row.setData(Qt.ItemDataRole.UserRole, (self.ROW_ITEM, item_key))
                    self.row_list.addItem(row)
        self.row_list.currentRowChanged.connect(self._on_row_changed)

        self.name_edit = QLineEdit(self)

        self.instrument_combo = QComboBox(self)
        self.instrument_combo.setEditable(True)
        self.instrument_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        completer = QCompleter(self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.instrument_combo.setCompleter(completer)
        # Which list the combo currently holds - "pitched" (128 GM
        # instruments) or "percussion" (GM percussion sounds) - so
        # _commit_current_row resolves the typed/selected text against the
        # right name->key table without re-deriving it from the row id.
        self._combo_mode: Optional[str] = None

        form = QFormLayout()
        form.addRow("&Name:", self.name_edit)
        form.addRow("&Instrument:", self.instrument_combo)

        self.auto_correct_checkbox = QCheckBox("Apply MusicXML offset for percussion", self)
        self.auto_correct_checkbox.setChecked(auto_correct_enabled)
        self._auto_correct_available = bool(percussion_rows)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        controls = QWidget(self)
        controls_layout = QVBoxLayout(controls)
        controls_layout.addLayout(form)
        controls_layout.addStretch()

        top_row = QHBoxLayout()
        top_row.addWidget(self.row_list)
        top_row.addWidget(controls)

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        if self._auto_correct_available:
            layout.addWidget(self.auto_correct_checkbox)
        layout.addWidget(buttons)

        if self.row_list.count() > 0:
            self.row_list.setCurrentRow(0)
        else:
            self.name_edit.setEnabled(False)
            self.instrument_combo.setEnabled(False)

    def _set_combo_mode(self, mode: str) -> None:
        """mode: "pitched", "percussion", or "none" (a percussion part's own
        row, which has no single instrument to pick). Rebuilding the item
        list only when the mode actually changes avoids losing the
        completer's popup state on every row switch within the same mode."""
        if mode == self._combo_mode:
            return
        self._combo_mode = mode
        self.instrument_combo.blockSignals(True)
        self.instrument_combo.clear()
        if mode == "pitched":
            self.instrument_combo.addItems(GM_INSTRUMENT_NAMES)
            self.instrument_combo.completer().setModel(QStringListModel(GM_INSTRUMENT_NAMES, self))
        elif mode == "percussion":
            self.instrument_combo.addItems(GM_PERCUSSION_SOUND_NAMES)
            self.instrument_combo.completer().setModel(QStringListModel(GM_PERCUSSION_SOUND_NAMES, self))
        self.instrument_combo.blockSignals(False)

    def _on_row_changed(self, row: int) -> None:
        # Commit whatever the OUTGOING row's fields currently show before
        # swapping the displayed values - a row switch is the only point a
        # partially-typed instrument search needs resolving against the
        # combo's actual selection.
        self._commit_current_row()

        item = self.row_list.item(row) if row >= 0 else None
        row_id = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        self._current_row_id = row_id
        if row_id is None:
            return

        if row_id[0] == self.ROW_PART:
            part_id = row_id[1]
            name, program = self._part_values.get(part_id, ("", 25))
            self.name_edit.setText(name)
            if part_id in self._percussion_part_ids:
                # A whole kit has no single "instrument" - each of its
                # items (below, as their own rows) has its own sound.
                self._set_combo_mode("none")
                self.instrument_combo.setEnabled(False)
                self.instrument_combo.setCurrentText("")
            else:
                self._set_combo_mode("pitched")
                self.instrument_combo.setEnabled(True)
                self.instrument_combo.setCurrentText(gm_instrument_name(program))
        else:
            item_key = row_id[1]
            name, sounding_key = self._item_values.get(item_key, ("", 0))
            self.name_edit.setText(name)
            self._set_combo_mode("percussion")
            self.instrument_combo.setEnabled(True)
            # blockSignals isn't needed here - setCurrentText alone never
            # fires anything this dialog reads at commit time (see
            # _commit_current_row, which reads currentText()/findText()
            # only when actually asked to, not via a valueChanged-style
            # signal).
            self.instrument_combo.setCurrentText(gm_percussion_name(sounding_key))

    def _commit_current_row(self) -> None:
        if self._current_row_id is None:
            return
        if self._current_row_id[0] == self.ROW_PART:
            part_id = self._current_row_id[1]
            name = self.name_edit.text().strip()
            if not name:
                name, _ = self._part_values.get(part_id, ("", 25))
            _, program = self._part_values.get(part_id, ("", 25))
            if self.instrument_combo.isEnabled():
                program = GM_PROGRAM_BY_NAME.get(self.instrument_combo.currentText(), program)
            self._part_values[part_id] = (name, program)
        else:
            item_key = self._current_row_id[1]
            name = self.name_edit.text().strip()
            if not name:
                name, _ = self._item_values.get(item_key, ("", 0))
            _, sounding_key = self._item_values.get(item_key, ("", 0))
            resolved = gm_percussion_key_for_name(self.instrument_combo.currentText())
            if resolved is not None:
                sounding_key = resolved
            self._item_values[item_key] = (name, sounding_key)

    def overrides(self) -> Tuple[Dict[str, str], Dict[str, int], Dict[Tuple[str, int], str], Dict[Tuple[str, int], int], bool]:
        """(part_name_overrides, part_program_overrides,
        percussion_item_name_overrides, percussion_item_overrides,
        auto_correct_enabled) - only entries whose value actually changed
        from what the dialog opened with, matching the "explicit overrides
        only" shape MusicData.apply_part_overrides/apply_percussion_overrides
        and ScoreConfig all expect. Call after exec() returns Accepted.

        Commits the currently-displayed row first - whichever row was on
        screen when OK was pressed was never "switched away from", so
        _on_row_changed's own commit-on-switch never ran for it."""
        self._commit_current_row()

        name_overrides: Dict[str, str] = {}
        program_overrides: Dict[str, int] = {}
        for part_id, (name, program) in self._part_values.items():
            original_name, original_program = self._original_part_values.get(part_id, (name, program))
            if name != original_name:
                name_overrides[part_id] = name
            if program != original_program:
                program_overrides[part_id] = program

        item_name_overrides: Dict[Tuple[str, int], str] = {}
        item_sound_overrides: Dict[Tuple[str, int], int] = {}
        for item_key, (name, sounding_key) in self._item_values.items():
            original_name, original_key = self._original_item_values.get(item_key, (name, sounding_key))
            if name != original_name:
                item_name_overrides[item_key] = name
            if sounding_key != original_key:
                item_sound_overrides[item_key] = sounding_key

        return (
            name_overrides,
            program_overrides,
            item_name_overrides,
            item_sound_overrides,
            self.auto_correct_checkbox.isChecked(),
        )

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, lambda: focus_list_and_reannounce_current_row(self.row_list))
