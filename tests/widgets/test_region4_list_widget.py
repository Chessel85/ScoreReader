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


def test_refresh_list_stores_attribute_key_and_renders_display_value(qtbot):
    fake_window = _FakeWindow()
    qtbot.addWidget(fake_window)
    widget = Region4ListWidget(parent=fake_window)

    widget.refresh_list([("step", "step", "C"), ("octave", "octave", "4")])

    assert [widget.item(i).text() for i in range(widget.count())] == ["step: C", "octave: 4"]
    assert widget.item(0).data(Qt.ItemDataRole.UserRole) == "step"
    assert widget.item(1).data(Qt.ItemDataRole.UserRole) == "octave"


def test_refresh_list_re_anchors_on_the_same_attribute_key(qtbot):
    """Reported: Alt+Right/Alt+Left (Find) can jump to a note whose
    attribute set/order is entirely different from the previous one, unlike
    ordinary Left/Right between neighbouring notes - a raw row-index clamp
    landed on an unrelated attribute, or row 0 whenever the new note simply
    had fewer rows. Re-anchoring on the same attribute_key fixes both."""
    fake_window = _FakeWindow()
    qtbot.addWidget(fake_window)
    widget = Region4ListWidget(parent=fake_window)
    widget.refresh_list([
        ("step", "step", "C"), ("octave", "octave", "4"),
        ("string", "string", "3"), ("articulation", "articulation", "staccato"),
    ])
    widget.setCurrentRow(3)  # "articulation: staccato"

    # The new note has articulation at a DIFFERENT row (1, not 3) and no
    # "string" at all - a plain index clamp would land on "octave".
    widget.refresh_list([
        ("step", "step", "D"), ("articulation", "articulation", "trill"),
    ])

    assert widget.currentRow() == 1
    assert widget.item(1).text() == "articulation: trill"


def test_refresh_list_falls_back_to_index_clamp_when_the_key_is_gone(qtbot):
    fake_window = _FakeWindow()
    qtbot.addWidget(fake_window)
    widget = Region4ListWidget(parent=fake_window)
    widget.refresh_list([
        ("step", "step", "C"), ("octave", "octave", "4"), ("fret", "fret", "3"),
    ])
    widget.setCurrentRow(2)  # "fret: 3"

    widget.refresh_list([("step", "step", "D"), ("octave", "octave", "5")])

    assert widget.currentRow() == 1, "clamped to the last valid index, same as before this fix"


def test_refresh_list_with_no_rows_leaves_an_empty_list(qtbot):
    fake_window = _FakeWindow()
    qtbot.addWidget(fake_window)
    widget = Region4ListWidget(parent=fake_window)

    widget.refresh_list([])

    assert widget.count() == 0
    assert widget.currentRow() == -1


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
