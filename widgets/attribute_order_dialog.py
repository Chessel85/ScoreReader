# widgets/attribute_order_dialog.py
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)


class AttributeOrderDialog(QDialog):
    """Options > Reorder Attributes... (F2, Ref 15 AC4) - reorders the single
    global attribute_order Region 3/4 both render from, scoped for editing to
    whatever part/staff/voice was selected in Region 2 when this was opened
    (MusicData.attribute_keys_for_voices).

    A working-copy OK/Cancel dialog, like widgets/part_order_dialog.py:
    moves are staged in this dialog's own list only, and MainWindow reads
    ordered_keys() after exec() returns Accepted to commit the result via
    MusicData.set_attribute_order_within - Cancel (or Escape, or the window
    close box) discards them untouched. Pure view like every other dialog
    here: this class never touches MusicData itself.

    User-requested follow-up: this dialog already lists every attribute
    present in scope regardless of on/off state, so a rare one spotted here
    used to have no way to actually be switched on without first finding a
    note that already showed it in Region 4. The Add/&Remove button below
    opens the same voice/stave/part/score scope menu Region 4's own
    context menu offers (AttributeController._scope_action_labels), fanning
    out from this dialog's own node instead of a selected note. Unlike the
    Up/Down moves, an Add/Remove change is applied immediately (it toggles
    which attributes are visible at all, a different feature to F2's
    ordering) rather than staged for OK.

    Same focus-on-show reasoning as GotoMeasureDialog: setFocus() before the
    native window exists never reaches NVDA, so it's deferred to showEvent."""

    # attribute_key of the row the button was clicked for - MainWindow
    # builds and shows the actual scope menu (AttributeController.
    # show_order_menu), since its content depends on live MusicData state
    # this dialog has no access to.
    add_remove_requested = Signal(str)

    def __init__(self, parent=None, pairs: Optional[List[Tuple[str, str]]] = None, scope_description: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Reorder Attributes")

        label = QLabel(f"Attribute order for {scope_description}:", self)
        self.attribute_list = QListWidget(self)
        label.setBuddy(self.attribute_list)
        self._populate(pairs or [])
        self.attribute_list.currentRowChanged.connect(self._update_button_state)

        self.up_button = QPushButton("Move &Up", self)
        self.up_button.setAutoDefault(False)
        self.up_button.clicked.connect(lambda: self._move(-1))
        self.down_button = QPushButton("Move &Down", self)
        self.down_button.setAutoDefault(False)
        self.down_button.clicked.connect(lambda: self._move(1))
        self.add_remove_button = QPushButton("Add/&Remove...", self)
        self.add_remove_button.setAutoDefault(False)
        self.add_remove_button.clicked.connect(self._request_add_remove)
        self._update_button_state()

        button_row = QHBoxLayout()
        button_row.addWidget(self.up_button)
        button_row.addWidget(self.down_button)
        button_row.addWidget(self.add_remove_button)

        # autoDefault=False above, live-tested and load-bearing: autoDefault
        # isn't just "is this the dialog's default button" - Qt dynamically
        # HANDS default status to whichever autoDefault button currently has
        # keyboard focus (that's what "auto" means), and a screen reader's
        # accessible "keyboard shortcut" text for a button is generated from
        # that same live default-button flag - so an autoDefault button
        # reports "Enter" the moment it's tabbed to, silently replacing its
        # own &U/&D mnemonic. Confirmed live with NVDA; not reproducible
        # offscreen, since the offscreen platform never gives a widget real
        # OS focus. Disabling autoDefault keeps Up/Down/Add-Remove from ever
        # taking default status, so their mnemonics always announce
        # correctly and Ok stays the sole default - the trade-off (an
        # explicit, confirmed user choice) is that Enter no longer performs
        # the move itself while one of these buttons is focused; Space
        # still does, and Enter now behaves like it would on any other
        # non-default button in a standard dialog (triggers Ok instead).
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(label)
        layout.addWidget(self.attribute_list)
        layout.addLayout(button_row)
        layout.addWidget(buttons)

    def _populate(self, pairs: List[Tuple[str, str]]):
        self.attribute_list.clear()
        for attribute_key, attribute_label in pairs:
            item = QListWidgetItem(attribute_label)
            item.setData(Qt.ItemDataRole.UserRole, attribute_key)
            self.attribute_list.addItem(item)

    def _update_button_state(self, current_row: Optional[int] = None):
        if current_row is None:
            current_row = self.attribute_list.currentRow()
        self.up_button.setEnabled(current_row > 0)
        self.down_button.setEnabled(0 <= current_row < self.attribute_list.count() - 1)
        self.add_remove_button.setEnabled(current_row >= 0)

    def _move(self, delta: int):
        row = self.attribute_list.currentRow()
        if row < 0:
            return
        new_row = row + delta
        if not (0 <= new_row < self.attribute_list.count()):
            return
        item = self.attribute_list.takeItem(row)
        self.attribute_list.insertItem(new_row, item)
        self.attribute_list.setCurrentRow(new_row)

    def _request_add_remove(self):
        item = self.attribute_list.currentItem()
        if item is None:
            return
        attribute_key = item.data(Qt.ItemDataRole.UserRole)
        self.add_remove_requested.emit(attribute_key)

    def ordered_keys(self) -> List[str]:
        """The attribute_key order after any staged moves, only meaningful
        once exec() has returned Accepted."""
        return [
            self.attribute_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.attribute_list.count())
        ]

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.attribute_list.setFocus)
