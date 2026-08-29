# tests/test_main_window_performance.py
"""Ref 29 Performance region (Region 5), the Performance Report, and Guitar Pro load. Split from test_main_window.py (S10).
"""
from PySide6.QtCore import Qt

from tests.support.main_window_helpers import _focus, _show, load_and_wait


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


def test_performance_cue_refires_when_arrowing_back_onto_a_beginning_repeat_target(
    window, qtbot, null_synth, unmatched_backward_repeat_score
):
    """unmatched_backward_repeat_score's repeat has no forward counterpart,
    so it defaults its start to measure 1 (user-requested follow-up) -
    stepping from measure 2 back onto measure 1's first note is "arrowing
    onto the first note in bar 1" and must re-ding even though Region 5's
    row set (the same repeat span) hasn't changed."""
    load_and_wait(window, qtbot, unmatched_backward_repeat_score)  # starts on measure 1, span already active
    assert _region_5_labels(window) == ["Repeat start: measure 1", "Repeat end: measure 2"]

    qtbot.keyClick(window.region_3, Qt.Key.Key_Right)  # -> measure 2 (same active span, no refire)
    null_synth.performance_cues.clear()

    qtbot.keyClick(window.region_3, Qt.Key.Key_Left)  # back onto measure 1 - the repeat's own target

    assert len(null_synth.performance_cues) == 1


def test_performance_cue_fires_when_playback_starts_from_a_beginning_repeat_target(
    window, qtbot, null_synth, unmatched_backward_repeat_score
):
    """Starting playback from bar 1 note 1 without first moving the cursor
    elsewhere must still ding - the user's other explicit trigger, alongside
    arrowing back onto it."""
    load_and_wait(window, qtbot, unmatched_backward_repeat_score)
    from tests.support.main_window_helpers import no_lead_in
    no_lead_in(window)  # a plain Space play, no count-in in front of the first note
    null_synth.performance_cues.clear()

    window.toggle_play_stop()  # Space: plays from the cursor, still measure 1 note 1

    assert len(null_synth.performance_cues) == 1
    window.toggle_play_stop()  # stop, so no timer keeps running into the next test


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

    chords_node = window.region_2.model_manager.node("voice_P1_1_1000")
    assert chords_node.display_name == "Chords"

    _show(window, qtbot)
    _focus(window.region_2)

    # Mute every other part, then P1's own real tab voice, leaving only
    # P1's synthetic Chords voice active.
    for part_id in ("part_P0", "part_P2", "part_P3"):
        window.region_2.select_node(part_id)
        qtbot.keyClick(window.region_2, Qt.Key.Key_F8)
    window.region_2.select_node("voice_P1_1_1")
    qtbot.keyClick(window.region_2, Qt.Key.Key_F8)

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
