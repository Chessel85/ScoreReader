# tests/test_main_window_playback.py
"""Transport: play/pause/stop, the one lead-in/looping play session, Space
with a typed number committing the loop length, Shift+Space chord audition,
absolute tempo, metronome, position announcer, and F/S/D. Split from
test_main_window.py (S10); reworked when Preview folded into one play model.
"""
import pytest
from PySide6.QtCore import Qt

from audio.metronome import METRONOME_ACCENT_NOTE, METRONOME_OFFBEAT_NOTE
from models.play_settings import PlaySettings
from persistence import app_settings
from widgets import accessible_announcer
from widgets.play_settings_dialog import PlaySettingsDialog
from tests.support.main_window_helpers import _focus, _show, load_and_wait, no_lead_in


# --- E2: tempo up/down/reset (Ref 12) - now an ABSOLUTE tempo -----------

def test_tempo_faster_and_slower_move_the_absolute_tempo_and_status_bar(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)

    window.tempo_faster()

    assert window._music_data.playback_tempo_display_bpm() == 130
    assert window.status_bar._fields[3].text() == "Playback tempo: 130 quarter notes per minute"

    window.tempo_slower()
    window.tempo_slower()

    assert window._music_data.playback_tempo_display_bpm() == 110
    assert window.status_bar._fields[3].text() == "Playback tempo: 110 quarter notes per minute"


