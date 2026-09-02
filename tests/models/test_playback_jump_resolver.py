# tests/models/test_playback_jump_resolver.py
"""Pure MusicData.next_playback_index / PlaybackJumpState tests - repeat/
ending/Segno/Coda/D.C./D.S./Fine-aware playback stepping, built directly
against MusicData(file_path=...) (the fast ElementTree-only path, no
music21, no Sequencer/QTimer at all) so these stay pure unit tests of the
resolver itself. Sequencer-level wiring is covered separately in
tests/audio/test_sequencer.py, and Preview-level wiring in
tests/test_main_window.py.

Each fixture's own doc comment (tests/fixtures/*.musicxml) spells out the
expected step sequence in prose; the assertions here just walk
next_playback_index and check it matches.
"""
from models.event_slice import EventSlice
from models.music_data import MusicData
from models.note_data import NoteData
from models.playback_jump_state import PlaybackJumpState


def _walk(md, start_index=0, end_index=None, jump_lower_bound=0, guard=40):
    """Drives next_playback_index to exhaustion, like Sequencer does one
    step at a time, and returns the full list of visited indices."""
    jump_state = PlaybackJumpState()
    seq = [start_index]
    idx = start_index
    while guard > 0:
        guard -= 1
        nxt = md.next_playback_index(idx, jump_state, end_index, jump_lower_bound)
        if nxt is None:
            break
        seq.append(nxt)
        idx = nxt
    return seq


def test_no_jump_marks_matches_next_visible_event_index(timeline, minimal_score):
    """The core invariant: a score with none of these marks must behave
    identically to the plain, stateless next_visible_event_index - every
    new list is empty, so every resolver check is a no-op."""
    md = timeline(minimal_score)
    jump_state = PlaybackJumpState()

    idx = 0
    while idx is not None:
        via_resolver = md.next_playback_index(idx, jump_state)
        via_plain = md.next_visible_event_index(idx)
        assert via_resolver == via_plain
        idx = via_plain


def test_plain_dc_fires_once_then_plays_to_the_end(timeline, dc_plain_score):
    md = timeline(dc_plain_score)
    assert _walk(md) == [0, 1, 0, 1]


def test_dc_al_fine_stops_at_fine_not_the_physical_end(timeline, dc_al_fine_score):
    md = timeline(dc_al_fine_score)
    assert _walk(md) == [0, 1, 2, 0]


def test_dc_al_coda_diverts_to_the_coda_tail(timeline, dc_al_coda_score):
    md = timeline(dc_al_coda_score)
    assert _walk(md) == [0, 1, 2, 0, 1, 3]


def test_dacapo_targets_the_pickup_bar_not_measure_one(timeline, dc_with_pickup_score):
    md = timeline(dc_with_pickup_score)
    assert md.timeline_slices[0].measure == 0  # sanity: this is really the pickup
    assert _walk(md) == [0, 1, 2, 0, 1, 2]


def test_ds_targets_the_segno_not_the_piece_start(timeline, ds_plain_score):
    md = timeline(ds_plain_score)
    assert _walk(md) == [0, 1, 2, 1, 2]


def test_ds_al_fine_stops_at_fine(timeline, ds_al_fine_score):
    md = timeline(ds_al_fine_score)
    assert _walk(md) == [0, 1, 2, 3, 1, 2]


def test_ds_al_coda_diverts_to_the_coda_tail(timeline, ds_al_coda_score):
    md = timeline(ds_al_coda_score)
    assert _walk(md) == [0, 1, 2, 3, 1, 2, 4]


def test_multi_coda_label_matching_skips_the_decoy(timeline, multi_coda_labels_score):
    """The decoy coda (measure 4, label "1") must never be visited - only
    the labelled-"2" coda (measure 5) the tocoda="2" mark actually points
    at."""
    md = timeline(multi_coda_labels_score)
    seq = _walk(md)
    assert seq == [0, 1, 2, 0, 1, 4]
    assert 3 not in seq  # measure 4's decoy coda


def test_text_only_fallback_with_no_sound_element(timeline, text_only_jump_marks_score):
    md = timeline(text_only_jump_marks_score)
    assert md.navigation_jumps and md.navigation_jumps[0].kind == "dalsegno"
    assert md.segno_marks and md.segno_marks[0].label == "1"
    assert md.to_coda_marks and md.to_coda_marks[0].label == ""
    assert md.coda_marks and md.coda_marks[0].label == ""
    assert _walk(md) == [0, 1, 2, 3, 1, 2, 4]


