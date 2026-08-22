# tests/widgets/test_region_property_list_widget.py
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QWidget

from widgets.region_property_list_widget import RegionPropertyListWidget


class _FakeWindow(QWidget):
    """RegionPropertyListWidget's mixed-in RegionFocusCycleMixin calls
    self.window() - a plain top-level QWidget parent stands in for
    MainWindow so the wiring can be tested without constructing a real
    one."""

    def __init__(self):
        super().__init__()
        self.calls = []

    def focus_next_region(self, current):
        self.calls.append(current)


def test_refresh_list_with_empty_dict_leaves_the_list_empty(qtbot):
    widget = RegionPropertyListWidget()
    qtbot.addWidget(widget)

    widget.refresh_list({})

    assert widget.count() == 0


def test_refresh_list_populates_label_value_rows_in_order(qtbot):
    widget = RegionPropertyListWidget()
    qtbot.addWidget(widget)

    widget.refresh_list({"Title": "Bourree", "Composer": "Bach"})

    assert [widget.item(i).text() for i in range(widget.count())] == [
        "Title: Bourree",
        "Composer: Bach",
    ]


def test_refresh_list_preserves_current_row_across_a_same_size_rebuild(qtbot):
    widget = RegionPropertyListWidget()
    qtbot.addWidget(widget)
    widget.refresh_list({"a": "1", "b": "2", "c": "3"})
    widget.setCurrentRow(2)

    widget.refresh_list({"a": "1", "b": "2", "c": "9"})

    assert widget.currentRow() == 2


def test_refresh_list_clamps_a_now_out_of_range_row(qtbot):
    widget = RegionPropertyListWidget()
    qtbot.addWidget(widget)
    widget.refresh_list({"a": "1", "b": "2", "c": "3"})
    widget.setCurrentRow(2)

    widget.refresh_list({"a": "1"})

    assert widget.currentRow() == 0


def test_tab_still_forwards_to_the_region_cycle(qtbot):
    """R1: dispatch through event(), not keyPressEvent - QAbstractItemView
    consumes Tab in event() before keyPressEvent is ever invoked, so a
    keyPressEvent-driven test would pass without exercising the real path."""
    fake_window = _FakeWindow()
    qtbot.addWidget(fake_window)
    widget = RegionPropertyListWidget(parent=fake_window)

    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
    assert widget.event(event) is True

    assert fake_window.calls == [widget]
