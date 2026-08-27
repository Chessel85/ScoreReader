# tests/test_main_window_playback.py
"""Transport: play/pause/stop, phrase audition, Preview + lead-in + length adjust, Shift+Space chord audition, tempo offset, metronome, position announcer, and F/S/D. Split from test_main_window.py (S10).
"""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QValidator

from audio.metronome import METRONOME_OFFBEAT_NOTE
from models.preview_settings import PreviewSettings
from persistence import app_settings
from widgets.tempo_offset_dialog import TempoOffsetDialog
from tests.support.main_window_helpers import _focus, _show, load_and_wait, no_lead_in


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


@pytest.mark.parametrize(
    "focus_target",
    ["region_1", "region_2", "region_3", "region_4", "region_5", "status_bar"],
)
def test_f_s_d_shortcuts_fire_from_any_region_or_the_status_bar(
    window, qtbot, minimal_score, focus_target
):
    """F/S/D (tempo) are WindowShortcut-context QShortcuts (main_window.
    setup_shortcuts), so - like F6 and the Z/X/C/V/B region jumps - they
    must fire no matter which widget currently holds real Qt focus,
    including the status bar (none of Region 1-5's own keyPressEvent
    overrides ever see a key pressed there). User-requested review
    (2026-08-26): confirmed already true for every region; the status bar
    case is added here since it wasn't previously covered by any test."""
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    target = (
        window.status_bar.first_field() if focus_target == "status_bar"
        else getattr(window, focus_target)
    )
    _focus(target)

    qtbot.keyClick(window.focusWidget(), Qt.Key.Key_F)
    assert window._music_data.playback_tempo_offset == 10

    qtbot.keyClick(window.focusWidget(), Qt.Key.Key_S)
    qtbot.keyClick(window.focusWidget(), Qt.Key.Key_S)
    assert window._music_data.playback_tempo_offset == -10

    qtbot.keyClick(window.focusWidget(), Qt.Key.Key_D)
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


# --- Ref 19: PlaybackController.play_command/pause_command (hands-free
# voice control's directional play/pause, distinct from Space/Ctrl+Space's
# toggling behaviour) ------------------------------------------------------

