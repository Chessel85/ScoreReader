# tests/models/test_music_data.py
"""Harness proof for the timeline model.

The real characterisation suite is A2. These tests exist to show the
ElementTree-only path works and is wired up correctly.
"""
from models.music_data import MusicData
from models.note_data import NoteData
from models.parts_structure import PartStructureInfo
from models.vocabulary import attribute_label


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


# --- E9: beat positions become navigable with the metronome on (Ref 14 AC4) ---

def test_metronome_off_skips_beats_with_no_real_event(timeline, sparse_beat_score):
    """sparse_beat_score's measure 2 is a single quarter note G on beat 1,
    then silence (via <forward>) until measure 3's A - today's behaviour,
    unaffected by this feature existing, is unchanged: Right jumps straight
    from G to A, with no stop in between."""
    md = timeline(sparse_beat_score)
    md.active_event_index = 4  # G, measure 2 beat 1

    assert md.move_timeline_right() is True
    assert md.get_current_slice().measure == 3
    assert md.get_current_slice().beat_position == 1.0


def test_metronome_on_makes_silent_beats_navigable(timeline, sparse_beat_score):
    """The gap sits between G (measure 2 beat 1) and A (measure 3 beat 1) -
    an interior gap, not trailing padding after the piece's last note, so
    _sounding_bounds() still reaches through it (same "interior rest stays
    reachable" rule C5 already applies to rests)."""
    md = timeline(sparse_beat_score)
    md.set_metronome_enabled(True)
    md.active_event_index = 4  # G, measure 2 beat 1

    assert md.move_timeline_right() is True
    assert md.get_current_slice().beat_position == 2.0
    assert md.get_current_slice().measure == 2
    assert md.get_region_3_data() == ["Click"]

    assert md.move_timeline_right() is True
    assert md.get_current_slice().beat_position == 3.0

    assert md.move_timeline_right() is True
    assert md.get_current_slice().beat_position == 4.0

    assert md.move_timeline_right() is True, "reaches A, measure 3's real note"
    assert md.get_current_slice().measure == 3
    assert md.get_current_slice().notes != []


def test_toggling_metronome_off_again_removes_the_markers_and_relocates_the_cursor(
    timeline, sparse_beat_score
):
    md = timeline(sparse_beat_score)
    md.set_metronome_enabled(True)
    md.active_event_index = 4  # G, measure 2 beat 1
    md.move_timeline_right()  # onto the beat-2 marker
    assert md.get_current_slice().beat_position == 2.0

    md.set_metronome_enabled(False)

    assert len(md.timeline_slices) == 6, "back to the real-only timeline"
    assert md.get_current_slice().beat_position == 1.0, "relocated to G, not left dangling"
    assert md.get_current_slice().measure == 2


def test_toggling_metronome_on_preserves_the_cursor_on_a_real_note(timeline, sparse_beat_score):
    md = timeline(sparse_beat_score)
    md.active_event_index = 4  # G, measure 2 beat 1

    md.set_metronome_enabled(True)

    assert md.get_current_slice().beat_position == 1.0, "still on the real G, markers inserted after it"
    assert md.get_current_slice().measure == 2


def test_markers_fill_beats_inside_a_still_ringing_note(timeline, six_eight_score):
    """Ref 14 AC1 asks for a click "on every beat", unconditionally - not
    only beats with no note ringing through them. six_eight_score's C
    (quarter, beats 1-2) and D (quarter, beats 3-4) each start a real event
    only at their own onset beat, so beats 2 and 4 (mid-note) still get
    their own marker once the metronome is on, alongside the untouched
    beat-5/6 real eighth notes."""
    md = timeline(six_eight_score)
    md.set_metronome_enabled(True)

    beats = sorted(s.beat_position for s in md.timeline_slices if s.measure == 1)
    assert beats == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]


