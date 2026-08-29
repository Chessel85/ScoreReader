# tests/test_main_window_attributes.py
"""Reorder Attributes dialog (F2) and Region 4's attribute context menu (Ref 15 AC4). Split from test_main_window.py (S10).
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog

from widgets.attribute_order_dialog import AttributeOrderDialog
from tests.support.main_window_helpers import load_and_wait


# --- F2: Attribute order dialog (Ref 15 AC4) ------------------------------

def test_attribute_order_pairs_scope_to_the_selected_region_2_node(
    window, qtbot, dynamics_articulation_fingering_score
):
    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)
    node = window.region_2.model_manager.node("voice_P1_1_1")

    keys = [key for key, _ in window._attribute_order_pairs_for_node(node)]

    assert "dynamic" in keys
    assert "articulation" in keys
    assert "pluck" not in keys, "pluck only appears on the guitar part, not this piano voice"


def _stage_octave_move_up(window, qtbot):
    """Builds the real Reorder Attributes dialog for voice_P1_1_1, stages a
    Move Up on "octave" (a plain adjacent-item reorder in the dialog's own
    local list - the same thing clicking the button does), and patches
    exec() to return Accepted so window._show_attribute_order_dialog()'s
    post-exec commit (AttributeController.apply_order, via
    dialog.ordered_keys()) runs without a real modal loop - same injection
    convention as GotoMeasureDialog/TempoOffsetDialog. Returns the global
    attribute_order index "octave" should land on: its within-neighbour's
    original slot, since the dialog only ever swaps two adjacent within-
    scope items and set_attribute_order_within writes the new order back
    into exactly those items' original global slots."""
    node = window.region_2.model_manager.node("voice_P1_1_1")
    pairs = window._attribute_order_pairs_for_node(node)
    dialog = AttributeOrderDialog(window, pairs=pairs, scope_description="")

    octave_row = next(
        i for i in range(dialog.attribute_list.count())
        if dialog.attribute_list.item(i).data(Qt.ItemDataRole.UserRole) == "octave"
    )
    assert octave_row > 0, "fixture assumption: something in scope sorts before octave"
    neighbor_key = dialog.attribute_list.item(octave_row - 1).data(Qt.ItemDataRole.UserRole)
    neighbor_global_index = list(window._music_data.attribute_order).index(neighbor_key)

    dialog.attribute_list.setCurrentRow(octave_row)
    dialog._move(-1)

    return dialog, neighbor_global_index


def test_attribute_order_move_updates_music_data_and_restores_prior_focus(
    window, qtbot, dynamics_articulation_fingering_score, monkeypatch
):
    """Move Up is staged locally in the dialog, then committed only once
    exec() returns Accepted (OK) - see _stage_octave_move_up. Focus returns
    to wherever it was when the dialog was invoked (region_2 here, since
    that's how the dialog is normally opened, via _preserving_focus) -
    not hardcoded to any particular region."""
    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)
    dialog, neighbor_global_index = _stage_octave_move_up(window, qtbot)
    window.region_2.setFocus()

    monkeypatch.setattr(dialog, "exec", lambda: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(
        "main_window.AttributeOrderDialog",
        lambda parent, pairs, scope_description: dialog,
    )

    window._show_attribute_order_dialog()

    assert window._music_data.attribute_order[neighbor_global_index] == "octave"
    assert window.focusWidget() is window.region_2


def test_attribute_order_cancel_leaves_the_order_unchanged(
    window, qtbot, dynamics_articulation_fingering_score, monkeypatch
):
    """Cancel (Rejected) must discard the staged move entirely - the whole
    point of switching this dialog from live-apply to OK/Cancel."""
    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)
    original_order = list(window._music_data.attribute_order)
    dialog, _ = _stage_octave_move_up(window, qtbot)

    monkeypatch.setattr(dialog, "exec", lambda: QDialog.DialogCode.Rejected)
    monkeypatch.setattr(
        "main_window.AttributeOrderDialog",
        lambda parent, pairs, scope_description: dialog,
    )

    window._show_attribute_order_dialog()

    assert window._music_data.attribute_order == original_order


