# tests/test_main_window.py
"""Widget wiring, driven entirely offscreen with an injected synth.

If any test here opens a window or an audio device, the harness is broken.
"""
import pytest
from PySide6.QtCore import QLocale, Qt
from PySide6.QtGui import QKeySequence, QValidator
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QTableWidget, QWidget

from audio.metronome import METRONOME_OFFBEAT_NOTE
from main_window import MainWindow, detect_default_uk_terms
from models import mixer_settings
from widgets.about_dialog import AboutDialog
from widgets.attribute_order_dialog import AttributeOrderDialog
from widgets.goto_measure_dialog import GotoMeasureDialog
from widgets.instrument_dialog import InstrumentDialog
from widgets.key_signature_dialog import KeySignatureDialog
from widgets.mixer_dialog import MixerDialog
from widgets.tempo_offset_dialog import TempoOffsetDialog


@pytest.fixture
def window(qtbot, null_synth):
    # uk_terms=False: deterministic regardless of the machine's own OS
    # locale (F4/D-6) - every existing assertion here expects US wording.
    w = MainWindow(synth=null_synth, uk_terms=False)
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


def test_five_distinct_regions_are_tab_focusable(window):
    """Groundwork for Ref 1 AC2/AC3. Verifying the cycle actually wraps needs
    a shown window, so that assertion waits for the Ref 4 work in C1. Ref 29
    added Region 5 (the Performance region) alongside the original four."""
    regions = [window.region_1, window.region_2, window.region_3, window.region_4, window.region_5]

    assert len(set(id(r) for r in regions)) == 5
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


def test_navigating_onto_a_single_note_slice_sets_a_current_row(window, qtbot, minimal_score):
    """Live-tested bug: selectAll() marks every row selected but leaves the
    view's own "current" item untouched, so a slice with exactly one note
    had nothing for NVDA to announce after a Left/Right move - only
    pressing Up/Down (which Qt's own key handling moves explicitly) worked.
    minimal_score's slices are all single notes, so any Right move exercises
    this."""
    load_and_wait(window, qtbot, minimal_score)
    assert window.region_3.currentRow() == 0

    window.navigate_timeline_right()

    assert window.region_3.currentRow() == 0
    assert window.region_3.currentItem() is not None


def test_navigating_onto_a_chord_selects_and_sounds_every_note(window, qtbot, null_synth, chord_score):
    """Live-tested regression: the fix above (setCurrentRow(0) after
    selectAll() so a single-note slice has a definite current item for NVDA)
    was believed to leave selectAll()'s selection untouched via
    QItemSelectionModel::NoUpdate, since that's what the plain one-arg
    setCurrentRow overload is documented to do - it doesn't, in the PySide6
    version this app runs on, and collapsed a chord's selection down to just
    row 0. That silently turned "moving onto a chord sounds every note in
    it" into "only the first note sounds". chord_score's second slice is a
    D+F chord - both notes must stay selected and both must sound. Ordered
    F then D: highest pitch first, regardless of the source XML's D-then-F
    chord order."""
    load_and_wait(window, qtbot, chord_score)
    null_synth.played.clear()

    window.navigate_timeline_right()  # C -> the D+F chord

    assert [window.region_3.item(i).text() for i in range(window.region_3.count())] == ["F", "D"]
    assert sorted(i.row() for i in window.region_3.selectedIndexes()) == [0, 1]
    assert null_synth.last_played["midi_notes"] == [65, 62]


def test_up_arrow_at_the_top_of_a_chord_collapses_selection_to_the_first_note(
    window, qtbot, null_synth, chord_score
):
    """Live-tested regression: landing on a chord selects every note in it
    (current row 0). Down correctly narrows the selection to row 1, but
    pressing Up right away did nothing - Qt's native ExtendedSelection arrow
    handling only collapses a multi-row selection down to the new current
    row as a SIDE EFFECT of the current row actually changing; Up at row 0
    has nowhere to move to, so it silently no-ops and leaves the whole chord
    selected instead of narrowing to just the top note."""
    load_and_wait(window, qtbot, chord_score)
    window.navigate_timeline_right()  # C -> the D+F chord
    assert sorted(i.row() for i in window.region_3.selectedIndexes()) == [0, 1]

    qtbot.keyClick(window.region_3, Qt.Key.Key_Up)

    assert [i.row() for i in window.region_3.selectedIndexes()] == [0]
    assert window.region_3.currentRow() == 0


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
    staff duplicating it, so the first slice shows E,E,G,G today - highest
    pitch first (E4 over G2), the two staves' duplicate E4s and G2s each
    kept adjacent by the stable sort. Toggling the TAB staff off in
    Region 2 (O key) must filter Region 3 down to just the notation
    staff's E,G."""
    load_and_wait(window, qtbot, score_bourree)

    assert [
        window.region_3.item(i).text() for i in range(window.region_3.count())
    ] == ["E", "E", "G", "G"]

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


def test_status_bar_updates_on_load_and_navigation(window, qtbot, null_synth, ts_change_score):
    """C6: status bar reflects the loaded score and then the new position
    after Ctrl+Right jumps into the 6/8 measure."""
    load_and_wait(window, qtbot, ts_change_score)

    fields = window.status_bar._fields
    assert [f.text() for f in fields] == [
        "Measure 1 beat 1", "Key: C major / A minor", "Time: 4/4",
        "Playback tempo: 120 quarter notes per minute (score default)", "Playback: Stopped",
        "Metronome: Off", "Position Announcer: Off",
    ]

    qtbot.keyClick(window.region_3, Qt.Key.Key_Right, Qt.KeyboardModifier.ControlModifier)

    assert [f.text() for f in fields] == [
        "Measure 2 beat 1", "Key: C major / A minor", "Time: 6/8",
        "Playback tempo: 120 quarter notes per minute (score default)", "Playback: Stopped",
        "Metronome: Off", "Position Announcer: Off",
    ]


def test_status_bar_shows_pending_digits_while_typing_a_bar_number(
    window, qtbot, null_synth, many_measures_score
):
    load_and_wait(window, qtbot, many_measures_score)

    qtbot.keyClicks(window.region_3, "12")
    # F4/D-6: this used to hardcode "bar" regardless of dialect (a
    # pre-existing inconsistency with "Measure" everywhere else) - now
    # dialect-aware, so under this fixture's uk_terms=False it says
    # "measure" like the rest of the status bar.
    assert window.status_bar._fields[0].text() == "Go to measure: 12"

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

    assert window._music_data.active_event_index == 0
    assert null_synth.played == [], "Escape itself must not jump, play the boundary cue, or play anything"
    # A subsequent Enter (no pending digits left) is E6's phrase audition,
    # not this key's concern - see test_a_second_enter_while_a_phrase_is_playing_stops_it
    # and friends.


def test_an_arrow_key_clears_any_pending_digits(window, qtbot, null_synth, many_measures_score):
    """Typing "1" then moving right before pressing Enter must not leave a
    stale "1" waiting to be actioned by a later, unrelated Enter."""
    load_and_wait(window, qtbot, many_measures_score)

    qtbot.keyClicks(window.region_3, "1")
    qtbot.keyClick(window.region_3, Qt.Key.Key_Right)  # measure 2, clears the pending "1"
    qtbot.keyClick(window.region_3, Qt.Key.Key_Return)  # no digits pending - starts phrase audition (E6)

    assert window._music_data.active_event_index == 1  # phrase audition never moves the cursor


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
    monkeypatch.setattr(
        "main_window.GotoMeasureDialog", lambda parent, current_measure=None, word="Measure": dialog
    )

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
    monkeypatch.setattr(
        "main_window.GotoMeasureDialog", lambda parent, current_measure=None, word="Measure": dialog
    )

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
    monkeypatch.setattr(
        "main_window.GotoMeasureDialog", lambda parent, current_measure=None, word="Measure": dialog
    )

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
        lambda parent, current_measure=None, word="Measure": type(
            "FakeDialog", (), {"exec": lambda self: opened.append(True) or QDialog.DialogCode.Rejected}
        )(),
    )

    qtbot.keyClick(window, Qt.Key.Key_G, Qt.KeyboardModifier.ControlModifier)

    assert opened == [True]


