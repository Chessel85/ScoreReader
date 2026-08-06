# tests/models/test_music_data.py
"""Harness proof for the timeline model.

The real characterisation suite is A2. These tests exist to show the
ElementTree-only path works and is wired up correctly.
"""
from models.music_data import MusicData
from models.parts_structure import PartStructureInfo


def test_minimal_score_yields_one_slice_per_note(timeline, minimal_score):
    md = timeline(minimal_score)

    assert len(md.timeline_slices) == 4
    assert [s.notes[0].step_name for s in md.timeline_slices] == ["C", "D", "E", "F"]


def test_complete_first_bar_is_measure_one(timeline, minimal_score):
    """A full opening bar must not be mistaken for a pickup (Ref 17)."""
    md = timeline(minimal_score)

    assert md.timeline_slices[0].measure == 1
    assert md.timeline_slices[0].beat_position == 1.0


def test_quarter_note_is_one_beat_unit_in_four_four(timeline, minimal_score):
    """Ref 18: durations are relative to the time signature denominator."""
    md = timeline(minimal_score)

    assert md.timeline_slices[0].notes[0].ts_duration == 1.0
    assert md.timeline_slices[0].notes[0].quarter_length == 1.0


def test_timeline_navigation_stops_at_both_boundaries(timeline, minimal_score):
    md = timeline(minimal_score)

    assert md.move_timeline_left() is False, "already at the first event"

    for _ in range(3):
        assert md.move_timeline_right() is True

    assert md.move_timeline_right() is False, "already at the last event"
    assert md.active_event_index == 3


def test_navigation_skips_slices_hidden_by_voice_filter(
    timeline, flute_crotchets_viola_semibreves_score
):
    """Deactivating the flute (Region 2) must let Right/Left step directly
    between the still-active viola's semibreves, not through the flute's
    crotchet-rate slices that no longer show any visible note."""
    md = timeline(flute_crotchets_viola_semibreves_score)

    viola_only = {("P2", 1, 1)}
    md.set_active_voice_filter(viola_only)

    assert md.active_event_index == 0  # bar 1, beat 1: flute+viola chord

    assert md.move_timeline_right() is True
    assert md.active_event_index == 4  # bar 2, beat 1 - not beat 2/3/4 of bar 1
    assert md.get_region_3_data() == ["E"]

    assert md.move_timeline_right() is False, "no more visible viola events"

    assert md.move_timeline_left() is True
    assert md.active_event_index == 0
    assert md.get_region_3_data() == ["C"]


def test_region_3_shows_rest_as_the_word_rest(timeline, rest_score):
    """A5: Region 3 needs no special-casing - a rest's step_name IS "rest"."""
    md = timeline(rest_score)
    md.active_event_index = 1  # C, rest, E, F

    assert md.get_region_3_data() == ["rest"]


def test_region_4_omits_octave_and_midi_rows_for_a_rest(timeline, rest_score):
    md = timeline(rest_score)
    md.active_event_index = 1

    data = md.get_region_4_data_for_indices([0])

    assert data["step"] == "rest"
    assert "octave" not in data
    assert "midi" not in data


def test_playback_stays_silent_on_a_rest(timeline, rest_score):
    """get_midi_notes_for_indices must drop None pitches so a rest plays nothing."""
    md = timeline(rest_score)
    md.active_event_index = 1

    assert md.get_midi_notes_for_indices([0]) == []


def test_measure_numbers_lists_each_measure_once_in_order(timeline, ts_change_score):
    md = timeline(ts_change_score)

    assert md.measure_numbers() == [1, 2, 3]


def test_first_event_index_of_measure_finds_the_first_slice_in_that_bar(timeline, ts_change_score):
    md = timeline(ts_change_score)

    assert md.first_event_index_of_measure(1) == 0
    assert md.first_event_index_of_measure(2) == 4
    assert md.first_event_index_of_measure(3) == 8


def test_first_event_index_of_measure_returns_none_for_an_unknown_bar(timeline, ts_change_score):
    """Ref 6: an unknown bar plays an error sound and does not move."""
    md = timeline(ts_change_score)

    assert md.first_event_index_of_measure(99) is None


def test_last_event_index_is_the_final_slice(timeline, ts_change_score):
    md = timeline(ts_change_score)

    assert md.last_event_index() == len(md.timeline_slices) - 1 == 11


def test_last_event_index_is_minus_one_when_timeline_is_empty(timeline):
    md = timeline("")

    assert md.timeline_slices == []
    assert md.last_event_index() == -1