def test_attribute_order_persists_per_file_not_across_different_files(
    window, qtbot, dynamics_articulation_fingering_score, minimal_score, monkeypatch
):
    """Ref 27: attribute_order is per-file (a Phase G decision, unlike
    uk_terms which stays a global preference) - reordering one file must
    not leak into a different file that has no saved config of its own, and
    must be there again when that same file is reloaded (load_score_from_file
    saves the outgoing file's config before swapping in the new one)."""
    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)
    dialog, neighbor_global_index = _stage_octave_move_up(window, qtbot)

    monkeypatch.setattr(dialog, "exec", lambda: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(
        "main_window.AttributeOrderDialog",
        lambda parent, pairs, scope_description: dialog,
    )
    window._show_attribute_order_dialog()
    assert window._music_data.attribute_order[neighbor_global_index] == "octave"

    load_and_wait(window, qtbot, minimal_score)
    assert window._music_data.attribute_order[neighbor_global_index] != "octave"

    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)
    assert window._music_data.attribute_order[neighbor_global_index] == "octave"


# --- Reorder Attributes dialog's Add/Remove button (user-requested) -----

def test_order_menu_actions_offers_add_wording_when_not_yet_present(
    window, qtbot, dynamics_articulation_fingering_score
):
    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)
    node = window.region_2.model_manager.node("voice_P1_1_1")

    actions = window.attributes.order_menu_actions(node, "dynamic")

    assert [label for label, _ in actions] == [
        "Add to notes for this voice",
        "Add to notes in same stave",
        "Add to notes in the same part",
        "Add to notes in the whole score",
    ]


def test_order_menu_actions_omits_voice_scope_for_a_stave_level_dialog(
    window, qtbot, dynamics_articulation_fingering_score
):
    """Reported: a stave-level dialog offered "Add to notes for this
    voice" - genuinely ambiguous, since a stave can carry more than one
    voice underneath it. Only scopes at or broader than the dialog's own
    Region 2 node level are unambiguous - it's fine to say "stave", "part"
    or "whole score" from here, just not "voice"."""
    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)
    node = window.region_2.model_manager.node("staff_P1_1")

    actions = window.attributes.order_menu_actions(node, "dynamic")

    assert [label for label, _ in actions] == [
        "Add to notes in same stave",
        "Add to notes in the same part",
        "Add to notes in the whole score",
    ]


def test_order_menu_actions_omits_voice_and_stave_scope_for_a_part_level_dialog(
    window, qtbot, dynamics_articulation_fingering_score
):
    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)
    node = window.region_2.model_manager.node("part_P1")

    actions = window.attributes.order_menu_actions(node, "dynamic")

    assert [label for label, _ in actions] == [
        "Add to notes in the same part",
        "Add to notes in the whole score",
    ]


def test_order_menu_actions_add_actually_applies_and_switches_to_remove_wording(
    window, qtbot, dynamics_articulation_fingering_score
):
    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)
    node = window.region_2.model_manager.node("voice_P1_1_1")

    window.attributes.order_menu_actions(node, "dynamic")[0][1]()  # "Add ... for this voice"

    assert window._music_data.display_attribute_present_for_voice("dynamic", "P1", 1, 1) is True
    actions = window.attributes.order_menu_actions(node, "dynamic")
    assert [label for label, _ in actions] == [
        "Remove for notes in current voice",
        "Remove for notes in current stave",
        "Remove for notes in current part",
        "Remove for notes in the whole score",
    ]


