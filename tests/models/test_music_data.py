# tests/models/test_music_data.py
"""Harness proof for the timeline model.

The real characterisation suite is A2. These tests exist to show the
ElementTree-only path works and is wired up correctly.
"""
import pytest

from models.event_slice import EventSlice
from models.music_data import MusicData
from models.note_data import NoteData
from models.parts_structure import PartStructureInfo
from models.vocabulary import attribute_label
from persistence.score_config import ScoreConfig


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


def test_get_score_structure_stave_name_is_unaffected_by_uk_terms():
    """D-15: stave/staff wording is deliberately excluded from F4's toggle -
    Region 2's clef names stay exactly as generated, regardless of dialect."""
    md = MusicData(
        parts_info=[
            PartStructureInfo(
                part_id="P1", name="Guitar", staves_clefs={1: "Treble stave"}, staves_voices={1: [1]}
            )
        ]
    )

    assert md.get_score_structure()[0]["staves"][0]["name"] == "Treble stave"
    md.uk_terms = True
    assert md.get_score_structure()[0]["staves"][0]["name"] == "Treble stave"


def test_get_stave_name_for_part_is_unaffected_by_uk_terms():
    """D-15: see test_get_score_structure_stave_name_is_unaffected_by_uk_terms."""
    md = MusicData(
        parts_info=[
            PartStructureInfo(
                part_id="P1", name="Guitar", staves_clefs={1: "Treble stave"}, staves_voices={1: [1]}
            )
        ]
    )

    assert md.get_stave_name_for_part("P1", 1) == "Treble stave"
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


def test_get_channel_for_part_skips_the_percussion_announcer_and_cue_channels():
    """MIDI channel 10 (0-indexed 9) is reserved for percussion (D-5);
    channel 9 (0-indexed 8) is reserved for the position announcer
    (Ref 28); channel 8 (0-indexed 7) is reserved for the Performance
    region's change cue (Ref 29) - see MusicData.RESERVED_CHANNELS. 11
    parts (idx 0-10) walk straight through the 7 usable channels below the
    reservations, then resume past all three."""
    parts = [PartStructureInfo(part_id=f"P{i}", gmidi_program=1) for i in range(1, 12)]
    md = MusicData(parts_info=parts)

    assert md.get_channel_for_part("P7") == 6, "last channel before all three reservations"
    assert md.get_channel_for_part("P8") == 10, "channel indices 7, 8 and 9 are all skipped"
    assert md.get_channel_for_part("P9") == 11
    assert md.get_channel_for_part("P10") == 12
    assert md.get_channel_for_part("P11") == 13


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

    events_by_channel = {channel: (program, notes) for channel, program, notes, _ in events}
    assert events_by_channel[0] == (0, [60]), "Piano: channel 0, program 0-indexed, C4"
    assert events_by_channel[1] == (24, [52]), "Guitar: channel 1, program 0-indexed, E3"


def test_playback_events_carry_each_parts_own_duration_not_the_shortest_at_the_slice(
    timeline, flute_crotchets_viola_semibreves_score
):
    """Reported bug, live-tested against Pachelbel's Canon: a part's note was
    being cut short to match a shorter note in a different part sounding at
    the same instant (Ref 9 AC2 "matches note duration", Ref 13 AC2 "hold
    for their marked length"). flute_crotchets_viola_semibreves_score's bar
    1 beat 1 is exactly this shape - the flute's quarter note and the
    viola's whole note share one EventSlice - so each part's playback
    duration_ms must reflect its own note value, not get clamped to the
    other part's shorter one."""
    md = timeline(flute_crotchets_viola_semibreves_score)

    assert md.timeline_slices[0].measure == 1
    current = md.get_current_slice()
    assert {n.part_id for n in current.notes} == {"P1", "P2"}, "flute crotchet + viola whole note"

    events = md.get_playback_events_for_indices([0, 1])
    duration_by_part_id = {
        next(n.part_id for n in current.notes if n.midi_pitch in midi_notes): duration_ms
        for _, _, midi_notes, duration_ms in events
    }

    assert duration_by_part_id["P2"] == pytest.approx(duration_by_part_id["P1"] * 4, rel=0.01), (
        "viola's whole note must ring 4x as long as the flute's quarter note, not be clamped to it"
    )


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
    _, _, midi_notes, _ = events[0]
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
    note = md.timeline_slices[0].notes[0]  # C, octave 4, a quarter note
    voice_key = (note.part_id, note.staff, note.voice)
    md.voice_display_attributes[voice_key] = {"duration", "step", "octave"}  # order must not matter

    # "duration" renders as a bare US/UK duration word ("quarter"), with no
    # "Duration" prefix - unlike every other extra attribute (e.g. "octave
    # 4") - because the word alone already says what it is.
    assert md.get_region_3_data() == ["C, octave 4, quarter"]


