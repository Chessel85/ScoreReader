# tests/test_main_window_focus.py
"""F6 pane cycling, Tab/Shift+Tab region cycle, application-focus tracking, and the focus-dependent action enablement (FocusController). Split from test_main_window.py (S10). The _show / _focus helpers moved to tests/support/main_window_helpers.py.
"""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from tests.support.main_window_helpers import _focus, _show, load_and_wait


def test_f6_activated_moves_focus_from_a_region_to_the_status_bar(
    window, qtbot, null_synth, minimal_score
):
    """End-to-end proof the F6 QShortcut is actually wired to _toggle_pane
    (as opposed to test_f6_toggles_between_regions_and_status_bar below,
    which calls that logic directly - real QShortcut activation via a
    simulated keypress is otherwise untested anywhere in this app, e.g. the
    existing Ctrl+A shortcut has no test at all, and is flakier to drive
    reliably offscreen depending on which widget already has focus)."""
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    _focus(window.region_1)

    qtbot.keyClick(window, Qt.Key.Key_F6)

    assert window.focusWidget() is window.status_bar.first_field()


def test_f6_toggles_between_regions_and_status_bar(window, qtbot, null_synth, minimal_score):
    """Just two panes - menu bar access stays on the OS's native Alt
    mechanism, not F6 (corrected 2026-08-06 after live testing)."""
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    _focus(window.region_1)

    window._toggle_pane()
    assert window.focusWidget() is window.status_bar.first_field()

    window._toggle_pane()
    assert window.focusWidget() is window.region_1