def test_order_menu_actions_remove_actually_applies(
    window, qtbot, dynamics_articulation_fingering_score
):
    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)
    node = window.region_2.model_manager.node("voice_P1_1_1")
    window.attributes.order_menu_actions(node, "dynamic")[0][1]()  # add
    assert window._music_data.display_attribute_present_for_voice("dynamic", "P1", 1, 1) is True

    window.attributes.order_menu_actions(node, "dynamic")[0][1]()  # "Remove ... current voice"

    assert window._music_data.display_attribute_present_for_voice("dynamic", "P1", 1, 1) is False


def test_order_menu_actions_omits_voice_and_stave_scopes_for_a_collapsed_part(
    window, qtbot, midi_test1
):
    """Same reasoning as Region 4's own context menu (MIDI has no real
    stave/voice concept - MusicData.collapsed_part_ids)."""
    load_and_wait(window, qtbot, midi_test1)
    node = window.region_2.model_manager.node("part_P0")

    actions = window.attributes.order_menu_actions(node, "octave")

    assert [label for label, _ in actions] == [
        "Add to notes in the same part",
        "Add to notes in the whole score",
    ]


def test_attribute_order_dialog_add_remove_button_disabled_with_no_selection(window):
    dialog = AttributeOrderDialog(window, pairs=[], scope_description="")

    assert dialog.add_remove_button.isEnabled() is False


def test_attribute_order_dialog_add_remove_button_enabled_once_a_row_is_current(window):
    dialog = AttributeOrderDialog(
        window, pairs=[("dynamic", "dynamic"), ("articulation", "articulation")],
        scope_description="",
    )

    dialog.attribute_list.setCurrentRow(0)

    assert dialog.add_remove_button.isEnabled() is True


def test_attribute_order_dialog_add_remove_button_emits_the_current_rows_key(window, qtbot):
    dialog = AttributeOrderDialog(
        window, pairs=[("dynamic", "dynamic"), ("articulation", "articulation")],
        scope_description="",
    )
    dialog.attribute_list.setCurrentRow(1)
    emitted = []
    dialog.add_remove_requested.connect(emitted.append)

    qtbot.mouseClick(dialog.add_remove_button, Qt.MouseButton.LeftButton)

    assert emitted == ["articulation"]


def test_add_remove_requested_is_wired_to_show_order_menu(
    window, qtbot, dynamics_articulation_fingering_score, monkeypatch
):
    """Simulates clicking the Add/Remove button while the dialog is open,
    the same exec()-patching injection convention used elsewhere in this
    file - fakes exec() to emit the signal and return, since the real
    button click would open a blocking QMenu that show_order_menu itself is
    responsible for (untestable via exec() patching, per
    AttributeController.show_menu's own docstring). Unlike Up/Down,
    add_remove_requested is still live - it isn't part of what OK/Cancel
    stages, so no dialog.ordered_keys()/apply_order commit is involved
    here."""
    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)
    node = window.region_2.model_manager.node("voice_P1_1_1")

    dialog = AttributeOrderDialog(window, pairs=[], scope_description="")
    calls = []
    monkeypatch.setattr(
        window.attributes, "show_order_menu",
        lambda d, n, attribute_key: calls.append((d, n, attribute_key)),
    )

    def fake_exec():
        dialog.add_remove_requested.emit("dynamic")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(dialog, "exec", fake_exec)
    monkeypatch.setattr(
        "main_window.AttributeOrderDialog",
        lambda parent, pairs, scope_description: dialog,
    )
    monkeypatch.setattr(window.attributes, "scope_node", lambda: node)

    window._show_attribute_order_dialog()

    assert calls == [(dialog, node, "dynamic")]


def _region_3_labels(window):
    return [window.region_3.item(i).text() for i in range(window.region_3.count())]


