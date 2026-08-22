# widgets/find_dialog.py
from typing import List, Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QListWidget, QListWidgetItem, QVBoxLayout

from models.find_target import FindTarget

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
    this dialog. No search/filter box in this first pass - the list is
    already short and presence-filtered by MusicData.available_find_
    targets(), so nothing invites narrowing it further yet.

    Same focus-on-show reasoning as GotoMeasureDialog: setFocus() before the
    native window exists never reaches NVDA, so it's deferred to showEvent."""

    def __init__(self, parent=None, targets: Optional[List[FindTarget]] = None):
        super().__init__(parent)
        self.setWindowTitle("Find")
        self._targets = targets or []

        label = QLabel("Find:", self)
        self.target_list = QListWidget(self)
        label.setBuddy(self.target_list)
        for target in self._targets:
            prefix = _CATEGORY_PREFIX.get(target.category, target.category.capitalize())
            item = QListWidgetItem(f"{prefix}: {target.label}")
            item.setData(Qt.ItemDataRole.UserRole, target)
            self.target_list.addItem(item)
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
        layout.addWidget(buttons)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.target_list.setFocus)

    def selected_target(self) -> Optional[FindTarget]:
        item = self.target_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None
