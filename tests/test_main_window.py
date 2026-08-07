# tests/test_main_window.py
"""Widget wiring, driven entirely offscreen with an injected synth.

If any test here opens a window or an audio device, the harness is broken.
"""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QValidator
from PySide6.QtWidgets import QApplication, QDialog, QLabel

from main_window import MainWindow
from widgets.about_dialog import AboutDialog
from widgets.goto_measure_dialog import GotoMeasureDialog


@pytest.fixture
def window(qtbot, null_synth):
    w = MainWindow(synth=null_synth)
    qtbot.addWidget(w)
    return w


def load_and_wait(window, qtbot, file_path: str):
    """load_score_from_file (R1) runs on a background QThread - block until
    it signals completion so assertions run against the loaded state.

    _on_score_loaded (sets _music_data) is queued to the main thread before
    the thread's finished signal (emitted after run() returns), so waiting
    for _load_thread to clear back to None is sufficient.
    """
    window.load_score_from_file(file_path)
    qtbot.waitUntil(lambda: window._load_thread is None, timeout=5000)


def test_constructs_without_touching_audio(window, null_synth):
    assert window.synth is null_synth
    assert null_synth.played == []
    assert not null_synth.closed


def test_four_distinct_regions_are_tab_focusable(window):
    """Groundwork for Ref 1 AC2/AC3. Verifying the cycle actually wraps needs
    a shown window, so that assertion waits for the Ref 4 work in C1."""
    regions = [window.region_1, window.region_2, window.region_3, window.region_4]

    assert len(set(id(r) for r in regions)) == 4
    for region in regions:
        assert region.focusPolicy().name in ("TabFocus", "StrongFocus")


def test_loading_a_score_populates_regions_and_plays(window, qtbot, null_synth, minimal_score):
    load_and_wait(window, qtbot, minimal_score)

    assert window.region_1.rowCount() > 0, "score metadata"
    assert [
        window.region_3.item(i).text() for i in range(window.region_3.count())
    ] == ["C"]
    assert window.region_4.rowCount() > 0, "note attributes"

    assert null_synth.last_played is not None
    assert null_synth.last_played["midi_notes"] == [60], "middle C"


