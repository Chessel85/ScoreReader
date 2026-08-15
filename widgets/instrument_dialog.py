# widgets/instrument_dialog.py
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QStringListModel, Qt, QTimer
from PySide6.QtWidgets import (
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
    """

    def __init__(self, parent=None, rows: Optional[List[Tuple[str, str, int]]] = None):
        super().__init__(parent)
        self.setWindowTitle("Instruments")

        # part_id -> (name, gmidi_program), the working copy every commit
        # writes into and overrides() diffs against the untouched original.
        self._values: Dict[str, Tuple[str, int]] = {
            part_id: (name, program) for part_id, name, program in (rows or [])
        }
        self._original_values: Dict[str, Tuple[str, int]] = dict(self._values)
        self._current_part_id: Optional[str] = None

        self.row_list = QListWidget(self)
        for part_id, name, _ in (rows or []):
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, part_id)
            self.row_list.addItem(item)
        self.row_list.currentRowChanged.connect(self._on_row_changed)

        self.name_edit = QLineEdit(self)

        self.instrument_combo = QComboBox(self)
        self.instrument_combo.setEditable(True)
        self.instrument_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.instrument_combo.addItems(GM_INSTRUMENT_NAMES)
        completer = QCompleter(QStringListModel(GM_INSTRUMENT_NAMES, self), self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.instrument_combo.setCompleter(completer)

        form = QFormLayout()
        form.addRow("&Name:", self.name_edit)
        form.addRow("&Instrument:", self.instrument_combo)

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
        layout.addWidget(buttons)

        if self.row_list.count() > 0:
            self.row_list.setCurrentRow(0)
        else:
            self.name_edit.setEnabled(False)
            self.instrument_combo.setEnabled(False)

    def _on_row_changed(self, row: int) -> None:
        # Commit whatever the OUTGOING row's fields currently show before
        # swapping the displayed values - a row switch is the only point a
        # partially-typed instrument search needs resolving against the
        # combo's actual selection.
        self._commit_current_row()

        item = self.row_list.item(row) if row >= 0 else None
        part_id = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        self._current_part_id = part_id
        if part_id is None:
            return

        name, program = self._values.get(part_id, ("", 25))
        self.name_edit.setText(name)
        # blockSignals isn't needed here - setCurrentText alone never fires
        # anything this dialog reads at commit time (see _commit_current_row,
        # which reads currentText()/findText() only when actually asked to,
        # not via a valueChanged-style signal).
        self.instrument_combo.setCurrentText(gm_instrument_name(program))

    def _commit_current_row(self) -> None:
        if self._current_part_id is None:
            return
        name = self.name_edit.text().strip()
        if not name:
            name, _ = self._values.get(self._current_part_id, ("", 25))
        program = GM_PROGRAM_BY_NAME.get(self.instrument_combo.currentText())
        if program is None:
            # Unresolved free text (no exact/completer match yet) - keep
            # whatever program this part already had rather than losing it.
            _, program = self._values.get(self._current_part_id, ("", 25))
        self._values[self._current_part_id] = (name, program)

    def overrides(self) -> Tuple[Dict[str, str], Dict[str, int]]:
        """(name_overrides, program_overrides) - only parts whose value
        actually changed from what the dialog opened with, matching the
        "explicit overrides only" shape MusicData.apply_part_overrides and
        ScoreConfig both expect. Call after exec() returns Accepted.

        Commits the currently-displayed row first - whichever row was on
        screen when OK was pressed was never "switched away from", so
        _on_row_changed's own commit-on-switch never ran for it."""
        self._commit_current_row()
        name_overrides: Dict[str, str] = {}
        program_overrides: Dict[str, int] = {}
        for part_id, (name, program) in self._values.items():
            original_name, original_program = self._original_values.get(part_id, (name, program))
            if name != original_name:
                name_overrides[part_id] = name
            if program != original_program:
                program_overrides[part_id] = program
        return name_overrides, program_overrides

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.row_list.setFocus)
