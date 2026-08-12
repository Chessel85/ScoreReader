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
