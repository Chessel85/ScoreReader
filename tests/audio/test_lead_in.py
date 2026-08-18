"""The Preview count-in schedule (audio/lead_in.py).

Pure timing maths - no Qt, no synth, no window, which is the whole reason
it lives outside controllers/playback_controller.py.
"""
from audio.lead_in import build_lead_in_schedule
from audio.metronome import METRONOME_ACCENT_NOTE, METRONOME_OFFBEAT_NOTE, click_event_for_beat


def test_no_lead_in_produces_no_clicks_and_no_wait():
    assert build_lead_in_schedule(0, 0, 4, 4, 120.0) == ([], 0)


def test_one_bar_of_four_four_counts_four_beats_at_the_quarter():
    clicks, total_ms = build_lead_in_schedule(1, 0, 4, 4, 120.0)

    # 120 quarter-BPM = 500ms a beat.
    assert [offset for offset, _ in clicks] == [0, 500, 1000, 1500]
    assert [beat for _, beat in clicks] == [1.0, 2.0, 3.0, 4.0]
    # The preview starts a beat after the last click, not on it.
    assert total_ms == 2000


def test_extra_beats_are_added_on_top_of_whole_bars():
    clicks, _ = build_lead_in_schedule(1, 2, 4, 4, 120.0)

    assert len(clicks) == 6
    # Counted backwards from the downbeat, so it reads "3 4 1 2 3 4" - the
    # count-in lands in step with the bar it is leading into.
    assert [beat for _, beat in clicks] == [3.0, 4.0, 1.0, 2.0, 3.0, 4.0]


def test_a_beat_is_the_time_signature_denominator_not_a_quarter():
    """Ref 18: 6/8 counts six eighths, each half the length of a quarter."""
    clicks, total_ms = build_lead_in_schedule(1, 0, 6, 8, 120.0)

    assert len(clicks) == 6
    assert [offset for offset, _ in clicks] == [0, 250, 500, 750, 1000, 1250]
    assert total_ms == 1500


def test_seven_eight_wraps_beat_numbers_at_the_bar_length():
    clicks, _ = build_lead_in_schedule(1, 1, 7, 8, 120.0)

    assert [beat for _, beat in clicks] == [7.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]


def test_counting_into_a_preview_that_starts_off_the_downbeat():
    """A pickup bar's first event is not beat 1 (Ref 17), so the count-in
    has to end on the beat before wherever the preview actually starts."""
    clicks, _ = build_lead_in_schedule(1, 0, 4, 4, 120.0, start_beat_position=3.0)

    assert [beat for _, beat in clicks] == [3.0, 4.0, 1.0, 2.0]


def test_every_scheduled_beat_produces_a_click_with_beat_one_accented():
    """The schedule and audio/metronome.py have to agree on what a beat is:
    a fractional position would silently click nothing at all."""
    clicks, _ = build_lead_in_schedule(2, 0, 4, 4, 90.0)

    events = [click_event_for_beat(beat) for _, beat in clicks]
    assert all(event is not None for event in events)
    pitches = [event[3] for event in events]
    assert pitches == [METRONOME_ACCENT_NOTE] + [METRONOME_OFFBEAT_NOTE] * 3 + \
        [METRONOME_ACCENT_NOTE] + [METRONOME_OFFBEAT_NOTE] * 3


def test_a_slower_tempo_spaces_the_count_further_apart():
    _, fast = build_lead_in_schedule(1, 0, 4, 4, 120.0)
    _, slow = build_lead_in_schedule(1, 0, 4, 4, 60.0)

    assert slow == fast * 2