def test_region_4_attribute_menu_add_updates_region_3_without_reauditioning(
    window, qtbot, null_synth, minimal_score
):
    """Ref 15 AC4. minimal_score's single note (C, octave 4) has no
    string/fret, so Region 4 row 1 is always "octave" - step is row 0."""
    load_and_wait(window, qtbot, minimal_score)
    assert _region_3_labels(window) == ["C"]

    actions = window._region_4_attribute_menu_actions(1)
    # D-15: "stave" is NOT translated by F4's uk_terms toggle - deliberate
    # decision, see tasks.txt.
    assert [label for label, _ in actions] == [
        "Add to notes for this voice",
        "Add to notes in same stave",
        "Add to notes in the same part",
        "Add to notes in the whole score",
    ]

    null_synth.played.clear()
    actions[0][1]()  # "Add to notes for this voice"

    assert _region_3_labels(window) == ["C, octave 4"]
    assert null_synth.played == [], "an attribute toggle must not re-audition the note"
    assert len(window.region_3.selectedIndexes()) == 1, "selection must be preserved"
    assert window.region_4.count() > 0, "Region 4 refreshed alongside Region 3"


def test_region_4_attribute_menu_first_action_is_add_to_this_voice(
    window, qtbot, null_synth, minimal_score
):
    """Locks in menu item ordering (via _build_region_4_attribute_menu,
    which stops short of the real exec() call - QMenu.exec cannot be
    monkeypatched around, see that method's docstring). An earlier attempt
    pre-highlighted this first action via exec()'s `at` parameter to help
    screen readers, but that was reverted (live-tested: it didn't produce a
    real NVDA announcement) - see show_region_4_attribute_menu."""
    load_and_wait(window, qtbot, minimal_score)

    menu = window._build_region_4_attribute_menu(1)

    assert menu is not None
    assert menu.actions()[0].text() == "Add to notes for this voice"


def test_restore_region_4_focus_after_menu_returns_to_the_same_row(
    window, qtbot, null_synth, minimal_score
):
    """Originally a live-tested bug: selecting a menu action rebuilds Region
    4's rows (via _apply_display_attribute_change -> _refresh_region_3_labels
    -> _on_region_3_selection_changed -> refresh_list) while the menu's own
    exec() is still running (QAction.triggered fires before exec() returns),
    and that rebuild used to reset the list's current row to 0 - NVDA kept
    reporting the stale menu item, and the next Down landed on row 0 ("step")
    instead of back where the menu was opened. RegionPropertyListWidget.
    refresh_list itself now preserves the current row across a rebuild (F4's
    Region 1/4 position-persistence fix), so that half of the bug is fixed
    at the source - the current row is already correct by the time
    _restore_region_4_focus_after_menu runs. What that method still owns is
    giving actual WIDGET FOCUS back: exec() steals focus to the menu while
    it's open, and nothing else returns it to Region 4 once the menu closes."""
    load_and_wait(window, qtbot, minimal_score)

    window.region_4.setCurrentRow(1)  # octave row
    selected_notes = window._music_data.notes_for_indices([0])
    window._apply_display_attribute_change("octave", "voice", selected_notes, add=True)
    assert window.region_4.currentRow() == 1, (
        "refresh_list already preserved the row through the rebuild"
    )

    window._restore_region_4_focus_after_menu(1)
    QApplication.processEvents()

    assert window.region_4.currentRow() == 1
    assert window.focusWidget() is window.region_4


def test_region_4_attribute_menu_callback_survives_qactions_checked_argument(
    window, qtbot, null_synth, minimal_score
):
    """Live-tested bug: QAction.triggered always calls a connected slot with
    one positional bool ("checked"). The callback's scope=scope default-arg
    lambda swallowed that bool into scope itself (Qt/PySide calls a
    connected callable with one positional arg whenever it accepts one),
    so every real menu selection raised
    ValueError("Unknown display-attribute scope: False") - invisible to the
    zero-arg actions[0][1]() calls the other tests here use, since those
    never exercised the argument QAction actually passes."""
    load_and_wait(window, qtbot, minimal_score)

    actions = window._region_4_attribute_menu_actions(1)  # row 1 = octave
    actions[0][1](False)  # exactly how QAction.triggered(bool) calls it

    assert _region_3_labels(window) == ["C, octave 4"]