def test_play_command_starts_playback_and_is_a_no_op_if_already_playing(
    window, qtbot, null_synth, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    null_synth.played.clear()

    window.playback.play_command()
    assert window.sequencer.is_playing is True
    played_count = len(null_synth.played)

    window.playback.play_command()  # already playing - must not stop or retrigger
    assert window.sequencer.is_playing is True
    assert len(null_synth.played) == played_count


def test_play_command_resumes_from_the_paused_position(window, qtbot, null_synth, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
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

    window.playback.pause_command()  # must not raise or start anything

    assert window.sequencer.is_playing is False
    assert window.sequencer.is_paused is False


def test_pause_command_does_not_resume_when_already_paused(window, qtbot, null_synth, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    window.playback.play_command()
    window.playback.pause_command()
    assert window.sequencer.is_paused is True

    window.playback.pause_command()  # must stay paused, never resume

    assert window.sequencer.is_paused is True
    assert window.sequencer.is_playing is False


def test_play_command_and_pause_command_are_no_ops_before_a_score_is_loaded(window, qtbot):
    window.playback.play_command()
    window.playback.pause_command()

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
    no_lead_in(window)
    null_synth.played.clear()

    window.audition_phrase()

    assert window.sequencer.is_playing is True
    assert window._music_data.active_event_index == 0
    assert null_synth.played[0]["midi_notes"] == [60]  # C, measure 1


def test_enter_keypress_with_no_pending_digits_starts_phrase_audition(
    window, qtbot, null_synth, many_measures_score
):
    load_and_wait(window, qtbot, many_measures_score)
    no_lead_in(window)
    null_synth.played.clear()

    qtbot.keyClick(window.region_3, Qt.Key.Key_Return)

    assert window.sequencer.is_playing is True
    assert null_synth.played[0]["midi_notes"] == [60]


def test_phrase_audition_stops_at_the_end_of_the_next_measure(
    window, qtbot, null_synth, many_measures_score
):
    load_and_wait(window, qtbot, many_measures_score)
    no_lead_in(window)
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
    no_lead_in(window)
    window.audition_phrase()
    assert window.sequencer.is_playing is True

    window.audition_phrase()

    assert window.sequencer.is_playing is False
    assert window._music_data.active_event_index == 0


def test_phrase_audition_from_the_last_measure_plays_to_the_end_of_the_piece(
    window, qtbot, null_synth, many_measures_score
):
    load_and_wait(window, qtbot, many_measures_score)
    no_lead_in(window)
    assert window._music_data.jump_to_measure(12) is True
    null_synth.played.clear()

    window.audition_phrase()

    assert null_synth.played[-1]["midi_notes"] == [79]  # G5, measure 12
    assert window._music_data.active_event_index == 11, "jump_to_measure moved it, not audition_phrase"
    assert window.sequencer.is_playing is True, "only one note left - still ringing out"

    qtbot.waitUntil(lambda: window.sequencer.is_playing is False, timeout=2000)


def test_preview_lead_in_counts_through_a_whole_bar_before_a_pickup_plays(
    window, qtbot, null_synth, score_bourree_full
):
    """Reported from real practice use, then corrected: previewing from
    inside score_bourree_full's anacrusis (a one-beat pickup in 4/4, its one
    real note notated at beat 4 - see tests/conftest.py's score_bourree_full)
    must play the requested lead-in bar in FULL ("1, 2, 3, 4"), then keep
    counting through the beats needed to complete the anacrusis into a
    whole bar ("1, 2, 3") before the pickup note itself sounds - never
    landing the count-in on the pickup's own notated beat straight away."""
    load_and_wait(window, qtbot, score_bourree_full)
    window.playback.set_preview_settings(PreviewSettings(lead_in_bars=1, lead_in_beats=0))
    assert window._music_data.active_event_index == 0  # already inside the pickup

    window.audition_phrase()

    run = window.playback._preview
    assert run is not None and run.is_pickup is True
    counts = [action[1] for _, action in run.events if action[0] == "count"]
    assert counts == [1.0, 2.0, 3.0, 4.0, 1.0, 2.0, 3.0], (
        "one full lead-in bar, then the 3 beats needed to complete the pickup's own bar"
    )

    # The pickup starts right after that 7th click, with no further gap -
    # its one beat of real content exactly fills what the count-in left.
    beat_ms = 60000.0 / window._music_data.effective_tempo_bpm(0)
    play_offset = next(offset for offset, action in run.events if action[0] == "play")
    last_count_offset = max(offset for offset, action in run.events if action[0] == "count")
    assert play_offset == pytest.approx(last_count_offset + beat_ms, abs=1)


def test_preview_from_a_pickup_bar_does_not_wait_out_the_beats_it_replaces(
    window, qtbot, null_synth, score_bourree_full
):
    """A pickup bar's NOTIONAL start is before the piece begins, so
    MusicData.bar_bounds_quarters returns a NEGATIVE start for it
    (score_bourree_full's one-beat 4/4 anacrusis starts at -3.0 quarters).
    PlaybackController._refresh_preview_span clamps that at 0 before
    deriving offset_ms - the silent lead the preview waits through before
    the first note sounds - because looping a pickup must repeat the pickup
    NOTES, not the three empty beats the pickup replaces.

    Without the clamp offset_ms comes out at 1500ms here (3 quarters at
    120bpm): a second and a half of silence at the top of every loop
    iteration. Nothing else in the suite pins this - the sibling lead-in
    tests above assert count-in timing RELATIVE to the play offset, so they
    stay green either way, and the clamp survived an S8 dead-code sweep only
    because it was read closely (its duplicate in _build_preview_run really
    was dead and was removed). Hence this test.
    """
    load_and_wait(window, qtbot, score_bourree_full)
    window.playback.set_preview_settings(PreviewSettings(lead_in_bars=0, lead_in_beats=0))
    assert window._music_data.active_event_index == 0  # already inside the pickup

    window.audition_phrase()

    run = window.playback._preview
    assert run is not None
    assert run.is_pickup is True, "bar_bounds_quarters must report a negative bar start here"
    assert run.offset_ms == 0, (
        "a pickup preview starts on its own first note - it must not wait out "
        "the beats the anacrusis replaces"
    )


def test_preview_lead_in_pads_a_fractional_pickup_with_a_silent_remainder(
    window, qtbot, null_synth, score_bourree_full
):
    """A pickup that starts mid-beat can't have its remainder clicked -
    audio/metronome.py's click_event_for_beat only fires on whole beats -
    so after the whole completing beats are counted, the leftover fraction
    of a beat is a silent wait before the note itself, not another click."""
    load_and_wait(window, qtbot, score_bourree_full)
    window.playback.set_preview_settings(PreviewSettings(lead_in_bars=1, lead_in_beats=0))
    md = window._music_data
    md.timeline_slices[0].beat_position = 2.5  # a 1.5-beat pickup in 4/4
    md.tempo_bpm = 120

    window.audition_phrase()

    run = window.playback._preview
    counts = [action[1] for _, action in run.events if action[0] == "count"]
    assert counts == [1.0, 2.0, 3.0, 4.0, 1.0], "one whole completing beat (2.5 - 1 = 1.5, floor 1)"

    # 4 lead-in beats + the full 1.5-beat gap (1 clicked, 0.5 silent) to
    # reach the real note - the fractional part can't be a click, but it
    # still has to elapse before the note sounds.
    beat_ms = 60000.0 / 120.0
    play_offset = next(offset for offset, action in run.events if action[0] == "play")
    assert play_offset == pytest.approx((4 + 1.5) * beat_ms, abs=1)


# --- Repeat/D.C./D.S./Coda-aware Preview ---------------------------------

def test_preview_jump_lower_bound_is_wired_to_the_preview_windows_start(
    window, qtbot, dc_plain_score
):
    """The bound that keeps Preview from following a jump outside its own
    short window (see MusicData.next_playback_index/PlaybackController.
    _fire_preview_event): the Sequencer run this starts must receive
    jump_lower_bound=run.start_index, not 0 - a D.C. reached while
    previewing measure 2 alone must never be able to land back on measure
    1, which sits outside the previewed window."""
    load_and_wait(window, qtbot, dc_plain_score)
    no_lead_in(window)
    assert window._music_data.jump_to_measure(2) is True

    window.audition_phrase()

    run = window.playback._preview
    assert run is not None and run.start_index != 0
    assert window.sequencer._jump_lower_bound == run.start_index


def test_preview_loop_timing_accounts_for_a_repeat_fully_inside_the_window(
    window, qtbot, repeat_ending_then_dc_al_coda_score
):
    """Bug fix: iteration_ms (which schedules the loop-restart timer) used
    to come from a flat, jump-unaware walk (span_ms_to_quarters) - with a
    repeat fully inside the previewed 4 bars (the repeat+1st/2nd-ending
    shape, measures 1-4), the REAL Sequencer run replays measures 2-3 an
    extra time, taking longer than that flat walk predicts (8000ms) would
    account for. playback_span_ms fixes this by simulating the same
    jump-aware walk: m1->D4 (2000) + D4->D5 (1000) + D5->E (1000) + [repeat
    retake: E's own duration, 2000] + D4->D5 second pass (1000) + [ending-
    skip: D5's own duration, 1000, instead of the raw quarters gap to
    measure 4] + measure 4 to end_quarters=16.0 (2000) = 10000ms total
    (independently verified via MusicData.playback_span_ms directly)."""
    load_and_wait(window, qtbot, repeat_ending_then_dc_al_coda_score)
    no_lead_in(window, preview_bars=4)
    md = window._music_data
    assert md.active_event_index == 0  # measure 1, already the default

    window.audition_phrase()

    run = window.playback._preview
    assert (run.start_index, run.end_index) == (0, 4)
    assert run.end_quarters == 16.0
    assert run.iteration_ms == 10000, "must be the jump-aware duration, not the flat 8000ms"


def test_preview_loop_restart_timing_tracks_a_tempo_change_made_mid_loop(
    window, qtbot, repeat_ending_then_dc_al_coda_score
):
    """Reported live: speeding up (F, Ref 12) while a repeat-containing
    passage was already looping in Preview left the loop-restart drifting
    out of time - it kept using the span computed at whatever tempo was in
    force when Enter was first pressed. iteration_ms/offset_ms (the loop-
    restart's own timing) used to be computed once in _build_preview_run and
    never touched again, unlike the lead-in count-in's own bpm, which was
    already re-derived every iteration (see _start_preview_iteration's own
    comment). _refresh_preview_span now reruns that same computation at the
    top of every _start_preview_iteration call - simulated here the same
    way a real loop repeat would trigger it, without waiting on a real
    QTimer."""
    load_and_wait(window, qtbot, repeat_ending_then_dc_al_coda_score)
    no_lead_in(window, preview_bars=4, loop=True)
    window.audition_phrase()

    run = window.playback._preview
    assert run.iteration_ms == 10000, "sanity check at the starting tempo (120bpm)"

    window._music_data.tempo_bpm = 240  # double speed
    window.playback._start_preview_iteration(with_lead_in=False)  # what a loop repeat triggers

    assert run.iteration_ms == 5000, "must reflect the new tempo, not the stale one from Enter"


# --- Alt+PageUp/PageDown: adjust preview length -------------------------

def test_alt_page_up_and_down_adjust_the_preview_length_by_one_bar(
    window, qtbot, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    assert window.playback.preview_settings.preview_bars == 2

    qtbot.keyClick(window.region_3, Qt.Key.Key_PageUp, Qt.KeyboardModifier.AltModifier)

    assert window.playback.preview_settings.preview_bars == 3
    assert window.status_bar._fields[7].text() == "Preview length: 3 measures"

    qtbot.keyClick(window.region_3, Qt.Key.Key_PageDown, Qt.KeyboardModifier.AltModifier)
    qtbot.keyClick(window.region_3, Qt.Key.Key_PageDown, Qt.KeyboardModifier.AltModifier)

    assert window.playback.preview_settings.preview_bars == 1
    assert window.status_bar._fields[7].text() == "Preview length: 1 measures"


def test_alt_page_down_cannot_go_below_one_bar(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)

    for _ in range(5):
        qtbot.keyClick(window.region_3, Qt.Key.Key_PageDown, Qt.KeyboardModifier.AltModifier)

    assert window.playback.preview_settings.preview_bars == 1


def test_alt_page_up_has_no_practical_upper_cap(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)

    for _ in range(50):
        qtbot.keyClick(window.region_3, Qt.Key.Key_PageUp, Qt.KeyboardModifier.AltModifier)

    assert window.playback.preview_settings.preview_bars == 52


def test_bare_page_up_down_leaves_the_preview_length_untouched(window, qtbot, minimal_score):
    """No Alt: that's QListWidget's own native paging, not this feature -
    the same reasoning bare Left/Right vs Ctrl+Left/Right already has."""
    load_and_wait(window, qtbot, minimal_score)

    qtbot.keyClick(window.region_3, Qt.Key.Key_PageUp)
    qtbot.keyClick(window.region_3, Qt.Key.Key_PageDown)

    assert window.playback.preview_settings.preview_bars == 2


def test_alt_page_up_persists_the_new_length_globally(window, qtbot, minimal_score):
    """Same persistence as the Preview Settings dialog's OK - a bar count
    set this way is a practice habit that should follow the user, not just
    stay live for this session."""
    load_and_wait(window, qtbot, minimal_score)

    qtbot.keyClick(window.region_3, Qt.Key.Key_PageUp, Qt.KeyboardModifier.AltModifier)

    assert app_settings.load().preview.preview_bars == 3


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
    no_lead_in(window)
    position_before = window.status_bar._fields[0].text()

    window.audition_phrase()

    assert window.status_bar._fields[4].text() == "Playback: Preview"
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