def test_repeat_and_ending_not_retaken_after_dc_fires(
    timeline, repeat_ending_then_dc_al_coda_score
):
    """End-to-end: the repeat/1st-2nd-ending is taken once as normal, then
    once the D.C. fires, the repeat is not retaken and ending 1's content
    (index 3, measure 3) is never visited again."""
    md = timeline(repeat_ending_then_dc_al_coda_score)
    seq = _walk(md)
    assert seq == [0, 1, 2, 3, 1, 2, 4, 5, 6, 0, 1, 2, 4, 5, 7]
    assert seq.count(3) == 1  # ending 1's content sounds exactly once


def test_jump_lower_bound_rejects_an_out_of_window_backward_target(
    timeline, dc_plain_score
):
    """The bound that makes Preview safe: a D.C. whose target falls before
    jump_lower_bound is silently skipped, falling through to plain linear
    stepping - exactly Preview's "short window, jump ignored" case."""
    md = timeline(dc_plain_score)
    # Preview-style call: window is [1, 1] (measure 2 only), so the dacapo
    # target (measure 1, index 0) falls below jump_lower_bound.
    seq = _walk(md, start_index=1, end_index=1, jump_lower_bound=1)
    assert seq == [1]  # the dacapo jump never fires; nothing left in-window


def test_last_step_was_jump_flags_every_kind_of_jump(
    timeline, repeat_ending_then_dc_al_coda_score
):
    """PlaybackJumpState.last_step_was_jump is what tells Sequencer to
    retrigger (stop_all_notes()) instead of layering the new note over the
    departing one - must be True for a repeat retake, an ending-skip
    redirect, and a D.C./D.S./Coda jump, and False for every ordinary
    forward step."""
    md = timeline(repeat_ending_then_dc_al_coda_score)
    jump_state = PlaybackJumpState()

    idx = 0
    flags = []
    for _ in range(14):
        idx = md.next_playback_index(idx, jump_state)
        flags.append(jump_state.last_step_was_jump)

    jump_positions = [i + 1 for i, was_jump in enumerate(flags) if was_jump]
    assert jump_positions == [4, 6, 9, 12, 14]


def test_playback_span_ms_detects_a_jump_whose_trigger_is_exactly_end_index(
    timeline, repeats_and_endings_score
):
    """Reported bug, live-tested (carcassi-etudes-1.mxl, whose repeats are
    exactly as many bars as Preview's own default length - a very common
    real-world alignment): a repeat's closing measure is often exactly the
    LAST bar of a preview window. playback_span_ms's walk used to stop the
    instant it reached end_index, before ever calling next_playback_index
    FOR end_index itself - which is exactly where a repeat closing there
    would be detected. That silently dropped the repeat from the duration
    estimate entirely (span_ms_to_quarters's flat 4000ms, not a jump-aware
    8000ms for two full passes), making Preview's loop-restart timer fire
    at HALF the real duration and cut the second pass off mid-replay -
    reported as "the last note before a repeat only plays for half its
    stated duration"."""
    md = timeline(repeats_and_endings_score, tempo_bpm=120)
    # Preview window: measure 2 to measure 3 (indices 1-3) - the repeat
    # (measures 2-3) closes exactly at end_index (3), same shape as
    # carcassi's real repeats relative to Preview's default 2-bar length.
    assert md.repeat_spans[0].end_measure == 3

    flat = md.span_ms_to_quarters(1, 12.0)
    jump_aware = md.playback_span_ms(1, 3, 12.0)

    assert flat == 4000, "sanity check on the flat (bug-reproducing) baseline"
    assert jump_aware == 8000, "must account for the repeat replaying measures 2-3"