def test_tempo_reset_returns_to_the_score_default(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    window.tempo_faster()

    window.tempo_reset()

    assert window._music_data.playback_tempo_bpm is None
    assert window.status_bar._fields[3].text() == "Playback tempo: 120 quarter notes per minute (score default)"


def test_playback_is_flat_across_a_score_with_internal_tempo_changes(window, qtbot, tempo_change_score):
    """Ref 12: "always flat" - effective_tempo_bpm no longer follows the
    score's internal rall./accel./section tempo markings."""
    load_and_wait(window, qtbot, tempo_change_score)
    md = window._music_data

    first = md.effective_tempo_bpm(0)
    last = md.effective_tempo_bpm(len(md.timeline_slices) - 1)
    assert first == last == md.effective_playback_quarter_bpm()


def test_tempo_keys_announce_the_new_tempo_number(window, qtbot, monkeypatch, minimal_score):
    announcements = []
    monkeypatch.setattr(
        accessible_announcer.QAccessible,
        "updateAccessibility",
        lambda event: announcements.append(event.message()),
    )
    load_and_wait(window, qtbot, minimal_score)
    announcements.clear()

    window.tempo_faster()   # 120 -> 130
    window.tempo_slower()   # 130 -> 120
    window.tempo_reset()    # -> 120 (score default)

    assert announcements == ["130.", "120.", "120."]


def test_tempo_keys_do_not_move_the_timeline_or_reaudition(window, qtbot, null_synth, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    index_before = window._music_data.active_event_index
    null_synth.played.clear()

    window.tempo_faster()

    assert window._music_data.active_event_index == index_before
    assert null_synth.played == []


@pytest.mark.parametrize(
    "focus_target",
    ["region_1", "region_2", "region_3", "region_4", "region_5", "status_bar"],
)
def test_f_s_d_shortcuts_fire_from_any_region_or_the_status_bar(
    window, qtbot, minimal_score, focus_target
):
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    target = (
        window.status_bar.first_field() if focus_target == "status_bar"
        else getattr(window, focus_target)
    )
    _focus(target)

    qtbot.keyClick(window.focusWidget(), Qt.Key.Key_F)
    assert window._music_data.playback_tempo_display_bpm() == 130

    qtbot.keyClick(window.focusWidget(), Qt.Key.Key_S)
    qtbot.keyClick(window.focusWidget(), Qt.Key.Key_S)
    assert window._music_data.playback_tempo_display_bpm() == 110

    qtbot.keyClick(window.focusWidget(), Qt.Key.Key_D)
    assert window._music_data.playback_tempo_bpm is None


# --- Play Settings dialog (absolute tempo + lead-in + looping) ----------

def _fake_play_settings_dialog(window, monkeypatch, *, tempo=None, settings=None, accept=True):
    dialog = PlaySettingsDialog(
        window,
        play_settings=settings or window.playback.play_settings,
        current_tempo_display_bpm=(
            tempo if tempo is not None
            else window._music_data.playback_tempo_display_bpm()
        ),
        uk_terms=window._uk_terms,
    )
    monkeypatch.setattr(
        dialog, "exec",
        lambda: PlaySettingsDialog.DialogCode.Accepted if accept
        else PlaySettingsDialog.DialogCode.Rejected,
    )
    monkeypatch.setattr(
        "main_window.PlaySettingsDialog",
        lambda *a, **k: dialog,
    )
    return dialog


def test_play_settings_dialog_sets_the_absolute_tempo(window, qtbot, minimal_score, monkeypatch):
    load_and_wait(window, qtbot, minimal_score)
    dialog = _fake_play_settings_dialog(window, monkeypatch)
    dialog.tempo_spin.setValue(72)

    window._show_play_settings_dialog()

    assert window._music_data.playback_tempo_display_bpm() == 72
    assert window.status_bar._fields[3].text() == "Playback tempo: 72 quarter notes per minute"


def test_play_settings_dialog_clamps_an_out_of_range_tempo(window, qtbot, minimal_score, monkeypatch):
    load_and_wait(window, qtbot, minimal_score)
    dialog = _fake_play_settings_dialog(window, monkeypatch)
    dialog.tempo_spin.setValue(dialog.tempo_spin.maximum())

    window._show_play_settings_dialog()

    assert window._music_data.playback_tempo_display_bpm() == window._music_data.MAX_TEMPO_BPM


def test_play_settings_dialog_cancelled_changes_nothing(window, qtbot, minimal_score, monkeypatch):
    load_and_wait(window, qtbot, minimal_score)
    dialog = _fake_play_settings_dialog(window, monkeypatch, accept=False)
    dialog.tempo_spin.setValue(50)
    dialog.loop_check.setChecked(True)

    window._show_play_settings_dialog()

    assert window._music_data.playback_tempo_bpm is None
    assert window.playback.play_settings.loop_enabled is False


def test_play_settings_dialog_toggles_looping_and_lead_in_and_syncs_the_menu(
    window, qtbot, minimal_score, monkeypatch
):
    load_and_wait(window, qtbot, minimal_score)
    dialog = _fake_play_settings_dialog(window, monkeypatch)
    dialog.loop_check.setChecked(True)
    dialog.lead_in_check.setChecked(False)

    window._show_play_settings_dialog()

    assert window.playback.play_settings.loop_enabled is True
    assert window.playback.play_settings.lead_in_enabled is False
    assert window.loop_toggle_action.isChecked() is True
    assert window.lead_in_toggle_action.isChecked() is False


def test_absolute_tempo_persists_per_score(window, qtbot, minimal_score, chord_score):
    load_and_wait(window, qtbot, minimal_score)
    window._music_data.set_playback_tempo_display_bpm(66)

    load_and_wait(window, qtbot, chord_score)
    assert window._music_data.playback_tempo_bpm is None, "a different score is unaffected"

    load_and_wait(window, qtbot, minimal_score)
    assert round(window._music_data.playback_tempo_display_bpm()) == 66


# --- E5: play/pause/stop (Ref 10) --------------------------------------

def test_space_starts_playback_from_the_cursor(window, qtbot, null_synth, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    no_lead_in(window)
    null_synth.played.clear()

    window.toggle_play_stop()

    assert window.sequencer.is_playing is True
    assert null_synth.played[0]["midi_notes"] == [60]


def test_space_again_stops_and_reverts_the_cursor(window, qtbot, null_synth, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    no_lead_in(window)
    window.toggle_play_stop()
    window._music_data.active_event_index = 2

    window.toggle_play_stop()

    assert window.sequencer.is_playing is False
    assert window._music_data.active_event_index == 0


def test_space_and_ctrl_space_shortcuts_fire_via_real_keypress_from_any_region(
    window, qtbot, null_synth, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    no_lead_in(window)
    _show(window, qtbot)
    _focus(window.region_1)

    qtbot.keyClick(window, Qt.Key.Key_Space)
    assert window.sequencer.is_playing is True

    qtbot.keyClick(window, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
    assert window.sequencer.is_paused is True


def test_ctrl_space_pauses_and_space_resumes(window, qtbot, null_synth, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    no_lead_in(window)
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


# --- Ref 19: PlaybackController.play_command/pause_command --------------

def test_play_command_starts_playback_and_is_a_no_op_if_already_playing(
    window, qtbot, null_synth, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    no_lead_in(window)
    null_synth.played.clear()

    window.playback.play_command()
    assert window.sequencer.is_playing is True
    played_count = len(null_synth.played)

    window.playback.play_command()
    assert window.sequencer.is_playing is True
    assert len(null_synth.played) == played_count


def test_play_command_resumes_from_the_paused_position(window, qtbot, null_synth, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    no_lead_in(window)
    window.playback.play_command()
    window.playback.pause_command()
    assert window.sequencer.is_paused is True
    paused_index = window.sequencer.current_index

    window.playback.play_command()

    assert window.sequencer.is_playing is True
    assert window.sequencer.is_paused is False
    assert window.sequencer.current_index == paused_index


def test_pause_command_is_a_no_op_when_not_playing(window, qtbot, null_synth, minimal_score):
    load_and_wait(window, qtbot, minimal_score)

    window.playback.pause_command()

    assert window.sequencer.is_playing is False
    assert window.sequencer.is_paused is False


def test_pause_command_does_not_resume_when_already_paused(window, qtbot, null_synth, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    no_lead_in(window)
    window.playback.play_command()
    window.playback.pause_command()
    assert window.sequencer.is_paused is True

    window.playback.pause_command()

    assert window.sequencer.is_paused is True
    assert window.sequencer.is_playing is False


def test_play_command_and_pause_command_are_no_ops_before_a_score_is_loaded(window, qtbot):
    window.playback.play_command()
    window.playback.pause_command()

    assert window.sequencer is None


def test_sequencer_steps_advance_the_cursor_and_regions_over_real_time(
    window, qtbot, null_synth, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    no_lead_in(window)
    window._music_data.playback_tempo_bpm = 60000  # 1 quarter = 1ms
    null_synth.played.clear()

    window.toggle_play_stop()
    qtbot.waitUntil(lambda: not window.sequencer.is_playing, timeout=2000)

    assert [p["midi_notes"] for p in null_synth.played] == [[60], [62], [64], [65]]
    assert window._music_data.active_event_index == 0
    assert window.status_bar._fields[0].text() == "Measure 1 beat 1"


# --- The one lead-in/looping play session -------------------------------

def test_looping_space_plays_from_the_bar_line_and_restores_the_cursor_on_stop(
    window, qtbot, null_synth, many_measures_score
):
    load_and_wait(window, qtbot, many_measures_score)
    assert window._music_data.jump_to_measure(3) is True
    restore = window._music_data.active_event_index
    assert restore > 0
    no_lead_in(window, loop_enabled=True, loop_length_bars=2)
    null_synth.played.clear()

    window.toggle_play_stop()

    assert window.sequencer.is_playing is True
    # The Note region follows the loop to its bar-line start, away from
    # where the cursor was left.
    assert window._music_data.active_event_index == window.playback._play_run.start_index
    assert null_synth.played, "the loop window's first note sounded"

    window.toggle_play_stop()  # stop the loop
    assert window.sequencer.is_playing is False
    assert window._music_data.active_event_index == restore


def test_looping_run_tracks_the_playing_position_in_the_note_region(
    window, qtbot, null_synth, many_measures_score
):
    load_and_wait(window, qtbot, many_measures_score)
    assert window._music_data.jump_to_measure(3) is True
    restore = window._music_data.active_event_index
    no_lead_in(window, loop_enabled=True, loop_length_bars=2)

    window.toggle_play_stop()
    run = window.playback._play_run
    assert window._music_data.active_event_index == run.start_index

    # A natural step advance moves the Note region with the sound, exactly
    # as it does for a non-looping run.
    window.sequencer._advance()
    assert window._music_data.active_event_index == window.sequencer.current_index
    assert window._music_data.active_event_index != run.start_index

    window.toggle_play_stop()  # stop the loop
    assert window._music_data.active_event_index == restore


def test_a_second_space_while_looping_stops_it(window, qtbot, null_synth, many_measures_score):
    load_and_wait(window, qtbot, many_measures_score)
    no_lead_in(window, loop_enabled=True, loop_length_bars=2)
    window.toggle_play_stop()
    assert window.playback.is_play_run_active is True

    window.toggle_play_stop()

    assert window.playback.is_play_run_active is False
    assert window.sequencer.is_playing is False


def test_lead_in_only_space_counts_in_then_plays_to_the_end(
    window, qtbot, null_synth, many_measures_score
):
    load_and_wait(window, qtbot, many_measures_score)
    window.playback.set_play_settings(
        PlaySettings(lead_in_enabled=True, lead_in_bars=1, loop_enabled=False)
    )
    null_synth.played.clear()

    window.toggle_play_stop()

    run = window.playback._play_run
    assert run is not None and run.looping is False
    counts = [action[1] for _, action in run.events if action[0] == "count"]
    assert counts and counts[0] == 1.0, "a count-in runs first"
    # No notes yet - still counting in.
    assert null_synth.played == []
    assert window.status_bar._fields[4].text() == "Playback: Lead-in"

    window.toggle_play_stop()  # cancel the count-in


def test_looping_space_window_spans_loop_length_bars(
    window, qtbot, repeat_ending_then_dc_al_coda_score
):
    load_and_wait(window, qtbot, repeat_ending_then_dc_al_coda_score)
    no_lead_in(window, loop_enabled=True, loop_length_bars=4)
    md = window._music_data
    assert md.active_event_index == 0

    window.toggle_play_stop()

    run = window.playback._play_run
    assert (run.start_index, run.end_index) == (0, 4)
    assert run.end_quarters == 16.0
    assert run.iteration_ms == 10000, "jump-aware duration, not the flat 8000ms"

    window.toggle_play_stop()


def test_looping_restart_timing_tracks_a_tempo_change_made_mid_loop(
    window, qtbot, repeat_ending_then_dc_al_coda_score
):
    load_and_wait(window, qtbot, repeat_ending_then_dc_al_coda_score)
    no_lead_in(window, loop_enabled=True, loop_length_bars=4)
    window.toggle_play_stop()

    run = window.playback._play_run
    assert run.iteration_ms == 10000

    window._music_data.playback_tempo_bpm = 240  # double speed
    window.playback._start_play_iteration(with_lead_in=False)

    assert run.iteration_ms == 5000

    window.toggle_play_stop()


def test_looping_jump_lower_bound_is_wired_to_the_windows_start(window, qtbot, many_measures_score):
    load_and_wait(window, qtbot, many_measures_score)
    no_lead_in(window, loop_enabled=True, loop_length_bars=2)
    assert window._music_data.jump_to_measure(3) is True

    window.toggle_play_stop()

    run = window.playback._play_run
    assert run is not None and run.start_index != 0
    assert window.sequencer._jump_lower_bound == run.start_index

    window.toggle_play_stop()


def test_lead_in_counts_through_a_whole_bar_before_a_pickup_plays(
    window, qtbot, null_synth, score_bourree_full
):
    load_and_wait(window, qtbot, score_bourree_full)
    window.playback.set_play_settings(
        PlaySettings(lead_in_enabled=True, lead_in_bars=1, lead_in_beats=0, loop_enabled=True, loop_length_bars=1)
    )
    assert window._music_data.active_event_index == 0

    window.toggle_play_stop()

    run = window.playback._play_run
    assert run is not None and run.is_pickup is True
    counts = [action[1] for _, action in run.events if action[0] == "count"]
    assert counts == [1.0, 2.0, 3.0, 4.0, 1.0, 2.0, 3.0]

    beat_ms = 60000.0 / window._music_data.effective_tempo_bpm(0)
    play_offset = next(offset for offset, action in run.events if action[0] == "play")
    last_count_offset = max(offset for offset, action in run.events if action[0] == "count")
    assert play_offset == pytest.approx(last_count_offset + beat_ms, abs=1)

    window.toggle_play_stop()


def test_looping_pickup_does_not_wait_out_the_beats_it_replaces(
    window, qtbot, null_synth, score_bourree_full
):
    load_and_wait(window, qtbot, score_bourree_full)
    no_lead_in(window, loop_enabled=True, loop_length_bars=1)
    assert window._music_data.active_event_index == 0

    window.toggle_play_stop()

    run = window.playback._play_run
    assert run is not None and run.is_pickup is True
    assert run.offset_ms == 0

    window.toggle_play_stop()


# --- Alt+PageUp/PageDown: adjust loop length --------------------------

def test_alt_page_up_and_down_adjust_the_loop_length_by_one_bar(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    assert window.playback.play_settings.loop_length_bars == 2

    qtbot.keyClick(window.region_3, Qt.Key.Key_PageUp, Qt.KeyboardModifier.AltModifier)

    assert window.playback.play_settings.loop_length_bars == 3
    assert window.status_bar._fields[7].text() == "Loop length: 3 measures"

    qtbot.keyClick(window.region_3, Qt.Key.Key_PageDown, Qt.KeyboardModifier.AltModifier)
    qtbot.keyClick(window.region_3, Qt.Key.Key_PageDown, Qt.KeyboardModifier.AltModifier)

    assert window.playback.play_settings.loop_length_bars == 1
    assert window.status_bar._fields[7].text() == "Loop length: 1 measures"


def test_alt_page_down_cannot_go_below_one_bar(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)

    for _ in range(5):
        qtbot.keyClick(window.region_3, Qt.Key.Key_PageDown, Qt.KeyboardModifier.AltModifier)

    assert window.playback.play_settings.loop_length_bars == 1


def test_alt_page_up_is_capped_at_the_maximum_loop_length(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)

    for _ in range(80):
        qtbot.keyClick(window.region_3, Qt.Key.Key_PageUp, Qt.KeyboardModifier.AltModifier)

    assert window.playback.play_settings.loop_length_bars == 64


def test_bare_page_up_down_leaves_the_loop_length_untouched(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)

    qtbot.keyClick(window.region_3, Qt.Key.Key_PageUp)
    qtbot.keyClick(window.region_3, Qt.Key.Key_PageDown)

    assert window.playback.play_settings.loop_length_bars == 2


def test_alt_page_up_persists_the_new_length_globally(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)

    qtbot.keyClick(window.region_3, Qt.Key.Key_PageUp, Qt.KeyboardModifier.AltModifier)

    assert app_settings.load().play.loop_length_bars == 3


# --- Ctrl+Enter: commit a typed number as the loop length ------------

def test_ctrl_enter_sets_the_loop_length_from_a_typed_number(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    window.playback.set_play_settings(PlaySettings(loop_enabled=True))
    window.navigation.append_pending_digit("8")

    window.commit_loop_length()

    assert window.playback.play_settings.loop_length_bars == 8
    assert window.navigation.pending_digits == ""
    assert app_settings.load().play.loop_length_bars == 8


def test_ctrl_enter_with_looping_off_announces_and_clears(window, qtbot, monkeypatch, minimal_score):
    announcements = []
    monkeypatch.setattr(
        accessible_announcer.QAccessible,
        "updateAccessibility",
        lambda event: announcements.append(event.message()),
    )
    load_and_wait(window, qtbot, minimal_score)
    window.playback.set_play_settings(PlaySettings(loop_enabled=False, loop_length_bars=2))
    window.navigation.append_pending_digit("8")

    window.commit_loop_length()

    assert "Looping is off" in announcements
    assert window.navigation.pending_digits == ""
    assert window.playback.play_settings.loop_length_bars == 2


def test_ctrl_enter_with_no_pending_number_is_a_no_op(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    window.playback.set_play_settings(PlaySettings(loop_enabled=True, loop_length_bars=2))

    window.commit_loop_length()

    assert window.playback.play_settings.loop_length_bars == 2


# --- Ctrl+L / Ctrl+I quick toggles ----------------------------------

def test_ctrl_l_toggles_looping_and_keeps_the_menu_in_sync(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    assert window.playback.play_settings.loop_enabled is False

    window.toggle_loop()

    assert window.playback.play_settings.loop_enabled is True
    assert window.loop_toggle_action.isChecked() is True
    assert app_settings.load().play.loop_enabled is True

    window.toggle_loop()
    assert window.playback.play_settings.loop_enabled is False


def test_ctrl_i_toggles_the_lead_in_and_keeps_the_menu_in_sync(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    assert window.playback.play_settings.lead_in_enabled is True

    window.toggle_lead_in()

    assert window.playback.play_settings.lead_in_enabled is False
    assert window.lead_in_toggle_action.isChecked() is False
    assert app_settings.load().play.lead_in_enabled is False


# --- E7: chord audition retrigger on Shift+Space (Ref 13) --------------

def test_shift_space_plays_the_current_chord_with_no_navigation(
    window, qtbot, null_synth, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    _focus(window.region_3)
    null_synth.played.clear()

    qtbot.keyClick(window, Qt.Key.Key_Space, Qt.KeyboardModifier.ShiftModifier)

    assert window._music_data.active_event_index == 0
    assert null_synth.played[-1]["midi_notes"] == [60]


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


# --- Reported bugs, live-tested 2026-08-07 ----------------------------

def test_space_at_the_last_active_note_plays_the_boundary_cue_instead_of_playing(
    window, qtbot, null_synth, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    no_lead_in(window)
    window._music_data.move_timeline_end()
    null_synth.played.clear()

    window.toggle_play_stop()

    assert window.sequencer.is_playing is False
    assert null_synth.last_played["channel"] == window.BOUNDARY_CHANNEL


def test_playback_status_field_reflects_playing_paused_and_stopped(
    window, qtbot, null_synth, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    no_lead_in(window)
    assert window.status_bar._fields[4].text() == "Playback: Stopped"

    window.toggle_play_stop()
    assert window.status_bar._fields[4].text() == "Playback: Playing"

    window.toggle_pause_resume()
    assert window.status_bar._fields[4].text() == "Playback: Paused"

    window.toggle_play_stop()
    assert window.status_bar._fields[4].text() == "Playback: Playing"

    window.toggle_play_stop()
    assert window.status_bar._fields[4].text() == "Playback: Stopped"


def test_playback_status_field_shows_looping_for_a_looping_run(
    window, qtbot, null_synth, many_measures_score
):
    load_and_wait(window, qtbot, many_measures_score)
    no_lead_in(window, loop_enabled=True, loop_length_bars=2)

    window.toggle_play_stop()
    assert window.status_bar._fields[4].text() == "Playback: Playing (looping)"

    window.toggle_play_stop()
    assert window.status_bar._fields[4].text() == "Playback: Stopped"


def test_playback_status_field_shows_stopped_when_playback_finishes_naturally(
    window, qtbot, null_synth, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    no_lead_in(window)
    window._music_data.playback_tempo_bpm = 60000
    window.toggle_play_stop()

    qtbot.waitUntil(lambda: not window.sequencer.is_playing, timeout=2000)

    assert window.status_bar._fields[4].text() == "Playback: Stopped"


def test_space_resumes_from_the_paused_position_not_stops(
    window, qtbot, null_synth, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    no_lead_in(window)

    window.toggle_play_stop()
    window.toggle_pause_resume()
    assert window.sequencer.is_paused is True
    paused_index = window.sequencer.current_index

    window.toggle_play_stop()
    assert window.sequencer.is_playing is True
    assert window.sequencer.is_paused is False
    assert window.sequencer.current_index == paused_index


# --- E8: metronome (Ref 14) ------------------------------------------

def test_toggle_metronome_updates_music_data_menu_and_status_bar(window, qtbot, minimal_score):
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


# --- Play Metronome (Alt+Space): a free-running click track ------------

def test_play_metronome_clicks_without_moving_the_timeline(
    window, qtbot, null_synth, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    window._music_data.active_event_index = 1
    null_synth.clicks.clear()

    window.toggle_play_metronome()

    assert window.playback.is_play_metronome_running is True
    # A click sounded straight away, starting on the accent (beat 1)...
    assert null_synth.clicks[0]["pitch"] == METRONOME_ACCENT_NOTE
    # ...and nothing about the score's position or the transport changed.
    assert window._music_data.active_event_index == 1
    assert window.sequencer.is_playing is False

    window.toggle_play_metronome()

    assert window.playback.is_play_metronome_running is False


def test_play_metronome_beat_interval_tracks_the_current_playback_tempo(
    window, qtbot, null_synth, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    window.toggle_play_metronome()

    def expected_interval_ms():
        md = window._music_data
        _, ts_den = md.get_current_slice().time_sig
        return max(1, round((4.0 / ts_den) * 60000.0 / md.effective_tempo_bpm()))

    assert window.playback._play_metronome_timer.interval() == expected_interval_ms()

    window.tempo_faster()
    window.playback._sound_play_metronome_beat()  # re-arms off the new tempo

    assert window.playback._play_metronome_timer.interval() == expected_interval_ms()


def test_space_stops_a_running_play_metronome_rather_than_starting_playback(
    window, qtbot, null_synth, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    window.toggle_play_metronome()

    window.toggle_play_stop()

    assert window.playback.is_play_metronome_running is False
    assert window.sequencer.is_playing is False


def test_ctrl_alt_space_shortcut_toggles_the_play_metronome(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    _focus(window.region_1)

    qtbot.keyClick(
        window, Qt.Key.Key_Space,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
    )

    assert window.playback.is_play_metronome_running is True


def test_play_metronome_is_a_no_op_before_a_score_is_loaded(window, qtbot):
    window.toggle_play_metronome()

    assert window.playback.is_play_metronome_running is False


def test_loading_a_score_stops_a_running_play_metronome(
    window, qtbot, minimal_score, chord_score
):
    load_and_wait(window, qtbot, minimal_score)
    window.toggle_play_metronome()
    assert window.playback.is_play_metronome_running is True

    load_and_wait(window, qtbot, chord_score)

    assert window.playback.is_play_metronome_running is False


# --- Ref 28: position announcer -------------------------------------

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
    load_and_wait(window, qtbot, minimal_score)
    window.toggle_position_announcer()
    assert window.position_announcer_action.isChecked() is True

    load_and_wait(window, qtbot, minimal_score)

    assert window._music_data.position_announcer_enabled is True
    assert window.position_announcer_action.isChecked() is True


def test_toggling_position_announcer_does_not_affect_the_metronome(window, qtbot, minimal_score):
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
    assert null_synth.words == []
    _show(window, qtbot)
    _focus(window.region_3)

    qtbot.keyClick(window.region_3, Qt.Key.Key_Right)

    assert len(null_synth.words) == 1


def test_navigating_onto_a_beat_plays_a_click_alongside_the_note(
    window, qtbot, null_synth, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    window.toggle_metronome()
    null_synth.clicks.clear()

    qtbot.keyClick(window.region_3, Qt.Key.Key_Right)

    assert null_synth.played[-1]["midi_notes"] == [62]
    assert len(null_synth.clicks) == 1
    assert null_synth.clicks[0]["pitch"] == METRONOME_OFFBEAT_NOTE


def test_no_click_when_moving_up_or_down_within_a_chord(window, qtbot, null_synth, chord_score):
    load_and_wait(window, qtbot, chord_score)
    window.toggle_metronome()
    window.toggle_position_announcer()
    _show(window, qtbot)
    _focus(window.region_3)
    qtbot.keyClick(window.region_3, Qt.Key.Key_Right)
    assert window.region_3.count() > 1
    null_synth.clicks.clear()
    null_synth.words.clear()
    played_before = len(null_synth.played)

    qtbot.keyClick(window.region_3, Qt.Key.Key_Down)

    assert null_synth.clicks == []
    assert null_synth.words == []
    assert len(null_synth.played) > played_before


def test_no_click_on_navigation_when_metronome_is_off(window, qtbot, null_synth, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    null_synth.clicks.clear()

    qtbot.keyClick(window.region_3, Qt.Key.Key_Right)

    assert null_synth.clicks == []
