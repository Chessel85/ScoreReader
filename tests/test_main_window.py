# tests/test_main_window.py
"""Widget wiring, driven entirely offscreen with an injected synth.

If any test here opens a window or an audio device, the harness is broken.
"""
import pytest
from PySide6.QtCore import Qt

from main_window import MainWindow


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


def test_loading_a_missing_file_does_not_crash_or_leave_the_thread_dangling(window, qtbot):
    """R1: MusicXMLReader.load() currently swallows parse errors into an
    empty MusicData rather than raising (tasks.txt I1 is the fix for that) -
    this just proves the background thread still completes cleanly and
    clears _load_thread so a later Open is not silently ignored."""
    load_and_wait(window, qtbot, "does_not_exist.musicxml")

    assert window._load_thread is None
    assert window._music_data is not None
    assert window._music_data.timeline_slices == []
