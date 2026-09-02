# tests/audio/test_sequencer.py
"""E4: Sequencer scheduling, driven entirely with FakeTimer/NullSynth so no
real wall-clock wait or audio device is ever involved (mirrors D-7's
constructor-injection pattern, extended to the timer)."""
from audio.metronome import METRONOME_ACCENT_NOTE, METRONOME_OFFBEAT_NOTE
from audio.position_announcer import WORD_NOTES
from audio.sequencer import Sequencer
from tests.support.fake_timer import FakeTimer


def _build(music_data, null_synth):
    timer = FakeTimer()
    seq = Sequencer(music_data, null_synth, timer=timer)
    return seq, timer


def test_play_from_sounds_the_start_index_immediately(timeline, null_synth, minimal_score):
    md = timeline(minimal_score, tempo_bpm=120)
    seq, timer = _build(md, null_synth)

    seq.play_from(0)

    assert len(null_synth.played) == 1
    assert null_synth.played[0]["midi_notes"] == [60]  # C4
    assert seq.current_index == 0
    assert seq.is_playing is True
    assert timer.scheduled_ms == [500]  # 1 quarter at 120bpm


def test_firing_the_timer_advances_to_the_next_step(timeline, null_synth, minimal_score):
    md = timeline(minimal_score, tempo_bpm=120)
    seq, timer = _build(md, null_synth)
    seq.play_from(0)

    timer.fire()

    assert seq.current_index == 1
    assert null_synth.played[-1]["midi_notes"] == [62]  # D4
    assert timer.scheduled_ms == [500, 500]


def test_playback_waits_for_the_last_note_to_ring_out_before_finishing(
    timeline, null_synth, minimal_score
):
    """Reported bug, live-tested: finished() used to fire the instant the
    last note started sounding, not after it had rung out for its own
    duration - is_playing going False that early confused Space into
    trying to start a new run (hitting the boundary cue) instead of
    cleanly stopping. Now the last note's own duration_ms is scheduled as
    a genuine ring-out wait before is_playing flips and finished fires."""
    md = timeline(minimal_score, tempo_bpm=120)
    seq, timer = _build(md, null_synth)
    finished = []
    seq.finished.connect(lambda: finished.append(True))

    seq.play_from(0)
    for _ in range(3):
        timer.fire()

    assert [p["midi_notes"] for p in null_synth.played] == [[60], [62], [64], [65]]
    assert finished == [], "must not finish until the last note has rung out"
    assert seq.is_playing is True, "still \"playing\" during the ring-out wait"
    assert timer.scheduled_ms == [500, 500, 500, 500]  # ring-out wait for the last note

    timer.fire()  # the ring-out wait elapses

    assert finished == [True]
    assert seq.is_playing is False


def test_a_later_parts_new_attack_does_not_silence_an_earlier_parts_ringing_note(
    timeline, null_synth, staggered_two_part_entry_score
):
    """Reported bug, live-tested against Pachelbel's Canon: turning on
    Violin I (which enters on beats 2/4) was cutting Violin II/Viola/
    Cello's beat-1 minims short to one beat - "like Violin I was sending a
    MIDI off to the other parts". It was: SynthEngine.play_chord
    unconditionally called stop_all_notes() before every step, silencing
    whatever was still ringing from an earlier, unrelated part's slice.
    staggered_two_part_entry_score's Viola half note (beat 1, 2 beats) and
    Violin I quarter note (beat 2, its own EventSlice) reproduce this
    exactly - advancing onto Violin I's slice must not call
    stop_all_notes() again (retrigger=False for a natural advance)."""
    md = timeline(staggered_two_part_entry_score)
    seq, timer = _build(md, null_synth)

    seq.play_from(0)  # Viola's half note - play_from's own reposition clears the deck once
    stop_count_after_start = null_synth.stop_count

    timer.fire()  # Violin I's quarter note on beat 2 - a natural advance

    assert null_synth.stop_count == stop_count_after_start, (
        "Violin I's entry must not silence Viola's still-ringing half note"
    )
    assert [p["midi_notes"] for p in null_synth.played] == [[48], [69]], "Viola C3, then Violin I A4"


