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

    name_overrides, program_overrides, _, _, _ = dialog.overrides()

    assert name_overrides == {"P1": "Grand Piano"}
    assert program_overrides == {"P1": 72}  # Clarinet


def test_overrides_only_include_parts_that_actually_changed(qtbot):
    dialog = InstrumentDialog(rows=ROWS)
    qtbot.addWidget(dialog)

    dialog.row_list.setCurrentRow(1)  # touch P2's row without editing anything
    dialog._commit_current_row()

    name_overrides, program_overrides, _, _, _ = dialog.overrides()
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

    _, program_overrides, _, _, _ = dialog.overrides()
    assert program_overrides == {}


def test_accept_commits_the_currently_selected_row_too(qtbot):
    """overrides() must reflect the LAST row's edits even though the user
    never switched away from it before pressing OK."""
    dialog = InstrumentDialog(rows=ROWS)
    qtbot.addWidget(dialog)
    dialog.row_list.setCurrentRow(1)

    dialog.name_edit.setText("Cello")
    dialog.accept()

    name_overrides, _, _, _, _ = dialog.overrides()
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


# Wishlist #8 follow-up: a percussion part contributes one row for itself
# (name only, no instrument combo) plus one row per distinct item it
# carries, right after it in the list.
PERCUSSION_ROWS = {
    "P1": [
        (("P1", 43), "Closed Hi-Hat", 43),
        (("P1", 39), "Snare", 39),
    ],
}


def test_percussion_items_appear_as_their_own_rows_after_their_part(qtbot):
    dialog = InstrumentDialog(
        rows=ROWS, percussion_part_ids=["P1"], percussion_rows=PERCUSSION_ROWS
    )
    qtbot.addWidget(dialog)

    labels = [dialog.row_list.item(i).text() for i in range(dialog.row_list.count())]
    assert labels == ["Track 1", "Closed Hi-Hat", "Snare", "Cool Violin"]


def test_percussion_part_row_has_no_instrument_combo(qtbot):
    dialog = InstrumentDialog(
        rows=ROWS, percussion_part_ids=["P1"], percussion_rows=PERCUSSION_ROWS
    )
    qtbot.addWidget(dialog)

    dialog.row_list.setCurrentRow(0)  # P1's own row
    assert not dialog.instrument_combo.isEnabled()


def test_percussion_item_row_shows_the_percussion_combo(qtbot):
    dialog = InstrumentDialog(
        rows=ROWS, percussion_part_ids=["P1"], percussion_rows=PERCUSSION_ROWS
    )
    qtbot.addWidget(dialog)

    dialog.row_list.setCurrentRow(1)  # Closed Hi-Hat, declared/sounding key 43
    assert dialog.instrument_combo.isEnabled()
    # The combo shows what key 43 ACTUALLY sounds like per GM ("High Floor
    # Tom"), not the item's own possibly-wrong declared name - the whole
    # point of the feature is surfacing that mismatch.
    assert dialog.instrument_combo.currentText() == "High Floor Tom"
    assert dialog.instrument_combo.findText("Acoustic Grand Piano") == -1, "pitched names must not appear"
    assert dialog.instrument_combo.findText("Acoustic Snare") != -1


def test_editing_a_percussion_item_combo_is_returned_as_a_sound_override(qtbot):
    dialog = InstrumentDialog(
        rows=ROWS, percussion_part_ids=["P1"], percussion_rows=PERCUSSION_ROWS
    )
    qtbot.addWidget(dialog)

    dialog.row_list.setCurrentRow(1)  # Closed Hi-Hat, declared key 43
    dialog.instrument_combo.setCurrentText("Closed Hi-Hat")  # GM's real 42
    dialog.row_list.setCurrentRow(0)  # commits row 1

    _, _, item_name_overrides, item_sound_overrides, _ = dialog.overrides()
    assert item_name_overrides == {}
    assert item_sound_overrides == {("P1", 43): 42}


def test_renaming_a_percussion_item_is_returned_as_a_name_override(qtbot):
    dialog = InstrumentDialog(
        rows=ROWS, percussion_part_ids=["P1"], percussion_rows=PERCUSSION_ROWS
    )
    qtbot.addWidget(dialog)

    dialog.row_list.setCurrentRow(1)
    dialog.name_edit.setText("Renamed Hat")
    dialog.row_list.setCurrentRow(0)

    _, _, item_name_overrides, item_sound_overrides, _ = dialog.overrides()
    assert item_name_overrides == {("P1", 43): "Renamed Hat"}
    assert item_sound_overrides == {}


def test_unresolved_percussion_combo_text_keeps_the_previous_sound(qtbot):
    dialog = InstrumentDialog(
        rows=ROWS, percussion_part_ids=["P1"], percussion_rows=PERCUSSION_ROWS
    )
    qtbot.addWidget(dialog)

    dialog.row_list.setCurrentRow(1)
    dialog.instrument_combo.setCurrentText("not a real drum sound")
    dialog.row_list.setCurrentRow(0)

    _, _, _, item_sound_overrides, _ = dialog.overrides()
    assert item_sound_overrides == {}


def test_auto_correct_checkbox_hidden_without_any_percussion(qtbot):
    dialog = InstrumentDialog(rows=ROWS)
    qtbot.addWidget(dialog)

    assert dialog.layout().indexOf(dialog.auto_correct_checkbox) == -1


def test_auto_correct_checkbox_shown_and_returned_when_percussion_present(qtbot):
    dialog = InstrumentDialog(
        rows=ROWS,
        percussion_part_ids=["P1"],
        percussion_rows=PERCUSSION_ROWS,
        auto_correct_enabled=True,
    )
    qtbot.addWidget(dialog)

    assert dialog.layout().indexOf(dialog.auto_correct_checkbox) != -1
    assert dialog.auto_correct_checkbox.isChecked() is True

    dialog.auto_correct_checkbox.setChecked(False)
    *_, auto_correct_enabled = dialog.overrides()
    assert auto_correct_enabled is False
