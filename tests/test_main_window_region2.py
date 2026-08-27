# tests/test_main_window_region2.py
"""Region 2 mute/solo (F8/F9/Alt+F8/Alt+F9) and collapse/expand behaviour. Split from test_main_window.py (S10).
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication

from tests.support.main_window_helpers import _focus, _show, load_and_wait


# --- Playback menu: mute/solo (F8/F9/Alt+F8/Alt+F9) -----------------------

def test_playback_menu_shortcuts(window):
    assert window.play_stop_action.shortcut() == QKeySequence(Qt.Key.Key_Space)
    assert window.pause_resume_action.shortcut() == QKeySequence("Ctrl+Space")
    assert window.pause_resume_action.text() == "Pa&use", (
        "user-requested 2026-08-26: this shortcut only ever pauses - "
        "resuming is Space, not Ctrl+Space again - so 'Resume' in its own "
        "name was misleading"
    )
    # Enter/Return is now a real global shortcut (user-requested
    # 2026-08-26), enabled everywhere except the Note region - see
    # test_preview_action_is_enabled_everywhere_except_the_note_region.
    assert window.preview_action.shortcut() == QKeySequence(Qt.Key.Key_Enter)
    assert QKeySequence(Qt.Key.Key_Return) in window.preview_action.shortcuts()
    assert window.mute_action.shortcut() == QKeySequence(Qt.Key.Key_F8)
    assert window.solo_action.shortcut() == QKeySequence(Qt.Key.Key_F9)
    assert window.unmute_all_action.shortcut() == QKeySequence("Alt+F8")
    assert window.unsolo_all_action.shortcut() == QKeySequence("Alt+F9")
    assert window.mixer_action.shortcut() == QKeySequence("Ctrl+Shift+X")


def test_mute_solo_actions_are_only_enabled_with_region_2_focused(
    window, qtbot, minimal_score
):
    """Greyed out everywhere except Region 2, same "only meaningful with a
    particular region focused" pattern as Move to First/Last Note."""
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)

    for region in (window.region_1, window.region_3, window.region_4):
        _focus(region)
        assert not window.mute_action.isEnabled()
        assert not window.solo_action.isEnabled()
        assert not window.unmute_all_action.isEnabled()
        assert not window.unsolo_all_action.isEnabled()

    _focus(window.region_2)
    assert window.mute_action.isEnabled()
    assert window.solo_action.isEnabled()
    assert window.unmute_all_action.isEnabled()
    assert window.unsolo_all_action.isEnabled()


def test_mute_solo_actions_stay_enabled_while_the_menu_bar_itself_has_focus(
    window, qtbot, minimal_score
):
    """Reported bug, live-tested: opening the Playback menu (Alt or mouse)
    moves real Qt keyboard focus onto the QMenuBar/QMenu while it's open,
    which used to flip these actions to disabled via the very same
    focus-tracking path - so Mute/Solo/Unmute All/Unsolo All looked
    unavailable right when the user opened the menu to use them, even
    though Region 2 genuinely had focus a moment before."""
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    _focus(window.region_2)
    assert window.mute_action.isEnabled()

    window.menuBar().setFocus()
    QApplication.processEvents()

    assert window.mute_action.isEnabled()
    assert window.solo_action.isEnabled()
    assert window.unmute_all_action.isEnabled()
    assert window.unsolo_all_action.isEnabled()


def test_f9_solos_the_focused_row_and_overrides_a_muted_ancestor(
    window, qtbot, flute_crotchets_viola_semibreves_score
):
    load_and_wait(window, qtbot, flute_crotchets_viola_semibreves_score)
    _show(window, qtbot)
    _focus(window.region_2)

    window.region_2.select_node("part_P1")  # flute
    qtbot.keyClick(window.region_2, Qt.Key.Key_F8)  # mute the flute part
    assert window._music_data.active_voice_filter == {("P2", 1, 1)}

    window.region_2.select_node("voice_P1_1_1")
    qtbot.keyClick(window.region_2, Qt.Key.Key_F9)  # solo the muted flute's own voice

    assert window._music_data.active_voice_filter == {("P1", 1, 1)}, (
        "a soloed voice must be heard even though its part is muted"
    )
    assert window.region_2.model_manager.node("part_P1").muted is True, (
        "the ancestor's own mute flag is untouched by soloing a descendant"
    )
    assert window.region_2.model_manager.node("voice_P1_1_1").soloed is True