def test_reaching_the_end_naturally_reverts_to_the_original_start_index(
    timeline, null_synth, minimal_score
):
    """Ref 10 AC5 (user decision): reaching the end of a run on its own is
    still "stopping" from the listener's point of view, not a new position
    to land on - it reverts current_index the same way an explicit stop()
    does, rather than leaving the cursor on the last note played."""
    md = timeline(minimal_score, tempo_bpm=120)
    seq, timer = _build(md, null_synth)

    seq.play_from(1)  # start mid-piece, at D
    for _ in range(3):
        timer.fire()  # E, F, then the ring-out wait for F

    assert seq.current_index == 1
    assert seq.is_playing is False


def test_pause_freezes_the_index_and_silences_the_sounding_note(
    timeline, null_synth, minimal_score
):
    """Reported bug, live-tested: pause used to leave the current note
    ringing out on its own natural duration, which for a short note gave no
    audible confirmation that pause had done anything at all."""
    md = timeline(minimal_score, tempo_bpm=120)
    seq, timer = _build(md, null_synth)
    seq.play_from(0)
    timer.fire()  # now on index 1 (D)
    stop_count_before_pause = null_synth.stop_count

    seq.pause()

    assert seq.current_index == 1
    assert seq.is_playing is False
    assert seq.is_paused is True
    assert timer.running is False
    assert null_synth.stop_count == stop_count_before_pause + 1, (
        "pause must silence the currently-sounding note immediately"
    )


def test_resume_replays_the_paused_step_then_continues(timeline, null_synth, minimal_score):
    md = timeline(minimal_score, tempo_bpm=120)
    seq, timer = _build(md, null_synth)
    seq.play_from(0)
    timer.fire()  # index 1 (D)
    seq.pause()
    played_before_resume = len(null_synth.played)

    seq.resume()

    assert seq.is_playing is True
    assert seq.is_paused is False
    assert len(null_synth.played) == played_before_resume + 1
    assert null_synth.played[-1]["midi_notes"] == [62]  # D4 again - Ref 10 AC3
    assert timer.running is True  # scheduled onward to index 2


def test_stop_reverts_to_the_original_start_index_and_silences_notes(
    timeline, null_synth, minimal_score
):
    md = timeline(minimal_score, tempo_bpm=120)
    seq, timer = _build(md, null_synth)
    seq.play_from(2)  # start mid-piece, at E
    timer.fire()  # advance to F

    seq.stop()

    assert seq.current_index == 2
    assert seq.original_start_index == 2
    assert seq.is_playing is False
    assert seq.is_paused is False
    assert null_synth.stop_count >= 1
    assert timer.running is False


def test_end_index_bounds_playback_for_phrase_audition(timeline, null_synth, minimal_score):
    md = timeline(minimal_score, tempo_bpm=120)
    seq, timer = _build(md, null_synth)
    finished = []
    seq.finished.connect(lambda: finished.append(True))

    seq.play_from(0, end_index=1)
    timer.fire()  # plays index 1 (end_index) - now waits for its ring-out

    assert [p["midi_notes"] for p in null_synth.played] == [[60], [62]]
    assert finished == [], "must ring out index 1 before finishing"
    assert timer.running is True

    timer.fire()  # ring-out wait elapses

    assert finished == [True]
    assert timer.running is False


def test_update_cursor_flag_is_recorded_for_the_caller_to_read(timeline, null_synth, minimal_score):
    """The Sequencer itself never touches active_event_index - E5/E6 read
    this flag to decide whether to move the cursor as playback proceeds."""
    md = timeline(minimal_score, tempo_bpm=120)
    seq, timer = _build(md, null_synth)

    seq.play_from(0, update_cursor=False)

    assert seq.update_cursor is False
    assert md.active_event_index == 0  # untouched


def test_absolute_tempo_changed_mid_playback_affects_the_next_scheduled_delay(
    timeline, null_synth, minimal_score
):
    md = timeline(minimal_score, tempo_bpm=120)
    seq, timer = _build(md, null_synth)

    seq.play_from(0)  # schedules index0->1 at 120bpm: 500ms
    md.set_playback_tempo_display_bpm(240)  # absolute tempo now 240bpm
    timer.fire()  # index1->2 delay computed fresh, at the new tempo

    assert timer.scheduled_ms == [500, 250]