def test_playback_span_ms_waits_out_the_final_notes_real_ring_not_just_the_bar_line():
    """Reported live: with Preview looping, the last note of the previewed
    span was cut short - similar in spirit to the repeat-landing-on-
    end_index bug above, but a plain single-pass case, no repeat involved.

    playback_span_ms's tail used to be purely the tempo-based distance from
    the final note's onset to the bar line (end_quarters), ignoring what
    the note would actually ring for. A short final note (here a 32nd at
    120bpm, nominally 62.5ms) is floored up to 100ms by _quarters_to_ms
    (the same floor get_playback_events_for_indices' duration_ms applies) -
    the REAL Sequencer run (whose ring_out_ms already uses that floored,
    per-part-max duration - see get_ring_out_ms_for_index) keeps sounding
    for 100ms after the note's onset, past the bar line. Preview's loop
    restart used to fire at the bar line (2000ms), calling stop_all_notes()
    and cutting that still-ringing note off early.

    2037, not the arithmetically-exact 2038 (3.875 * 500 = 1937.5 + 100 ring
    -out), because the leading step is truncated via int(), matching
    Sequencer._delay_ms_to's own per-step truncation exactly (see
    playback_span_ms's walk) rather than accumulating the unrounded float -
    a separate reported-live bug (sped up ~40bpm from a score's default
    tempo, a real repeat's loop-restart drifted audibly out of time; this
    single-note fixture just happens to also exercise that truncation).
    """
    md = MusicData(
        tempo_bpm=120,
        timeline_slices=[
            EventSlice(
                measure=1,
                beat_position=1.0,
                quarter_length=3.875,
                quarters_from_start=0.0,
                notes=[
                    NoteData(
                        step_name="C",
                        measure=1,
                        beat_position=1.0,
                        ts_duration=3.875,
                        quarter_length=3.875,
                        part_id="P1",
                        part_name="Test",
                        staff=1,
                        voice=1,
                        midi_pitch=60,
                    )
                ],
            ),
            EventSlice(
                measure=1,
                beat_position=3.875,
                quarter_length=0.125,
                quarters_from_start=3.875,
                notes=[
                    NoteData(
                        step_name="D",
                        measure=1,
                        beat_position=3.875,
                        ts_duration=0.125,
                        quarter_length=0.125,
                        part_id="P1",
                        part_name="Test",
                        staff=1,
                        voice=1,
                        midi_pitch=62,
                    )
                ],
            ),
        ],
    )

    bar_line_only = md.span_ms_to_quarters(0, 4.0)
    assert bar_line_only == 2000, "sanity check on the bar-line-only (bug-reproducing) baseline"

    assert md.get_ring_out_ms_for_index(1) == 100, "the 32nd note's real ring is floored to 100ms"
    assert md.playback_span_ms(0, 1, 4.0) == 2037, "must wait out the floored ring, not just the bar line"


def test_playback_span_ms_matches_a_real_sequencer_run_when_sped_up(
    timeline, null_synth, repeats_and_endings_score
):
    """Reported live, follow-up to the two tests above: with Preview
    looping on a passage containing a repeat, sped up ~40bpm from the
    score's default, the repeat "didn't sync quite right" - the loop was
    restarting a few ms later than the real Sequencer run it's meant to
    predict, an audible gap right before each repeat.

    Both playback_span_ms's per-step walk and its final tail used to
    accumulate/compare un-truncated floats, while Sequencer._delay_ms_to
    and get_ring_out_ms_for_index truncate every step via int() - fine at a
    tempo where every interval happens to land on a whole ms (120bpm here),
    but any tempo/subdivision combination that doesn't drifts the predicted
    total away from what the real run actually takes. Directly compares
    playback_span_ms's prediction against a real (FakeTimer-driven, so no
    wall-clock wait) Sequencer run through the same jump-aware window, at
    the default tempo and 40bpm faster.
    """
    from audio.sequencer import Sequencer
    from tests.support.fake_timer import FakeTimer

    def real_elapsed_ms(md, start_index, end_index):
        timer = FakeTimer()
        seq = Sequencer(md, null_synth, timer=timer)
        seq.play_from(start_index, end_index=end_index)
        total = 0
        while timer.running:
            total += timer.scheduled_ms[-1]
            timer.fire()
        return total

    start_index, end_index, end_quarters = 1, 3, 12.0
    for bpm in (120, 161):
        md = timeline(repeats_and_endings_score, tempo_bpm=bpm)
        predicted = md.playback_span_ms(start_index, end_index, end_quarters)
        real = real_elapsed_ms(md, start_index, end_index)
        assert predicted == real, f"drifted by {real - predicted}ms at {bpm}bpm"