def test_ctrl_t_shortcut_opens_the_tempo_offset_dialog(window, qtbot, null_synth, minimal_score, monkeypatch):
    """Same scope as Ctrl+G (C8): fires from anywhere normal for a
    shortcut, not just a particular region."""
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    _focus(window.region_1)
    opened = []
    monkeypatch.setattr(
        "main_window.TempoOffsetDialog",
        lambda parent, current_offset=0.0, beat_unit_name="quarter": type(
            "FakeDialog", (), {"exec": lambda self: opened.append(True) or QDialog.DialogCode.Rejected}
        )(),
    )

    qtbot.keyClick(window, Qt.Key.Key_T, Qt.KeyboardModifier.ControlModifier)

    assert opened == [True]


def test_navigation_menu_items_use_home_and_end_shortcuts(window):
    assert window.first_measure_action.shortcut() == QKeySequence(Qt.Key.Key_Home)
    assert window.last_measure_action.shortcut() == QKeySequence(Qt.Key.Key_End)
    assert window.goto_measure_action.shortcut() == QKeySequence("Ctrl+G")
    assert window.move_to_notes_action.shortcut() == QKeySequence("N")
    assert window.move_to_metadata_action.shortcut() == QKeySequence("I")
    assert window.move_to_parts_action.shortcut() == QKeySequence("V")
    assert window.move_to_attributes_action.shortcut() == QKeySequence("A")
    assert window.move_to_performance_action.shortcut() == QKeySequence("P")


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


@pytest.mark.parametrize(
    "key, target_region_attr",
    [
        (Qt.Key.Key_I, "region_1"),
        (Qt.Key.Key_V, "region_2"),
        (Qt.Key.Key_A, "region_4"),
        (Qt.Key.Key_P, "region_5"),
    ],
)
def test_move_to_region_actions_focus_their_region_from_any_pane(
    window, qtbot, null_synth, minimal_score, key, target_region_attr
):
    """Ref 29 follow-up (user-requested): I/V/A/P mirror Move to Notes (N)
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


def test_loading_a_midi_file_populates_regions_and_plays(window, qtbot, null_synth, midi_bach_bourree):
    """End-to-end J1/Ref 25 smoke test: ScoreLoadThread dispatches a .mid
    path to MidiReader instead of MusicXMLReader (workers/score_load_worker.py),
    and the rest of MainWindow's load path (regions, audition) needs no
    changes at all - it only ever reads through MusicData's accessors."""
    load_and_wait(window, qtbot, midi_bach_bourree)

    assert window.region_1.rowCount() > 0, "score metadata"
    assert window.region_3.count() > 0, "note list"
    assert window._music_data.timeline_slices
    assert null_synth.last_played is not None


def test_loading_a_midi_file_collapses_region_2_to_part_rows(window, qtbot, midi_bach_bourree):
    """Ref 25/S2: a MIDI score's Region 2 shows track on/off only, no
    staff/voice rows."""
    load_and_wait(window, qtbot, midi_bach_bourree)

    assert window.region_2.count() == len(window._music_data.parts_info)
    assert window.region_2.item(0).text().startswith("클래식 기타")


def test_loading_a_musicxml_file_still_shows_staff_and_voice_rows(window, qtbot, score_duet):
    """Confirms S2's collapse is MIDI-only - a MusicXML score's real staff/
    voice structure must still be fully navigable, unchanged."""
    load_and_wait(window, qtbot, score_duet)

    assert window.region_2.count() > len(window._music_data.parts_info)


def test_loading_a_missing_file_does_not_crash_or_leave_the_thread_dangling(window, qtbot):
    """R1: MusicXMLReader.load() currently swallows parse errors into an
    empty MusicData rather than raising (tasks.txt I1 is the fix for that) -
    this just proves the background thread still completes cleanly and
    clears _load_thread so a later Open is not silently ignored."""
    load_and_wait(window, qtbot, "does_not_exist.musicxml")

    assert window._load_thread is None
    assert window._music_data is not None
    assert window._music_data.timeline_slices == []


# --- E2: tempo up/down/reset (Ref 12) -----------------------------------

def test_tempo_faster_and_slower_update_the_offset_and_status_bar(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)

    window.tempo_faster()

    assert window._music_data.playback_tempo_offset == 10
    assert window.status_bar._fields[3].text() == "Playback tempo: 130 quarter notes per minute"

    window.tempo_slower()
    window.tempo_slower()

    assert window._music_data.playback_tempo_offset == -10
    assert window.status_bar._fields[3].text() == "Playback tempo: 110 quarter notes per minute"


def test_tempo_reset_returns_to_the_score_default(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    window.tempo_faster()

    window.tempo_reset()

    assert window._music_data.playback_tempo_offset == 0
    assert window.status_bar._fields[3].text() == "Playback tempo: 120 quarter notes per minute (score default)"


def test_tempo_keys_do_not_move_the_timeline_or_reaudition(window, qtbot, null_synth, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    index_before = window._music_data.active_event_index
    null_synth.played.clear()

    window.tempo_faster()

    assert window._music_data.active_event_index == index_before
    assert null_synth.played == []


# --- E3: Tempo Offset dialog (Ref 12 AC5) -------------------------------

def test_tempo_offset_dialog_accepts_a_decimal_value(window, qtbot, minimal_score, monkeypatch):
    load_and_wait(window, qtbot, minimal_score)

    dialog = TempoOffsetDialog(window, current_offset=0.0)
    dialog.offset_edit.setText("15.5")
    monkeypatch.setattr(dialog, "exec", lambda: TempoOffsetDialog.DialogCode.Accepted)
    monkeypatch.setattr(
        "main_window.TempoOffsetDialog",
        lambda parent, current_offset=0.0, beat_unit_name="quarter": dialog,
    )

    window._show_tempo_offset_dialog()

    assert window._music_data.playback_tempo_offset == 15.5
    assert window.status_bar._fields[3].text() == "Playback tempo: 135.5 quarter notes per minute"


def test_tempo_offset_dialog_clamps_rather_than_rejects_an_out_of_range_value(
    window, qtbot, minimal_score, monkeypatch
):
    load_and_wait(window, qtbot, minimal_score)

    dialog = TempoOffsetDialog(window, current_offset=0.0)
    dialog.offset_edit.setText("500")  # 120 + 500 = 620, way past MAX_TEMPO_BPM
    monkeypatch.setattr(dialog, "exec", lambda: TempoOffsetDialog.DialogCode.Accepted)
    monkeypatch.setattr(
        "main_window.TempoOffsetDialog",
        lambda parent, current_offset=0.0, beat_unit_name="quarter": dialog,
    )

    window._show_tempo_offset_dialog()

    assert window._music_data.effective_tempo_display_bpm() == window._music_data.MAX_TEMPO_BPM


def test_tempo_offset_dialog_cancelled_does_not_change_the_offset(
    window, qtbot, minimal_score, monkeypatch
):
    load_and_wait(window, qtbot, minimal_score)

    dialog = TempoOffsetDialog(window, current_offset=0.0)
    dialog.offset_edit.setText("50")
    monkeypatch.setattr(dialog, "exec", lambda: TempoOffsetDialog.DialogCode.Rejected)
    monkeypatch.setattr(
        "main_window.TempoOffsetDialog",
        lambda parent, current_offset=0.0, beat_unit_name="quarter": dialog,
    )

    window._show_tempo_offset_dialog()

    assert window._music_data.playback_tempo_offset == 0


def test_tempo_offset_dialog_prefilled_with_the_current_offset(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    window._music_data.set_playback_tempo_offset(20)

    dialog = TempoOffsetDialog(window, current_offset=window._music_data.playback_tempo_offset)

    assert dialog.offset_edit.text() == "20"


def test_tempo_offset_dialog_rejects_non_numeric_input(window):
    dialog = TempoOffsetDialog(window)
    validator = dialog.offset_edit.validator()

    assert validator.validate("abc", 0)[0] == QValidator.State.Invalid


# --- F2: Attribute order dialog (Ref 15 AC4) ------------------------------

def test_attribute_order_pairs_scope_to_the_selected_region_2_node(
    window, qtbot, dynamics_articulation_fingering_score
):
    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)
    node = next(
        n for n in window.region_2._current_visible_nodes if n.node_id == "voice_P1_1_1"
    )

    keys = [key for key, _ in window._attribute_order_pairs_for_node(node)]

    assert "dynamic" in keys
    assert "articulation" in keys
    assert "pluck" not in keys, "pluck only appears on the guitar part, not this piano voice"


def test_attribute_order_move_updates_music_data_and_returns_focus_to_region_2(
    window, qtbot, dynamics_articulation_fingering_score, monkeypatch
):
    """Simulates clicking Move Up on "octave" while the dialog is open -
    move_requested is connected before exec() is called, same as the real
    button click would fire it, so faking exec() to emit the signal and
    then return is enough to drive the whole wiring without a real modal
    loop (same injection convention as GotoMeasureDialog/TempoOffsetDialog)."""
    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)

    dialog = AttributeOrderDialog(window, pairs=[], scope_description="")

    def fake_exec():
        dialog.move_requested.emit("octave", True)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(dialog, "exec", fake_exec)
    monkeypatch.setattr(
        "main_window.AttributeOrderDialog",
        lambda parent, pairs, scope_description: dialog,
    )

    window._show_attribute_order_dialog()

    assert window._music_data.attribute_order[0] == "octave"
    assert window.focusWidget() is window.region_2


def test_attribute_order_persists_per_file_not_across_different_files(
    window, qtbot, dynamics_articulation_fingering_score, minimal_score, monkeypatch
):
    """Ref 27: attribute_order is per-file (a Phase G decision, unlike
    uk_terms which stays a global preference) - reordering one file must
    not leak into a different file that has no saved config of its own, and
    must be there again when that same file is reloaded (load_score_from_file
    saves the outgoing file's config before swapping in the new one)."""
    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)

    dialog = AttributeOrderDialog(window, pairs=[], scope_description="")

    def fake_exec():
        dialog.move_requested.emit("octave", True)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(dialog, "exec", fake_exec)
    monkeypatch.setattr(
        "main_window.AttributeOrderDialog",
        lambda parent, pairs, scope_description: dialog,
    )
    window._show_attribute_order_dialog()
    assert window._music_data.attribute_order[0] == "octave"

    load_and_wait(window, qtbot, minimal_score)
    assert window._music_data.attribute_order[0] != "octave"

    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)
    assert window._music_data.attribute_order[0] == "octave"