def test_playback_is_flat_across_an_internal_tempo_change(
    timeline, null_synth, tempo_change_score
):
    """Ref 12: playback is always flat now - the score's internal tempo
    markings are described (Region 5 / the report) but never sounded, so
    every scheduled delay uses the one absolute tempo regardless of
    position."""
    md = timeline(tempo_change_score)
    seq, timer = _build(md, null_synth)
    quarter_bpm = md.effective_playback_quarter_bpm()
    one_quarter_ms = round(60000 / quarter_bpm)

    seq.play_from(0)
    for _ in range(5):
        timer.fire()

    assert all(ms == one_quarter_ms for ms in timer.scheduled_ms), (
        "flat: every delay is one quarter at the absolute tempo"
    )


def test_metronome_click_layers_on_top_of_notes_when_enabled(
    timeline, null_synth, minimal_score
):
    """E8/Ref 14 AC1/AC2: minimal_score is four quarter notes in 4/4 - every
    note already lands on beat 1/2/3/4, so this exercises the click firing
    on top of real notes with no Part 3 synthetic markers involved."""
    md = timeline(minimal_score, tempo_bpm=120)
    md.set_metronome_enabled(True)
    seq, timer = _build(md, null_synth)

    seq.play_from(0)  # beat 1 - C

    assert len(null_synth.clicks) == 1
    assert null_synth.clicks[0]["pitch"] == METRONOME_ACCENT_NOTE, "beat 1 is accented"

    timer.fire()  # beat 2 - D

    assert len(null_synth.clicks) == 2
    assert null_synth.clicks[1]["pitch"] == METRONOME_OFFBEAT_NOTE, "not beat 1 - regular click"
    assert null_synth.played[-1]["midi_notes"] == [62], "the note still sounds alongside the click"


def test_sequencer_visits_a_silent_beat_marker_and_clicks_there(
    timeline, null_synth, sparse_beat_score
):
    """E9/Ref 14 AC1/AC4: sparse_beat_score's measure 2 is a single quarter
    note G on beat 1, then silence - with the metronome on, the Sequencer's
    own step walk must still visit beats 2/3/4 (no play_chord call there,
    nothing to play) and click on each."""
    md = timeline(sparse_beat_score, tempo_bpm=120)
    md.set_metronome_enabled(True)
    seq, timer = _build(md, null_synth)

    seq.play_from(4)  # G, measure 2 beat 1
    assert len(null_synth.played) == 1  # just the G
    assert len(null_synth.clicks) == 1  # not accented - beat 1 of measure 2, not the piece

    timer.fire()  # beat 2 marker - click only
    assert len(null_synth.played) == 1, "no note to play at a silent beat"
    assert len(null_synth.clicks) == 2
    assert null_synth.clicks[-1]["pitch"] == METRONOME_OFFBEAT_NOTE


def test_no_click_when_metronome_disabled(timeline, null_synth, minimal_score):
    md = timeline(minimal_score, tempo_bpm=120)
    seq, timer = _build(md, null_synth)

    seq.play_from(0)

    assert null_synth.clicks == []


def test_position_announcer_speaks_beats_alongside_notes(timeline, null_synth, minimal_score):
    """Ref 28 AC1: works independently of the metronome - minimal_score's
    four quarter notes land on beats 1-4, each speaking its own number."""
    md = timeline(minimal_score, tempo_bpm=120)
    md.set_position_announcer_enabled(True)
    seq, timer = _build(md, null_synth)

    seq.play_from(0)  # beat 1 - C
    assert len(null_synth.words) == 1
    assert null_synth.words[0]["pitch"] == WORD_NOTES["one"]
    assert null_synth.played[-1]["midi_notes"] == [60], "the note still sounds alongside the word"

    timer.fire()  # beat 2 - D
    assert len(null_synth.words) == 2
    assert null_synth.words[1]["pitch"] == WORD_NOTES["two"]