def test_pickup_measure_gets_no_markers_before_its_own_start_beat(timeline, score_duet):
    """score_duet's pickup (6/8, number="0" implicit="yes") is entirely
    filled by real notes at beats 4, 5, 6 (A3's "positioned at the end of
    the notional bar") - if marker generation used the wrong start_beat
    (e.g. 1 instead of 4), it would wrongly synthesize markers at beats
    1/2/3, which don't correspond to any real time before the piece starts.
    """
    md = timeline(score_duet)
    md.set_metronome_enabled(True)

    pickup_beats = sorted(s.beat_position for s in md.timeline_slices if s.measure == 0)
    assert pickup_beats == [4.0, 5.0, 6.0], "no markers before the pickup's real start_beat"


def test_jump_to_measure_moves_to_the_first_event_of_that_measure(timeline, ts_change_score):
    """C4, Ref 6: typing a bar number then Enter."""
    md = timeline(ts_change_score)
    md.active_event_index = 2  # measure 1, not its first event

    assert md.jump_to_measure(2) is True
    assert md.active_event_index == 4  # first event of measure 2


def test_jump_to_measure_returns_false_for_an_unknown_measure(timeline, ts_change_score):
    """Ref 6 AC4: an unknown bar plays an error sound and does not move."""
    md = timeline(ts_change_score)
    md.active_event_index = 4

    assert md.jump_to_measure(99) is False
    assert md.active_event_index == 4


def test_jump_to_measure_reaches_the_pickup_bar_numbered_zero(timeline, score_duet):
    """Chessel Duet's pickup is measure 0 (A3) - typing "0" must reach it."""
    md = timeline(score_duet)
    md.active_event_index = 3  # measure 1, beat 1

    assert md.jump_to_measure(0) is True
    assert md.active_event_index == 0
    assert md.timeline_slices[0].measure == 0


def test_jump_to_measure_respects_the_voice_filter(timeline, flute_crotchets_viola_semibreves_score):
    """Sympathetic to active notes, same as C2's Ctrl+Right/Left."""
    md = timeline(flute_crotchets_viola_semibreves_score)
    md.set_active_voice_filter({("P2", 1, 1)})

    assert md.jump_to_measure(2) is True
    assert md.active_event_index == 4


def test_jump_to_measure_reaches_a_multi_digit_bar_number(timeline, many_measures_score):
    md = timeline(many_measures_score)

    assert md.jump_to_measure(12) is True
    assert md.active_event_index == 11
    assert md.timeline_slices[11].measure == 12


def test_jump_to_measure_reaches_a_multi_digit_bar_number_on_a_real_long_score(
    timeline, score_long_tune
):
    """The user-provided 'Long tune' score (130 measures on paper, no
    pickup) - the realistic case many_measures_score's hand-rolled fixture
    stands in for above. The piece's real notes end around measure 112;
    measures 113-130 are trailing empty bars padding out the final system,
    same rest-only-tail pattern _sounding_bounds already excludes elsewhere
    (C5) - so 100 is used here as a real, safely-reachable multi-digit
    target rather than the highest-numbered measure on the page."""
    md = timeline(score_long_tune)

    assert md.jump_to_measure(100) is True
    landed = md.timeline_slices[md.active_event_index]
    assert landed.measure == 100
    assert landed.beat_position == 1.0

    assert md.jump_to_measure(999) is False
    assert md.timeline_slices[md.active_event_index].measure == 100, "unchanged on an unknown bar"


def test_jump_to_measure_on_a_bar_with_trailing_rests_lands_on_its_first_sounding_event(
    timeline, score_duet
):
    """Chessel Duet's measure 3 is a dotted crotchet followed by rests padding
    the bar - jumping there must land on the crotchet (its real first event),
    same sounding-bounds rule C5 already applies to Left/Right/Home/End."""
    md = timeline(score_duet)
    md.active_event_index = 0

    assert md.jump_to_measure(3) is True
    assert md.active_event_index == 15