def test_alt_f8_unmutes_every_row_and_leaves_solo_state_alone(
    window, qtbot, flute_crotchets_viola_semibreves_score
):
    load_and_wait(window, qtbot, flute_crotchets_viola_semibreves_score)
    _show(window, qtbot)
    _focus(window.region_2)

    window.region_2.select_node("part_P1")
    qtbot.keyClick(window.region_2, Qt.Key.Key_F8)  # flute muted
    window.region_2.select_node("part_P2")
    qtbot.keyClick(window.region_2, Qt.Key.Key_F9)  # viola soloed

    qtbot.keyClick(window, Qt.Key.Key_F8, Qt.KeyboardModifier.AltModifier)

    assert window.region_2.model_manager.node("part_P1").muted is False
    assert window.region_2.model_manager.node("part_P2").soloed is True, (
        "Unmute All must not also clear solo state"
    )


def test_alt_f9_unsolos_every_row_and_leaves_mute_state_alone(
    window, qtbot, flute_crotchets_viola_semibreves_score
):
    load_and_wait(window, qtbot, flute_crotchets_viola_semibreves_score)
    _show(window, qtbot)
    _focus(window.region_2)

    window.region_2.select_node("part_P1")
    qtbot.keyClick(window.region_2, Qt.Key.Key_F8)  # flute muted
    window.region_2.select_node("part_P2")
    qtbot.keyClick(window.region_2, Qt.Key.Key_F9)  # viola soloed

    qtbot.keyClick(window, Qt.Key.Key_F9, Qt.KeyboardModifier.AltModifier)

    assert window.region_2.model_manager.node("part_P2").soloed is False
    assert window.region_2.model_manager.node("part_P1").muted is True, (
        "Unsolo All must not also clear mute state"
    )
    assert window._music_data.active_voice_filter == {("P2", 1, 1)}, (
        "with nothing soloed anymore, the flute's own mute state applies again"
    )


def test_muting_a_part_keeps_its_staff_and_voice_rows_visible(
    window, qtbot, score_duet
):
    """Region 2 is a real tree now - unlike the old on/off toggle, mute no
    longer hides descendant rows, since a voice must stay reachable to be
    individually soloed even while its part is muted. Expand the part
    first (nodes start collapsed) so there are staff/voice rows to check
    at all."""
    load_and_wait(window, qtbot, score_duet)
    _show(window, qtbot)
    _focus(window.region_2)

    part_id = window.region_2.model_manager.roots[0].node_id
    window.region_2.select_node(part_id)
    qtbot.keyClick(window.region_2, Qt.Key.Key_Right)
    before = len(window.region_2.visible_item_texts())
    assert before > 1, "the part must have expanded to reveal at least one staff row"

    window.region_2.select_node(part_id)
    qtbot.keyClick(window.region_2, Qt.Key.Key_F8)

    assert len(window.region_2.visible_item_texts()) == before


def test_region_2_starts_fully_collapsed(window, qtbot, score_duet):
    """The user's own confirmed preference (revising the original spec):
    every part row shows on load, but with no staff/voice rows built
    underneath until the user expands one - not "fully expanded"."""
    load_and_wait(window, qtbot, score_duet)

    r2 = window.region_2
    assert r2.topLevelItemCount() == len(window._music_data.parts_info)
    for i in range(r2.topLevelItemCount()):
        item = r2.topLevelItem(i)
        assert item.childCount() == 0
        assert item.childIndicatorPolicy() == item.ChildIndicatorPolicy.ShowIndicator, (
            "a part with real staves underneath must still show an expand arrow"
        )