def test_click_and_position_announcer_both_fire_on_the_same_beat(
    timeline, null_synth, minimal_score
):
    """Ref 28 AC2: both can be on at once and must both actually sound -
    the whole reason play_word/play_click use separate channels/timers."""
    md = timeline(minimal_score, tempo_bpm=120)
    md.set_metronome_enabled(True)
    md.set_position_announcer_enabled(True)
    seq, timer = _build(md, null_synth)

    seq.play_from(0)  # beat 1 - accented click + "one"

    assert len(null_synth.clicks) == 1
    assert null_synth.clicks[0]["pitch"] == METRONOME_ACCENT_NOTE
    assert len(null_synth.words) == 1
    assert null_synth.words[0]["pitch"] == WORD_NOTES["one"]


def test_no_announcement_when_position_announcer_disabled(timeline, null_synth, minimal_score):
    md = timeline(minimal_score, tempo_bpm=120)
    seq, timer = _build(md, null_synth)

    seq.play_from(0)

    assert null_synth.words == []


def test_full_playback_follows_repeat_ending_and_dc_al_coda(
    timeline, null_synth, repeat_ending_then_dc_al_coda_score
):
    """Real Sequencer wiring (not just the pure resolver, see
    tests/models/test_playback_jump_resolver.py) - proves play_from actually
    steps through the repeat, skips ending 1's content on the second pass,
    and follows the D.C. al Coda jump. See the fixture's own doc comment for
    the full expected sequence."""
    md = timeline(repeat_ending_then_dc_al_coda_score, tempo_bpm=120)
    seq, timer = _build(md, null_synth)

    seq.play_from(0)
    visited = [seq.current_index]
    for _ in range(14):
        timer.fire()
        visited.append(seq.current_index)

    assert visited == [0, 1, 2, 3, 1, 2, 4, 5, 6, 0, 1, 2, 4, 5, 7]


def test_measure_budget_stops_the_run_after_n_distinct_bars(
    timeline, null_synth, repeats_and_endings_score
):
    """The looped respect-repeats path: play_from(measure_budget=N) ends the
    run once it has entered N distinct bars, not at a linear end_index. From
    m1 with budget 4 the run plays m1, m2, m3, then the repeat sends it back
    to m2 (a backward jump counts as a fresh bar entry) - four bar entries -
    and stops there rather than continuing on to m4."""
    md = timeline(repeats_and_endings_score, tempo_bpm=120)
    seq, timer = _build(md, null_synth)

    sounded = []
    seq.step_played.connect(sounded.append)

    seq.play_from(0, end_index=None, jump_lower_bound=0, measure_budget=4)
    guard = 30
    while timer.running and guard:
        guard -= 1
        timer.fire()

    assert sounded == [0, 1, 2, 3, 1, 2]
    assert seq.is_playing is False


def test_measure_budget_run_leaves_the_seed_jump_state_unmutated(
    timeline, null_synth, repeats_and_endings_score
):
    """initial_jump_state is a template the caller reuses across iterations
    (alternate mode) - play_from must take a copy, never mutate it."""
    from models.playback_jump_state import PlaybackJumpState

    md = timeline(repeats_and_endings_score, tempo_bpm=120)
    seq, timer = _build(md, null_synth)

    seed = PlaybackJumpState(repeats_taken={0}, endings_to_skip={0}, jump_taken=True)
    before = (set(seed.repeats_taken), set(seed.endings_to_skip), seed.jump_taken)

    seq.play_from(1, end_index=None, jump_lower_bound=0, initial_jump_state=seed, measure_budget=8)
    guard = 30
    while timer.running and guard:
        guard -= 1
        timer.fire()

    assert (set(seed.repeats_taken), set(seed.endings_to_skip), seed.jump_taken) == before