# --- Wishlist #4: Mixer dialog ------------------------------------------

def _fake_mixer_dialog(monkeypatch, window, *, accept: bool, on_exec=None):
    """Builds a real MixerDialog from the window's own current rows, fakes
    exec() to optionally run on_exec(dialog) (e.g. emit a signal, matching
    the AttributeOrderDialog injection convention above) and then return
    Accepted/Rejected, and patches main_window.MixerDialog to hand it back
    regardless of constructor args."""
    dialog = MixerDialog(window, rows=window.playback.begin_mixer_edit())

    def fake_exec():
        if on_exec is not None:
            on_exec(dialog)
        return QDialog.DialogCode.Accepted if accept else QDialog.DialogCode.Rejected

    monkeypatch.setattr(dialog, "exec", fake_exec)
    monkeypatch.setattr("main_window.MixerDialog", lambda parent, rows: dialog)
    return dialog


def test_mixer_dialog_rows_cover_every_part_plus_click_announcer_and_cue(
    window, qtbot, score_duet
):
    load_and_wait(window, qtbot, score_duet)

    rows = window.playback.begin_mixer_edit()

    assert [label for _, label, _, _ in rows] == [
        "Piano", "Classical Guitar", "Metronome", "Position Announcer", "Performance Cue",
    ]
    # No saved mixer yet: every row shows the real engine default, not a
    # placeholder - parts/cue centred, click hard right, announcer hard left.
    assert [pan for _, _, _, pan in rows] == [0, 0, 100, -100, 0]


def test_mixer_dialog_ok_commits_and_persists_the_change(window, qtbot, minimal_score, monkeypatch):
    load_and_wait(window, qtbot, minimal_score)
    part_id = window._music_data.parts_info[0].part_id

    def edit(dialog):
        dialog.row_list.setCurrentRow(0)
        dialog.volume_spin.setValue(68)
        dialog.pan_spin.setValue(-100)

    dialog = _fake_mixer_dialog(monkeypatch, window, accept=True, on_exec=edit)
    window._show_mixer_dialog()

    # Volume is a perceived-loudness multiplier of the default (100 CC),
    # via a sqrt curve compensating FluidSynth's own audio-taper CC7
    # response - 68% -> round(100 * sqrt(0.68)) == 82.
    assert window._music_data.mixer.volume_for(part_id) == 82
    assert window._music_data.mixer.pan_for(part_id) == 0      # -100% -> full left CC 0
    assert (0, 82) in window.synth.volume_changes
    assert (0, 0) in window.synth.pan_changes

    # Ref 27-style persistence: reload the same file and the override
    # must still be there (load_score_from_file saves the outgoing file's
    # config before swapping, same mechanism attribute_order relies on).
    load_and_wait(window, qtbot, minimal_score)
    assert window._music_data.mixer.volume_for(part_id) == 82


def test_mixer_dialog_cancel_reverts_the_synth_and_leaves_the_mixer_untouched(
    window, qtbot, minimal_score, monkeypatch
):
    load_and_wait(window, qtbot, minimal_score)
    part_id = window._music_data.parts_info[0].part_id
    channel = window._music_data.get_channel_for_part(part_id)

    def edit(dialog):
        dialog.row_list.setCurrentRow(0)
        dialog.volume_spin.setValue(20)  # live-previewed, never committed

    dialog = _fake_mixer_dialog(monkeypatch, window, accept=False, on_exec=edit)
    window._show_mixer_dialog()

    assert window._music_data.mixer.is_empty()
    # The live preview did push a CC while the dialog was open - 20% via the
    # sqrt curve is round(100 * sqrt(0.2)) == 45.
    assert (channel, 45) in window.synth.volume_changes
    # ...and cancelling explicitly put the channel back to its true default -
    # cancel_mixer_edit resends every row, not just this one, so check the
    # revert batch (the calls made after the live-preview one) rather than
    # assuming this channel's revert is the very last entry overall.
    revert_calls = window.synth.volume_changes[window.synth.volume_changes.index((channel, 45)) + 1:]
    assert (channel, 100) in revert_calls


def test_switching_files_does_not_leak_a_mixer_override_onto_the_new_score(
    window, qtbot, minimal_score, score_duet, monkeypatch
):
    """Reported bug, live-tested: the synth is a long-lived singleton across
    file loads, so a channel's volume CC value from the PREVIOUS score used
    to survive untouched into a new one with no override of its own -
    apply_mixer only sent CC for parts with an explicit override. The
    user's repro was a cello set to 0% in one score's Mixer staying silent
    after switching to an unrelated score whose part happened to land on
    the same channel. Both fixtures' first part lands on channel 0
    (get_channel_for_part assigns sequentially from the low end)."""
    load_and_wait(window, qtbot, minimal_score)
    part_id = window._music_data.parts_info[0].part_id
    channel = window._music_data.get_channel_for_part(part_id)

    def edit(dialog):
        dialog.row_list.setCurrentRow(0)
        dialog.volume_spin.setValue(0)

    dialog = _fake_mixer_dialog(monkeypatch, window, accept=True, on_exec=edit)
    window._show_mixer_dialog()
    assert (channel, 0) in window.synth.volume_changes

    load_and_wait(window, qtbot, score_duet)
    new_channel = window._music_data.get_channel_for_part(window._music_data.parts_info[0].part_id)
    assert new_channel == channel
    assert window._music_data.mixer.is_empty()
    assert (channel, mixer_settings.DEFAULT_VOLUME) in window.synth.volume_changes


def test_mixer_dialog_preview_plays_without_moving_the_main_cursor(
    window, qtbot, minimal_score, monkeypatch
):
    """Alt+P / the Preview button reuses PlaybackController.audition_phrase
    (Ref 11) - update_cursor=False, so the main timeline cursor and Region 3
    selection are untouched by opening the Mixer and previewing from it."""
    load_and_wait(window, qtbot, minimal_score)
    cursor_before = window._music_data.active_event_index
    window.synth.played.clear()

    dialog = _fake_mixer_dialog(
        monkeypatch, window, accept=True, on_exec=lambda d: d.preview_requested.emit()
    )
    window._show_mixer_dialog()

    assert window.synth.played != []
    assert window._music_data.active_event_index == cursor_before