def test_navigating_right_auditions_the_new_slice(window, qtbot, null_synth, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    null_synth.played.clear()

    window.navigate_timeline_right()

    assert [
        window.region_3.item(i).text() for i in range(window.region_3.count())
    ] == ["D"]
    assert null_synth.last_played["midi_notes"] == [62]


def test_playback_stops_previous_notes_before_starting_new_ones(
    window, qtbot, null_synth, minimal_score
):
    """Ref 8 AC2."""
    load_and_wait(window, qtbot, minimal_score)
    stops_before = null_synth.stop_count

    window.navigate_timeline_right()

    assert null_synth.stop_count > stops_before


def test_gm_program_is_converted_to_zero_based_on_the_wire(
    window, qtbot, null_synth, minimal_score
):
    """The model holds 1-indexed GM programs; the synth takes 0-indexed."""
    load_and_wait(window, qtbot, minimal_score)

    assert window._music_data.parts_info[0].gmidi_program == 1
    assert null_synth.last_played["program"] == 0


def test_toggling_the_tab_staff_off_removes_the_duplicate_notes(
    window, qtbot, null_synth, score_bourree
):
    """B4, Ref 7/Ref 8: the Bourree sample has a notation staff and a TAB
    staff duplicating it, so the first slice shows E,G,E,G today. Toggling
    the TAB staff off in Region 2 (O key) must filter Region 3 down to just
    the notation staff's E,G."""
    load_and_wait(window, qtbot, score_bourree)

    assert [
        window.region_3.item(i).text() for i in range(window.region_3.count())
    ] == ["E", "G", "E", "G"]

    tab_staff_row = next(
        i for i, node in enumerate(window.region_2._current_visible_nodes)
        if node.node_id == "staff_P1_2"
    )
    window.region_2.setCurrentRow(tab_staff_row)
    qtbot.keyClick(window.region_2, Qt.Key.Key_O)

    assert [
        window.region_3.item(i).text() for i in range(window.region_3.count())
    ] == ["E", "G"]


def test_timeline_navigation_keys_have_no_effect_outside_the_note_region(
    window, qtbot, null_synth, minimal_score
):
    """Ref 4, D-2 RESOLVED: navigation keystrokes are scoped to the Note
    region, not global - pressing them while another region has focus must
    not move the timeline. Region 1/4 (RegionTableWidget) and Region 2
    (Region2ListWidget) never call the navigate_timeline_* methods for
    these keys, so this is a regression test for that, not new wiring."""
    load_and_wait(window, qtbot, minimal_score)
    start_index = window._music_data.active_event_index

    for region in (window.region_1, window.region_2, window.region_4):
        qtbot.keyClick(region, Qt.Key.Key_Right)
        qtbot.keyClick(region, Qt.Key.Key_Left, Qt.KeyboardModifier.ControlModifier)
        qtbot.keyClick(region, Qt.Key.Key_End)
        qtbot.keyClick(region, Qt.Key.Key_Home)

    assert window._music_data.active_event_index == start_index


def test_ctrl_right_and_ctrl_left_jump_by_measure(window, qtbot, null_synth, ts_change_score):
    load_and_wait(window, qtbot, ts_change_score)

    qtbot.keyClick(window.region_3, Qt.Key.Key_Right, Qt.KeyboardModifier.ControlModifier)
    assert window._music_data.active_event_index == 4  # first event of measure 2

    qtbot.keyClick(window.region_3, Qt.Key.Key_Left, Qt.KeyboardModifier.ControlModifier)
    assert window._music_data.active_event_index == 0  # first event of measure 1


def test_home_and_end_jump_to_the_timeline_limits(window, qtbot, null_synth, minimal_score):
    load_and_wait(window, qtbot, minimal_score)

    qtbot.keyClick(window.region_3, Qt.Key.Key_End)
    assert window._music_data.active_event_index == 3

    qtbot.keyClick(window.region_3, Qt.Key.Key_Home)
    assert window._music_data.active_event_index == 0


def test_left_at_the_first_event_plays_the_boundary_cue_and_does_not_move(
    window, qtbot, null_synth, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    null_synth.played.clear()

    qtbot.keyClick(window.region_3, Qt.Key.Key_Left)

    assert window._music_data.active_event_index == 0
    assert null_synth.last_played == {
        "midi_notes": [window.BOUNDARY_MIDI_PITCH],
        "duration_ms": window.BOUNDARY_DURATION_MS,
        "channel": window.BOUNDARY_CHANNEL,
        "program": window.BOUNDARY_GM_PROGRAM,
    }


def test_ctrl_left_at_the_first_measure_plays_the_boundary_cue_and_does_not_move(
    window, qtbot, null_synth, minimal_score
):
    """minimal_score is a single complete bar, so Ctrl+Left from its first
    event has no preceding measure to land on (Ref 3 AC4)."""
    load_and_wait(window, qtbot, minimal_score)
    null_synth.played.clear()

    qtbot.keyClick(window.region_3, Qt.Key.Key_Left, Qt.KeyboardModifier.ControlModifier)

    assert window._music_data.active_event_index == 0
    assert null_synth.last_played["channel"] == window.BOUNDARY_CHANNEL


def test_home_and_end_never_play_the_boundary_cue(window, qtbot, null_synth, minimal_score):
    """Ref 5 AC3: Home/End jump to a known limit rather than attempting to
    move past one, so they must never trigger the boundary sound - even
    pressed repeatedly once already at that limit."""
    load_and_wait(window, qtbot, minimal_score)
    null_synth.played.clear()

    qtbot.keyClick(window.region_3, Qt.Key.Key_End)
    qtbot.keyClick(window.region_3, Qt.Key.Key_End)
    qtbot.keyClick(window.region_3, Qt.Key.Key_Home)
    qtbot.keyClick(window.region_3, Qt.Key.Key_Home)

    assert all(p["channel"] != window.BOUNDARY_CHANNEL for p in null_synth.played)


def _show(window, qtbot):
    """F6 pane cycling (C7) moves real Qt keyboard focus between widgets,
    which needs a shown, exposed window to behave correctly - unlike every
    other test in this file, which only exercises keyPressEvent handlers
    directly and never needed real focus tracking (see the docstring on
    test_four_distinct_regions_are_tab_focusable)."""
    window.show()
    qtbot.waitExposed(window)


def _focus(widget):
    """setFocus() alone only schedules a focusChanged signal - process
    events so MainWindow._on_focus_changed (which _last_focused_region
    tracking relies on) has actually run before the next assertion."""
    widget.setFocus()
    QApplication.processEvents()


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


def test_tab_cycles_through_all_four_regions_and_wraps(
    window, qtbot, null_synth, minimal_score
):
    """Regression: Tab used to be forwarded to window().focusNextChild(),
    relying on QWidget.setTabOrder to have built a clean 4-widget loop.
    Qt's focus chain is ONE shared window-wide ring, and setTabOrder(a, b)
    works by relocating b's node into it - closing the loop needs region_1
    relocated too (the wrap-around region_4->region_1 call), which resets
    region_1's own outgoing pointer as a side effect, silently breaking the
    region_1->region_2 edge set by an earlier call. This isn't fixable by
    reordering the calls: with 4 widgets each used once as a source and once
    as a target, the dependency between the calls is circular - some edge
    always breaks. Fixed by having MainWindow.focus_next_region move focus
    directly instead of going through Qt's global chain at all."""
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    _focus(window.region_1)

    for expected in (window.region_2, window.region_3, window.region_4, window.region_1):
        qtbot.keyClick(window.focusWidget(), Qt.Key.Key_Tab)
        assert window.focusWidget() is expected


def test_shift_tab_cycles_through_all_four_regions_in_reverse(
    window, qtbot, null_synth, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    _focus(window.region_1)

    for expected in (window.region_4, window.region_3, window.region_2, window.region_1):
        qtbot.keyClick(window.focusWidget(), Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
        assert window.focusWidget() is expected


def test_status_bar_updates_on_load_and_navigation(window, qtbot, null_synth, ts_change_score):
    """C6: status bar reflects the loaded score and then the new position
    after Ctrl+Right jumps into the 6/8 measure."""
    load_and_wait(window, qtbot, ts_change_score)

    fields = window.status_bar._fields
    assert [f.text() for f in fields] == ["Measure 1 beat 1", "Key: C major / A minor", "Time: 4/4"]

    qtbot.keyClick(window.region_3, Qt.Key.Key_Right, Qt.KeyboardModifier.ControlModifier)

    assert [f.text() for f in fields] == ["Measure 2 beat 1", "Key: C major / A minor", "Time: 6/8"]


def test_status_bar_shows_pending_digits_while_typing_a_bar_number(
    window, qtbot, null_synth, many_measures_score
):
    load_and_wait(window, qtbot, many_measures_score)

    qtbot.keyClicks(window.region_3, "12")
    assert window.status_bar._fields[0].text() == "Go to bar: 12"

    qtbot.keyClick(window.region_3, Qt.Key.Key_Return)
    assert window.status_bar._fields[0].text() == "Measure 12 beat 1"


def test_typing_digits_then_enter_jumps_to_that_measure(window, qtbot, null_synth, many_measures_score):
    """C4, Ref 6: multi-digit bar number typed into the Note region."""
    load_and_wait(window, qtbot, many_measures_score)

    qtbot.keyClicks(window.region_3, "12")
    qtbot.keyClick(window.region_3, Qt.Key.Key_Return)

    assert window._music_data.active_event_index == 11  # measure 12's only event


def test_typing_an_unknown_bar_number_then_enter_plays_the_boundary_cue_and_does_not_move(
    window, qtbot, null_synth, many_measures_score
):
    load_and_wait(window, qtbot, many_measures_score)
    null_synth.played.clear()

    qtbot.keyClicks(window.region_3, "99")
    qtbot.keyClick(window.region_3, Qt.Key.Key_Return)

    assert window._music_data.active_event_index == 0
    assert null_synth.last_played["channel"] == window.BOUNDARY_CHANNEL


def test_escape_clears_pending_digits_without_moving(window, qtbot, null_synth, many_measures_score):
    load_and_wait(window, qtbot, many_measures_score)
    null_synth.played.clear()

    qtbot.keyClicks(window.region_3, "5")
    qtbot.keyClick(window.region_3, Qt.Key.Key_Escape)
    qtbot.keyClick(window.region_3, Qt.Key.Key_Return)

    assert window._music_data.active_event_index == 0
    assert null_synth.played == [], "Escape then Enter must not jump nor play the boundary cue"


def test_an_arrow_key_clears_any_pending_digits(window, qtbot, null_synth, many_measures_score):
    """Typing "1" then moving right before pressing Enter must not leave a
    stale "1" waiting to be actioned by a later, unrelated Enter."""
    load_and_wait(window, qtbot, many_measures_score)

    qtbot.keyClicks(window.region_3, "1")
    qtbot.keyClick(window.region_3, Qt.Key.Key_Right)  # measure 2, clears the pending "1"
    qtbot.keyClick(window.region_3, Qt.Key.Key_Return)  # no digits pending - inert (E6 not built)

    assert window._music_data.active_event_index == 1  # still just one step right from start


def test_navigation_menu_first_and_last_measure_move_focus_and_position(
    window, qtbot, null_synth, ts_change_score
):
    load_and_wait(window, qtbot, ts_change_score)
    window.region_1.setFocus()

    window._navigation_menu_last_measure()
    assert window._music_data.active_event_index == window._music_data.last_event_index()
    assert window.focusWidget() is window.region_3

    window.region_1.setFocus()
    window._navigation_menu_first_measure()
    assert window._music_data.active_event_index == 0
    assert window.focusWidget() is window.region_3


def test_goto_measure_dialog_accepts_a_valid_measure_number(
    window, qtbot, null_synth, ts_change_score, monkeypatch
):
    load_and_wait(window, qtbot, ts_change_score)

    dialog = GotoMeasureDialog(window)
    dialog.measure_edit.setText("2")
    monkeypatch.setattr(dialog, "exec", lambda: GotoMeasureDialog.DialogCode.Accepted)
    monkeypatch.setattr("main_window.GotoMeasureDialog", lambda parent, current_measure=None: dialog)

    window._show_goto_measure_dialog()

    assert window._music_data.active_event_index == 4  # first event of measure 2
    assert window.focusWidget() is window.region_3


def test_goto_measure_dialog_rejects_an_unknown_measure_with_the_boundary_cue(
    window, qtbot, null_synth, ts_change_score, monkeypatch
):
    load_and_wait(window, qtbot, ts_change_score)
    null_synth.played.clear()

    dialog = GotoMeasureDialog(window)
    dialog.measure_edit.setText("99")
    monkeypatch.setattr(dialog, "exec", lambda: GotoMeasureDialog.DialogCode.Accepted)
    monkeypatch.setattr("main_window.GotoMeasureDialog", lambda parent, current_measure=None: dialog)

    window._show_goto_measure_dialog()

    assert window._music_data.active_event_index == 0
    assert null_synth.last_played["channel"] == window.BOUNDARY_CHANNEL


def test_goto_measure_dialog_cancelled_does_not_move(
    window, qtbot, null_synth, ts_change_score, monkeypatch
):
    load_and_wait(window, qtbot, ts_change_score)
    null_synth.played.clear()

    dialog = GotoMeasureDialog(window)
    dialog.measure_edit.setText("2")
    monkeypatch.setattr(dialog, "exec", lambda: GotoMeasureDialog.DialogCode.Rejected)
    monkeypatch.setattr("main_window.GotoMeasureDialog", lambda parent, current_measure=None: dialog)

    window._show_goto_measure_dialog()

    assert window._music_data.active_event_index == 0
    assert null_synth.played == []


def test_goto_measure_dialog_prefilled_with_the_current_measure(
    window, qtbot, null_synth, ts_change_score
):
    load_and_wait(window, qtbot, ts_change_score)
    qtbot.keyClick(window.region_3, Qt.Key.Key_Right, Qt.KeyboardModifier.ControlModifier)
    assert window._music_data.get_current_slice().measure == 2

    dialog = GotoMeasureDialog(window, current_measure=window._music_data.get_current_slice().measure)

    assert dialog.measure_edit.text() == "2"


def test_goto_measure_dialog_rejects_a_decimal_beat_position(window):
    """C8 clarification: this is "go to measure", not "go to measure and
    beat" - "4.3" must never be read as measure 4 beat 3. setText() bypasses
    the validator (it's only consulted for user keystrokes), so exercise the
    validator directly rather than through the QLineEdit."""
    dialog = GotoMeasureDialog(window)

    state, _, _ = dialog.measure_edit.validator().validate("4.3", 3)

    assert state != QValidator.State.Acceptable


def test_ctrl_g_shortcut_opens_the_goto_measure_dialog(window, qtbot, null_synth, minimal_score, monkeypatch):
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    _focus(window.region_1)
    opened = []
    monkeypatch.setattr(
        "main_window.GotoMeasureDialog",
        lambda parent, current_measure=None: type(
            "FakeDialog", (), {"exec": lambda self: opened.append(True) or QDialog.DialogCode.Rejected}
        )(),
    )

    qtbot.keyClick(window, Qt.Key.Key_G, Qt.KeyboardModifier.ControlModifier)

    assert opened == [True]


def test_navigation_menu_items_use_home_and_end_shortcuts(window):
    assert window.first_measure_action.shortcut() == QKeySequence(Qt.Key.Key_Home)
    assert window.last_measure_action.shortcut() == QKeySequence(Qt.Key.Key_End)
    assert window.goto_measure_action.shortcut() == QKeySequence("Ctrl+G")
    assert window.move_to_notes_action.shortcut() == QKeySequence("N")


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


def test_move_to_notes_action_focuses_region_3_from_any_pane(
    window, qtbot, null_synth, minimal_score
):
    """New Navigation > Move to Notes (N) - the deliberate exception that
    stays enabled everywhere, since its job is getting focus into the Note
    region for quick navigation in the first place."""
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)

    for start in (window.region_1, window.region_2, window.region_4, window.status_bar.first_field()):
        _focus(start)
        assert window.move_to_notes_action.isEnabled()

        qtbot.keyClick(window.focusWidget(), Qt.Key.Key_N)

        assert window.focusWidget() is window.region_3


def test_goto_measure_dialog_shows_with_focus_on_the_edit_field(window, qtbot):
    """The dialog used to call setFocus() in __init__, before the native
    window existed - Qt's own focus tracking accepted it, but no
    accessibility focus-changed event ever reached NVDA, which kept
    announcing whatever had focus before Ctrl+G was pressed. Deferring the
    setFocus() to after showEvent (see GotoMeasureDialog.showEvent) fixes
    that; this proves the edit field actually ends up with real Qt focus
    once the dialog is shown, not just tab-order to it."""
    dialog = GotoMeasureDialog(window)
    qtbot.addWidget(dialog)

    dialog.show()
    qtbot.waitExposed(dialog)
    qtbot.waitUntil(lambda: dialog.focusWidget() is dialog.measure_edit)

    assert dialog.focusWidget() is dialog.measure_edit


def test_about_dialog_shows_the_version_number(window):
    from version import __version__

    dialog = AboutDialog(window)
    labels = dialog.findChildren(QLabel)

    assert any(__version__ in label.text() for label in labels)


def test_about_dialog_labels_are_individually_tab_focusable(window):
    """Each piece of the About text (name, version, description) is its own
    Tab stop, so NVDA users can move through them one at a time instead of
    hearing one large label read all at once."""
    dialog = AboutDialog(window)
    labels = dialog.findChildren(QLabel)

    assert len(labels) >= 3
    for label in labels:
        assert label.focusPolicy() == Qt.FocusPolicy.StrongFocus


def test_about_action_opens_without_crashing(window, qtbot, monkeypatch):
    opened = []
    monkeypatch.setattr("main_window.AboutDialog", lambda parent: type(
        "FakeDialog", (), {"exec": lambda self: opened.append(True)}
    )())

    window._show_about_dialog()

    assert opened == [True]


def test_loading_a_missing_file_does_not_crash_or_leave_the_thread_dangling(window, qtbot):
    """R1: MusicXMLReader.load() currently swallows parse errors into an
    empty MusicData rather than raising (tasks.txt I1 is the fix for that) -
    this just proves the background thread still completes cleanly and
    clears _load_thread so a later Open is not silently ignored."""
    load_and_wait(window, qtbot, "does_not_exist.musicxml")

    assert window._load_thread is None
    assert window._music_data is not None
    assert window._music_data.timeline_slices == []
