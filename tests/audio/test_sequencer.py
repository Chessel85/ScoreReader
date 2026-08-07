# tests/audio/test_sequencer.py
"""E4: Sequencer scheduling, driven entirely with FakeTimer/NullSynth so no
real wall-clock wait or audio device is ever involved (mirrors D-7's
constructor-injection pattern, extended to the timer)."""
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


def test_playback_stops_and_emits_finished_at_the_last_event(timeline, null_synth, minimal_score):
    md = timeline(minimal_score, tempo_bpm=120)
    seq, timer = _build(md, null_synth)
    finished = []
    seq.finished.connect(lambda: finished.append(True))

    seq.play_from(0)
    for _ in range(3):
        timer.fire()

    assert [p["midi_notes"] for p in null_synth.played] == [[60], [62], [64], [65]]
    assert finished == [True]
    assert seq.is_playing is False
    assert timer.scheduled_ms == [500, 500, 500]  # no further schedule after the last note


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
    timer.fire()  # plays index 1, then must stop - end_index reached

    assert [p["midi_notes"] for p in null_synth.played] == [[60], [62]]
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


def test_tempo_offset_changed_mid_playback_affects_the_next_scheduled_delay(
    timeline, null_synth, minimal_score
):
    md = timeline(minimal_score, tempo_bpm=120)
    seq, timer = _build(md, null_synth)

    seq.play_from(0)  # schedules index0->1 at 120bpm: 500ms
    md.set_playback_tempo_offset(120)  # effective tempo now 240bpm
    timer.fire()  # index1->2 delay computed fresh, at the new tempo

    assert timer.scheduled_ms == [500, 250]


def test_mid_score_tempo_change_affects_delays_from_the_point_it_takes_effect(
    timeline, null_synth, tempo_change_score
):
    """Ref 12 "multi-tempo scope": tempo_change_score goes quarter=100 in
    measure 1 to quarter=200 in measure 2. The delay leaving measure 1's
    last note must still use the old (100) tempo - the new marking takes
    effect starting at measure 2's first note, not before it - and every
    delay inside measure 2 must use the new (200) tempo."""
    md = timeline(tempo_change_score)
    seq, timer = _build(md, null_synth)

    seq.play_from(0)  # C, measure 1 - schedules the C->D delay
    assert timer.scheduled_ms == [600]  # 1 quarter at 100bpm
    timer.fire()  # now D - schedules D->E
    timer.fire()  # now E - schedules E->F
    timer.fire()  # now F - schedules F->G, still measure 1's tempo (100)

    assert timer.scheduled_ms[-1] == 600, "the boundary delay uses the tempo active before it, not after"

    timer.fire()  # now G, measure 2 - schedules G->A at the new tempo (200)
    assert timer.scheduled_ms[-1] == 300  # 1 quarter at 200bpm


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