def test_move_timeline_right_by_measure_jumps_to_first_event_of_next_bar(timeline, ts_change_score):
    """Ctrl+Right (C2, Ref 3): always lands on the next bar's first event,
    regardless of which beat of the current bar the cursor started on."""
    md = timeline(ts_change_score)
    md.active_event_index = 2  # measure 1, not its first event

    assert md.move_timeline_right_by_measure() is True
    assert md.active_event_index == 4  # first event of measure 2


def test_move_timeline_right_by_measure_stops_at_the_last_measure(timeline, ts_change_score):
    md = timeline(ts_change_score)
    md.active_event_index = 8  # first event of measure 3, the last measure

    assert md.move_timeline_right_by_measure() is False, "already at the last measure"
    assert md.active_event_index == 8


def test_move_timeline_left_by_measure_goes_to_the_start_of_the_current_bar_first(timeline, ts_change_score):
    md = timeline(ts_change_score)
    md.active_event_index = 6  # measure 2, not its first event

    assert md.move_timeline_left_by_measure() is True
    assert md.active_event_index == 4  # first event of measure 2, same bar


def test_move_timeline_left_by_measure_goes_to_the_previous_bar_once_already_at_the_start(timeline, ts_change_score):
    md = timeline(ts_change_score)
    md.active_event_index = 4  # already the first event of measure 2

    assert md.move_timeline_left_by_measure() is True
    assert md.active_event_index == 0  # first event of measure 1


def test_move_timeline_left_by_measure_stops_at_the_first_measure(timeline, ts_change_score):
    md = timeline(ts_change_score)
    md.active_event_index = 0

    assert md.move_timeline_left_by_measure() is False
    assert md.active_event_index == 0


def test_move_timeline_left_by_measure_from_measure_one_lands_on_the_pickup(timeline, score_duet):
    """Chessel Duet's pickup is measure 0 (A3). Ctrl+Left from measure 1's
    first event must land there, not skip past it (Ref 3 AC2)."""
    md = timeline(score_duet)
    md.active_event_index = 3  # measure 1, beat 1 - see conftest fixture layout

    assert md.move_timeline_left_by_measure() is True
    assert md.active_event_index == 0
    assert md.timeline_slices[0].measure == 0


def test_move_timeline_left_by_measure_stops_once_already_on_the_pickup(timeline, score_duet):
    md = timeline(score_duet)
    md.active_event_index = 0  # already the pickup's first event

    assert md.move_timeline_left_by_measure() is False
    assert md.active_event_index == 0


def test_move_timeline_right_by_measure_only_lands_on_events_visible_under_the_voice_filter(
    timeline, flute_crotchets_viola_semibreves_score
):
    """Sympathetic to active notes, not just what is in the score: with the
    flute deactivated, Ctrl+Right must land on the viola's next semibreve
    (measure 2), not the flute's crotchet-rate measure 1 events."""
    md = timeline(flute_crotchets_viola_semibreves_score)
    md.set_active_voice_filter({("P2", 1, 1)})

    assert md.move_timeline_right_by_measure() is True
    assert md.active_event_index == 4

    assert md.move_timeline_right_by_measure() is False, "no more visible measures"


def test_move_timeline_home_jumps_to_the_first_event(timeline, ts_change_score):
    md = timeline(ts_change_score)
    md.active_event_index = 7

    assert md.move_timeline_home() is True
    assert md.active_event_index == 0


def test_move_timeline_end_jumps_to_the_last_event(timeline, ts_change_score):
    md = timeline(ts_change_score)

    assert md.move_timeline_end() is True
    assert md.active_event_index == 11


def test_move_timeline_home_and_end_respect_the_voice_filter(
    timeline, flute_crotchets_viola_semibreves_score
):
    """Home/End (C3, Ref 5) must also be sympathetic to active notes: with
    only the viola visible, they jump to the viola's first/last event, not
    the flute's."""
    md = timeline(flute_crotchets_viola_semibreves_score)
    md.set_active_voice_filter({("P2", 1, 1)})
    md.active_event_index = 2

    assert md.move_timeline_end() is True
    assert md.active_event_index == 4

    assert md.move_timeline_home() is True
    assert md.active_event_index == 0


def test_move_timeline_right_stops_at_the_last_sounding_note_not_trailing_rests(
    timeline, score_duet
):
    """Live-tested bug: Chessel Duet's final bar (measure 3) is a dotted
    crotchet on beat 1 followed by rests in every voice on beats 4, 5 and 6 -
    padding to complete the bar, not further active events. Right from the
    dotted crotchet must fail immediately, not step through the three
    trailing rest slices first."""
    md = timeline(score_duet)
    md.active_event_index = 15  # measure 3, beat 1 - the final dotted crotchet

    assert md.move_timeline_right() is False
    assert md.active_event_index == 15


