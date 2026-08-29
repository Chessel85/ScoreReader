# widgets/part_order_dialog.py
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)


class PartOrderDialog(QDialog):
    """Options > Reorder Parts... - controls the order parts_info lists
    parts in, which in turn controls Region 3's note-row order (Region 3's
    "current" row after every navigation step is always row 0, so this is
    what decides which part's row a screen reader lands on first - the
    user's own stated reason for wanting this: NVDA reading a UG import's
    chord name when they wanted the lyric, or vice versa).

    A working-copy, OK/Cancel dialog (like widgets/instrument_dialog.py),
    not a live-apply one like widgets/attribute_order_dialog.py - moves
    are staged in this list and only committed on OK; Cancel discards them
    untouched. Move &Up/Move &Down give Alt+U/Alt+D via Qt's own mnemonic
    handling, same button-text convention AttributeOrderDialog already
    uses.

    Pure view like every other dialog here: main_window.py's
    _show_part_order_dialog reads self.part_order() after exec() and
    applies it through MusicData.reorder_parts/Region2ListWidget.reorder_
    parts - this class never touches MusicData."""

    def __init__(self, parent=None, parts: Optional[List[Tuple[str, str]]] = None):
        super().__init__(parent)
        self.setWindowTitle("Part Order")

        self.part_list = QListWidget(self)
        for part_id, name in (parts or []):
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, part_id)
            self.part_list.addItem(item)
        if self.part_list.count() > 0:
            self.part_list.setCurrentRow(0)

        self.up_button = QPushButton("Move &Up", self)
        self.up_button.setAutoDefault(False)
        self.up_button.clicked.connect(lambda: self._move(-1))
        self.down_button = QPushButton("Move &Down", self)
        self.down_button.setAutoDefault(False)
        self.down_button.clicked.connect(lambda: self._move(1))
        self._update_button_state()
        # Connected only after the buttons exist - setCurrentRow above
        # fires this synchronously, and _update_button_state reaches
        # self.up_button/down_button, which don't exist until just now.
        self.part_list.currentRowChanged.connect(self._update_button_state)

        button_row = QHBoxLayout()
        button_row.addWidget(self.up_button)
        button_row.addWidget(self.down_button)

        # autoDefault=False above - see AttributeOrderDialog's identical,
        # longer comment. Live-tested with NVDA: autoDefault dynamically
        # hands "default button" status to whichever autoDefault button
        # currently has keyboard focus, and a screen reader's accessible
        # shortcut text for a button is generated from that same flag - so
        # leaving it on masks Up/Down's own &U/&D mnemonic as "Enter" the
        # moment either is tabbed to, regardless of Ok's own setDefault(True)
        # below. Confirmed user trade-off: Space still moves the item;
        # Enter on a focused Up/Down now triggers Ok instead (same as any
        # other non-default button in a standard dialog), rather than
        # performing the move itself.
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.part_list)
        layout.addLayout(button_row)
        layout.addWidget(buttons)

    def _update_button_state(self, current_row: Optional[int] = None):
        if current_row is None:
            current_row = self.part_list.currentRow()
        self.up_button.setEnabled(current_row > 0)
        self.down_button.setEnabled(0 <= current_row < self.part_list.count() - 1)

    def _move(self, delta: int):
        row = self.part_list.currentRow()
        if row < 0:
            return
        new_row = row + delta
        if not (0 <= new_row < self.part_list.count()):
            return
        item = self.part_list.takeItem(row)
        self.part_list.insertItem(new_row, item)
        self.part_list.setCurrentRow(new_row)
        self.part_list.setFocus()

    def part_order(self) -> List[str]:
        """The part_id order after any moves, only meaningful once exec()
        has returned Accepted."""
        return [
            self.part_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.part_list.count())
        ]

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.part_list.setFocus)