def test_status_bar_fields_reflect_the_time_and_key_signature_at_the_current_position(
    timeline, score_way_to_go
):
    """C6/D-11: Way To Go changes both time and key signature mid-piece
    (4/4 -> 3/4 -> 4/4, fifths 1 -> 2 -> 1) - the status bar must track the
    cursor's own position, not the score's opening values."""
    md = timeline(score_way_to_go)

    early_fields = md.get_status_bar_fields()
    assert early_fields[0].startswith("Measure 1 beat ")
    assert early_fields[1] == "Key: G major / E minor"
    assert early_fields[2] == "Time: 4/4"

    assert md.move_timeline_end() is True
    late_fields = md.get_status_bar_fields()

    assert late_fields != early_fields, "position, key and/or time must differ later in the score"


def test_status_bar_fields_before_a_score_is_loaded():
    md = MusicData()

    assert md.get_status_bar_fields() == [
        "Measure - beat -", "Key: -", "Time: -",
        "Playback tempo: 120 quarter notes per minute (score default)",
    ]


# --- F4/D-6: UK/US terminology toggle ------------------------------------

def test_uk_terms_defaults_to_false():
    """Required for backward compatibility - every test in this file that
    doesn't pass uk_terms expects today's (US-leaning) hardcoded text."""
    assert MusicData().uk_terms is False


def test_status_bar_measure_word_follows_uk_terms(timeline, minimal_score):
    md = timeline(minimal_score, uk_terms=True)

    assert md.get_status_bar_fields()[0].startswith("Bar 1 beat ")


def test_status_bar_placeholder_measure_word_follows_uk_terms():
    md = MusicData(uk_terms=True)

    assert md.get_status_bar_fields()[0] == "Bar - beat -"


def test_tempo_status_field_duration_name_follows_uk_terms():
    md = MusicData(tempo_bpm=48, tempo_beat_unit_quarter_length=0.5, tempo_beat_unit_name="eighth", uk_terms=True)

    assert "quaver notes per minute" in md.get_status_bar_fields()[3]


def test_tempo_beat_unit_name_at_translates_per_uk_terms():
    md = MusicData(tempo_bpm=48, tempo_beat_unit_quarter_length=0.5, tempo_beat_unit_name="eighth")

    assert md.tempo_beat_unit_name_at() == "eighth"
    md.uk_terms = True
    assert md.tempo_beat_unit_name_at() == "quaver"


def test_get_region_1_data_tempo_credit_follows_uk_terms():
    """The "Tempo" credit is baked once at parse time in US units
    (MusicXMLReader) - get_region_1_data must override it live rather than
    returning self.credits verbatim, or toggling wouldn't affect Region 1
    without reloading the file."""
    md = MusicData(
        credits={"Title": "Test", "Tempo": "96 eighth notes per minute"},
        tempo_bpm=48,
        tempo_beat_unit_quarter_length=0.5,
        tempo_beat_unit_name="eighth",
    )

    assert md.get_region_1_data()["Tempo"] == "96 eighth notes per minute"
    md.uk_terms = True
    assert md.get_region_1_data()["Tempo"] == "96 quaver notes per minute"
    assert md.get_region_1_data()["Title"] == "Test", "other credits pass through untouched"


def test_get_score_structure_stave_name_follows_uk_terms():
    md = MusicData(
        parts_info=[
            PartStructureInfo(
                part_id="P1", name="Guitar", staves_clefs={1: "Treble stave"}, staves_voices={1: [1]}
            )
        ]
    )

    assert md.get_score_structure()[0]["staves"][0]["name"] == "Treble staff"
    md.uk_terms = True
    assert md.get_score_structure()[0]["staves"][0]["name"] == "Treble stave"