def test_mixer_dialog_does_nothing_with_no_score_loaded(window, qtbot):
    """Guards the same way _show_performance_report_dialog does - opening
    the Mixer before any file is loaded must not crash."""
    window._show_mixer_dialog()


# --- S5: Instrument dialog -------------------------------------------------

def _fake_instrument_dialog(monkeypatch, window, *, accept: bool, on_exec=None):
    """Same convention as _fake_mixer_dialog: build a real InstrumentDialog
    from the window's own current parts, fake exec() to run on_exec(dialog)
    and return Accepted/Rejected, and patch main_window.InstrumentDialog to
    hand it back regardless of constructor args."""
    rows = [(p.part_id, p.name, p.gmidi_program) for p in window._music_data.parts_info]
    dialog = InstrumentDialog(window, rows=rows)

    def fake_exec():
        if on_exec is not None:
            on_exec(dialog)
        return QDialog.DialogCode.Accepted if accept else QDialog.DialogCode.Rejected

    monkeypatch.setattr(dialog, "exec", fake_exec)
    monkeypatch.setattr("main_window.InstrumentDialog", lambda parent, rows: dialog)
    return dialog


def test_instrument_dialog_ok_renames_the_part_and_reprograms_it(
    window, qtbot, minimal_score, monkeypatch
):
    load_and_wait(window, qtbot, minimal_score)
    part_id = window._music_data.parts_info[0].part_id

    def edit(dialog):
        dialog.row_list.setCurrentRow(0)
        dialog.name_edit.setText("Renamed Part")
        dialog.instrument_combo.setCurrentText("Clarinet")

    _fake_instrument_dialog(monkeypatch, window, accept=True, on_exec=edit)
    window._show_instrument_dialog()

    assert window._music_data.parts_info[0].name == "Renamed Part"
    assert window._music_data.parts_info[0].gmidi_program == 72

    # NoteData.part_name kept in sync (R5's invariant) - Region 3/the
    # Performance Report both key off it.
    matching = [
        n for s in window._music_data.timeline_slices for n in s.notes if n.part_id == part_id
    ]
    assert matching and all(n.part_name == "Renamed Part" for n in matching)

    # Region 2's part row reflects the rename in place.
    assert window.region_2.item(0).text().startswith("Renamed Part")

    # Ref 27-style persistence: reload the same file and the override must
    # still be there.
    load_and_wait(window, qtbot, minimal_score)
    assert window._music_data.parts_info[0].name == "Renamed Part"
    assert window._music_data.parts_info[0].gmidi_program == 72


def test_instrument_dialog_cancel_leaves_the_part_untouched(
    window, qtbot, minimal_score, monkeypatch
):
    load_and_wait(window, qtbot, minimal_score)
    original_name = window._music_data.parts_info[0].name
    original_program = window._music_data.parts_info[0].gmidi_program

    def edit(dialog):
        dialog.row_list.setCurrentRow(0)
        dialog.name_edit.setText("Should Not Stick")
        dialog.instrument_combo.setCurrentText("Clarinet")

    _fake_instrument_dialog(monkeypatch, window, accept=False, on_exec=edit)
    window._show_instrument_dialog()

    assert window._music_data.parts_info[0].name == original_name
    assert window._music_data.parts_info[0].gmidi_program == original_program


def test_instrument_dialog_rename_does_not_reset_region_2_toggle_state(
    window, qtbot, score_duet, monkeypatch
):
    """The rename must go through Region2ListWidget.rename_part (an
    in-place label edit), never a load_score_structure rebuild - that would
    silently switch every part/staff/voice back on, discarding whatever the
    user had already toggled off."""
    load_and_wait(window, qtbot, score_duet)
    window.region_2.setCurrentRow(0)
    qtbot.keyClick(window.region_2, Qt.Key.Key_O)  # switch the first part off
    assert window.region_2.model_manager.roots[0].enabled is False

    def edit(dialog):
        dialog.row_list.setCurrentRow(0)
        dialog.name_edit.setText("Renamed")

    _fake_instrument_dialog(monkeypatch, window, accept=True, on_exec=edit)
    window._show_instrument_dialog()

    assert window.region_2.model_manager.roots[0].enabled is False
    assert window.region_2.model_manager.roots[0].display_name == "Renamed"


def _fake_key_signature_dialog(monkeypatch, window, *, accept: bool, on_exec=None):
    """Same convention as _fake_mixer_dialog/_fake_instrument_dialog."""
    current_key = (
        window._music_data.key_signature_override_fifths,
        window._music_data.key_signature_override_mode,
    )
    dialog = KeySignatureDialog(window, current_key=current_key)

    def fake_exec():
        if on_exec is not None:
            on_exec(dialog)
        return QDialog.DialogCode.Accepted if accept else QDialog.DialogCode.Rejected

    monkeypatch.setattr(dialog, "exec", fake_exec)
    monkeypatch.setattr(
        "main_window.KeySignatureDialog", lambda parent, current_key: dialog
    )
    return dialog


def test_key_signature_override_updates_region_1_and_status_bar_and_persists(
    window, qtbot, midi_test1, monkeypatch
):
    """midi_test1 has no key metadata at all (files/midi/readme.md.txt),
    so it opens as fifths=0/"C major / A minor" - a real case the override
    is meant for."""
    load_and_wait(window, qtbot, midi_test1)

    def edit(dialog):
        g_major_index = next(
            i for i in range(dialog.key_combo.count())
            if dialog.key_combo.itemText(i) == "G major"
        )
        dialog.key_combo.setCurrentIndex(g_major_index)

    _fake_key_signature_dialog(monkeypatch, window, accept=True, on_exec=edit)
    window._show_key_signature_dialog()

    assert window._music_data.key_signature_override_fifths == 1
    assert window._music_data.key_signature_override_mode == "major"
    assert window._music_data.get_region_1_data()["Key Signature"] == "G major"
    assert window._music_data.get_status_bar_fields()[1] == "Key: G major"

    # Ref 27-style persistence: reload the same file and the override must
    # still be there.
    load_and_wait(window, qtbot, midi_test1)
    assert window._music_data.key_signature_override_fifths == 1
    assert window._music_data.key_signature_override_mode == "major"


def test_key_signature_dialog_cancel_leaves_the_override_untouched(
    window, qtbot, midi_test1, monkeypatch
):
    load_and_wait(window, qtbot, midi_test1)

    def edit(dialog):
        g_major_index = next(
            i for i in range(dialog.key_combo.count())
            if dialog.key_combo.itemText(i) == "G major"
        )
        dialog.key_combo.setCurrentIndex(g_major_index)

    _fake_key_signature_dialog(monkeypatch, window, accept=False, on_exec=edit)
    window._show_key_signature_dialog()

    assert window._music_data.key_signature_override_fifths is None
    assert window._music_data.key_signature_override_mode is None


def test_key_signature_dialog_does_nothing_with_no_score_loaded(window, qtbot):
    window._show_key_signature_dialog()


def test_instrument_dialog_does_nothing_with_no_score_loaded(window, qtbot):
    window._show_instrument_dialog()