def test_region_3_prefixes_duration_when_it_has_no_word():
    """Ref 25/S3: duration_name_us=None (no clean word match - MIDI's
    per-track weird-durations fallback, or MusicXML's rare no-<type> case)
    must keep the "Duration" label, unlike the word case above - a bare
    number alone in the comma list could be mistaken for anything."""
    md = MusicData()
    note = _note()
    note.duration_name_us = None
    note.ts_duration = 1.5
    md.timeline_slices = [EventSlice(measure=1, beat_position=1.0, quarter_length=1.5, notes=[note])]
    md.active_event_index = 0
    md.voice_display_attributes[("P1", 1, 1)] = {"step", "duration"}

    # Lowercase "duration", matching every other Region 3 label ("octave 4",
    # "midi 60") - attribute_label never capitalizes attribute_key (only
    # "measure" is special-cased for UK/US wording).
    assert md.get_region_3_data() == ["C, duration 1.5"]


def test_region_3_omits_missing_attributes_without_a_dangling_comma(timeline, rest_score):
    """A rest has no octave/midi - those must vanish from the display
    entirely, not leave an empty "octave , midi" gap or a double comma."""
    md = timeline(rest_score)
    md.voice_display_attributes[("P1", 1, 1)] = {"step", "octave", "midi", "duration"}

    md.active_event_index = 0
    assert md.get_region_3_data() == ["C, octave 4, midi 60, quarter"]

    md.active_event_index = 1  # the rest
    assert md.get_region_3_data() == ["rest, quarter"]


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
    dict's key - not literal string equality, since "measure"'s label
    diverges from its key under uk_terms=True (renders as "bar")."""
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


# F2/Ref 15 AC4: attribute ORDERING (as opposed to F1's add/remove above).

def test_move_attribute_order_swaps_adjacent_entries():
    md = MusicData(parts_info=[PartStructureInfo(part_id="P1", staves_voices={1: [1]})])

    assert md.move_attribute_order("octave", up=True) is True
    assert md.attribute_order[:2] == ["octave", "step"]

    assert md.move_attribute_order("octave", up=False) is True
    assert md.attribute_order[:2] == ["step", "octave"]


def test_move_attribute_order_boundary_and_unknown_key_are_no_ops():
    md = MusicData(parts_info=[PartStructureInfo(part_id="P1", staves_voices={1: [1]})])
    original = list(md.attribute_order)

    assert md.move_attribute_order("step", up=True) is False, "step is already first"
    assert md.move_attribute_order("strum", up=False) is False, "strum is already last"
    assert md.move_attribute_order("not-a-real-attribute", up=True) is False
    assert md.attribute_order == original


def test_move_attribute_order_within_scope_skips_hidden_neighbours():
    """A dialog filtered to attributes present for one Region 2 node
    (`within`) still moves the visible list by exactly one row per click -
    any attribute_order entries not in `within` sitting between the moved
    key and its visible neighbour are displaced, but their order among
    themselves is untouched."""
    md = MusicData(parts_info=[PartStructureInfo(part_id="P1", staves_voices={1: [1]})])

    md.attribute_order = ["A", "B", "C", "D", "E"]
    assert md.move_attribute_order("E", up=True, within=["A", "C", "E"]) is True
    assert md.attribute_order == ["A", "B", "E", "C", "D"]

    md.attribute_order = ["A", "B", "C", "D", "E"]
    assert md.move_attribute_order("A", up=False, within=["A", "C", "E"]) is True
    assert md.attribute_order == ["B", "C", "A", "D", "E"]


def test_move_attribute_order_within_scope_boundary_is_a_no_op():
    md = MusicData(parts_info=[PartStructureInfo(part_id="P1", staves_voices={1: [1]})])
    md.attribute_order = ["A", "B", "C", "D", "E"]

    assert md.move_attribute_order("A", up=True, within=["A", "C", "E"]) is False
    assert md.move_attribute_order("E", up=False, within=["A", "C", "E"]) is False
    assert md.attribute_order == ["A", "B", "C", "D", "E"]


def test_attribute_keys_for_voices_filters_by_voice_and_unions_across_notes(
    timeline, dynamics_articulation_fingering_score
):
    md = timeline(dynamics_articulation_fingering_score)

    piano_bass = md.attribute_keys_for_voices({("P1", 2, 2)})
    assert "fingering" in piano_bass
    assert "dynamic" not in piano_bass
    assert "articulation" not in piano_bass
    assert "pluck" not in piano_bass

    guitar = md.attribute_keys_for_voices({("P2", 1, 1)})
    assert "fingering" in guitar
    assert "pluck" in guitar
    assert "dynamic" not in guitar

    piano_treble = md.attribute_keys_for_voices({("P1", 1, 1)})
    assert "dynamic" in piano_treble
    assert "articulation" in piano_treble


def test_attribute_keys_for_voices_orders_by_attribute_order(
    timeline, dynamics_articulation_fingering_score
):
    md = timeline(dynamics_articulation_fingering_score)
    md.move_attribute_order("fingering", up=True, within=["dynamic", "articulation", "fingering"])

    keys = md.attribute_keys_for_voices({("P1", 1, 1)})

    assert keys.index("fingering") < keys.index("articulation")


def test_region_3_extra_attributes_follow_a_mutated_attribute_order(timeline, minimal_score):
    md = timeline(minimal_score)
    note = md.timeline_slices[0].notes[0]  # C, octave 4, a quarter note
    voice_key = (note.part_id, note.staff, note.voice)
    md.voice_display_attributes[voice_key] = {"duration", "step", "octave"}
    md.move_attribute_order("duration", up=True, within=["step", "octave", "duration"])

    assert md.get_region_3_data() == ["C, quarter, octave 4"]


def test_region_4_rows_follow_a_mutated_attribute_order(timeline, minimal_score):
    md = timeline(minimal_score)
    md.move_attribute_order("octave", up=True)  # now sits before "step"

    data_keys = list(md.get_region_4_data_for_indices([0]).keys())

    assert data_keys[0] == attribute_label("octave", md.uk_terms)
    assert data_keys[1] == attribute_label("step", md.uk_terms)


# --- Ref 27: export_config/apply_config -------------------------------------

def test_export_config_defaults_to_an_all_visible_empty_config(timeline, minimal_score):
    """A fresh MusicData with nothing toggled must export an empty
    voices_off (not the full voice list) - see apply_config's docstring for
    why voices_off, not an on-list, is what makes reloading best-effort."""
    md = timeline(minimal_score)

    config = md.export_config()

    assert config.voices_off == set()
    assert config.metronome_enabled is False
    assert config.position_announcer_enabled is False
    assert config.voice_display_attributes == {}
    assert config.attribute_order == md.DISPLAY_ATTRIBUTE_ORDER


def test_export_then_apply_config_round_trips_full_state(
    timeline, flute_crotchets_viola_semibreves_score
):
    md = timeline(flute_crotchets_viola_semibreves_score)
    md.set_active_voice_filter({("P2", 1, 1)})  # viola only, flute off
    md.voice_display_attributes[("P2", 1, 1)] = {"step", "octave"}
    md.move_attribute_order("octave", up=True)
    md.toggle_metronome()
    md.toggle_position_announcer()
    md.mixer.set_volume("P1", 86)
    md.mixer.set_pan("click", 0)

    config = md.export_config()

    fresh = timeline(flute_crotchets_viola_semibreves_score)
    fresh.apply_config(config)

    assert fresh.active_voice_filter == {("P2", 1, 1)}
    assert fresh.voice_display_attributes == {("P2", 1, 1): {"step", "octave"}}
    assert fresh.attribute_order == md.attribute_order
    assert fresh.metronome_enabled is True
    assert fresh.position_announcer_enabled is True
    assert fresh.mixer.volume_for("P1") == 86
    assert fresh.mixer.pan_for("click") == 0


def test_export_config_copies_the_mixer_not_alias_it(timeline, minimal_score):
    """Wishlist #4: export_config()/apply_config() must hand back an
    independent MixerSettings, or a later live edit to md.mixer (e.g. from
    the Mixer dialog) would silently mutate an already-saved ScoreConfig."""
    md = timeline(minimal_score)
    md.mixer.set_volume("P1", 50)

    config = md.export_config()
    md.mixer.set_volume("P1", 10)

    assert config.mixer.volume_for("P1") == 50

    fresh = timeline(minimal_score)
    fresh.apply_config(config)
    fresh.mixer.set_volume("P1", 99)

    assert config.mixer.volume_for("P1") == 50


def test_apply_config_is_best_effort_against_a_mismatched_score(timeline, minimal_score):
    """Ref 27: a saved config referencing a part/voice or attribute key that
    doesn't exist in the freshly-loaded score must be silently dropped -
    not rejected wholesale - and whatever else it references must still
    apply. This is the resolved "what if the config doesn't match" design
    question: best-effort, no dialog, no partial-vs-abort choice exposed to
    the user."""
    config = ScoreConfig(
        # "Classical Guitar" part/voice this score doesn't have - the
        # scenario from planning: config says a part is off, but that part
        # is simply absent from the current score.
        voices_off={("Classical Guitar", 1, 1)},
        metronome_enabled=True,
        position_announcer_enabled=True,
        voice_display_attributes={("Classical Guitar", 1, 1): {"step", "octave"}},
        attribute_order=["not-a-real-attribute", "octave", "step"],
    )

    target = timeline(minimal_score)  # single part "P1", no "Classical Guitar" voice at all
    target.apply_config(config)

    # The unknown voices_off entry doesn't correspond to anything in this
    # score, so every voice minimal_score actually has stays visible.
    assert target.active_voice_filter == {("P1", 1, 1)}
    # Same for voice_display_attributes: the unknown key is dropped.
    assert target.voice_display_attributes == {}
    # The unknown attribute key is dropped but the rest of the saved order
    # survives, and every valid key still ends up present (nothing vanishes
    # from rendering just because it wasn't in the saved list).
    assert "not-a-real-attribute" not in target.attribute_order
    assert target.attribute_order[:2] == ["octave", "step"]
    assert set(target.attribute_order) == set(target.DISPLAY_ATTRIBUTE_ORDER)
    # metronome_enabled has no notion of "matching the score", so it always
    # applies as-is.
    assert target.metronome_enabled is True
    assert target.position_announcer_enabled is True


def test_toggle_position_announcer_flips_state_without_touching_timeline(timeline, minimal_score):
    """Ref 28: unlike toggle_metronome, this must NOT change timeline_slices
    at all - AC5 says the position announcer never creates its own events."""
    md = timeline(minimal_score)
    original_slices = md.timeline_slices

    assert md.position_announcer_enabled is False

    md.toggle_position_announcer()
    assert md.position_announcer_enabled is True
    assert md.timeline_slices is original_slices

    md.toggle_position_announcer()
    assert md.position_announcer_enabled is False
    assert md.timeline_slices is original_slices


# --- S5: per-part instrument/name overrides ---------------------------------

def test_apply_part_overrides_renames_part_and_reprograms_it():
    """The dialog's OK path: parts_info is mutated in place, and
    NoteData.part_name (baked in at parse time - see CLAUDE.md's R5 note on
    TimelineBuilder._part_names) is kept in sync, or a part_name-keyed
    lookup like get_performance_report_lines would silently show the old
    name."""
    md = MusicData(parts_info=[PartStructureInfo(part_id="P1", name="Track 1", gmidi_program=1)])
    note = _note(part_id="P1")
    md.timeline_slices = [EventSlice(measure=1, beat_position=1.0, quarter_length=1.0, notes=[note])]
    md._real_timeline_slices = md.timeline_slices

    md.apply_part_overrides({"P1": "Cool Violin"}, {"P1": 41})

    assert md.parts_info[0].name == "Cool Violin"
    assert md.parts_info[0].gmidi_program == 41
    assert note.part_name == "Cool Violin"
    assert md.get_gmidi_program_for_part("P1") == 41


def test_apply_part_overrides_leaves_other_parts_untouched():
    md = MusicData(parts_info=[
        PartStructureInfo(part_id="P1", name="Flute", gmidi_program=74),
        PartStructureInfo(part_id="P2", name="Viola", gmidi_program=42),
    ])
    flute_note = _note(part_id="P1")
    viola_note = _note(part_id="P2")
    md.timeline_slices = [
        EventSlice(measure=1, beat_position=1.0, quarter_length=1.0, notes=[flute_note]),
        EventSlice(measure=1, beat_position=2.0, quarter_length=1.0, notes=[viola_note]),
    ]
    md._real_timeline_slices = md.timeline_slices

    md.apply_part_overrides({"P1": "Cool Flute"}, {})

    assert flute_note.part_name == "Cool Flute"
    assert viola_note.part_name == "Test"  # _note()'s default, untouched
    assert md.parts_info[1].name == "Viola"


def test_export_config_then_apply_config_round_trips_part_overrides():
    md = MusicData(parts_info=[PartStructureInfo(part_id="P1", name="Track 1", gmidi_program=1)])
    md.apply_part_overrides({"P1": "Cool Violin"}, {"P1": 41})

    config = md.export_config()

    fresh = MusicData(parts_info=[PartStructureInfo(part_id="P1", name="Track 1", gmidi_program=1)])
    fresh.apply_config(config)

    assert fresh.parts_info[0].name == "Cool Violin"
    assert fresh.parts_info[0].gmidi_program == 41


def test_apply_config_drops_a_part_override_for_a_part_no_longer_in_the_score():
    """Best-effort, same as every other ScoreConfig field: a saved override
    for a part_id the freshly-loaded score no longer has must be silently
    dropped, not applied to nothing or raise."""
    config = ScoreConfig(
        part_name_overrides={"P99": "Ghost"}, part_program_overrides={"P99": 10}
    )
    md = MusicData(parts_info=[PartStructureInfo(part_id="P1", name="Track 1", gmidi_program=1)])

    md.apply_config(config)

    assert md.parts_info[0].name == "Track 1"
    assert md.parts_info[0].gmidi_program == 1


# --- S6: key signature override ---------------------------------------------

def _midi_note(file_key_fifths, midi_pitch=66, step_name="") -> NoteData:
    """MIDI pitch 66 = F#4 (pc 6) - spells "F sharp" under the sharp
    convention (fifths >= 0) or "G flat" under the flat one (fifths < 0),
    so it's a clear witness for which convention was actually applied."""
    return NoteData(
        step_name=step_name, measure=1, beat_position=1.0, ts_duration=1.0,
        quarter_length=1.0, part_id="P1", part_name="Test", staff=1, voice=1,
        midi_pitch=midi_pitch, file_key_fifths=file_key_fifths,
    )