def test_get_stave_name_for_part_follows_uk_terms():
    md = MusicData(
        parts_info=[
            PartStructureInfo(
                part_id="P1", name="Guitar", staves_clefs={1: "Treble stave"}, staves_voices={1: [1]}
            )
        ]
    )

    assert md.get_stave_name_for_part("P1", 1) == "Treble staff"
    md.uk_terms = True
    assert md.get_stave_name_for_part("P1", 1) == "Treble stave"


def test_region_3_and_region_4_attribute_labels_follow_uk_terms(timeline, minimal_score):
    md = timeline(minimal_score, uk_terms=True)
    md.set_display_attribute("measure", "voice", md.notes_for_indices([0]), add=True)

    assert md.get_region_3_data() == ["C, bar 1"]
    assert md.get_region_4_data_for_indices([0])["bar"] == "1"


def test_region_4_attribute_key_lookups_are_unaffected_by_uk_terms(timeline, minimal_score):
    """The internal "measure"/"stave" keys used for storage and menu wiring
    must never change - only rendered label TEXT does."""
    md = timeline(minimal_score, uk_terms=True)
    notes = md.notes_for_indices([0])
    md.set_display_attribute("measure", "voice", notes, add=True)

    assert md.note_has_display_attribute(notes[0], "measure") is True
    targets = md.get_region_4_row_targets([0])
    assert any(attribute_key == "measure" for attribute_key, _ in targets)


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


# --- E1: playback tempo offset (Ref 12) ---------------------------------

def test_effective_tempo_defaults_to_the_scores_own_tempo():
    md = MusicData(tempo_bpm=120)

    assert md.effective_tempo_bpm() == 120


def test_playback_tempo_offset_shifts_effective_tempo_without_touching_score_tempo():
    md = MusicData(tempo_bpm=120)

    md.set_playback_tempo_offset(30)

    assert md.effective_tempo_bpm() == 150
    assert md.tempo_bpm == 120, "AC1: offset must never mutate the score's own tempo"


def test_playback_tempo_offset_clamps_at_the_upper_hard_boundary():
    md = MusicData(tempo_bpm=120)

    md.set_playback_tempo_offset(500)  # would be 620bpm, way past MAX_TEMPO_BPM

    assert md.effective_tempo_bpm() == MusicData.MAX_TEMPO_BPM


def test_playback_tempo_offset_clamps_at_the_lower_hard_boundary():
    md = MusicData(tempo_bpm=40)

    md.set_playback_tempo_offset(-500)  # would be negative, way past MIN_TEMPO_BPM

    assert md.effective_tempo_bpm() == MusicData.MIN_TEMPO_BPM


def test_reset_playback_tempo_returns_to_the_scores_own_tempo():
    md = MusicData(tempo_bpm=96)
    md.set_playback_tempo_offset(-20)
    assert md.effective_tempo_bpm() == 76

    md.reset_playback_tempo()

    assert md.effective_tempo_bpm() == 96


def test_get_current_duration_ms_reflects_the_playback_tempo_offset(timeline, minimal_score):
    md = timeline(minimal_score, tempo_bpm=120)

    baseline_ms = md.get_current_duration_ms()
    md.set_playback_tempo_offset(120)  # double the effective tempo -> half the duration

    assert md.get_current_duration_ms() == baseline_ms // 2


def test_score_tempo_display_bpm_converts_out_of_the_internal_quarter_bpm():
    """Reported bug: a score marked eighth=96 stores tempo_bpm=48
    internally (quarter-note BPM, for playback timing) - the score's own
    displayed tempo must still read as 96, matching Region 1 (A9)."""
    md = MusicData(tempo_bpm=48, tempo_beat_unit_quarter_length=0.5, tempo_beat_unit_name="eighth")

    assert md.score_tempo_display_bpm() == 96