def test_f_s_d_shortcuts_fire_from_any_region(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    _focus(window.region_1)

    qtbot.keyClick(window, Qt.Key.Key_F)
    assert window._music_data.playback_tempo_offset == 10

    qtbot.keyClick(window, Qt.Key.Key_S)
    qtbot.keyClick(window, Qt.Key.Key_S)
    assert window._music_data.playback_tempo_offset == -10

    qtbot.keyClick(window, Qt.Key.Key_D)
    assert window._music_data.playback_tempo_offset == 0


# --- E5: play/pause/stop (Ref 10) ----------------------------------------

def test_space_starts_playback_from_the_cursor(window, qtbot, null_synth, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    null_synth.played.clear()

    window.toggle_play_stop()

    assert window.sequencer.is_playing is True
    assert null_synth.played[0]["midi_notes"] == [60]  # C4, the cursor's starting note


def test_space_again_stops_and_reverts_the_cursor(window, qtbot, null_synth, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    window.toggle_play_stop()
    window._music_data.active_event_index = 2  # simulate a step having advanced the cursor

    window.toggle_play_stop()

    assert window.sequencer.is_playing is False
    assert window._music_data.active_event_index == 0


def test_space_and_ctrl_space_shortcuts_fire_via_real_keypress_from_any_region(
    window, qtbot, null_synth, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    _focus(window.region_1)

    qtbot.keyClick(window, Qt.Key.Key_Space)
    assert window.sequencer.is_playing is True

    qtbot.keyClick(window, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
    assert window.sequencer.is_paused is True


def test_ctrl_space_pauses_and_space_resumes(window, qtbot, null_synth, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    window.toggle_play_stop()

    window.toggle_pause_resume()
    assert window.sequencer.is_paused is True
    assert window.sequencer.is_playing is False

    played_before_resume = len(null_synth.played)
    window.toggle_play_stop()
    assert window.sequencer.is_playing is True
    assert window.sequencer.is_paused is False
    assert len(null_synth.played) == played_before_resume + 1


def test_space_and_ctrl_space_are_no_ops_before_a_score_is_loaded(window, qtbot):
    window.toggle_play_stop()
    window.toggle_pause_resume()

    assert window.sequencer is None


def test_sequencer_steps_advance_the_cursor_and_regions_over_real_time(
    window, qtbot, null_synth, minimal_score
):
    """Only the wiring is exercised here - the Sequencer's own scheduling
    math is covered deterministically in tests/audio/test_sequencer.py with
    a FakeTimer. This one real QTimer is sped up via a very high tempo so
    the whole 4-note piece finishes in well under a second. Ref 10 AC5 (user
    decision): reaching the end naturally reverts the cursor to where
    playback started, same as an explicit Stop - not a new position of its
    own - so the final active_event_index is back at 0, not the last note
    actually played."""
    load_and_wait(window, qtbot, minimal_score)
    window._music_data.tempo_bpm = 60000  # 1 quarter = 1ms
    null_synth.played.clear()

    window.toggle_play_stop()
    qtbot.waitUntil(lambda: not window.sequencer.is_playing, timeout=2000)

    assert [p["midi_notes"] for p in null_synth.played] == [[60], [62], [64], [65]]
    assert window._music_data.active_event_index == 0
    assert window.status_bar._fields[0].text() == "Measure 1 beat 1"


# --- E6: two-bar phrase audition on Enter (Ref 11) -----------------------

def test_audition_phrase_plays_from_beat_1_without_moving_the_cursor(
    window, qtbot, null_synth, many_measures_score
):
    load_and_wait(window, qtbot, many_measures_score)
    null_synth.played.clear()

    window.audition_phrase()

    assert window.sequencer.is_playing is True
    assert window._music_data.active_event_index == 0
    assert null_synth.played[0]["midi_notes"] == [60]  # C, measure 1


def test_enter_keypress_with_no_pending_digits_starts_phrase_audition(
    window, qtbot, null_synth, many_measures_score
):
    load_and_wait(window, qtbot, many_measures_score)
    null_synth.played.clear()

    qtbot.keyClick(window.region_3, Qt.Key.Key_Return)

    assert window.sequencer.is_playing is True
    assert null_synth.played[0]["midi_notes"] == [60]


def test_phrase_audition_stops_at_the_end_of_the_next_measure(
    window, qtbot, null_synth, many_measures_score
):
    load_and_wait(window, qtbot, many_measures_score)
    window._music_data.tempo_bpm = 60000  # 1 beat = 1ms
    null_synth.played.clear()

    window.audition_phrase()
    qtbot.waitUntil(lambda: not window.sequencer.is_playing, timeout=2000)

    assert [p["midi_notes"] for p in null_synth.played] == [[60], [62]]  # C, D only
    assert window._music_data.active_event_index == 0, "phrase audition never moves the cursor"


def test_a_second_enter_while_a_phrase_is_playing_stops_it(
    window, qtbot, null_synth, many_measures_score
):
    load_and_wait(window, qtbot, many_measures_score)
    window.audition_phrase()
    assert window.sequencer.is_playing is True

    window.audition_phrase()

    assert window.sequencer.is_playing is False
    assert window._music_data.active_event_index == 0


def test_phrase_audition_from_the_last_measure_plays_to_the_end_of_the_piece(
    window, qtbot, null_synth, many_measures_score
):
    load_and_wait(window, qtbot, many_measures_score)
    assert window._music_data.jump_to_measure(12) is True
    null_synth.played.clear()

    window.audition_phrase()

    assert null_synth.played[-1]["midi_notes"] == [79]  # G5, measure 12
    assert window._music_data.active_event_index == 11, "jump_to_measure moved it, not audition_phrase"
    assert window.sequencer.is_playing is True, "only one note left - still ringing out"

    qtbot.waitUntil(lambda: window.sequencer.is_playing is False, timeout=2000)


# --- E7: chord audition retrigger on Shift+Space (Ref 13) ----------------

def test_shift_space_plays_the_current_chord_with_no_navigation(
    window, qtbot, null_synth, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    _focus(window.region_3)
    null_synth.played.clear()

    qtbot.keyClick(window, Qt.Key.Key_Space, Qt.KeyboardModifier.ShiftModifier)

    assert window._music_data.active_event_index == 0
    assert null_synth.played[-1]["midi_notes"] == [60]  # C4, the cursor's current note


def test_shift_space_pressed_twice_retriggers_rather_than_holding(
    window, qtbot, null_synth, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    _focus(window.region_3)
    null_synth.played.clear()

    qtbot.keyClick(window, Qt.Key.Key_Space, Qt.KeyboardModifier.ShiftModifier)
    qtbot.keyClick(window, Qt.Key.Key_Space, Qt.KeyboardModifier.ShiftModifier)

    assert len(null_synth.played) == 2
    assert null_synth.played[0]["midi_notes"] == null_synth.played[1]["midi_notes"] == [60]


def test_shift_space_fires_from_any_region(window, qtbot, null_synth, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    _focus(window.region_1)
    null_synth.played.clear()

    qtbot.keyClick(window, Qt.Key.Key_Space, Qt.KeyboardModifier.ShiftModifier)

    assert null_synth.played[-1]["midi_notes"] == [60]


# --- Reported bugs, live-tested 2026-08-07 --------------------------------

def test_space_at_the_last_active_note_plays_the_boundary_cue_instead_of_playing(
    window, qtbot, null_synth, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    window._music_data.move_timeline_end()  # last note, F
    null_synth.played.clear()

    window.toggle_play_stop()

    assert window.sequencer.is_playing is False
    assert null_synth.last_played["channel"] == window.BOUNDARY_CHANNEL


def test_playback_status_field_reflects_playing_paused_and_stopped(
    window, qtbot, null_synth, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    assert window.status_bar._fields[4].text() == "Playback: Stopped"

    window.toggle_play_stop()
    assert window.status_bar._fields[4].text() == "Playback: Playing"

    window.toggle_pause_resume()
    assert window.status_bar._fields[4].text() == "Playback: Paused"

    window.toggle_play_stop()  # Space resumes from a paused state
    assert window.status_bar._fields[4].text() == "Playback: Playing"

    window.toggle_play_stop()
    assert window.status_bar._fields[4].text() == "Playback: Stopped"


def test_playback_status_field_updates_for_phrase_audition_without_moving_position_fields(
    window, qtbot, null_synth, many_measures_score
):
    load_and_wait(window, qtbot, many_measures_score)
    position_before = window.status_bar._fields[0].text()

    window.audition_phrase()

    assert window.status_bar._fields[4].text() == "Playback: Playing"
    assert window.status_bar._fields[0].text() == position_before

    window.audition_phrase()  # re-press stops it

    assert window.status_bar._fields[4].text() == "Playback: Stopped"
    assert window.status_bar._fields[0].text() == position_before


def test_playback_status_field_shows_stopped_when_playback_finishes_naturally(
    window, qtbot, null_synth, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    window._music_data.tempo_bpm = 60000  # finishes in well under a second
    window.toggle_play_stop()

    qtbot.waitUntil(lambda: not window.sequencer.is_playing, timeout=2000)

    assert window.status_bar._fields[4].text() == "Playback: Stopped"


def test_space_resumes_from_the_paused_position_not_stops(
    window, qtbot, null_synth, minimal_score
):
    """Regression for the reported sequence: Space (play), Ctrl+Space
    (pause), Space was wrongly treated the same as "stop" and reverted to
    the original start, requiring a second Space to actually restart
    playback. Space while paused must resume in place instead - stopping
    is still available, just not via the first post-pause Space press."""
    load_and_wait(window, qtbot, minimal_score)

    window.toggle_play_stop()  # play
    window.toggle_pause_resume()  # pause
    assert window.sequencer.is_paused is True
    paused_index = window.sequencer.current_index

    window.toggle_play_stop()  # resumes from the paused position
    assert window.sequencer.is_playing is True
    assert window.sequencer.is_paused is False
    assert window.sequencer.current_index == paused_index


# --- E8: metronome (Ref 14) ----------------------------------------------

def test_toggle_metronome_updates_music_data_menu_and_status_bar(
    window, qtbot, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    assert window.metronome_action.isChecked() is False
    assert window.status_bar._fields[5].text() == "Metronome: Off"

    window.toggle_metronome()

    assert window._music_data.metronome_enabled is True
    assert window.metronome_action.isChecked() is True
    assert window.status_bar._fields[5].text() == "Metronome: On"

    window.toggle_metronome()

    assert window._music_data.metronome_enabled is False
    assert window.metronome_action.isChecked() is False
    assert window.status_bar._fields[5].text() == "Metronome: Off"


def test_ctrl_m_shortcut_toggles_the_metronome(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    _focus(window.region_1)

    qtbot.keyClick(window, Qt.Key.Key_M, Qt.KeyboardModifier.ControlModifier)

    assert window._music_data.metronome_enabled is True


def test_metronome_state_persists_across_reload_of_same_file(window, qtbot, minimal_score):
    """Ref 27 AC1: unlike the old always-resets-to-off behaviour, the
    metronome is now per-file - load_score_from_file saves the outgoing
    score's config (including metronome_enabled) before swapping in a fresh
    MusicData, and _on_score_loaded restores it when the same file's .rsc is
    found again."""
    load_and_wait(window, qtbot, minimal_score)
    window.toggle_metronome()
    assert window.metronome_action.isChecked() is True

    load_and_wait(window, qtbot, minimal_score)

    assert window._music_data.metronome_enabled is True
    assert window.metronome_action.isChecked() is True


def test_metronome_starts_off_for_a_file_with_no_saved_config(window, qtbot, minimal_score, chord_score):
    load_and_wait(window, qtbot, minimal_score)
    window.toggle_metronome()
    assert window.metronome_action.isChecked() is True

    load_and_wait(window, qtbot, chord_score)

    assert window._music_data.metronome_enabled is False
    assert window.metronome_action.isChecked() is False


# --- Ref 28: position announcer -------------------------------------------

def test_toggle_position_announcer_updates_music_data_menu_and_status_bar(
    window, qtbot, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    assert window.position_announcer_action.isChecked() is False
    assert window.status_bar._fields[6].text() == "Position Announcer: Off"

    window.toggle_position_announcer()

    assert window._music_data.position_announcer_enabled is True
    assert window.position_announcer_action.isChecked() is True
    assert window.status_bar._fields[6].text() == "Position Announcer: On"

    window.toggle_position_announcer()

    assert window._music_data.position_announcer_enabled is False
    assert window.position_announcer_action.isChecked() is False
    assert window.status_bar._fields[6].text() == "Position Announcer: Off"


def test_ctrl_p_shortcut_toggles_the_position_announcer(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    _focus(window.region_1)

    qtbot.keyClick(window, Qt.Key.Key_P, Qt.KeyboardModifier.ControlModifier)

    assert window._music_data.position_announcer_enabled is True


def test_position_announcer_state_persists_across_reload_of_same_file(window, qtbot, minimal_score):
    """Ref 27 AC1: same per-file persistence as the metronome."""
    load_and_wait(window, qtbot, minimal_score)
    window.toggle_position_announcer()
    assert window.position_announcer_action.isChecked() is True

    load_and_wait(window, qtbot, minimal_score)

    assert window._music_data.position_announcer_enabled is True
    assert window.position_announcer_action.isChecked() is True


def test_toggling_position_announcer_does_not_affect_the_metronome(window, qtbot, minimal_score):
    """Ref 28 AC1: the two toggles are independent of each other."""
    load_and_wait(window, qtbot, minimal_score)

    window.toggle_position_announcer()

    assert window._music_data.position_announcer_enabled is True
    assert window._music_data.metronome_enabled is False
    assert window.metronome_action.isChecked() is False


def test_position_announcer_word_plays_on_region_3_navigation(
    window, qtbot, null_synth, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    window.toggle_position_announcer()
    assert null_synth.words == [], "toggling alone doesn't re-audition - only navigation does"
    _show(window, qtbot)
    _focus(window.region_3)

    qtbot.keyClick(window.region_3, Qt.Key.Key_Right)

    assert len(null_synth.words) == 1


# --- F4/D-6: UK/US terminology toggle -------------------------------------

def test_detect_default_uk_terms_true_for_a_non_us_locale():
    assert detect_default_uk_terms(QLocale(QLocale.Language.English, QLocale.Country.UnitedKingdom)) is True
    assert detect_default_uk_terms(QLocale(QLocale.Language.German, QLocale.Country.Germany)) is True


def test_detect_default_uk_terms_false_only_for_a_us_locale():
    assert detect_default_uk_terms(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)) is False


def test_set_uk_terms_updates_music_data_menu_and_status_bar(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    assert window.uk_language_action.isChecked() is False
    assert window.us_language_action.isChecked() is True
    assert window.status_bar._fields[0].text().startswith("Measure ")

    window.set_uk_terms(True)

    assert window._music_data.uk_terms is True
    assert window.uk_language_action.isChecked() is True
    assert window.us_language_action.isChecked() is False
    assert window.status_bar._fields[0].text().startswith("Bar ")
    assert window.goto_measure_action.text() == "&Go to Bar..."

    window.set_uk_terms(False)

    assert window._music_data.uk_terms is False
    assert window.uk_language_action.isChecked() is False
    assert window.us_language_action.isChecked() is True
    assert window.status_bar._fields[0].text().startswith("Measure ")
    assert window.goto_measure_action.text() == "&Go to Measure..."


def test_terminology_language_actions_fire_set_uk_terms(window, qtbot, minimal_score):
    """Live-tested feedback: a submenu of two mutually exclusive, checkable
    items (QActionGroup) rather than one toggle, so "at least one ticked" is
    always visibly true."""
    load_and_wait(window, qtbot, minimal_score)

    window.uk_language_action.trigger()
    assert window._music_data.uk_terms is True
    assert window.uk_language_action.isChecked() is True
    assert window.us_language_action.isChecked() is False

    window.us_language_action.trigger()
    assert window._music_data.uk_terms is False
    assert window.uk_language_action.isChecked() is False
    assert window.us_language_action.isChecked() is True


def test_set_uk_terms_works_with_no_score_loaded(qtbot, null_synth):
    """A session preference, not a per-score one - must still set the
    preference and update the menu even before any file is opened (unlike
    toggle_metronome, which is a no-op with no score)."""
    w = MainWindow(synth=null_synth, uk_terms=False)
    qtbot.addWidget(w)
    assert w.uk_language_action.isChecked() is False

    w.set_uk_terms(True)

    assert w._uk_terms is True
    assert w.uk_language_action.isChecked() is True
    assert w.us_language_action.isChecked() is False


def test_uk_terms_preference_survives_loading_a_new_score(window, qtbot, minimal_score):
    """MusicData is wholly replaced on every file load - the preference
    must be reapplied, or it would silently reset to MusicData's own
    bare-construction default (US) on every open."""
    load_and_wait(window, qtbot, minimal_score)
    window.set_uk_terms(True)
    assert window._music_data.uk_terms is True

    load_and_wait(window, qtbot, minimal_score)

    assert window._music_data.uk_terms is True
    assert window.uk_language_action.isChecked() is True


def test_populate_table_preserves_current_cell_across_a_rebuild(window, qtbot, minimal_score):
    """Live-tested bug: Region 1/4's current cell jumped to the top-left on
    every terminology-language change - _populate_table must restore the
    previous row/column instead."""
    load_and_wait(window, qtbot, minimal_score)
    window.region_1.setCurrentCell(2, 1)

    window.set_uk_terms(True)

    assert window.region_1.currentRow() == 2
    assert window.region_1.currentColumn() == 1


def test_populate_table_clamps_a_now_out_of_range_row(window):
    table = QTableWidget(3, 2)
    table.setCurrentCell(2, 1)

    window._populate_table(table, {"a": "1"})

    assert table.currentRow() == 0
    assert table.currentColumn() == 1


def test_navigating_onto_a_beat_plays_a_click_alongside_the_note(
    window, qtbot, null_synth, minimal_score
):
    """minimal_score is four quarter notes in 4/4 - every note is on a
    whole beat, so Right onto the second note (D, beat 2) must sound both
    the note and a (non-accented) click."""
    load_and_wait(window, qtbot, minimal_score)
    window.toggle_metronome()
    null_synth.clicks.clear()

    qtbot.keyClick(window.region_3, Qt.Key.Key_Right)

    assert null_synth.played[-1]["midi_notes"] == [62]  # D4
    assert len(null_synth.clicks) == 1
    assert null_synth.clicks[0]["pitch"] == METRONOME_OFFBEAT_NOTE  # not beat 1 - regular click


def test_no_click_on_navigation_when_metronome_is_off(
    window, qtbot, null_synth, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    null_synth.clicks.clear()

    qtbot.keyClick(window.region_3, Qt.Key.Key_Right)

    assert null_synth.clicks == []


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
    assert window.region_4.rowCount() > 0, "Region 4 refreshed alongside Region 3"


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


def test_restore_region_4_focus_after_menu_returns_to_the_same_row_and_column(
    window, qtbot, null_synth, minimal_score
):
    """Originally a live-tested bug: selecting a menu action rebuilds Region
    4's rows (via _apply_display_attribute_change -> _refresh_region_3_labels
    -> _on_region_3_selection_changed -> _populate_table) while the menu's
    own exec() is still running (QAction.triggered fires before exec()
    returns), and that rebuild used to reset the table's current cell to
    (0, 0) - NVDA kept reporting the stale menu item, and the next Down
    landed on row 0 ("step") instead of back where the menu was opened.
    _populate_table itself now preserves the current cell across a rebuild
    (F4's Region 1/4 position-persistence fix), so that half of the bug is
    fixed at the source - the current cell is already correct by the time
    _restore_region_4_focus_after_menu runs. What that method still owns is
    giving actual WIDGET FOCUS back: exec() steals focus to the menu while
    it's open, and nothing else returns it to Region 4 once the menu closes."""
    load_and_wait(window, qtbot, minimal_score)

    window.region_4.setCurrentCell(1, 1)  # octave row, value column
    selected_notes = window._music_data.notes_for_indices([0])
    window._apply_display_attribute_change("octave", "voice", selected_notes, add=True)
    assert (window.region_4.currentRow(), window.region_4.currentColumn()) == (1, 1), (
        "_populate_table already preserved the cell through the rebuild"
    )

    window._restore_region_4_focus_after_menu(1, 1)
    QApplication.processEvents()

    assert (window.region_4.currentRow(), window.region_4.currentColumn()) == (1, 1)
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


# --- Ref 27: app naming, window title, Edit menu, per-file persistence ------

def test_window_title_before_any_file_is_loaded(window):
    assert window.windowTitle() == "Recall Score"


def test_window_title_shows_loaded_filename(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)

    assert window.windowTitle() == "minimal_4_4.musicxml - Recall Score"


def test_clear_preferences_action_disabled_with_no_file_loaded(window):
    assert window.clear_preferences_action.isEnabled() is False
    assert window.clear_preferences_action.text() == "&Clear Preferences"


def test_clear_preferences_action_enabled_and_labelled_after_load(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)

    assert window.clear_preferences_action.isEnabled() is True
    assert window.clear_preferences_action.text() == "&Clear Preferences for minimal_4_4.musicxml"


def test_open_local_folder_action_opens_the_config_directory(window, monkeypatch):
    from pathlib import Path

    from persistence import score_config

    opened = []
    monkeypatch.setattr(
        "main_window.QDesktopServices.openUrl",
        lambda url: opened.append(url.toLocalFile()),
    )

    window._open_score_config_folder()

    assert len(opened) == 1
    assert Path(opened[0]) == score_config.config_dir()


def test_clear_preferences_deletes_the_saved_config(window, qtbot, minimal_score):
    from persistence import score_config

    load_and_wait(window, qtbot, minimal_score)
    window.toggle_metronome()
    window._save_current_score_config()
    assert score_config.load_for(minimal_score) is not None

    window._clear_current_score_preferences()

    assert score_config.load_for(minimal_score) is None


def test_closing_the_window_saves_the_current_score_config(window, qtbot, minimal_score):
    from persistence import score_config

    load_and_wait(window, qtbot, minimal_score)
    window.toggle_metronome()

    window.close()

    saved = score_config.load_for(minimal_score)
    assert saved is not None
    assert saved.metronome_enabled is True


def test_voice_filter_persists_across_reload_of_same_file(
    window, qtbot, flute_crotchets_viola_semibreves_score
):
    """Live-tested regression: _update_ui_regions rebuilds Region 2 from
    scratch via load_score_structure, which resets every node to its
    default enabled=True and - through the very same filter_changed signal
    a live toggle uses - silently overwrote the active_voice_filter
    MusicData.apply_config had just restored, so a saved "voice off" toggle
    came back on after every reload. _on_score_loaded must hand the saved
    per-node toggles to Region 2 (apply_off_node_keys) after that rebuild,
    not rely on apply_config's write to MusicData surviving it."""
    load_and_wait(window, qtbot, flute_crotchets_viola_semibreves_score)

    viola_row = next(
        i for i, node in enumerate(window.region_2._current_visible_nodes)
        if node.node_id == "part_P2"
    )
    window.region_2.setCurrentRow(viola_row)
    qtbot.keyClick(window.region_2, Qt.Key.Key_O)
    assert window._music_data.active_voice_filter == {("P1", 1, 1)}

    load_and_wait(window, qtbot, flute_crotchets_viola_semibreves_score)

    assert window._music_data.active_voice_filter == {("P1", 1, 1)}
    assert window.region_2._current_visible_nodes[viola_row].enabled is False


def test_initial_audition_on_reload_respects_the_restored_voice_filter(
    window, qtbot, null_synth, flute_crotchets_viola_semibreves_score
):
    """Live-tested regression, found right after the filter-persistence fix
    above: the filter itself was restored correctly (Region 2 showed viola
    off, subsequent navigation excluded it), but _update_ui_regions's own
    initial audition (play_all=True) fired BEFORE the restored filter was
    handed to Region 2, so the very first sound on load still included the
    voice that was supposed to be off. _on_score_loaded now suppresses that
    first audition when there's a filter to restore and fires it itself once
    Region 2's restored state is actually in effect."""
    load_and_wait(window, qtbot, flute_crotchets_viola_semibreves_score)
    viola_row = next(
        i for i, node in enumerate(window.region_2._current_visible_nodes)
        if node.node_id == "part_P2"
    )
    window.region_2.setCurrentRow(viola_row)
    qtbot.keyClick(window.region_2, Qt.Key.Key_O)  # viola off

    null_synth.played.clear()
    load_and_wait(window, qtbot, flute_crotchets_viola_semibreves_score)

    assert len(null_synth.played) == 1, "must not audition twice (once wrong, once corrected)"
    assert null_synth.played[0]["midi_notes"] == [72]  # flute's C5 only, not the viola too


def test_a_sub_staffs_own_toggle_survives_reload_under_an_off_part(
    window, qtbot, dynamics_articulation_fingering_score
):
    """Reported bug, live-tested: toggling a part off with a sub-element
    still individually on, closing, then reopening the score showed the
    part correctly off - but switching the part back on revealed its
    sub-elements had also silently gone off, losing their original state.
    dynamics_articulation_fingering_score's Piano (P1) has two staves;
    switch staff 2 off individually, then the whole Piano part off (staff 1
    stays individually on underneath), reload, and switch Piano back on -
    staff 1 must come back on and staff 2 must still be off, exactly as
    they were before the part was toggled."""
    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)

    def node_row(node_id):
        return next(
            i for i, n in enumerate(window.region_2._current_visible_nodes)
            if n.node_id == node_id
        )

    window.region_2.setCurrentRow(node_row("staff_P1_2"))
    qtbot.keyClick(window.region_2, Qt.Key.Key_O)  # staff 2 off, staff 1 stays on

    window.region_2.setCurrentRow(node_row("part_P1"))
    qtbot.keyClick(window.region_2, Qt.Key.Key_O)  # whole Piano part off

    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)

    assert window.region_2._current_visible_nodes[node_row("part_P1")].enabled is False

    window.region_2.setCurrentRow(node_row("part_P1"))
    qtbot.keyClick(window.region_2, Qt.Key.Key_O)  # Piano back on

    assert window.region_2._current_visible_nodes[node_row("staff_P1_1")].enabled is True, (
        "staff 1 was individually on before the part was toggled off - must come back on"
    )
    assert window.region_2._current_visible_nodes[node_row("staff_P1_2")].enabled is False, (
        "staff 2 was individually off before the part was toggled off - must stay off"
    )


# --- Ref 29: Performance region (Region 5) + Performance Report --------

def _region_5_labels(window):
    return [window.region_5.item(i).text() for i in range(window.region_5.count())]


def test_region_5_shows_none_outside_any_span(window, qtbot, repeats_and_endings_score):
    load_and_wait(window, qtbot, repeats_and_endings_score)  # starts on measure 1

    assert _region_5_labels(window) == ["None"]


def test_navigating_into_a_repeated_section_updates_region_5_and_plays_the_cue(
    window, qtbot, null_synth, repeats_and_endings_score
):
    load_and_wait(window, qtbot, repeats_and_endings_score)
    null_synth.performance_cues.clear()

    qtbot.keyClick(window.region_3, Qt.Key.Key_Right)  # measure 1 -> measure 2 (repeat opens here)

    assert _region_5_labels(window) == ["Repeat start: measure 2", "Repeat end: measure 3"]
    assert len(null_synth.performance_cues) == 1


def test_performance_cue_does_not_refire_while_the_active_span_set_is_unchanged(
    window, qtbot, null_synth, repeats_and_endings_score
):
    """measure 2 has two notes (two navigable slices), both inside the same
    repeat span - only the first move into the span should fire the cue."""
    load_and_wait(window, qtbot, repeats_and_endings_score)
    qtbot.keyClick(window.region_3, Qt.Key.Key_Right)  # -> measure 2, note 1
    null_synth.performance_cues.clear()

    qtbot.keyClick(window.region_3, Qt.Key.Key_Right)  # -> measure 2, note 2 (same active spans)

    assert null_synth.performance_cues == []


def test_performance_cue_fires_again_when_leaving_a_repeated_section(
    window, qtbot, null_synth, repeats_and_endings_score
):
    load_and_wait(window, qtbot, repeats_and_endings_score)
    for _ in range(4):  # measure 1 -> measure 2 note 1/2 -> measure 3 -> measure 4
        qtbot.keyClick(window.region_3, Qt.Key.Key_Right)
    null_synth.performance_cues.clear()

    assert _region_5_labels(window) == [
        "Ending 2 start: measure 4",
        "Ending 2 end: measure 4",
    ]


def test_ctrl_home_on_region_5_jumps_to_the_span_start(
    window, qtbot, repeats_and_endings_score
):
    load_and_wait(window, qtbot, repeats_and_endings_score)
    qtbot.keyClick(window.region_3, Qt.Key.Key_Right)  # -> measure 2 note 1 (repeat span active)
    window.region_5.setCurrentRow(0)  # "Repeat start: measure 2"

    qtbot.keyClick(window.region_5, Qt.Key.Key_Home, Qt.KeyboardModifier.ControlModifier)

    assert window._music_data.get_current_slice().measure == 2


def test_ctrl_end_on_region_5_jumps_to_the_last_note_of_the_end_bar(
    window, qtbot, repeats_and_endings_score
):
    """The end bar (measure 3) has a single note - Ctrl+End must land there,
    the LAST sounding note of that measure (the user's own decision on this,
    not the first)."""
    load_and_wait(window, qtbot, repeats_and_endings_score)
    qtbot.keyClick(window.region_3, Qt.Key.Key_Right)  # -> measure 2 note 1
    window.region_5.setCurrentRow(1)  # "Repeat end: measure 3"

    qtbot.keyClick(window.region_5, Qt.Key.Key_End, Qt.KeyboardModifier.ControlModifier)

    current = window._music_data.get_current_slice()
    assert current.measure == 3
    assert current.notes[0].step_name == "E"


def test_navigating_into_a_time_signature_change_updates_region_5_and_plays_the_cue(
    window, qtbot, null_synth, ts_change_score
):
    """S7: ts_change_score is 4/4 (bar 1, 4 slices) -> 6/8 (bar 2) -> 4/4
    (bar 3) - four Right presses land on the first slice of bar 2."""
    load_and_wait(window, qtbot, ts_change_score)
    null_synth.performance_cues.clear()

    for _ in range(4):
        qtbot.keyClick(window.region_3, Qt.Key.Key_Right)

    assert _region_5_labels(window) == ["Time signature change: 6/8"]
    assert len(null_synth.performance_cues) == 1

    # One-shot: moving on within the same new signature clears the row
    # again (no further span to still be "inside").
    qtbot.keyClick(window.region_3, Qt.Key.Key_Right)
    assert _region_5_labels(window) == ["None"]


def test_performance_report_action_shows_the_dialog_and_restores_focus(
    window, qtbot, minimal_score, monkeypatch
):
    load_and_wait(window, qtbot, minimal_score)
    window.region_2.setFocus()

    from widgets.performance_report_dialog import PerformanceReportDialog

    dialog = PerformanceReportDialog(window, lines=window._music_data.get_performance_report_lines())
    monkeypatch.setattr(dialog, "exec", lambda: PerformanceReportDialog.DialogCode.Rejected)
    monkeypatch.setattr(
        "main_window.PerformanceReportDialog",
        lambda parent, lines=None: dialog,
    )

    window._show_performance_report_dialog()

    assert dialog.report_list.count() > 0
    assert window.focusWidget() is window.region_2


def test_gp_file_loads_and_chords_voice_is_toggleable_and_auditions_full_chord(
    window, qtbot, gp_ripple, null_synth
):
    """End-to-end: opening a real Guitar Pro file through the full app
    pipeline (Open dialog -> ScoreLoadThread -> GpReader -> MusicData ->
    Region 2/3) shows the synthetic "Chords" voice as an ordinary,
    independently toggleable Region 2 row - isolating it (real tab voice and
    every other part switched off) leaves only chord/strum events on the
    timeline, and auditioning one sounds the whole chord, not one string."""
    load_and_wait(window, qtbot, gp_ripple)

    nodes = window.region_2._current_visible_nodes
    chords_row = next(i for i, n in enumerate(nodes) if n.node_id == "voice_P1_1_1000")
    assert nodes[chords_row].display_name.strip() == "Chords"

    def node_row(node_id: str) -> int:
        return next(i for i, n in enumerate(window.region_2._current_visible_nodes) if n.node_id == node_id)

    # Switch off every other part, then P1's own real tab voice, leaving
    # only P1's synthetic Chords voice active.
    for part_id in ("part_P0", "part_P2", "part_P3"):
        window.region_2.setCurrentRow(node_row(part_id))
        qtbot.keyClick(window.region_2, Qt.Key.Key_O)
    window.region_2.setCurrentRow(node_row("voice_P1_1_1"))
    qtbot.keyClick(window.region_2, Qt.Key.Key_O)

    active = window._music_data.active_voice_filter
    assert active == {("P1", 1, 1000)}

    # Move the cursor onto a slice with a chord-voice event and audition it.
    chord_index = next(
        i for i, s in enumerate(window._music_data.timeline_slices)
        if any(n.voice == 1000 and n.part_id == "P1" for n in s.notes)
    )
    window._music_data.active_event_index = chord_index
    window._update_timeline_views()

    assert window.region_3.count() == 1
    assert null_synth.played, "moving onto a chord-voice event must audition it"
    assert len(null_synth.last_played["midi_notes"]) >= 4, (
        "a chord-voice event must sound the whole chord, not a single representative note"
    )

