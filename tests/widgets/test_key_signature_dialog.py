# tests/widgets/test_key_signature_dialog.py
"""Pure widget-state tests for KeySignatureDialog (S6) - like MixerDialog,
it never touches MusicData itself, so it can be driven directly with no
MainWindow/score involved."""
from models.key_signatures import NO_KEY_OVERRIDE_LABEL, key_override_options
from widgets.key_signature_dialog import KeySignatureDialog


def test_combo_has_31_entries_and_defaults_to_no_override(qtbot):
    dialog = KeySignatureDialog()
    qtbot.addWidget(dialog)

    assert dialog.key_combo.count() == 31
    assert dialog.key_combo.itemText(0) == NO_KEY_OVERRIDE_LABEL
    assert dialog.key_override() == (None, None)


def test_combo_preselects_the_passed_in_current_key(qtbot):
    dialog = KeySignatureDialog(current_key=(-2, "minor"))
    qtbot.addWidget(dialog)

    assert dialog.key_combo.currentText() == "G minor"
    assert dialog.key_override() == (-2, "minor")


def test_key_override_reflects_a_new_selection(qtbot):
    dialog = KeySignatureDialog()
    qtbot.addWidget(dialog)
    options = key_override_options()
    g_major_index = next(i for i, (label, _, _) in enumerate(options) if label == "G major")

    dialog.key_combo.setCurrentIndex(g_major_index)

    assert dialog.key_override() == (1, "major")


def test_accidental_key_names_are_spelled_out_as_words(qtbot):
    """S6 was reworked specifically because "Bb major"/"F# minor" read
    badly under a screen reader - the combo's own entries must use the
    spelled-out form, not a symbol/letter shorthand."""
    dialog = KeySignatureDialog()
    qtbot.addWidget(dialog)
    labels = [dialog.key_combo.itemText(i) for i in range(dialog.key_combo.count())]

    assert "B flat major" in labels
    assert "F sharp minor" in labels
    assert not any("#" in label for label in labels)


def test_ok_and_cancel_set_the_dialog_result(qtbot):
    dialog = KeySignatureDialog()
    qtbot.addWidget(dialog)

    dialog.accept()
    assert dialog.result() == KeySignatureDialog.DialogCode.Accepted

    dialog2 = KeySignatureDialog()
    qtbot.addWidget(dialog2)
    dialog2.reject()
    assert dialog2.result() == KeySignatureDialog.DialogCode.Rejected