def test_f6_restores_the_last_focused_region_not_always_region_1(
    window, qtbot, null_synth, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    _focus(window.region_3)
    _focus(window.status_bar.first_field())  # simulate having left the regions area

    window._toggle_pane()  # -> regions: should restore region_3

    assert window.focusWidget() is window.region_3


def test_shift_f6_also_toggles_between_regions_and_status_bar(
    window, qtbot, null_synth, minimal_score
):
    """A plain two-pane toggle has no real "reverse" - Shift+F6 does the
    same thing as F6, so it's just as safe/expected to press either way."""
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    _focus(window.region_1)

    qtbot.keyClick(window, Qt.Key.Key_F6, Qt.KeyboardModifier.ShiftModifier)
    assert window.focusWidget() is window.status_bar.first_field()

    qtbot.keyClick(window, Qt.Key.Key_F6, Qt.KeyboardModifier.ShiftModifier)
    assert window.focusWidget() is window.region_1


def test_tab_cycles_through_all_five_regions_and_wraps(
    window, qtbot, null_synth, minimal_score
):
    """Regression: Tab used to be forwarded to window().focusNextChild(),
    relying on QWidget.setTabOrder to have built a clean N-widget loop.
    Qt's focus chain is ONE shared window-wide ring, and setTabOrder(a, b)
    works by relocating b's node into it - closing the loop needs region_1
    relocated too (the wrap-around region_N->region_1 call), which resets
    region_1's own outgoing pointer as a side effect, silently breaking the
    region_1->region_2 edge set by an earlier call. This isn't fixable by
    reordering the calls: with every widget used once as a source and once
    as a target, the dependency between the calls is circular - some edge
    always breaks. Fixed by having MainWindow.focus_next_region move focus
    directly instead of going through Qt's global chain at all. Ref 29
    added Region 5 (the Performance region) to the cycle."""
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    _focus(window.region_1)

    for expected in (
        window.region_2, window.region_3, window.region_4, window.region_5, window.region_1
    ):
        qtbot.keyClick(window.focusWidget(), Qt.Key.Key_Tab)
        assert window.focusWidget() is expected


def test_shift_tab_cycles_through_all_five_regions_in_reverse(
    window, qtbot, null_synth, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    _focus(window.region_1)

    for expected in (
        window.region_5, window.region_4, window.region_3, window.region_2, window.region_1
    ):
        qtbot.keyClick(window.focusWidget(), Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
        assert window.focusWidget() is expected


def test_every_region_routes_tab_through_the_region_cycle_not_qts_focus_chain(
    window, qtbot, null_synth, minimal_score
):
    """R1 regression, live-tested: Region 2 and Region 3 forwarded Tab from
    keyPressEvent, which QAbstractItemView never calls for Tab on a
    single-column view - so their handlers were dead code and focus moved
    only via Qt's implicit focus chain, which happened to match the intended
    cycle because widget creation order in setup_ui happened to match it too.
    Region 5 hitting the wrap-around is where that coincidence broke.

    The two tests above assert only WHERE focus lands, so they passed
    throughout - a coincidence is indistinguishable from correct wiring by
    that measure alone. This one asserts the cycle methods actually run, so
    the dead-handler state is detectable. Now shared via
    widgets/region_focus_cycle.py's RegionFocusCycleMixin, which intercepts
    at event() level."""
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)

    regions = [window.region_1, window.region_2, window.region_3, window.region_4, window.region_5]
    calls = []
    window.focus_next_region = lambda current: calls.append(("next", current))
    window.focus_previous_region = lambda current: calls.append(("prev", current))

    for region in regions:
        _focus(region)
        calls.clear()

        qtbot.keyClick(region, Qt.Key.Key_Tab)
        assert calls == [("next", region)], f"{type(region).__name__} did not handle Tab"

        calls.clear()
        # A synthetic Shift+Tab arrives as Key_Tab + ShiftModifier, not as
        # Key_Backtab - both spellings must reach focus_previous_region.
        qtbot.keyClick(region, Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
        assert calls == [("prev", region)], f"{type(region).__name__} did not handle Shift+Tab"

        calls.clear()
        qtbot.keyClick(region, Qt.Key.Key_Backtab)
        assert calls == [("prev", region)], f"{type(region).__name__} did not handle Backtab"


def test_closing_the_window_stops_it_tracking_application_focus(
    window, qtbot, null_synth, minimal_score
):
    """R3: focusChanged is an application-level signal, so a closed window
    that stays connected keeps reacting to focus moves in windows it has
    nothing to do with - and, once its own widgets are destroyed, reaches
    deleted C++ objects. Asserts via observable behaviour (the tracked
    _last_focused_region stops updating) rather than by inspecting Qt's
    connection list, which PySide6 doesn't expose."""
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    _focus(window.region_3)
    assert window._last_focused_region is window.region_3

    window.close()

    other = QWidget()
    qtbot.addWidget(other)
    other.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    other.show()
    _focus(other)

    assert window._last_focused_region is window.region_3
    assert window._focus_tracking_connected is False

    # closeEvent legitimately runs twice (explicit close, then fixture
    # teardown) - the second pass must be a silent no-op, not a stale
    # disconnect warning.
    window.close()
    assert window._focus_tracking_connected is False


def test_first_and_last_note_actions_are_only_enabled_in_the_note_region(
    window, qtbot, null_synth, minimal_score
):
    """Tidying: Move to First/Last Note used to act globally from any of the
    four regions or the status bar - now they're greyed out everywhere
    except the Note region (Region 3), so a stray Home/End elsewhere can't
    silently jump the timeline underneath whatever's being read."""
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)

    for region in (window.region_1, window.region_2, window.region_4):
        _focus(region)
        assert not window.first_measure_action.isEnabled()
        assert not window.last_measure_action.isEnabled()

    _focus(window.status_bar.first_field())
    assert not window.first_measure_action.isEnabled()
    assert not window.last_measure_action.isEnabled()

    _focus(window.region_3)
    assert window.first_measure_action.isEnabled()
    assert window.last_measure_action.isEnabled()


def test_preview_action_is_enabled_in_every_region_and_the_status_bar(
    window, qtbot, null_synth, minimal_score
):
    """Enter/Return (Playback > Preview) is a plain window-wide action now,
    always enabled - including the Note region. Its slot
    (MainWindow.audition_phrase) is the single global implementation of
    Enter's dual behaviour: complete a pending typed bar number, else
    toggle the phrase preview. There is no longer a Note-region carve-out
    (FocusController.update_preview_action_enabled is gone)."""
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)

    for region in (
        window.region_1, window.region_2, window.region_3,
        window.region_4, window.region_5,
    ):
        _focus(region)
        assert window.preview_action.isEnabled()

    _focus(window.status_bar.first_field())
    assert window.preview_action.isEnabled()


@pytest.mark.parametrize(
    "focus_target",
    ["region_1", "region_2", "region_3", "region_4", "region_5", "status_bar"],
)
def test_enter_starts_and_stops_preview_from_any_region_or_the_status_bar(
    window, qtbot, null_synth, minimal_score, focus_target
):
    """Functional counterpart of the enabled test above: with no bar number
    pending, pressing Enter must actually start Preview, and pressing it
    again must stop it early - the audition_phrase() toggle, now reachable
    from every region (the Note region included) and the status bar."""
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    target = (
        window.status_bar.first_field() if focus_target == "status_bar"
        else getattr(window, focus_target)
    )
    _focus(target)
    assert window.playback.is_preview_active is False

    qtbot.keyClick(window.focusWidget(), Qt.Key.Key_Return)
    assert window.playback.is_preview_active is True

    qtbot.keyClick(window.focusWidget(), Qt.Key.Key_Return)
    assert window.playback.is_preview_active is False


def test_enter_in_the_note_region_completes_a_typed_bar_number_not_a_preview(
    window, qtbot, null_synth, many_measures_score
):
    """Regression guard: a typed bar number followed by Enter must jump to
    that bar, not start a Preview - audition_phrase() checks for pending
    digits (NavigationController.commit_pending_digits) before previewing."""
    load_and_wait(window, qtbot, many_measures_score)
    _show(window, qtbot)
    _focus(window.region_3)

    qtbot.keyClicks(window.region_3, "2")
    qtbot.keyClick(window.region_3, Qt.Key.Key_Return)

    assert window.playback.is_preview_active is False
    assert window._music_data.get_current_slice().measure == 2


def test_move_to_notes_action_focuses_region_3_from_any_pane(
    window, qtbot, null_synth, minimal_score
):
    """New Navigation > Move to Notes (C) - the deliberate exception that
    stays enabled everywhere, since its job is getting focus into the Note
    region for quick navigation in the first place."""
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)

    for start in (window.region_1, window.region_2, window.region_4, window.status_bar.first_field()):
        _focus(start)
        assert window.move_to_notes_action.isEnabled()

        qtbot.keyClick(window.focusWidget(), Qt.Key.Key_C)

        assert window.focusWidget() is window.region_3