def _midi_music_data(note) -> MusicData:
    """is_midi requires a .mid file_path; that path doesn't exist on disk,
    but MidiTimelineBuilder.build() catches the resulting parse failure and
    returns an empty timeline (see parsers/midi_timeline_builder.py), which
    is then overwritten below - same manual-stub pattern S5's tests use."""
    md = MusicData(file_path="x.mid", parts_info=[PartStructureInfo(part_id="P1", name="Test")])
    md.timeline_slices = [EventSlice(measure=1, beat_position=1.0, quarter_length=1.0, notes=[note])]
    md._real_timeline_slices = md.timeline_slices
    return md


def test_apply_key_signature_override_respells_midi_notes():
    note = _midi_note(file_key_fifths=0, step_name="F sharp")  # file's own key: C major
    md = _midi_music_data(note)

    md.apply_key_signature_override(-2, "major")  # B flat major - flat convention

    assert note.step_name == "G flat"
    assert md.key_signature_override_fifths == -2
    assert md.key_signature_override_mode == "major"


def test_clearing_the_key_override_restores_each_notes_own_file_key():
    """file_key_fifths=-2 means the FILE's own key uses the flat convention -
    the note starts artificially set to "F sharp" (as if an override were
    already active) specifically so clearing can be observed actually
    recomputing, not merely leaving it alone."""
    note = _midi_note(file_key_fifths=-2, step_name="F sharp")
    md = _midi_music_data(note)

    md.apply_key_signature_override(None, None)

    assert note.step_name == "G flat"
    assert md.key_signature_override_fifths is None
    assert md.key_signature_override_mode is None