def test_playback_tempo_offset_is_in_display_units_not_quarter_units():
    """F/S's "+10" (Ref 12 AC3) must mean +10 in the units the user reads -
    e.g. +10 eighth notes per minute, not +10 quarter-note-equivalent bpm
    (which would display as +20 eighth notes per minute)."""
    md = MusicData(tempo_bpm=48, tempo_beat_unit_quarter_length=0.5, tempo_beat_unit_name="eighth")

    md.set_playback_tempo_offset(10)

    assert md.effective_tempo_display_bpm() == 106
    assert md.effective_tempo_bpm() == 53, "internal quarter-BPM timing must still be correct: 48 + 10*0.5"


def test_playback_tempo_offset_clamp_bounds_use_display_units():
    """The 30-300 hard boundary (Ref 12 AC2) is what the user reads/types
    (score display units), not the internal quarter-BPM equivalent."""
    md = MusicData(tempo_bpm=48, tempo_beat_unit_quarter_length=0.5, tempo_beat_unit_name="eighth")

    md.set_playback_tempo_offset(1000)  # would be far past 300 eighth-notes-per-minute

    assert md.effective_tempo_display_bpm() == MusicData.MAX_TEMPO_BPM


# --- E4: Sequencer support methods ---------------------------------------

def test_get_playback_events_at_index_reads_an_explicit_slice_not_the_cursor(
    timeline, minimal_score
):
    md = timeline(minimal_score, parts_info=[PartStructureInfo(part_id="P1", gmidi_program=1)])
    assert md.active_event_index == 0  # C

    events = md.get_playback_events_at_index(2)  # E, without moving the cursor

    assert md.active_event_index == 0
    assert len(events) == 1
    _, _, midi_notes = events[0]
    assert midi_notes == [64]  # E4


def test_get_duration_ms_for_index_uses_that_slices_own_quarter_length(timeline, six_eight_score):
    md = timeline(six_eight_score, tempo_bpm=120)
    # six_eight_score: quarter C, quarter D, eighth E, eighth F - the eighth
    # notes must resolve to half the duration of the quarter notes.
    quarter_ms = md.get_duration_ms_for_index(0)
    eighth_ms = md.get_duration_ms_for_index(2)

    assert eighth_ms == quarter_ms // 2


def test_next_visible_event_index_skips_slices_hidden_by_voice_filter(
    timeline, flute_crotchets_viola_semibreves_score
):
    md = timeline(flute_crotchets_viola_semibreves_score)
    md.set_active_voice_filter({("P2", 1, 1)})  # viola only

    assert md.next_visible_event_index(0) == 4  # bar 2 beat 1, not the flute's crotchets


def test_next_visible_event_index_respects_end_index_bound():
    md = MusicData(file_path="")  # empty timeline is fine - just exercising the bound math

    assert md.next_visible_event_index(0, end_index=0) is None


def test_next_visible_event_index_returns_none_at_the_last_event(timeline, minimal_score):
    md = timeline(minimal_score)

    assert md.next_visible_event_index(3) is None


def test_last_sounding_event_index_excludes_trailing_rest_padding(timeline, score_duet):
    """C5/E6: same guard already used by Home/End - a phrase audition must
    not be able to run on into rest-only padding at the end of the piece.
    Chessel Duet's final bar rests out in every voice after its last real
    note (see C5's DONE note in tasks.txt)."""
    md = timeline(score_duet)

    last_sounding = md.last_sounding_event_index()

    assert last_sounding is not None
    assert last_sounding < md.last_event_index()


# Ref 15 AC4: configurable note-attribute display in Region 3.

def _note(part_id="P1", staff=1, voice=1) -> NoteData:
    return NoteData(
        step_name="C", measure=1, beat_position=1.0, ts_duration=1.0,
        quarter_length=1.0, part_id=part_id, part_name="Test", staff=staff, voice=voice,
    )


def test_region_3_appends_configured_extra_attributes_comma_separated(timeline, minimal_score):
    md = timeline(minimal_score)
    note = md.timeline_slices[0].notes[0]  # C, octave 4, ts_duration 1.0
    voice_key = (note.part_id, note.staff, note.voice)
    md.voice_display_attributes[voice_key] = {"duration", "step", "octave"}  # order must not matter

    assert md.get_region_3_data() == ["C, octave 4, duration 1"]