@pytest.mark.parametrize(
    "key, target_region_attr",
    [
        (Qt.Key.Key_Z, "region_1"),
        (Qt.Key.Key_X, "region_2"),
        (Qt.Key.Key_V, "region_4"),
        (Qt.Key.Key_B, "region_5"),
    ],
)
def test_move_to_region_actions_focus_their_region_from_any_pane(
    window, qtbot, null_synth, minimal_score, key, target_region_attr
):
    """Ref 29 follow-up (user-requested): Z/X/V/B mirror Move to Notes (C)
    for the other four regions - same "stays enabled everywhere" behaviour,
    since each one's whole job is getting focus there from anywhere."""
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    target = getattr(window, target_region_attr)

    for start in (window.region_1, window.region_2, window.region_3, window.region_4, window.region_5):
        if start is target:
            continue
        _focus(start)

        qtbot.keyClick(window.focusWidget(), key)

        assert window.focusWidget() is target


def test_select_all_action_is_only_enabled_in_the_note_region(
    window, qtbot, null_synth, minimal_score
):
    """Edit > Select All (Ctrl+A) - user-requested review, 2026-08-26: the
    shortcut was already deliberate (selecting every note at the cursor is
    what makes Shift+Space's "play them all together" audition meaningful),
    but it used to be a bare QShortcut with no menu presence and no
    focus-based gating at all. Now a real QAction, greyed out everywhere
    except the Note region - same treatment as Move to First/Last Note."""
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)

    for region in (window.region_1, window.region_2, window.region_4, window.region_5):
        _focus(region)
        assert not window.select_all_action.isEnabled()

    _focus(window.status_bar.first_field())
    assert not window.select_all_action.isEnabled()

    _focus(window.region_3)
    assert window.select_all_action.isEnabled()


def test_ctrl_a_reselects_every_note_in_the_note_region_only(
    window, qtbot, null_synth, chord_score
):
    """Functional counterpart of the enabled/disabled test above: Ctrl+A
    must still actually reselect every note in the current chord when the
    Note region has focus, and must be a silent no-op (the disabled
    QAction's shortcut simply doesn't fire) everywhere else."""
    load_and_wait(window, qtbot, chord_score)
    _show(window, qtbot)
    window.navigate_timeline_right()  # C -> the D+F chord
    qtbot.keyClick(window.region_3, Qt.Key.Key_Up)  # narrow to just row 0
    assert [i.row() for i in window.region_3.selectedIndexes()] == [0]

    _focus(window.region_1)
    qtbot.keyClick(window.focusWidget(), Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert [i.row() for i in window.region_3.selectedIndexes()] == [0]

    _focus(window.region_3)
    qtbot.keyClick(window.focusWidget(), Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert sorted(i.row() for i in window.region_3.selectedIndexes()) == [0, 1]