def test_key_override_never_touches_musicxml_note_spelling():
    note = NoteData(
        step_name="F sharp", measure=1, beat_position=1.0, ts_duration=1.0,
        quarter_length=1.0, part_id="P1", part_name="Test", staff=1, voice=1,
        midi_pitch=66,
    )
    md = MusicData(parts_info=[PartStructureInfo(part_id="P1", name="Test")])  # no file_path -> not MIDI
    md.timeline_slices = [EventSlice(measure=1, beat_position=1.0, quarter_length=1.0, notes=[note])]
    md._real_timeline_slices = md.timeline_slices

    md.apply_key_signature_override(-2, "major")

    assert note.step_name == "F sharp"
    assert md.key_signature_override_fifths == -2


def test_region_1_key_signature_reflects_the_override():
    md = MusicData(credits={"Key Signature": "C major / A minor"})

    md.apply_key_signature_override(1, "major")

    assert md.get_region_1_data()["Key Signature"] == "G major"


def test_status_bar_key_field_reflects_the_override(timeline, minimal_score):
    md = timeline(minimal_score)

    md.apply_key_signature_override(-2, "minor")

    assert md.get_status_bar_fields()[1] == "Key: G minor"


def test_status_bar_key_field_falls_back_to_the_files_own_key_with_no_override(
    timeline, minimal_score
):
    md = timeline(minimal_score)  # fixture's own <key><fifths>0</fifths></key>

    assert md.get_status_bar_fields()[1] == "Key: C major / A minor"


def test_export_config_then_apply_config_round_trips_key_signature_override():
    md = MusicData(parts_info=[PartStructureInfo(part_id="P1", name="Test")])
    md.apply_key_signature_override(-2, "minor")

    config = md.export_config()

    fresh = MusicData(parts_info=[PartStructureInfo(part_id="P1", name="Test")])
    fresh.apply_config(config)

    assert fresh.key_signature_override_fifths == -2
    assert fresh.key_signature_override_mode == "minor"
