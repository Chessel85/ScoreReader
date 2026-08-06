# tests/widgets/test_status_bar_widget.py
"""C6: pure widget-state tests for StatusBarWidget, mirroring
test_region2_manager.py's style - no shown window needed since Tab/Backtab
are dispatched from each field's own known index, not real Qt focus state
(see status_bar_widget.py's _StatusField docstring)."""
from PySide6.QtCore import Qt

from widgets.status_bar_widget import StatusBarWidget


def test_status_bar_has_three_fields(qtbot):
    bar = StatusBarWidget()
    qtbot.addWidget(bar)

    assert len(bar._fields) == 3


def test_set_fields_updates_text_and_accessible_name(qtbot):
    bar = StatusBarWidget()
    qtbot.addWidget(bar)

    bar.set_fields(["Measure 3 beat 2.5", "Key: G major / E minor", "Time: 3/4"])

    assert [f.text() for f in bar._fields] == [
        "Measure 3 beat 2.5", "Key: G major / E minor", "Time: 3/4",
    ]
    assert [f.accessibleName() for f in bar._fields] == [
        "Measure 3 beat 2.5", "Key: G major / E minor", "Time: 3/4",
    ]


def test_tab_moves_to_the_next_field_and_wraps(qtbot):
    bar = StatusBarWidget()
    qtbot.addWidget(bar)
    calls = []
    bar.focus_field = calls.append

    qtbot.keyClick(bar._fields[0], Qt.Key.Key_Tab)
    assert calls == [1]

    calls.clear()
    qtbot.keyClick(bar._fields[2], Qt.Key.Key_Tab)
    assert calls == [0], "wraps from the last field back to the first"


def test_shift_tab_moves_to_the_previous_field_and_wraps(qtbot):
    bar = StatusBarWidget()
    qtbot.addWidget(bar)
    calls = []
    bar.focus_field = calls.append

    qtbot.keyClick(bar._fields[1], Qt.Key.Key_Backtab)
    assert calls == [0]

    calls.clear()
    qtbot.keyClick(bar._fields[0], Qt.Key.Key_Backtab)
    assert calls == [2], "wraps from the first field back to the last"
