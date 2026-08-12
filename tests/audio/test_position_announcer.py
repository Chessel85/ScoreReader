# tests/audio/test_position_announcer.py
"""Ref 28: spoken_word_for_beat_position/announcement_event_for_beat are the
one rule both the Sequencer (playback) and MainWindow (navigation) use to
decide whether/what a beat position speaks - pure functions, tested in
isolation, mirroring tests/audio/test_metronome.py's own approach."""
from audio.position_announcer import (
    POSITION_ANNOUNCER_BANK,
    POSITION_ANNOUNCER_CHANNEL,
    POSITION_ANNOUNCER_PROGRAM,
    POSITION_ANNOUNCER_VELOCITY,
    WORD_NOTES,
    announcement_event_for_beat,
    spoken_word_for_beat_position,
)


def test_whole_beats_one_through_seven_speak_their_number_word():
    expected = ["one", "two", "three", "four", "five", "six", "seven"]
    for beat, word in zip(range(1, 8), expected):
        assert spoken_word_for_beat_position(float(beat)) == word


def test_whole_beat_eight_is_not_covered():
    """AC3 only defines beats 1-7."""
    assert spoken_word_for_beat_position(8.0) is None


def test_four_semiquavers_from_the_start_of_a_bar():
    """User-supplied worked example: 4 semiquavers starting at the start of
    a bar are announced one, e, and, a."""
    assert spoken_word_for_beat_position(1.0) == "one"
    assert spoken_word_for_beat_position(1.25) == "e"
    assert spoken_word_for_beat_position(1.5) == "and"
    assert spoken_word_for_beat_position(1.75) == "a"


def test_three_quavers_in_six_eight_from_the_start_of_a_bar():
    """User-supplied worked example: 3 quavers in 6/8 time from the start
    of a bar are spoken 1, 2, 3."""
    assert spoken_word_for_beat_position(1.0) == "one"
    assert spoken_word_for_beat_position(2.0) == "two"
    assert spoken_word_for_beat_position(3.0) == "three"


def test_triplet_starting_on_beat_two_in_four_four():
    """User-supplied worked example: a triplet starting on beat 2 in 4/4
    time is announced 2, and, a."""
    assert spoken_word_for_beat_position(2.0) == "two"
    assert spoken_word_for_beat_position(2.33) == "and"
    assert spoken_word_for_beat_position(2.67) == "a"


def test_unsupported_part_beat_fraction_is_not_announced():
    """AC4 only defines the 25/33/50/66/75% family - a subdivision outside
    that (e.g. a demisemiquaver's 12.5%) stays silent rather than guessing."""
    assert spoken_word_for_beat_position(1.125) is None


def test_announcement_event_for_beat_returns_none_when_no_word_applies():
    assert announcement_event_for_beat(1.125) is None
    assert announcement_event_for_beat(8.0) is None


def test_announcement_event_for_beat_uses_the_reserved_channel_and_word_notes():
    channel, bank, program, pitch, velocity = announcement_event_for_beat(1.0)
    assert channel == POSITION_ANNOUNCER_CHANNEL
    assert bank == POSITION_ANNOUNCER_BANK
    assert program == POSITION_ANNOUNCER_PROGRAM
    assert pitch == WORD_NOTES["one"]
    assert velocity == POSITION_ANNOUNCER_VELOCITY


def test_position_announcer_channel_differs_from_metronome_channel():
    """The whole reason for a dedicated channel (see the module's own
    comment): a click and a word landing on the same beat must not share a
    (channel, key) pair."""
    from audio.metronome import METRONOME_CHANNEL

    assert POSITION_ANNOUNCER_CHANNEL != METRONOME_CHANNEL