def test_move_timeline_right_by_measure_stops_at_the_last_sounding_note(timeline, score_duet):
    md = timeline(score_duet)
    md.active_event_index = 15  # measure 3, beat 1 - the final dotted crotchet

    assert md.move_timeline_right_by_measure() is False
    assert md.active_event_index == 15


def test_move_timeline_end_lands_on_the_last_sounding_note_not_a_trailing_rest(
    timeline, score_duet
):
    """End must land on the dotted crotchet (measure 3 beat 1), not the
    empty final rest slot (measure 3 beat 6)."""
    md = timeline(score_duet)

    assert md.move_timeline_end() is True
    assert md.active_event_index == 15
    last_slice = md.get_current_slice()
    assert last_slice.measure == 3
    assert last_slice.beat_position == 1.0


def test_interior_rest_remains_individually_navigable(timeline, rest_score):
    """The sounding-bounds fix must not swallow a rest that sits BETWEEN two
    sounding notes (Ref 16 AC2) - only leading/trailing rest-only padding is
    excluded from navigation. rest_score is C, rest, E, F."""
    md = timeline(rest_score)

    assert md.move_timeline_right() is True
    assert md.active_event_index == 1
    assert md.get_region_3_data() == ["rest"]

    assert md.move_timeline_end() is True
    assert md.active_event_index == 3, "F, the real last note - not affected by the interior rest"


def test_get_channel_for_part_assigns_one_channel_per_part_in_order():
    md = MusicData(parts_info=[
        PartStructureInfo(part_id="P1", name="Piano", gmidi_program=1),
        PartStructureInfo(part_id="P2", name="Classical Guitar", gmidi_program=25),
    ])

    assert md.get_channel_for_part("P1") == 0
    assert md.get_channel_for_part("P2") == 1


def test_get_channel_for_part_skips_the_percussion_channel():
    """MIDI channel 10 (0-indexed 9) is reserved for percussion (D-5)."""
    parts = [PartStructureInfo(part_id=f"P{i}", gmidi_program=1) for i in range(1, 12)]
    md = MusicData(parts_info=parts)

    assert md.get_channel_for_part("P9") == 8
    assert md.get_channel_for_part("P10") == 10, "channel index 9 is skipped"
    assert md.get_channel_for_part("P11") == 11


def test_get_channel_for_part_returns_zero_for_an_unknown_part():
    md = MusicData(parts_info=[PartStructureInfo(part_id="P1", gmidi_program=1)])

    assert md.get_channel_for_part("does-not-exist") == 0


def test_get_gmidi_program_for_part_returns_that_parts_own_program():
    md = MusicData(parts_info=[
        PartStructureInfo(part_id="P1", name="Piano", gmidi_program=1),
        PartStructureInfo(part_id="P2", name="Classical Guitar", gmidi_program=25),
    ])

    assert md.get_gmidi_program_for_part("P1") == 1
    assert md.get_gmidi_program_for_part("P2") == 25


def test_playback_events_group_simultaneous_notes_by_part(timeline, two_parts_chord_score):
    """A8, Ref 8: a chord spanning two parts must not collapse onto one instrument."""
    md = timeline(two_parts_chord_score, parts_info=[
        PartStructureInfo(part_id="P1", name="Piano", gmidi_program=1),
        PartStructureInfo(part_id="P2", name="Classical Guitar", gmidi_program=25),
    ])

    assert len(md.timeline_slices) == 1, "both notes land on the same beat"
    current = md.get_current_slice()
    assert {n.part_id for n in current.notes} == {"P1", "P2"}

    events = md.get_playback_events_for_indices([0, 1])

    events_by_channel = {channel: (program, notes) for channel, program, notes in events}
    assert events_by_channel[0] == (0, [60]), "Piano: channel 0, program 0-indexed, C4"
    assert events_by_channel[1] == (24, [52]), "Guitar: channel 1, program 0-indexed, E3"


def test_playback_events_skip_indices_with_no_pitch(timeline, rest_score):
    md = timeline(rest_score, parts_info=[PartStructureInfo(part_id="P1", gmidi_program=1)])
    md.active_event_index = 1  # C, rest, E, F

    assert md.get_playback_events_for_indices([0]) == []
