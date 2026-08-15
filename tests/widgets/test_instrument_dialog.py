# tests/widgets/test_instrument_dialog.py
"""Pure widget-state tests for InstrumentDialog (S5) - like MixerDialog, it
never touches MusicData/PlaybackController itself, so it can be driven
directly with no MainWindow/score involved."""
from widgets.instrument_dialog import InstrumentDialog

ROWS = [
    ("P1", "Track 1", 1),       # Acoustic Grand Piano
    ("P2", "Cool Violin", 41),  # Violin
]


def test_populates_one_row_per_part_and_selects_the_first(qtbot):
    dialog = InstrumentDialog(rows=ROWS)
    qtbot.addWidget(dialog)

    assert dialog.row_list.count() == 2
    assert [dialog.row_list.item(i).text() for i in range(2)] == ["Track 1", "Cool Violin"]
    assert dialog.row_list.currentRow() == 0
    assert dialog.name_edit.text() == "Track 1"
    assert dialog.instrument_combo.currentText() == "Acoustic Grand Piano"


def test_changing_the_selected_row_updates_the_fields(qtbot):
    dialog = InstrumentDialog(rows=ROWS)
    qtbot.addWidget(dialog)

    dialog.row_list.setCurrentRow(1)

    assert dialog.name_edit.text() == "Cool Violin"
    assert dialog.instrument_combo.currentText() == "Violin"


def test_edits_are_committed_on_row_switch_and_returned_by_overrides(qtbot):
    dialog = InstrumentDialog(rows=ROWS)
    qtbot.addWidget(dialog)

    dialog.name_edit.setText("Grand Piano")
    dialog.instrument_combo.setCurrentText("Clarinet")
    dialog.row_list.setCurrentRow(1)  # commits the P1 edits above

    name_overrides, program_overrides = dialog.overrides()

    assert name_overrides == {"P1": "Grand Piano"}
    assert program_overrides == {"P1": 72}  # Clarinet


def test_overrides_only_include_parts_that_actually_changed(qtbot):
    dialog = InstrumentDialog(rows=ROWS)
    qtbot.addWidget(dialog)

    dialog.row_list.setCurrentRow(1)  # touch P2's row without editing anything
    dialog._commit_current_row()

    name_overrides, program_overrides = dialog.overrides()
    assert name_overrides == {}
    assert program_overrides == {}


def test_unresolved_typed_instrument_text_keeps_the_previous_program(qtbot):
    """Typing a search string that never resolves to a real GM name (no
    exact match, nothing picked from the completer popup) must not corrupt
    the part's program - the combo box is the only way to actually choose
    an instrument, per the user's "don't surface program numbers" design."""
    dialog = InstrumentDialog(rows=ROWS)
    qtbot.addWidget(dialog)

    dialog.instrument_combo.setCurrentText("not a real instrument")
    dialog.row_list.setCurrentRow(1)

    _, program_overrides = dialog.overrides()
    assert program_overrides == {}


def test_accept_commits_the_currently_selected_row_too(qtbot):
    """overrides() must reflect the LAST row's edits even though the user
    never switched away from it before pressing OK."""
    dialog = InstrumentDialog(rows=ROWS)
    qtbot.addWidget(dialog)
    dialog.row_list.setCurrentRow(1)

    dialog.name_edit.setText("Cello")
    dialog.accept()

    name_overrides, _ = dialog.overrides()
    assert name_overrides == {"P2": "Cello"}


def test_ok_and_cancel_set_the_dialog_result(qtbot):
    dialog = InstrumentDialog(rows=ROWS)
    qtbot.addWidget(dialog)

    dialog.accept()
    assert dialog.result() == InstrumentDialog.DialogCode.Accepted

    dialog2 = InstrumentDialog(rows=ROWS)
    qtbot.addWidget(dialog2)
    dialog2.reject()
    assert dialog2.result() == InstrumentDialog.DialogCode.Rejected


def test_empty_rows_disables_the_controls(qtbot):
    dialog = InstrumentDialog(rows=[])
    qtbot.addWidget(dialog)

    assert dialog.row_list.count() == 0
    assert not dialog.name_edit.isEnabled()
    assert not dialog.instrument_combo.isEnabled()