def test_a_repeat_jump_retriggers_but_ordinary_steps_do_not(
    timeline, null_synth, repeat_ending_then_dc_al_coda_score
):
    """Reported bug, live-tested against real scores (carcassi-etudes-1.mxl,
    bach-bourree-tab/score.xml): a step reached via a repeat/ending-skip/
    D.C./D.S./Coda jump is a reposition, not a natural continuation - it
    must call stop_all_notes() first (retrigger=True), same as play_from's
    own initial reposition, or the departing note's own scheduled note-off
    races the jump target's note-on and can briefly double-sound (an
    audible stutter right at the jump). An ordinary forward step must NOT
    retrigger (Ref 8/A8 - other parts keep ringing across an unrelated
    attack)."""
    md = timeline(repeat_ending_then_dc_al_coda_score, tempo_bpm=120)
    seq, timer = _build(md, null_synth)

    seq.play_from(0)  # index0 - play_from's own reposition: stop_count == 1
    assert null_synth.stop_count == 1

    stop_counts = [null_synth.stop_count]
    for _ in range(14):
        timer.fire()
        stop_counts.append(null_synth.stop_count)

    # Jumps land on steps 4 (repeat retake), 6 (ending-skip to m4), 9
    # (D.C. fires), 12 (ending-skip again, not retaken) and 14 (To Coda) -
    # see the fixture's own doc comment for the full index sequence
    # (0,1,2,3, 1,2,4, 5,6, 0,1,2, 4,5, 7). Every other step must be a
    # plain, non-retriggering advance.
    retriggered_at = [i for i in range(1, len(stop_counts)) if stop_counts[i] != stop_counts[i - 1]]
    assert retriggered_at == [4, 6, 9, 12, 14]


def test_backward_jump_lets_the_departing_note_ring_its_own_duration(
    timeline, null_synth, dc_plain_score
):
    """Bug fix: a repeat/D.C./D.S./Coda jump lands at or before the current
    position in elapsed-quarters, which the plain delta-quarters formula
    turns negative - max(1, negative) used to collapse that to a 1 ms
    delay, clipping the departing note almost instantly instead of letting
    it ring its own whole-note duration (2000 ms at 120bpm) before the jump."""
    md = timeline(dc_plain_score, tempo_bpm=120)
    seq, timer = _build(md, null_synth)

    seq.play_from(0)  # index0 (C, measure 1) - schedules the delay to index1
    timer.fire()  # now index1 (D, measure 2, carries the D.C. mark)

    # The jump back to index0 is what's now scheduled - its delay must be
    # the departing note's own ring-out duration, not the 1 ms floor.
    assert timer.scheduled_ms[-1] == 2000
    assert seq.current_index == 1


def test_forward_skip_jump_also_uses_the_departing_notes_own_duration(
    timeline, null_synth, repeat_ending_then_dc_al_coda_score
):
    """Reported bug, live-tested against bach-bourree-tab/score.xml: an
    ending-skip (or a To Coda redirect) moves FORWARD in elapsed-quarters,
    skipping over unplayed content - the old delta_quarters<=0 check only
    caught BACKWARD jumps, so a forward skip fell through to the plain
    formula, which computed the raw quarters gap across the skipped content
    as if it were real elapsed silence: a spurious ~1-bar pause was
    reported right where the 2nd ending should start. The departing note's
    own duration is the only sensible delay here too, regardless of
    direction."""
    md = timeline(repeat_ending_then_dc_al_coda_score, tempo_bpm=120)
    seq, timer = _build(md, null_synth)

    seq.play_from(0)
    for _ in range(5):
        timer.fire()
    # Now at index2 (D5, measure 2, a half note - quarter_length 2.0, 1000ms
    # at 120bpm) - the next step is the ending-skip redirect straight to
    # measure 4, which must schedule D5's own 1000ms, not the raw quarters
    # gap to measure 4's downbeat (which would span the skipped measure 3
    # content as a spurious pause).
    assert seq.current_index == 2
    assert timer.scheduled_ms[-1] == 1000


def test_restarting_playback_while_already_playing_replaces_the_previous_run(
    timeline, null_synth, minimal_score
):
    md = timeline(minimal_score, tempo_bpm=120)
    seq, timer = _build(md, null_synth)
    seq.play_from(0)
    timer.fire()  # index 1

    seq.play_from(3)  # e.g. Enter re-triggering phrase audition (E6) elsewhere

    assert seq.current_index == 3
    assert seq.original_start_index == 3
    assert null_synth.played[-1]["midi_notes"] == [65]  # F4
