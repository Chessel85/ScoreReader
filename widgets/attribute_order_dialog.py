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
    (MusicData.attribute_keys_for_voices). Unlike GotoMeasureDialog/
    TempoOffsetDialog, this dialog doesn't just collect one value for the
    caller to read after exec() - it stays open and interacts live, so
    MainWindow owns the actual MusicData.move_attribute_order() mutation and
    drives this dialog's display back via refresh_list().

    Same focus-on-show reasoning as GotoMeasureDialog: setFocus() before the
    native window exists never reaches NVDA, so it's deferred to showEvent."""

    # (attribute_key, up) - up=True means "move earlier". MainWindow performs
    # the actual reorder and calls refresh_list() with the result; this
    # dialog never touches MusicData itself.
    move_requested = Signal(str, bool)

    def __init__(self, parent=None, pairs: Optional[List[Tuple[str, str]]] = None, scope_description: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Reorder Attributes")

        label = QLabel(f"Attribute order for {scope_description}:", self)
        self.attribute_list = QListWidget(self)
        label.setBuddy(self.attribute_list)
        self._populate(pairs or [])
        self.attribute_list.currentRowChanged.connect(self._update_button_state)

        self.up_button = QPushButton("Move &Up", self)
        self.up_button.clicked.connect(lambda: self._request_move(up=True))
        self.down_button = QPushButton("Move &Down", self)
        self.down_button.clicked.connect(lambda: self._request_move(up=False))
        self._update_button_state()

        button_row = QHBoxLayout()
        button_row.addWidget(self.up_button)
        button_row.addWidget(self.down_button)

        # No Ok/Cancel semantics - every move already applied live via
        # move_requested, the same way F1's right-click attribute menu has
        # no undo step of its own.
        close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        close_buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(label)
        layout.addWidget(self.attribute_list)
        layout.addLayout(button_row)
        layout.addWidget(close_buttons)

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

    def _request_move(self, up: bool):
        item = self.attribute_list.currentItem()
        if item is None:
            return
        attribute_key = item.data(Qt.ItemDataRole.UserRole)
        self.move_requested.emit(attribute_key, up)

    def refresh_list(self, pairs: List[Tuple[str, str]], preferred_key: Optional[str] = None):
        """Rebuilds the rows after a move - re-anchors on preferred_key (the
        attribute that just moved) so NVDA keeps tracking it."""
        self._populate(pairs)
        target_row = 0
        if preferred_key is not None:
            for row in range(self.attribute_list.count()):
                if self.attribute_list.item(row).data(Qt.ItemDataRole.UserRole) == preferred_key:
                    target_row = row
                    break
        if self.attribute_list.count() > 0:
            self.attribute_list.setCurrentRow(target_row)
        self._update_button_state()
        self.attribute_list.setFocus()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.attribute_list.setFocus)
