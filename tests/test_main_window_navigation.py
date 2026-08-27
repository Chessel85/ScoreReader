# tests/test_main_window_navigation.py
"""Load, timeline navigation, boundary cues, status bar, typed-measure jumps, and file loading. Split from the original test_main_window.py (S10 of code_review_26th.md).
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import QDialog

from controllers import region_presenter
from widgets.goto_measure_dialog import GotoMeasureDialog
from tests.support.main_window_helpers import _focus, _show, load_and_wait


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

    assert window.region_1.count() > 0, "score metadata"
    assert [
        window.region_3.item(i).text() for i in range(window.region_3.count())
    ] == ["C"]
    assert window.region_4.count() > 0, "note attributes"

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


def test_measure_navigation_announces_the_new_bar_number_without_changing_row_text(
    window, qtbot, monkeypatch, tempo_change_score
):
    """Ctrl+Right's own delegator (navigate_measure_right) must get NVDA to
    hear the new bar number, but Region 3's row 0 text must stay exactly the
    note name, and the note text must never be duplicated into our own
    announcement. Live-tested regressions, in order:
    1) embedding "Measure N." directly into row 0's own text so the
       ordinary per-row accessibility announcement would pick it up meant
       the bar number was re-read every time the user arrowed off row 0
       (into a chord) and back, since it had become the row's real,
       persisted content rather than a one-off spoken event;
    2) trying to suppress that ordinary announcement (via blockSignals
       around setCurrentRow) and post one hand-built "Measure N. <note
       text>" replacement instead didn't actually suppress it - Region 3's
       natural announcement fired regardless, producing a doubled "C fret 2
       bar 6 C fret 2".
    The fix posts a short, TEXT-FREE "Measure N." announcement BEFORE
    Region 3 is even rebuilt, so it's heard ahead of - not instead of, and
    never repeating - the natural announcement of the note itself (see
    RegionPresenter._announce_measure_change/update_timeline_views).
    Captured here in place of a real screen reader."""
    announcements = []
    monkeypatch.setattr(
        region_presenter.QAccessible,
        "updateAccessibility",
        lambda event: announcements.append(event.message()),
    )
    load_and_wait(window, qtbot, tempo_change_score)
    announcements.clear()

    window.navigate_measure_right()  # bar 1 -> bar 2, first note G

    assert window.region_3.item(0).text() == "G"
    assert announcements == ["Measure 2."]


def test_note_by_note_navigation_does_not_announce_a_bar_number(
    window, qtbot, monkeypatch, tempo_change_score
):
    """Plain Left/Right (test_navigating_right_auditions_the_new_slice, above)
    stays unprefixed and un-announced - only Ctrl+Left/Right, Home/End, and
    "go to bar N" are measure-level jumps."""
    announcements = []
    monkeypatch.setattr(
        region_presenter.QAccessible,
        "updateAccessibility",
        lambda event: announcements.append(event.message()),
    )
    load_and_wait(window, qtbot, tempo_change_score)
    announcements.clear()

    window.navigate_timeline_right()  # C -> D, still bar 1

    assert announcements == []


def test_ctrl_number_in_note_region_announces_the_nth_region_4_attribute(
    window, qtbot, monkeypatch, minimal_score
):
    """The quick attribute lookup: Ctrl+1 in the Note region must speak
    Region 4's first row for the current selection ("step: C" for
    minimal_score's opening note) without moving focus or changing Region
    3's own row text."""
    announcements = []
    monkeypatch.setattr(
        region_presenter.QAccessible,
        "updateAccessibility",
        lambda event: announcements.append(event.message()),
    )
    load_and_wait(window, qtbot, minimal_score)
    announcements.clear()

    qtbot.keyClick(window.region_3, Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier)

    assert announcements == ["step: C"]
    assert window.region_3.item(0).text() == "C"


def test_ctrl_number_beyond_the_attribute_count_does_nothing(
    window, qtbot, monkeypatch, minimal_score
):
    """"If the number exceeds the number of entries in the list, do
    nothing" - a silent no-op, not an error, matching every other
    out-of-range convention in this app."""
    announcements = []
    monkeypatch.setattr(
        region_presenter.QAccessible,
        "updateAccessibility",
        lambda event: announcements.append(event.message()),
    )
    load_and_wait(window, qtbot, minimal_score)
    announcements.clear()

    window.announce_region_4_attribute(99)

    assert announcements == []