def test_region_3_omits_missing_attributes_without_a_dangling_comma(timeline, rest_score):
    """A rest has no octave/midi - those must vanish from the display
    entirely, not leave an empty "octave , midi" gap or a double comma."""
    md = timeline(rest_score)
    md.voice_display_attributes[("P1", 1, 1)] = {"step", "octave", "midi", "duration"}

    md.active_event_index = 0
    assert md.get_region_3_data() == ["C, octave 4, midi 60, duration 1"]

    md.active_event_index = 1  # the rest
    assert md.get_region_3_data() == ["rest, duration 1"]


def test_region_3_renders_blank_when_no_attributes_are_configured_on(timeline, minimal_score):
    """Still a valid, selectable, audible position - just nothing to show."""
    md = timeline(minimal_score)
    note = md.timeline_slices[0].notes[0]
    md.voice_display_attributes[(note.part_id, note.staff, note.voice)] = set()

    assert md.get_region_3_data() == [""]


def test_region_4_data_ignores_the_region_3_display_configuration(timeline, minimal_score):
    """Region 4 always shows every attribute a note has, regardless of what
    Region 3 is currently configured to display."""
    md = timeline(minimal_score)
    note = md.timeline_slices[0].notes[0]
    md.voice_display_attributes[(note.part_id, note.staff, note.voice)] = set()

    data = md.get_region_4_data_for_indices([0])

    assert data["step"] == "C"
    assert data["octave"] == "4"


def test_notes_for_indices_returns_the_real_note_objects(timeline, chord_score):
    md = timeline(chord_score)
    md.active_event_index = 1  # D, F chord
    notes = md.timeline_slices[1].notes

    assert md.notes_for_indices([0, 1]) == notes
    assert md.notes_for_indices([]) == []
    assert md.notes_for_indices([5]) == [], "out-of-range indices are ignored"


def test_get_region_4_row_targets_matches_data_keys_for_a_single_note(timeline, minimal_score):
    """Row order must match, and each row's raw attribute_key must be the
    one whose F4/D-6 display label (attribute_label) produced the data
    dict's key - not literal string equality, since "stave"'s label diverges
    from its key by default (uk_terms=False renders it as "staff")."""
    md = timeline(minimal_score)

    data_keys = list(md.get_region_4_data_for_indices([0]).keys())
    targets = md.get_region_4_row_targets([0])

    assert [attribute_label(attribute_key, md.uk_terms) for attribute_key, _ in targets] == data_keys
    assert all(note.step_name == "C" for _, note in targets)


def test_get_region_4_row_targets_strips_the_chord_note_prefix(timeline, chord_score):
    md = timeline(chord_score)
    md.active_event_index = 1  # D, F chord
    notes = md.timeline_slices[1].notes

    data_keys = list(md.get_region_4_data_for_indices([0, 1]).keys())
    targets = md.get_region_4_row_targets([0, 1])

    assert len(targets) == len(data_keys)
    assert all(not attribute_key.startswith("note ") for attribute_key, _ in targets)
    assert data_keys[0] == "note 1 step"
    assert targets[0] == ("step", notes[0])
    note_2_row = data_keys.index("note 2 step")
    assert targets[note_2_row] == ("step", notes[1])


def test_note_has_display_attribute_defaults_to_step_only():
    md = MusicData(parts_info=[PartStructureInfo(part_id="P1", staves_voices={1: [1]})])
    note = _note()

    assert md.note_has_display_attribute(note, "step") is True
    assert md.note_has_display_attribute(note, "octave") is False

    md.set_display_attribute("octave", "voice", [note], add=True)

    assert md.note_has_display_attribute(note, "octave") is True