def test_collapsing_a_part_removes_its_children_and_one_down_reaches_the_next_part(
    window, qtbot, score_duet
):
    """Reported bug, live-tested against NVDA: Qt's native isExpanded()/
    setExpanded() only visually hides children, it doesn't remove them, and
    NVDA's own browse-mode buffer kept announcing the now-hidden rows as
    blank on every further Down press - worse the more of the tree had been
    collapsed in the session. Region2ListWidget now actually removes the
    child QTreeWidgetItems on collapse (see its Left/Right handling), so a
    single Down press from a freshly-collapsed part must land straight on
    the next part, with no leftover rows in between."""
    load_and_wait(window, qtbot, score_duet)
    _show(window, qtbot)
    _focus(window.region_2)

    first_part = window.region_2.model_manager.roots[0]
    second_part = window.region_2.model_manager.roots[1]
    window.region_2.select_node(first_part.node_id)
    item = window.region_2.currentItem()
    assert item.childCount() == 0, "nodes start collapsed"

    qtbot.keyClick(window.region_2, Qt.Key.Key_Right)
    assert item.childCount() > 0, "Right must expand it, revealing at least one staff"

    qtbot.keyClick(window.region_2, Qt.Key.Key_Left)
    assert item.childCount() == 0, "collapsing must remove the child items, not just hide them"

    qtbot.keyClick(window.region_2, Qt.Key.Key_Down)
    assert window.region_2.current_node().node_id == second_part.node_id, (
        "one Down press from a collapsed part must land on the very next part"
    )

    # Right re-expands it, rebuilding its subtree from the model.
    window.region_2.select_node(first_part.node_id)
    qtbot.keyClick(window.region_2, Qt.Key.Key_Right)
    assert window.region_2.currentItem().childCount() > 0


def test_collapsing_a_part_forgets_a_childs_expand_state(
    window, qtbot, score_duet
):
    """Reverted per the user's own call after live-testing a "remember each
    descendant's own state across a collapse" version and finding it
    behaved oddly (it shared the setExpanded(True) bug the regression test
    below covers): "I'll live with the child nodes collapsing when the
    parent is collapsed." Expand a staff, collapse its parent part, then
    re-expand the part - the staff must come back collapsed again, not
    already open."""
    load_and_wait(window, qtbot, score_duet)
    _show(window, qtbot)
    _focus(window.region_2)

    part = window.region_2.model_manager.roots[0]
    window.region_2.select_node(part.node_id)
    qtbot.keyClick(window.region_2, Qt.Key.Key_Right)  # expand the part

    staff = part.children[0]
    window.region_2.select_node(staff.node_id)
    staff_item = window.region_2.currentItem()
    qtbot.keyClick(window.region_2, Qt.Key.Key_Right)  # expand the staff too
    assert staff_item.childCount() > 0

    # Collapse the part - the staff's own item is removed along with it.
    window.region_2.select_node(part.node_id)
    qtbot.keyClick(window.region_2, Qt.Key.Key_Left)

    # Re-expand the part: the staff comes back, but collapsed again.
    qtbot.keyClick(window.region_2, Qt.Key.Key_Right)
    rebuilt_staff_item = window.region_2._item_by_node_id[staff.node_id]
    assert rebuilt_staff_item.childCount() == 0


def test_down_arrow_reaches_a_freshly_expanded_nodes_children(
    window, qtbot, score_duet
):
    """Reported bug, live-tested: _expand_item added the child QTreeWidget
    Items but never called item.setExpanded(True) - QTreeWidget's keyboard
    navigation tracks that as a SEPARATE flag from whatever children an
    item actually holds, so Down from a freshly-expanded row silently
    skipped straight past its brand new children to the next sibling,
    however many "expand" presses had happened. A plain Right then Down
    must land on the first real child, not skip it."""
    load_and_wait(window, qtbot, score_duet)
    _show(window, qtbot)
    _focus(window.region_2)

    part = window.region_2.model_manager.roots[0]
    window.region_2.select_node(part.node_id)
    qtbot.keyClick(window.region_2, Qt.Key.Key_Right)

    qtbot.keyClick(window.region_2, Qt.Key.Key_Down)

    assert window.region_2.current_node().node_id == part.children[0].node_id, (
        "Down right after expanding must land on the part's first staff, not skip past it"
    )


def test_region_2_row_text_reflects_mute_and_solo_state(window, qtbot, score_duet):
    load_and_wait(window, qtbot, score_duet)
    _show(window, qtbot)
    _focus(window.region_2)
    part_id = window.region_2.model_manager.roots[0].node_id
    part_name = window.region_2.model_manager.roots[0].display_name

    assert window.region_2.visible_item_texts()[0] == part_name

    window.region_2.select_node(part_id)
    qtbot.keyClick(window.region_2, Qt.Key.Key_F8)
    assert window.region_2.visible_item_texts()[0] == f"{part_name} muted"

    qtbot.keyClick(window.region_2, Qt.Key.Key_F9)
    assert window.region_2.visible_item_texts()[0] == f"{part_name} muted soloed"
