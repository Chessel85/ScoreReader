# widgets/find_dialog.py
from typing import Dict, List, Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from models.find_target import FindTarget, occurrence_label
from widgets.list_focus_helper import focus_list_and_reannounce_current_row

# Reads out which kind of thing a row is, since attribute keys and marking
# labels sit in the same flat list (NVDA-friendly - one focus stop per row,
# same reasoning Region 2's flat list already has over a table).
_CATEGORY_PREFIX = {"attribute": "Attribute", "marking": "Marking"}


class FindDialog(QDialog):
    """Navigation > Find... (Ctrl+F) - pick an attribute or performance-
    marking type to jump to occurrences of. Modal, deliberately: a
    modeless dialog is confusing for a screen reader (the user's own
    reasoning). OK arms the selection as MainWindow/NavigationController's
    current find target and performs the initial jump
    (NavigationController.find_next from wherever the cursor already is);
    Alt+Right/Alt+Left then cycle further occurrences without reopening
    this dialog.

    Each row also carries its occurrence count (D13); a value-level target
    (D1) shows its value after the label ("Attribute: Articulation:
    staccato, 78 occurrences"). A single-line Filter box (D11) narrows the
    list as you type, matching the label text only (never the count digits).
    It sits after the list in tab order, so initial focus still lands on
    the list - the project's dialog-focus rule.

    Same focus-on-show reasoning as GotoMeasureDialog: setFocus() before the
    native window exists never reaches NVDA, so it's deferred to showEvent."""

    def __init__(
        self,
        parent=None,
        targets: Optional[List[FindTarget]] = None,
        counts: Optional[Dict[FindTarget, int]] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Find")
        self._targets = targets or []
        self._counts = counts or {}

        label = QLabel("Find:", self)
        self.target_list = QListWidget(self)
        label.setBuddy(self.target_list)

        filter_label = QLabel("Filter:", self)
        self.filter_edit = QLineEdit(self)
        filter_label.setBuddy(self.filter_edit)
        self.filter_edit.textChanged.connect(self._apply_filter)

        # (item, lowercased label-only text) - the filter matches this, not
        # the visible row text, so typing a digit never filters on the
        # trailing occurrence count.
        self._filter_index: List[tuple] = []
        for target in self._targets:
            prefix = _CATEGORY_PREFIX.get(target.category, target.category.capitalize())
            label_text = f"{prefix}: {target.label}"
            if target.value is not None:
                label_text = f"{label_text}: {target.value}"
            row_text = label_text
            count = self._counts.get(target)
            if count is not None:
                row_text = f"{label_text}, {occurrence_label(count)}"
            item = QListWidgetItem(row_text)
            item.setData(Qt.ItemDataRole.UserRole, target)
            self.target_list.addItem(item)
            self._filter_index.append((item, label_text.lower()))
        if self._targets:
            self.target_list.setCurrentRow(0)
        # Enter on the focused row accepts directly, same as double-click -
        # QAbstractItemView doesn't otherwise route Enter to the dialog's
        # default button while the list itself has focus.
        self.target_list.itemActivated.connect(self.accept)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(self._targets))

        layout = QVBoxLayout(self)
        layout.addWidget(label)
        layout.addWidget(self.target_list)
        layout.addWidget(filter_label)
        layout.addWidget(self.filter_edit)
        layout.addWidget(buttons)

        # List first in tab order so showEvent's focus stays on it; the
        # filter follows.
        self.setTabOrder(self.target_list, self.filter_edit)
        self.setTabOrder(self.filter_edit, buttons)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, lambda: focus_list_and_reannounce_current_row(self.target_list))

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        current = self.target_list.currentItem()
        for item, label_text in self._filter_index:
            item.setHidden(bool(needle) and needle not in label_text)
        if current is not None and current.isHidden():
            for row in range(self.target_list.count()):
                if not self.target_list.item(row).isHidden():
                    self.target_list.setCurrentRow(row)
                    break

    def selected_target(self) -> Optional[FindTarget]:
        item = self.target_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None