def test_alt_pageup_pagedown_announce_the_new_preview_length(
    window, qtbot, monkeypatch, minimal_score
):
    """User-requested (2026-08-26): Alt+PageUp/PageDown change Preview's
    length without moving focus off the Note region, so the only previous
    trace of the new value was the status bar's own text - never heard by
    someone not focused there. Wording follows the UK/US terminology
    setting ("bar"/"measure"), same as every other bar-word label; the
    `window` fixture runs with uk_terms=False (US), so "measure" here."""
    announcements = []
    monkeypatch.setattr(
        region_presenter.QAccessible,
        "updateAccessibility",
        lambda event: announcements.append(event.message()),
    )
    load_and_wait(window, qtbot, minimal_score)
    announcements.clear()

    window.increase_preview_bars()  # 2 -> 3

    assert announcements == ["Preview 3 measures."]

    window.decrease_preview_bars()  # 3 -> 2
    window.decrease_preview_bars()  # 2 -> 1 (MIN_PREVIEW_BARS)

    assert announcements[-2:] == ["Preview 2 measures.", "Preview 1 measure."]


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
    window, qtbot, null_synth, score_bourree_full
):
    """B4, Ref 7/Ref 8: the Bourree sample has a notation staff and a TAB
    staff duplicating it, so the first slice shows E,E,G,G today - highest
    pitch first (E4 over G2), the two staves' duplicate E4s and G2s each
    kept adjacent by the stable sort. Muting the TAB staff in Region 2
    (F8) must filter Region 3 down to just the notation staff's E,G."""
    load_and_wait(window, qtbot, score_bourree_full)

    assert [
        window.region_3.item(i).text() for i in range(window.region_3.count())
    ] == ["E", "E", "G", "G"]

    _show(window, qtbot)
    _focus(window.region_2)
    window.region_2.select_node("staff_P1_2")
    qtbot.keyClick(window.region_2, Qt.Key.Key_F8)

    assert [
        window.region_3.item(i).text() for i in range(window.region_3.count())
    ] == ["E", "G"]


def test_timeline_navigation_keys_have_no_effect_outside_the_note_region(
    window, qtbot, null_synth, minimal_score
):
    """Ref 4, D-2 RESOLVED: navigation keystrokes are scoped to the Note
    region, not global - pressing them while another region has focus must
    not move the timeline. Region 1/4 (RegionPropertyListWidget) and Region 2
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
        "bank": 0,
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


def test_status_bar_updates_on_load_and_navigation(window, qtbot, null_synth, ts_change_score):
    """C6: status bar reflects the loaded score and then the new position
    after Ctrl+Right jumps into the 6/8 measure."""
    load_and_wait(window, qtbot, ts_change_score)

    fields = window.status_bar._fields
    assert [f.text() for f in fields] == [
        "Measure 1 beat 1", "Key: C major / A minor", "Time: 4/4",
        "Playback tempo: 120 quarter notes per minute (score default)", "Playback: Stopped",
        "Metronome: Off", "Position Announcer: Off", "Preview length: 2 measures",
    ]

    qtbot.keyClick(window.region_3, Qt.Key.Key_Right, Qt.KeyboardModifier.ControlModifier)

    assert [f.text() for f in fields] == [
        "Measure 2 beat 1", "Key: C major / A minor", "Time: 6/8",
        "Playback tempo: 120 quarter notes per minute (score default)", "Playback: Stopped",
        "Metronome: Off", "Position Announcer: Off", "Preview length: 2 measures",
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


def test_loading_a_midi_file_populates_regions_and_plays(window, qtbot, null_synth, midi_bach_bourree):
    """End-to-end J1/Ref 25 smoke test: ScoreLoadThread dispatches a .mid
    path to MidiReader instead of MusicXMLReader (workers/score_load_worker.py),
    and the rest of MainWindow's load path (regions, audition) needs no
    changes at all - it only ever reads through MusicData's accessors."""
    load_and_wait(window, qtbot, midi_bach_bourree)

    assert window.region_1.count() > 0, "score metadata"
    assert window.region_3.count() > 0, "note list"
    assert window._music_data.timeline_slices
    assert null_synth.last_played is not None


def test_loading_a_midi_file_collapses_region_2_to_part_rows(window, qtbot, midi_bach_bourree):
    """Ref 25/S2: a MIDI score's Region 2 shows track on/off only, no
    staff/voice rows."""
    load_and_wait(window, qtbot, midi_bach_bourree)

    assert len(window.region_2.visible_item_texts()) == len(window._music_data.parts_info)
    assert window.region_2.visible_item_texts()[0].startswith("클래식 기타")


def test_loading_a_musicxml_file_still_shows_staff_and_voice_rows(window, qtbot, score_duet):
    """Confirms S2's collapse is MIDI-only - a MusicXML score's real staff/
    voice structure must still exist and be reachable (nodes start
    collapsed now, so this checks the underlying model richness, not the
    currently-built widget rows - see test_region_2_starts_fully_collapsed
    for that)."""
    load_and_wait(window, qtbot, score_duet)

    assert len(window.region_2.model_manager.get_visible_nodes()) > len(window._music_data.parts_info)


def test_loading_a_missing_file_does_not_crash_or_leave_the_thread_dangling(window, qtbot):
    """R1: MusicXMLReader.load() currently swallows parse errors into an
    empty MusicData rather than raising (tasks.txt I1 is the fix for that) -
    this just proves the background thread still completes cleanly and
    clears _load_thread so a later Open is not silently ignored."""
    load_and_wait(window, qtbot, "does_not_exist.musicxml")

    assert window._load_thread is None
    assert window._music_data is not None
    assert window._music_data.timeline_slices == []


def test_region_1_list_preserves_current_row_across_a_rebuild(window, qtbot, minimal_score):
    """Live-tested bug: Region 1/4's current row jumped to the top on every
    terminology-language change - RegionPropertyListWidget.refresh_list must
    restore the previous row instead."""
    load_and_wait(window, qtbot, minimal_score)
    window.region_1.setCurrentRow(2)

    window.set_uk_terms(True)

    assert window.region_1.currentRow() == 2