def test_region_4_attribute_menu_omits_voice_and_stave_scopes_for_a_collapsed_part(
    window, qtbot, null_synth, midi_test1
):
    """Reported: a part with no real stave/voice concept underneath it (a
    MIDI track here; also a pure Ultimate Guitar import or a MusicXML
    score's synthetic Chords/Lyrics parts - MusicData.collapsed_part_ids,
    the same check Region 2 uses) offered "current voice"/"current stave"
    scopes that acted on exactly the same notes as "current part" - real
    but redundant menu clutter with nothing behind it. Those two scopes are
    dropped for such a part."""
    load_and_wait(window, qtbot, midi_test1)

    actions = window._region_4_attribute_menu_actions(1)  # row 1 = octave

    assert [label for label, _ in actions] == [
        "Add to notes in the same part",
        "Add to notes in the whole score",
    ]


def test_region_4_attribute_menu_switches_to_remove_once_present(
    window, qtbot, null_synth, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    window._region_4_attribute_menu_actions(1)[0][1]()  # add octave to the voice
    assert _region_3_labels(window) == ["C, octave 4"]

    actions = window._region_4_attribute_menu_actions(1)
    assert [label for label, _ in actions] == [
        "Remove for notes in current voice",
        "Remove for notes in current stave",
        "Remove for notes in current part",
        "Remove for notes in the whole score",
    ]

    actions[0][1]()  # "Remove for notes in current voice"

    assert _region_3_labels(window) == ["C"]


def test_region_4_attribute_menu_stave_scope_fans_out_to_every_voice_on_that_stave(
    window, qtbot, null_synth, score_duet
):
    """Chessel Duet's Piano staff 2 carries two real voices (5 and 6) - a
    genuine multi-voice stave, unlike a same-part/same-staff single-voice
    fixture where stave scope would be indistinguishable from voice scope.

    Notes are ordered highest pitch first within each part: P1 staff 1
    voice 1 G5(79), P1 staff 2 voice 6 G3(55), P1 staff 2 voice 5 D3(50),
    then P2 staff 1 voice 1 D4(62), P2 staff 1 voice 2 D3(50)."""
    load_and_wait(window, qtbot, score_duet)
    assert _region_3_labels(window) == ["G", "G", "D", "D", "D"]

    window.region_3.clearSelection()
    window.region_3.setCurrentRow(1)
    window.region_3.item(1).setSelected(True)  # row 1: P1 staff 2 voice 6, "G"
    assert [i.row() for i in window.region_3.selectedIndexes()] == [1]

    actions = window._region_4_attribute_menu_actions(1)  # row 1 = octave
    stave_add = next(cb for label, cb in actions if label == "Add to notes in same stave")
    stave_add()

    labels = _region_3_labels(window)
    assert labels[0] == "G", "P1 staff 1 voice 1 untouched"
    assert labels[1].startswith("G, octave "), "P1 staff 2 voice 6 - the note the menu was opened on"
    assert labels[2].startswith("D, octave "), "P1 staff 2 voice 5 - same stave, different voice"
    assert labels[3] == "D" and labels[4] == "D", "P2's notes untouched"


def test_region_4_attribute_menu_score_scope_fans_out_to_every_part(
    window, qtbot, null_synth, score_duet
):
    load_and_wait(window, qtbot, score_duet)

    window.region_3.clearSelection()
    window.region_3.setCurrentRow(1)
    window.region_3.item(1).setSelected(True)  # row 1: P1 staff 2 voice 5

    actions = window._region_4_attribute_menu_actions(1)  # row 1 = octave
    score_add = next(cb for label, cb in actions if label == "Add to notes in the whole score")
    score_add()

    labels = _region_3_labels(window)
    assert all("octave " in label for label in labels), "every voice in the score, including P2, is affected"