def test_jump_lower_bound_allows_an_in_window_repeat(
    timeline, repeat_ending_then_dc_al_coda_score
):
    """The Preview-follows-a-contained-repeat case: a window spanning
    exactly the repeat+ending (measures 1-4, indices 0-4) still takes the
    repeat, since both the jump-off point and its target are in-window."""
    md = timeline(repeat_ending_then_dc_al_coda_score)
    seq = _walk(md, start_index=0, end_index=4, jump_lower_bound=0)
    assert seq == [0, 1, 2, 3, 1, 2, 4]


# --- simulate_loop_iteration (looped, repeat-aware, bar-budgeted) ----------


def _seed_second(md):
    """The 'repeat the second play-through' seed, mirroring
    PlaybackController._loop_seed_jump_state: every repeat consumed, every
    first-time ending (one spanning a repeat's backward barline) skipped."""
    endings_to_skip = {
        j
        for rs in md.repeat_spans
        for j, es in enumerate(md.ending_spans)
        if es.start_measure <= rs.end_measure <= es.end_measure
    }
    return PlaybackJumpState(
        repeats_taken=set(range(len(md.repeat_spans))),
        endings_to_skip=endings_to_skip,
        jump_taken=True,
    )


def _bars(md, indices):
    return [md.timeline_slices[i].measure for i in indices]


def test_simulate_loop_first_play_through_takes_the_clipped_repeat(
    timeline, repeats_and_endings_score
):
    """Loop from the forward-repeat bar (m2, index 1), length 4: the 'first'
    seed plays m2, m3 (ending 1), then the repeat sends it back to m2, then
    on to m4 - four distinct bar entries, the scaled-down analogue of the
    plan's '7, 8, 1, 2, 3, 4'."""
    md = timeline(repeats_and_endings_score)
    indices, span_ms, end_quarters = md.simulate_loop_iteration(1, 4, None)
    assert _bars(md, indices) == [2, 2, 3, 2, 2, 4]
    assert span_ms == 8000  # 120bpm, 4/4: four bars of real time
    assert end_quarters == 16.0


def test_simulate_loop_second_play_through_skips_the_first_time_ending(
    timeline, repeats_and_endings_score
):
    """Same window, the 'second' seed: the repeat is already spent and
    ending 1 (m3) is skipped, so it runs m2 straight to m4 - the analogue
    of the plan's '7, 9, 10, ...'."""
    md = timeline(repeats_and_endings_score)
    indices, span_ms, _end_quarters = md.simulate_loop_iteration(1, 4, _seed_second(md))
    assert _bars(md, indices) == [2, 2, 4]
    assert span_ms == 4000


def test_simulate_loop_alternates_between_the_two_seeds(
    timeline, repeats_and_endings_score
):
    md = timeline(repeats_and_endings_score)
    first = md.simulate_loop_iteration(1, 4, None)[0]
    second = md.simulate_loop_iteration(1, 4, _seed_second(md))[0]
    assert _bars(md, first) == [2, 2, 3, 2, 2, 4]
    assert _bars(md, second) == [2, 2, 4]


def test_simulate_loop_long_window_reproduces_normal_repeat_playback(
    timeline, repeats_and_endings_score
):
    """When the loop length is long enough that the repeat's target lies
    inside the window, the 'first' seed's walk matches a plain
    next_playback_index traversal of the whole piece - no special case."""
    md = timeline(repeats_and_endings_score)
    indices, _span_ms, _end_quarters = md.simulate_loop_iteration(0, 64, None)
    assert indices == _walk(md, start_index=0)


def test_simulate_loop_stops_early_at_the_end_of_the_timeline(
    timeline, repeats_and_endings_score
):
    """A budget larger than the piece stops at the last bar rather than
    walking off the end (the controller's loop timer then wraps and keeps
    looping)."""
    md = timeline(repeats_and_endings_score)
    indices, _span_ms, _end_quarters = md.simulate_loop_iteration(0, 999, None)
    assert indices[-1] == len(md.timeline_slices) - 1


def test_simulate_loop_does_not_mutate_the_seed_state(
    timeline, repeats_and_endings_score
):
    md = timeline(repeats_and_endings_score)
    seed = _seed_second(md)
    before = (set(seed.repeats_taken), set(seed.endings_to_skip), seed.jump_taken)
    md.simulate_loop_iteration(1, 4, seed)
    assert (set(seed.repeats_taken), set(seed.endings_to_skip), seed.jump_taken) == before