def test_set_display_attribute_voice_scope_only_touches_that_voice():
    md = MusicData(parts_info=[
        PartStructureInfo(part_id="P1", staves_voices={1: [1, 2], 2: [1]}),
        PartStructureInfo(part_id="P2", staves_voices={1: [1]}),
    ])

    md.set_display_attribute("octave", "voice", [_note("P1", 1, 1)], add=True)

    assert md.voice_display_attributes[("P1", 1, 1)] == {"step", "octave"}
    assert ("P1", 1, 2) not in md.voice_display_attributes
    assert ("P1", 2, 1) not in md.voice_display_attributes


def test_set_display_attribute_stave_scope_fans_out_to_every_voice_on_that_stave():
    md = MusicData(parts_info=[PartStructureInfo(part_id="P1", staves_voices={1: [1, 2], 2: [1]})])

    md.set_display_attribute("octave", "stave", [_note("P1", 1, 1)], add=True)

    assert md.voice_display_attributes[("P1", 1, 1)] == {"step", "octave"}
    assert md.voice_display_attributes[("P1", 1, 2)] == {"step", "octave"}
    assert ("P1", 2, 1) not in md.voice_display_attributes


def test_set_display_attribute_part_scope_fans_out_to_every_stave_in_that_part():
    md = MusicData(parts_info=[
        PartStructureInfo(part_id="P1", staves_voices={1: [1], 2: [1, 2]}),
        PartStructureInfo(part_id="P2", staves_voices={1: [1]}),
    ])

    md.set_display_attribute("octave", "part", [_note("P1", 1, 1)], add=True)

    assert md.voice_display_attributes[("P1", 1, 1)] == {"step", "octave"}
    assert md.voice_display_attributes[("P1", 2, 1)] == {"step", "octave"}
    assert md.voice_display_attributes[("P1", 2, 2)] == {"step", "octave"}
    assert ("P2", 1, 1) not in md.voice_display_attributes


def test_set_display_attribute_score_scope_fans_out_to_every_part():
    md = MusicData(parts_info=[
        PartStructureInfo(part_id="P1", staves_voices={1: [1]}),
        PartStructureInfo(part_id="P2", staves_voices={1: [1, 2]}),
    ])

    md.set_display_attribute("octave", "score", [_note("P1", 1, 1)], add=True)

    assert md.voice_display_attributes[("P1", 1, 1)] == {"step", "octave"}
    assert md.voice_display_attributes[("P2", 1, 1)] == {"step", "octave"}
    assert md.voice_display_attributes[("P2", 1, 2)] == {"step", "octave"}


def test_set_display_attribute_multi_select_unions_scope_across_selected_notes():
    """Confirmed design decision: a stave/part/score-scope action fired from
    a multi-note (chord) Region 3 selection unions the scope across every
    selected note's own stave/part, not just the one note the context menu
    happened to be opened on."""
    md = MusicData(parts_info=[
        PartStructureInfo(part_id="P1", staves_voices={1: [1, 2]}),
        PartStructureInfo(part_id="P2", staves_voices={1: [1]}),
    ])
    notes = [_note("P1", 1, 1), _note("P2", 1, 1)]

    md.set_display_attribute("octave", "stave", notes, add=True)

    assert md.voice_display_attributes[("P1", 1, 1)] == {"step", "octave"}
    assert md.voice_display_attributes[("P1", 1, 2)] == {"step", "octave"}
    assert md.voice_display_attributes[("P2", 1, 1)] == {"step", "octave"}


def test_set_display_attribute_can_remove_step_leaving_a_blank_voice():
    md = MusicData(parts_info=[PartStructureInfo(part_id="P1", staves_voices={1: [1]})])
    note = _note()

    md.set_display_attribute("step", "voice", [note], add=False)

    assert md.voice_display_attributes[("P1", 1, 1)] == set()
    assert md.note_has_display_attribute(note, "step") is False
