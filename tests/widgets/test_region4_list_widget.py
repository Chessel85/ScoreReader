# tests/widgets/test_region4_list_widget.py
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QListWidgetItem, QWidget

from widgets.region4_list_widget import Region4ListWidget


class _FakeWindow(QWidget):
    """Region4ListWidget calls self.window() - a plain top-level QWidget
    parent stands in for MainWindow so the wiring can be tested without
    constructing a real one."""

    def __init__(self):
        super().__init__()
        self.calls = []

    def show_region_4_attribute_menu(self, row, global_pos):
        self.calls.append((row, global_pos))


def test_context_menu_policy_is_custom(qtbot):
    fake_window = _FakeWindow()
    qtbot.addWidget(fake_window)
    widget = Region4ListWidget(parent=fake_window)

    assert widget.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu


def test_context_menu_request_forwards_the_clicked_row_to_the_window(qtbot):
    """The row comes from the click position, not currentRow() - a real
    right-click can land on a row other than the one keyboard focus is on."""
    fake_window = _FakeWindow()
    qtbot.addWidget(fake_window)
    widget = Region4ListWidget(parent=fake_window)
    widget.addItem(QListWidgetItem("step: C"))
    widget.addItem(QListWidgetItem("octave: 4"))
    widget.setCurrentRow(0)  # keyboard focus stays on row 0

    row_1_pos = widget.visualItemRect(widget.item(1)).center()
    widget.customContextMenuRequested.emit(row_1_pos)

    assert len(fake_window.calls) == 1
    row, _pos = fake_window.calls[0]
    assert row == 1
    assert widget.currentRow() == 1, "the click also moves the keyboard cursor to match"


def test_context_menu_request_is_a_noop_with_no_current_row(qtbot):
    fake_window = _FakeWindow()
    qtbot.addWidget(fake_window)
    widget = Region4ListWidget(parent=fake_window)  # empty list, no current row

    widget.customContextMenuRequested.emit(widget.rect().center())

    assert fake_window.calls == []


def test_menu_key_opens_the_attribute_menu(qtbot):
    """Live-tested finding: Qt does not reliably raise
    customContextMenuRequested for the Menu/Application key on a
    QListWidget on its own - Region4ListWidget must handle it itself."""
    fake_window = _FakeWindow()
    qtbot.addWidget(fake_window)
    widget = Region4ListWidget(parent=fake_window)
    widget.addItem(QListWidgetItem("step: C"))
    widget.addItem(QListWidgetItem("octave: 4"))
    widget.setCurrentRow(1)

    qtbot.keyClick(widget, Qt.Key.Key_Menu)

    assert len(fake_window.calls) == 1
    row, _pos = fake_window.calls[0]
    assert row == 1


def test_shift_f10_also_opens_the_attribute_menu(qtbot):
    fake_window = _FakeWindow()
    qtbot.addWidget(fake_window)
    widget = Region4ListWidget(parent=fake_window)
    widget.addItem(QListWidgetItem("step: C"))
    widget.addItem(QListWidgetItem("octave: 4"))
    widget.setCurrentRow(0)

    qtbot.keyClick(widget, Qt.Key.Key_F10, Qt.KeyboardModifier.ShiftModifier)

    assert len(fake_window.calls) == 1
    row, _pos = fake_window.calls[0]
    assert row == 0


def test_menu_key_is_a_noop_with_no_current_row(qtbot):
    fake_window = _FakeWindow()
    qtbot.addWidget(fake_window)
    widget = Region4ListWidget(parent=fake_window)  # empty list, no current row

    qtbot.keyClick(widget, Qt.Key.Key_Menu)

    assert fake_window.calls == []


def test_tab_still_forwards_to_the_region_cycle(qtbot):
    """Overriding keyPressEvent for the Menu key must not break
    RegionPropertyListWidget's Tab/Backtab -> focus_next_region forwarding.
    Dispatch through event(), not keyPressEvent - QAbstractItemView consumes
    Tab in event() before keyPressEvent is ever invoked."""
    calls = []
    fake_window = _FakeWindow()
    fake_window.focus_next_region = lambda current: calls.append(current)
    qtbot.addWidget(fake_window)
    widget = Region4ListWidget(parent=fake_window)
    widget.addItem(QListWidgetItem("step: C"))

    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
    assert widget.event(event) is True

    assert calls == [widget]
