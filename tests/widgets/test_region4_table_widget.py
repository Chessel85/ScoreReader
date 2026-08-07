# tests/widgets/test_region4_table_widget.py
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QTableWidgetItem, QWidget

from widgets.region4_table_widget import Region4TableWidget


class _FakeWindow(QWidget):
    """Region4TableWidget calls self.window() - a plain top-level QWidget
    parent stands in for MainWindow so the wiring can be tested without
    constructing a real one."""

    def __init__(self):
        super().__init__()
        self.calls = []

    def show_region_4_attribute_menu(self, row, column, global_pos):
        self.calls.append((row, column, global_pos))


def test_context_menu_policy_is_custom(qtbot):
    fake_window = _FakeWindow()
    qtbot.addWidget(fake_window)
    table = Region4TableWidget(2, 2, parent=fake_window)

    assert table.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu


def test_context_menu_request_forwards_the_clicked_row_to_the_window(qtbot):
    """The row comes from the click position, not currentRow() - a real
    right-click can land on a row other than the one keyboard focus is on."""
    fake_window = _FakeWindow()
    qtbot.addWidget(fake_window)
    table = Region4TableWidget(2, 2, parent=fake_window)
    table.setItem(0, 0, QTableWidgetItem("step"))
    table.setItem(1, 0, QTableWidgetItem("octave"))
    table.setCurrentCell(0, 0)  # keyboard focus stays on row 0

    row_1_pos = table.visualItemRect(table.item(1, 0)).center()
    table.customContextMenuRequested.emit(row_1_pos)

    assert len(fake_window.calls) == 1
    row, _column, _pos = fake_window.calls[0]
    assert row == 1
    assert table.currentRow() == 1, "the click also moves the keyboard cursor to match"


def test_context_menu_preserves_the_current_column(qtbot):
    """Live-tested bug: the row/column restored after the menu closes used
    to be hard-coded to column 0, so opening the menu from the value column
    (1) always landed back on the key column (0) instead. The column must
    be carried through to show_region_4_attribute_menu unchanged."""
    fake_window = _FakeWindow()
    qtbot.addWidget(fake_window)
    table = Region4TableWidget(2, 2, parent=fake_window)
    table.setItem(0, 0, QTableWidgetItem("step"))
    table.setItem(0, 1, QTableWidgetItem("C"))
    table.setCurrentCell(0, 1)  # focus on the value column

    qtbot.keyClick(table, Qt.Key.Key_Menu)

    assert len(fake_window.calls) == 1
    row, column, _pos = fake_window.calls[0]
    assert (row, column) == (0, 1)


def test_context_menu_request_is_a_noop_with_no_current_row(qtbot):
    fake_window = _FakeWindow()
    qtbot.addWidget(fake_window)
    table = Region4TableWidget(0, 2, parent=fake_window)  # empty table, no current row

    table.customContextMenuRequested.emit(table.rect().center())

    assert fake_window.calls == []


def test_menu_key_opens_the_attribute_menu(qtbot):
    """Live-tested finding: Qt does not reliably raise
    customContextMenuRequested for the Menu/Application key on a
    QTableWidget on its own - Region4TableWidget must handle it itself."""
    fake_window = _FakeWindow()
    qtbot.addWidget(fake_window)
    table = Region4TableWidget(2, 2, parent=fake_window)
    table.setItem(0, 0, QTableWidgetItem("step"))
    table.setItem(1, 0, QTableWidgetItem("octave"))
    table.setCurrentCell(1, 0)

    qtbot.keyClick(table, Qt.Key.Key_Menu)

    assert len(fake_window.calls) == 1
    row, _column, _pos = fake_window.calls[0]
    assert row == 1


def test_shift_f10_also_opens_the_attribute_menu(qtbot):
    fake_window = _FakeWindow()
    qtbot.addWidget(fake_window)
    table = Region4TableWidget(2, 2, parent=fake_window)
    table.setItem(0, 0, QTableWidgetItem("step"))
    table.setItem(1, 0, QTableWidgetItem("octave"))
    table.setCurrentCell(0, 0)

    qtbot.keyClick(table, Qt.Key.Key_F10, Qt.KeyboardModifier.ShiftModifier)

    assert len(fake_window.calls) == 1
    row, _column, _pos = fake_window.calls[0]
    assert row == 0


def test_menu_key_is_a_noop_with_no_current_row(qtbot):
    fake_window = _FakeWindow()
    qtbot.addWidget(fake_window)
    table = Region4TableWidget(0, 2, parent=fake_window)  # empty table, no current row

    qtbot.keyClick(table, Qt.Key.Key_Menu)

    assert fake_window.calls == []


def test_tab_still_forwards_to_the_region_cycle(qtbot):
    """Overriding keyPressEvent for the Menu key must not break
    RegionTableWidget's existing Tab/Backtab -> focus_next_region forwarding.
    Calls keyPressEvent directly rather than via qtbot.keyClick - Qt's own
    tab-focus handling intercepts a real Key_Tab before it reaches
    keyPressEvent on a widget that isn't genuinely focused/shown, the same
    QTest fragility already worked around for F6 pane-cycling (C7)."""
    calls = []
    fake_window = _FakeWindow()
    fake_window.focus_next_region = lambda current: calls.append(current)
    qtbot.addWidget(fake_window)
    table = Region4TableWidget(1, 2, parent=fake_window)

    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
    table.keyPressEvent(event)

    assert calls == [table]
