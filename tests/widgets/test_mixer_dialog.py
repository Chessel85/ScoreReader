# tests/widgets/test_mixer_dialog.py
"""Pure widget-state tests for MixerDialog (wishlist #4) - it never touches
MusicData/PlaybackController/SynthEngine itself, only emits signals, so it
can be driven directly with no MainWindow/score involved."""
from PySide6.QtCore import Qt

from widgets.mixer_dialog import MixerDialog

ROWS = [
    ("P1", "Piano", 79, 0),
    ("P2", "Classical Guitar", 100, 20),
    ("click", "Metronome", 100, 100),
    ("announcer", "Position Announcer", 100, -100),
]


def test_populates_one_row_per_entry_and_selects_the_first(qtbot):
    dialog = MixerDialog(rows=ROWS)
    qtbot.addWidget(dialog)

    assert dialog.row_list.count() == 4
    assert [dialog.row_list.item(i).text() for i in range(4)] == [
        "Piano", "Classical Guitar", "Metronome", "Position Announcer",
    ]
    assert dialog.row_list.currentRow() == 0
    assert dialog.volume_spin.value() == 79
    assert dialog.pan_spin.value() == 0


def test_changing_the_selected_row_updates_the_spin_boxes(qtbot):
    dialog = MixerDialog(rows=ROWS)
    qtbot.addWidget(dialog)

    dialog.row_list.setCurrentRow(1)

    assert dialog.volume_spin.value() == 100
    assert dialog.pan_spin.value() == 20


def test_changing_the_selected_row_does_not_emit_change_signals(qtbot):
    """Reflecting a newly-selected row's own stored values must not be
    mistaken for the user editing that row - see MixerDialog._on_row_changed."""
    dialog = MixerDialog(rows=ROWS)
    qtbot.addWidget(dialog)
    fired = []
    dialog.volume_changed.connect(lambda k, v: fired.append(("volume", k, v)))
    dialog.pan_changed.connect(lambda k, v: fired.append(("pan", k, v)))

    dialog.row_list.setCurrentRow(1)
    dialog.row_list.setCurrentRow(2)

    assert fired == []


def test_editing_volume_emits_volume_changed_for_the_selected_row(qtbot):
    dialog = MixerDialog(rows=ROWS)
    qtbot.addWidget(dialog)
    dialog.row_list.setCurrentRow(1)
    fired = []
    dialog.volume_changed.connect(lambda k, v: fired.append((k, v)))

    dialog.volume_spin.setValue(42)

    assert fired == [("P2", 42)]


def test_editing_pan_emits_pan_changed_for_the_selected_row(qtbot):
    dialog = MixerDialog(rows=ROWS)
    qtbot.addWidget(dialog)
    dialog.row_list.setCurrentRow(0)
    fired = []
    dialog.pan_changed.connect(lambda k, v: fired.append((k, v)))

    dialog.pan_spin.setValue(-55)

    assert fired == [("P1", -55)]


def test_preview_button_emits_preview_requested(qtbot):
    dialog = MixerDialog(rows=ROWS)
    qtbot.addWidget(dialog)
    fired = []
    dialog.preview_requested.connect(lambda: fired.append(True))

    dialog.preview_button.click()

    assert fired == [True]


def test_preview_button_mnemonic_is_w_for_alt_plus_w():
    """Alt+W, not Alt+P - a real reported bug: an earlier version used
    "&Preview" (Alt+P), which collided with the Pan field's own "&Pan:"
    mnemonic (also Alt+P), so Alt+P didn't reliably reach the Preview
    button. The visible label spells the shortcut out directly, per the
    user's own request."""
    dialog = MixerDialog(rows=ROWS)

    assert dialog.preview_button.text() == "Preview Alt+&W"


def test_home_and_end_jump_the_spin_boxes_to_their_extremes(qtbot):
    """A plain QSpinBox only uses Home/End to move the text cursor within
    the typed digits - _RangeSpinBox repurposes them to jump straight to an
    extreme. Home goes to the HIGHEST number each control has (matching the
    user's own spec: pan's Home is +100% full right, volume's Home is 100%
    full/default), End to the lowest, and Insert resets to the control's
    own reset_value (0/centre for pan, 50 for volume - the user's own
    preferred "put it somewhere reasonable" value, not the true 100%
    default)."""
    dialog = MixerDialog(rows=ROWS)
    qtbot.addWidget(dialog)
    dialog.row_list.setCurrentRow(0)

    dialog.pan_spin.setFocus()
    qtbot.keyClick(dialog.pan_spin, Qt.Key.Key_Home)
    assert dialog.pan_spin.value() == 100
    qtbot.keyClick(dialog.pan_spin, Qt.Key.Key_End)
    assert dialog.pan_spin.value() == -100
    qtbot.keyClick(dialog.pan_spin, Qt.Key.Key_Insert)
    assert dialog.pan_spin.value() == 0

    dialog.volume_spin.setFocus()
    qtbot.keyClick(dialog.volume_spin, Qt.Key.Key_Home)
    assert dialog.volume_spin.value() == 100
    qtbot.keyClick(dialog.volume_spin, Qt.Key.Key_End)
    assert dialog.volume_spin.value() == 0
    dialog.volume_spin.setValue(42)
    qtbot.keyClick(dialog.volume_spin, Qt.Key.Key_Insert)
    assert dialog.volume_spin.value() == 50


def test_ok_and_cancel_set_the_dialog_result(qtbot):
    dialog = MixerDialog(rows=ROWS)
    qtbot.addWidget(dialog)

    dialog.accept()
    assert dialog.result() == MixerDialog.DialogCode.Accepted

    dialog2 = MixerDialog(rows=ROWS)
    qtbot.addWidget(dialog2)
    dialog2.reject()
    assert dialog2.result() == MixerDialog.DialogCode.Rejected


def test_empty_rows_disables_the_controls(qtbot):
    dialog = MixerDialog(rows=[])
    qtbot.addWidget(dialog)

    assert dialog.row_list.count() == 0
    assert not dialog.volume_spin.isEnabled()
    assert not dialog.pan_spin.isEnabled()
    assert not dialog.preview_button.isEnabled()
