# tests/test_main_window_find.py
"""Find dialog (Ctrl+F) and next/previous occurrence cycling (Alt+Right / Alt+Left). Split from test_main_window.py (S10).
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from models.find_target import FindTarget
from widgets.find_dialog import FindDialog
from tests.support.main_window_helpers import _focus, _show, load_and_wait


def test_section_marking_row_drops_the_marking_prefix(qtbot):
    """A song section is the one marking kind users name directly, so its
    row reads "Section", not "Marking: Section" like every other kind."""
    section = FindTarget("marking", "section", "Section")
    repeat = FindTarget("marking", "repeat_start", "Repeat start")
    dialog = FindDialog(targets=[section, repeat], counts={section: 3, repeat: 1})
    qtbot.addWidget(dialog)

    labels = [dialog.target_list.item(i).text() for i in range(dialog.target_list.count())]
    assert labels == ["Section, 3 occurrences", "Marking: Repeat start, 1 occurrence"]


# --- Find (Ctrl+F / Alt+Right / Alt+Left) -------------------------------

def _select_find_target(dialog, key: str, category: str = "attribute"):
    for row in range(dialog.target_list.count()):
        item = dialog.target_list.item(row)
        target = item.data(Qt.ItemDataRole.UserRole)
        if target.category == category and target.key == key:
            dialog.target_list.setCurrentItem(item)
            return
    raise AssertionError(f"no {category} target {key!r} in the Find dialog's list")


def test_find_dialog_lists_attributes_and_markings_by_category_and_label(
    window, qtbot, dynamics_articulation_fingering_score
):
    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)

    targets_with_counts = window._music_data.available_find_targets_with_counts()
    dialog = FindDialog(
        window,
        targets=[t for t, _ in targets_with_counts],
        counts={t: c for t, c in targets_with_counts},
    )
    labels = [dialog.target_list.item(i).text() for i in range(dialog.target_list.count())]

    # articulation is value-expanded (D2): an "(any)" row plus one row per
    # distinct value, each carrying its occurrence count (D13).
    assert "Attribute: articulation (any), 2 occurrences" in labels
    assert "Attribute: articulation: staccato, 1 occurrence" in labels
    assert "Attribute: articulation: trill, 1 occurrence" in labels
    assert "Attribute: dynamic (any), 1 occurrence" in labels
    # fingering is NOT value-expanded - one plain row, no "(any)" suffix.
    assert any(label.startswith("Attribute: fingering,") for label in labels)
    assert not any("Attribute: fingering:" in label for label in labels)
    assert not any("Attribute: step" in label for label in labels), "core keys must not be offered"


def test_find_dialog_ok_arms_target_and_jumps_to_first_occurrence_at_or_after_cursor(
    window, qtbot, dynamics_articulation_fingering_score, monkeypatch
):
    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)
    assert window._music_data.get_current_slice().beat_position == 1.0

    dialog = FindDialog(window, targets=window._music_data.available_find_targets())
    _select_find_target(dialog, "articulation")
    monkeypatch.setattr(dialog, "exec", lambda: FindDialog.DialogCode.Accepted)
    monkeypatch.setattr("main_window.FindDialog", lambda parent, targets=None, counts=None: dialog)

    window._show_find_dialog()

    assert window._music_data.get_current_slice().beat_position == 2.0  # first staccato/trill note
    assert window.navigation.current_find_target.key == "articulation"
    assert window.focusWidget() is window.region_3


def test_find_dialog_cancelled_does_not_move_or_arm_a_target(
    window, qtbot, dynamics_articulation_fingering_score, monkeypatch
):
    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)

    dialog = FindDialog(window, targets=window._music_data.available_find_targets())
    _select_find_target(dialog, "articulation")
    monkeypatch.setattr(dialog, "exec", lambda: FindDialog.DialogCode.Rejected)
    monkeypatch.setattr("main_window.FindDialog", lambda parent, targets=None, counts=None: dialog)

    window._show_find_dialog()

    assert window._music_data.active_event_index == 0
    assert window.navigation.current_find_target is None


def test_ctrl_f_shortcut_opens_the_find_dialog(window, qtbot, null_synth, minimal_score, monkeypatch):
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    _focus(window.region_1)
    opened = []
    monkeypatch.setattr(
        "main_window.FindDialog",
        lambda parent, targets=None, counts=None: type(
            "FakeDialog", (), {"exec": lambda self: opened.append(True) or QDialog.DialogCode.Rejected}
        )(),
    )

    qtbot.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)

    assert opened == [True]


def test_find_action_lives_only_in_the_navigation_menu(window):
    """User-requested 2026-08-26: Find... used to be the SAME QAction added
    to both Edit and Navigation - "weird having find in the edit menu and
    the find prev and find next in navigation" - so it now lives only in
    Navigation, immediately before Find Next/Previous. This also fixes a
    real bug: a QAction added to two different QMenus left NVDA silently
    announcing nothing when arrowed onto in whichever menu built second
    (Qt's accessibility bridge doesn't reliably expose one QAction's name
    across two separate QMenu parents).

    Top-level menu QActions (unlike the ones in Actions/menu_builder.py)
    are never held by any persistent Python attribute - menuBar().actions()
    hands back freshly (re)wrapped objects each call, and per this file's
    existing "Actions are held as attributes, never locals" gotcha,
    letting them go out of scope before use can leave even the still-
    parented C++ QMenu reading as deleted. Named locals kept alive for the
    rest of the function, not a throwaway generator/list comprehension."""
    top_level_actions = window.menuBar().actions()
    edit_action = [a for a in top_level_actions if a.text() == "&Edit"][0]
    navigation_action = [a for a in top_level_actions if a.text() == "&Navigation"][0]
    edit_menu = edit_action.menu()
    navigation_menu = navigation_action.menu()

    assert window.find_action not in edit_menu.actions()
    assert window.find_action in navigation_menu.actions()
    assert window.find_action.shortcut().toString() == "Ctrl+F"

    find_index = navigation_menu.actions().index(window.find_action)
    assert navigation_menu.actions()[find_index + 1] is window.find_next_action
    assert navigation_menu.actions()[find_index + 2] is window.find_previous_action


def test_alt_right_and_alt_left_cycle_through_occurrences_of_the_armed_target(
    window, qtbot, dynamics_articulation_fingering_score
):
    """Cycling itself is exercised directly through MainWindow.find_next/
    find_previous (the QAction slots) rather than via synthetic Alt+Right/
    Alt+Left key events - see test_alt_right_shortcut_is_wired_to_find_next
    below for proof the real shortcut reaches those same methods; driving
    two real WindowShortcut-context key events back to back onto an
    offscreen, possibly-not-yet-torn-down-from-the-previous-test top-level
    window is flaky in this harness (Qt's ambiguous-shortcut resolution),
    independent of whether the feature itself works."""
    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)
    target = next(
        t for t in window._music_data.available_find_targets()
        if t.category == "attribute" and t.key == "articulation"
    )
    window.navigation.arm_find_target(target)

    window.find_next()
    assert window._music_data.get_current_slice().beat_position == 2.0  # staccato

    window.find_next()
    assert window._music_data.get_current_slice().beat_position == 3.0  # trill

    window.find_previous()
    assert window._music_data.get_current_slice().beat_position == 2.0  # back to staccato


def test_region_4_keeps_attribute_key_focus_across_a_find_jump(
    window, qtbot, dynamics_articulation_fingering_score
):
    """Reported: after Alt+Right, Region 4 focus jumped to the top item
    instead of staying on the same kind of attribute the user was reading.
    The re-anchoring algorithm itself is covered directly by
    tests/widgets/test_region4_list_widget.py; this proves RegionPresenter
    really routes MusicData.get_region_4_rows_for_indices into
    Region4ListWidget.refresh_list end to end, with no mocks."""
    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)
    target = next(
        t for t in window._music_data.available_find_targets()
        if t.category == "attribute" and t.key == "articulation"
    )
    window.navigation.arm_find_target(target)
    window.find_next()  # beat 2: D5 alone, articulation=staccato
    articulation_row = window.region_4.count() - 1
    assert window.region_4.item(articulation_row).text() == "articulation: staccato"
    window.region_4.setCurrentRow(articulation_row)

    window.find_next()  # beat 3: F5 (articulation=trill) + G4 (nothing extra)

    assert window.region_4.item(window.region_4.currentRow()).text() == "note 1 articulation: trill"
    assert window.region_4.item(window.region_4.currentRow()).data(Qt.ItemDataRole.UserRole) == "articulation"


def test_find_next_before_find_has_been_used_plays_the_boundary_cue_and_does_not_move(
    window, qtbot, null_synth, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    null_synth.played.clear()

    window.find_next()

    assert window._music_data.active_event_index == 0
    assert null_synth.last_played["channel"] == window.BOUNDARY_CHANNEL


def test_find_next_does_not_play_the_boundary_cue_on_an_ordinary_hop(
    window, qtbot, null_synth, dynamics_articulation_fingering_score
):
    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)
    target = next(
        t for t in window._music_data.available_find_targets()
        if t.category == "attribute" and t.key == "articulation"
    )
    window.navigation.arm_find_target(target)
    null_synth.played.clear()

    window.find_next()  # beat 2 (staccato) - the nearest one ahead, no wrap

    assert window._music_data.get_current_slice().beat_position == 2.0
    assert all(p["channel"] != window.BOUNDARY_CHANNEL for p in null_synth.played)


def test_find_next_plays_the_boundary_cue_when_it_wraps_back_to_the_first_occurrence(
    window, qtbot, null_synth, dynamics_articulation_fingering_score
):
    """Reported: wrapping around silently gave no audible sign it had
    happened, indistinguishable from an ordinary short hop."""
    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)
    target = next(
        t for t in window._music_data.available_find_targets()
        if t.category == "attribute" and t.key == "articulation"
    )
    window.navigation.arm_find_target(target)
    window.find_next()  # beat 2 (staccato)
    window.find_next()  # beat 3 (trill) - the last occurrence
    null_synth.played.clear()

    window.find_next()  # wraps back to beat 2 (staccato)

    assert window._music_data.get_current_slice().beat_position == 2.0
    assert null_synth.last_played["channel"] == window.BOUNDARY_CHANNEL, (
        "the cue must be the LAST thing heard - the destination note sounds "
        "first, same ordering already used for Region 5's own change cue"
    )


def test_find_previous_plays_the_boundary_cue_when_it_wraps_back_to_the_last_occurrence(
    window, qtbot, null_synth, dynamics_articulation_fingering_score
):
    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)
    target = next(
        t for t in window._music_data.available_find_targets()
        if t.category == "attribute" and t.key == "articulation"
    )
    window.navigation.arm_find_target(target)
    null_synth.played.clear()

    window.find_previous()  # nothing behind the cursor - wraps to beat 3 (trill)

    assert window._music_data.get_current_slice().beat_position == 3.0
    assert null_synth.last_played["channel"] == window.BOUNDARY_CHANNEL


def test_find_next_plays_the_boundary_cue_for_a_target_with_a_single_occurrence(
    window, qtbot, null_synth, dynamics_articulation_fingering_score
):
    """The cursor starts exactly on the one and only occurrence of
    "dynamic" (the beat-1 chord) - find_next has nowhere else to go, so
    every press "wraps" back to the same spot and should still cue that."""
    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)
    target = next(
        t for t in window._music_data.available_find_targets()
        if t.category == "attribute" and t.key == "dynamic"
    )
    window.navigation.arm_find_target(target)
    assert window._music_data.active_event_index == 0
    null_synth.played.clear()

    window.find_next()

    assert window._music_data.active_event_index == 0
    assert null_synth.last_played["channel"] == window.BOUNDARY_CHANNEL


def test_alt_right_shortcut_is_wired_to_find_next(window, qtbot, minimal_score, monkeypatch):
    """Proves the real Alt+Right key event reaches NavigationController.
    find_next, without needing find_next's own cycling logic to run (that's
    covered directly above) - same "spy on what the wiring calls" reasoning
    as test_ctrl_f_shortcut_opens_the_find_dialog. Patches the
    NavigationController instance, not window.find_next itself: the QAction
    was connected to the bound MainWindow.find_next captured at menu-build
    time, but that method's own body still looks up self.navigation.
    find_next fresh on every call, so a patch there is what the connected
    slot will actually see."""
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    _focus(window.region_1)
    calls = []
    monkeypatch.setattr(window.navigation, "find_next", lambda: calls.append(True))

    qtbot.keyClick(window, Qt.Key.Key_Right, Qt.KeyboardModifier.AltModifier)

    assert calls == [True]


def test_alt_left_shortcut_is_wired_to_find_previous(window, qtbot, minimal_score, monkeypatch):
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    _focus(window.region_1)
    calls = []
    monkeypatch.setattr(window.navigation, "find_previous", lambda: calls.append(True))

    qtbot.keyClick(window, Qt.Key.Key_Left, Qt.KeyboardModifier.AltModifier)

    assert calls == [True]


def test_find_dialog_filter_box_narrows_the_list_by_label_text_only(
    window, qtbot, dynamics_articulation_fingering_score
):
    """D11: typing in the Filter box hides non-matching rows; it matches the
    label text, never the trailing occurrence-count digits."""
    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)
    twc = window._music_data.available_find_targets_with_counts()
    dialog = FindDialog(window, targets=[t for t, _ in twc], counts={t: c for t, c in twc})
    qtbot.addWidget(dialog)

    def visible_texts():
        return [
            dialog.target_list.item(i).text()
            for i in range(dialog.target_list.count())
            if not dialog.target_list.item(i).isHidden()
        ]

    dialog.filter_edit.setText("staccato")
    assert visible_texts() == ["Attribute: articulation: staccato, 1 occurrence"]

    # A digit that appears only in the occurrence count must not match.
    dialog.filter_edit.setText("1 occurrence")
    assert visible_texts() == []

    dialog.filter_edit.setText("")
    assert len(visible_texts()) == dialog.target_list.count()


def test_find_dialog_shows_with_focus_on_the_list(window, qtbot, dynamics_articulation_fingering_score):
    """Same focus-on-show reasoning as GotoMeasureDialog: setFocus() before
    the native window exists never reaches NVDA."""
    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)
    dialog = FindDialog(window, targets=window._music_data.available_find_targets())
    qtbot.addWidget(dialog)

    dialog.show()
    qtbot.waitExposed(dialog)
    qtbot.waitUntil(lambda: dialog.focusWidget() is dialog.target_list)

    assert dialog.focusWidget() is dialog.target_list
