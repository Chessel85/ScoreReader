# tests/models/test_timeline_characterisation.py
"""Characterisation tests for _build_timeline_from_xml - A2.

These pin down behaviour that A3-A6 must not break: they all rewrite
_build_timeline_from_xml, and this file is what proves nothing regressed.
Written against hand-crafted fixtures (see tests/fixtures/) so each test
isolates one behaviour, per D-8.
"""
from models.music_data import MusicData


def test_quarter_note_is_one_beat_unit_in_four_four(timeline, minimal_score):
    """Ref 18: in 4/4 the beat unit is a quarter note, so ts_duration == 1.0."""
    md = timeline(minimal_score)

    assert md.timeline_slices[0].notes[0].ts_duration == 1.0


def test_quarter_note_is_two_beat_units_in_six_eight(timeline, six_eight_score):
    """Ref 18: in 6/8 the beat unit is an eighth note, so a quarter is 2.0."""
    md = timeline(six_eight_score)

    c_note, d_note = md.timeline_slices[0].notes[0], md.timeline_slices[1].notes[0]
    assert (c_note.step_name, d_note.step_name) == ("C", "D")
    assert c_note.ts_duration == 2.0
    assert d_note.ts_duration == 2.0


def test_eighth_note_is_one_beat_unit_in_six_eight(timeline, six_eight_score):
    """Ref 18: an eighth note is exactly one beat unit in 6/8, so ts_duration == 1.0."""
    md = timeline(six_eight_score)

    e_note, f_note = md.timeline_slices[2].notes[0], md.timeline_slices[3].notes[0]
    assert (e_note.step_name, f_note.step_name) == ("E", "F")
    assert e_note.ts_duration == 1.0
    assert f_note.ts_duration == 1.0


def test_chord_notes_share_one_event_slice(timeline, chord_score):
    """A <chord/> note shares its predecessor's offset, not a new one."""
    md = timeline(chord_score)

    chord_slice = next(s for s in md.timeline_slices if len(s.notes) > 1)
    assert {n.step_name for n in chord_slice.notes} == {"D", "F"}
    # Sorted highest pitch first within the instrument, regardless of the
    # source XML's D-then-F chord order (F4 > D4).
    assert [n.step_name for n in chord_slice.notes] == ["F", "D"]

    step_names = [s.notes[0].step_name for s in md.timeline_slices]
    assert step_names == ["C", "F", "G", "A"]


def test_string_and_fret_captured_from_notations_technical(timeline, string_fret_score):
    """Guitar tab data lives at notations/technical/{string,fret}."""
    md = timeline(string_fret_score)

    first_note = md.timeline_slices[0].notes[0]
    assert first_note.step_name == "E"
    assert first_note.string == 1
    assert first_note.fret == 0

    second_note = md.timeline_slices[1].notes[0]
    assert second_note.step_name == "G"
    assert second_note.string == 2
    assert second_note.fret == 3


def _note_by_pitch(md, step_name, octave):
    return next(
        n for s in md.timeline_slices for n in s.notes
        if n.step_name == step_name and n.octave == octave
    )


def test_direction_dynamics_attach_to_the_chord_that_follows(timeline, dynamics_articulation_fingering_score):
    """F3/Ref 16 AC3: a <direction><dynamics><f/></dynamics></direction>
    sibling is matched to the note landing at the same offset/staff, and
    both notes of a chord sharing that offset inherit it."""
    md = timeline(dynamics_articulation_fingering_score)

    c5 = _note_by_pitch(md, "C", 5)
    e5 = _note_by_pitch(md, "E", 5)
    assert c5.dynamic == "forte"
    assert e5.dynamic == "forte"


def test_dynamics_do_not_leak_onto_unrelated_notes(timeline, dynamics_articulation_fingering_score):
    """Only the note(s) at the direction's own offset/staff get the mark -
    a bass-staff note landing at the same offset in a different staff must
    not inherit the treble-staff direction."""
    md = timeline(dynamics_articulation_fingering_score)

    c3 = _note_by_pitch(md, "C", 3)
    assert c3.dynamic is None


def test_articulation_captured_from_notations_articulations(timeline, dynamics_articulation_fingering_score):
    md = timeline(dynamics_articulation_fingering_score)

    d5 = _note_by_pitch(md, "D", 5)
    assert d5.articulation == "staccato"


def test_ornament_captured_from_notations_ornaments(timeline, dynamics_articulation_fingering_score):
    md = timeline(dynamics_articulation_fingering_score)

    f5 = _note_by_pitch(md, "F", 5)
    assert f5.articulation == "trill"


def test_piano_fingering_captured_on_both_staves(timeline, dynamics_articulation_fingering_score):
    """notations/technical/fingering has no hand flag in MusicXML - both
    the treble-staff and bass-staff note just carry their own raw digit."""
    md = timeline(dynamics_articulation_fingering_score)

    g5 = _note_by_pitch(md, "G", 5)
    c3 = _note_by_pitch(md, "C", 3)
    assert g5.fingering == "1"
    assert c3.fingering == "5"


def test_guitar_note_captures_both_left_hand_fingering_and_right_hand_pluck(
    timeline, dynamics_articulation_fingering_score
):
    md = timeline(dynamics_articulation_fingering_score)

    e4 = _note_by_pitch(md, "E", 4)
    assert e4.fingering == "2"
    assert e4.pluck == "i"


def test_note_with_no_extra_attributes_leaves_all_four_fields_none(timeline, dynamics_articulation_fingering_score):
    md = timeline(dynamics_articulation_fingering_score)

    g4 = _note_by_pitch(md, "G", 4)
    assert g4.dynamic is None
    assert g4.articulation is None
    assert g4.fingering is None
    assert g4.pluck is None


def test_multiple_fingering_and_pluck_marks_on_one_note_are_all_captured(timeline, multi_value_technical_score):
    """A rasgueado-style note can carry more than one <fingering>/<pluck> in
    the same notations/technical block - all of them must survive, not just
    the first (regression: live MuseScore export hit this)."""
    md = timeline(multi_value_technical_score)

    note = md.timeline_slices[0].notes[0]
    assert note.fingering == "1, 2"
    assert note.pluck == "i, m, a"


def test_slices_are_ordered_by_measure_then_offset(timeline, slice_ordering_score):
    """Notes written out of offset order via forward/backup must still sort.

    The fixture writes G (offset 2) before C and D (offsets 0-1) before F
    (offset 3); the timeline must come out C, D, G, F regardless.
    """
    md = timeline(slice_ordering_score)

    assert [s.notes[0].step_name for s in md.timeline_slices] == ["C", "D", "G", "F"]
    assert [s.beat_position for s in md.timeline_slices] == [1.0, 2.0, 3.0, 4.0]


def test_pickup_already_numbered_zero_stays_measure_zero(timeline, score_duet):
    """Ref 17: Chessel Duet numbers its pickup 0 - it must not be re-indexed."""
    md = timeline(score_duet)

    pickup_slice = md.timeline_slices[0]
    assert pickup_slice.measure == 0


def test_time_signature_change_mid_score_is_tracked_per_measure(timeline, ts_change_score):
    """Ref 18: a quarter note's ts_duration must follow ITS OWN measure's
    time signature, not whatever the first measure in the file declared.

    Measure 1 is 4/4 (quarter note = ts_duration 1.0); measure 2 changes to
    6/8, where a quarter note is two beat units (ts_duration 2.0).
    """
    md = timeline(ts_change_score)

    m1_notes = [n for s in md.timeline_slices for n in s.notes if n.measure == 1]
    m2_notes = [n for s in md.timeline_slices for n in s.notes if n.measure == 2]

    c_note = next(n for n in m1_notes if n.step_name == "C")
    assert c_note.ts_duration == 1.0

    g_note = next(n for n in m2_notes if n.step_name == "G")
    b_note = next(n for n in m2_notes if n.step_name == "B")
    assert g_note.ts_duration == 2.0  # quarter note in 6/8
    assert b_note.ts_duration == 1.0  # eighth note in 6/8


def test_divisions_change_mid_score_is_tracked_per_measure(timeline, ts_change_score):
    """Ref 18: quarter_length must use the divisions active in THAT measure.

    Measure 3 changes divisions from 4 to 8 and reverts to 4/4. A quarter
    note there (duration=8) must still resolve to quarter_length 1.0, not
    2.0 as it would if a stale divisions=4 were applied.
    """
    md = timeline(ts_change_score)

    d5_note = next(
        n for s in md.timeline_slices for n in s.notes if n.measure == 3 and n.step_name == "D"
    )
    assert d5_note.quarter_length == 1.0
    assert d5_note.ts_duration == 1.0


def test_quarters_from_start_accumulates_through_time_signature_changes(timeline, ts_change_score):
    """E4: real elapsed-time offset for the Sequencer, independent of
    beat_position's ts-relative display units (Ref 18). Measure 1 is 4/4
    (4.0 quarters long), measure 2 is 6/8 (3.0 quarters long) - measure 3
    must start at 4.0 + 3.0 = 7.0, not 4.0 + 4.0 as it would if measure 2's
    own (shorter) length were ignored."""
    md = timeline(ts_change_score)

    m1_first = next(s for s in md.timeline_slices if s.measure == 1)
    m2_first = next(s for s in md.timeline_slices if s.measure == 2)
    m3_first = next(s for s in md.timeline_slices if s.measure == 3)

    assert m1_first.quarters_from_start == 0.0
    assert m2_first.quarters_from_start == 4.0
    assert m3_first.quarters_from_start == 7.0


def test_every_tempo_marking_is_captured_not_just_the_first(timeline, tempo_change_score):
    """Ref 12 "multi-tempo scope": TimelineBuilder walks the whole file for
    <sound tempo=.../> markings, not just the first one MusicXMLReader's own
    music21-based _extract_tempo looks at."""
    md = timeline(tempo_change_score)

    assert [c.tempo_bpm for c in md.tempo_changes] == [100, 200]
    assert [c.quarters_from_start for c in md.tempo_changes] == [0.0, 4.0]
    assert [c.beat_unit_name for c in md.tempo_changes] == ["quarter", "quarter"]


def test_effective_tempo_bpm_follows_the_marking_in_effect_at_each_index(
    timeline, tempo_change_score
):
    """The tempo used for playback timing must switch exactly at the
    measure the new marking belongs to, not apply retroactively or lag."""
    md = timeline(tempo_change_score)

    m1_last_index = next(i for i, s in enumerate(md.timeline_slices) if s.measure == 1 and s.notes[0].step_name == "F")
    m2_first_index = next(i for i, s in enumerate(md.timeline_slices) if s.measure == 2 and s.notes[0].step_name == "G")

    assert md.effective_tempo_bpm(m1_last_index) == 100
    assert md.effective_tempo_bpm(m2_first_index) == 200


def test_playback_tempo_offset_applies_on_top_of_whichever_tempo_is_current(
    timeline, tempo_change_score
):
    """F/S (Ref 12 AC3) add to "whatever the current tempo is" per-position,
    not always the score's opening tempo."""
    md = timeline(tempo_change_score)
    md.active_event_index = 0  # measure 1, tempo 100
    md.set_playback_tempo_offset(10)

    assert md.effective_tempo_bpm(0) == 110

    m2_first_index = next(i for i, s in enumerate(md.timeline_slices) if s.measure == 2)
    assert md.effective_tempo_bpm(m2_first_index) == 210


def test_repeat_and_ending_spans_are_paired_correctly(timeline, repeats_and_endings_score):
    """Ref 29: forward repeat (m2) pairs with the backward repeat (m3);
    ending 1 (start+discontinue both in m3) and ending 2 (start+discontinue
    both in m4, no trailing repeat - the "last time through" case) are each
    their own EndingSpan."""
    md = timeline(repeats_and_endings_score)

    assert len(md.repeat_spans) == 1
    assert (md.repeat_spans[0].start_measure, md.repeat_spans[0].end_measure) == (2, 3)

    assert len(md.ending_spans) == 2
    e1, e2 = md.ending_spans
    assert (e1.number, e1.start_measure, e1.end_measure) == (1, 3, 3)
    assert (e2.number, e2.start_measure, e2.end_measure) == (2, 4, 4)


def test_unmatched_backward_repeat_defaults_start_to_measure_one(
    timeline, unmatched_backward_repeat_score
):
    """A backward repeat with no preceding forward repeat is the standard
    notation reading of an unmarked opening repeat (Ref 29)."""
    md = timeline(unmatched_backward_repeat_score)

    assert len(md.repeat_spans) == 1
    assert (md.repeat_spans[0].start_measure, md.repeat_spans[0].end_measure) == (1, 2)


def test_hairpin_spans_cross_measure_and_same_measure(timeline, hairpin_score):
    """Ref 29: a crescendo starting at m1 beat 3 and stopping at m2 beat 2
    (crosses a measure boundary), and a diminuendo fully contained within
    m3 (beat 1 to beat 3) - both captured with their ts-relative beat
    positions and monotonic quarters_from_start."""
    md = timeline(hairpin_score)

    assert len(md.hairpin_spans) == 2
    crescendo, diminuendo = md.hairpin_spans

    assert crescendo.kind == "crescendo"
    assert (crescendo.start_measure, crescendo.start_beat_position) == (1, 3.0)
    assert (crescendo.end_measure, crescendo.end_beat_position) == (2, 2.0)
    assert crescendo.start_quarters_from_start == 2.0
    assert crescendo.end_quarters_from_start == 5.0

    assert diminuendo.kind == "diminuendo"
    assert (diminuendo.start_measure, diminuendo.start_beat_position) == (3, 1.0)
    assert (diminuendo.end_measure, diminuendo.end_beat_position) == (3, 3.0)


def test_total_measures_counts_the_whole_score_not_just_sounding_slices(
    timeline, repeats_and_endings_score
):
    """Ref 29: sourced from measure_start_quarters (built regardless of note
    content), not timeline_slices, which would undercount a trailing
    all-rest measure - not exercised by this fixture (every bar has a
    note), but the source must be the structural one regardless."""
    md = timeline(repeats_and_endings_score)

    assert md.total_measures == 4


def test_performance_region_rows_follow_the_cursor_into_and_out_of_a_span(
    timeline, repeats_and_endings_score
):
    """Ref 29: Region 5's rows are empty outside any span, two rows per
    active repeat/ending span while inside one, in the documented order
    (repeats, then endings)."""
    md = timeline(repeats_and_endings_score)

    m1_index = next(i for i, s in enumerate(md.timeline_slices) if s.measure == 1)
    assert md.get_performance_region_rows(m1_index) == []

    m3_index = next(i for i, s in enumerate(md.timeline_slices) if s.measure == 3)
    rows = md.get_performance_region_rows(m3_index)
    labels = [r.label for r in rows]
    assert labels == [
        "Repeat start: measure 2",
        "Repeat end: measure 3",
        "Ending 1 start: measure 3",
        "Ending 1 end: measure 3",
    ]


def test_performance_region_rows_hairpin_wording_omits_beat_on_the_downbeat(
    timeline, hairpin_score
):
    """Ref 29 follow-up (user-requested): a marker landing exactly on beat 1
    needs no beat spelled out - "measure N" alone already pins it down, the
    same as every repeat/ending row (barlines only occur at measure
    boundaries, so they never show a beat either). Only an off-the-downbeat
    position (e.g. the crescendo's own start/end here) gets "measure N
    beat B" appended, matching get_status_bar_fields's own wording."""
    md = timeline(hairpin_score)

    crescendo_start_index = md.slice_index_at_or_after_quarters(2.0)  # m1 beat 3
    labels = [r.label for r in md.get_performance_region_rows(crescendo_start_index)]
    assert labels == [
        "Crescendo start: measure 1 beat 3",
        "Crescendo end: measure 2 beat 2",
    ]

    diminuendo_start_index = next(
        i
        for i, s in enumerate(md.timeline_slices)
        if s.measure == 3 and s.notes[0].step_name == "D"
    )
    labels = [r.label for r in md.get_performance_region_rows(diminuendo_start_index)]
    assert labels == [
        "Diminuendo start: measure 3",
        "Diminuendo end: measure 3 beat 3",
    ]


# --- S7: one-shot time-signature/tempo change alerts ------------------------

def test_time_signature_change_fires_a_one_shot_row_at_the_transition(
    timeline, ts_change_score
):
    """ts_change_score: 4/4 (bar 1) -> 6/8 (bar 2) -> 4/4 (bar 3)."""
    md = timeline(ts_change_score)

    assert md.get_performance_region_rows(0) == []  # bar 1: the opening signature, no alert
    assert [r.label for r in md.get_performance_region_rows(3)] == []  # still 4/4, last slice of bar 1

    bar_2_index = md.first_event_index_of_measure(2)
    assert [r.label for r in md.get_performance_region_rows(bar_2_index)] == [
        "Time signature change: 6/8"
    ]
    # One-shot: the row is gone again one slice later, still inside bar 2.
    assert md.get_performance_region_rows(bar_2_index + 1) == []

    bar_3_index = md.first_event_index_of_measure(3)
    assert [r.label for r in md.get_performance_region_rows(bar_3_index)] == [
        "Time signature change: 4/4"
    ]


def test_tempo_change_fires_a_one_shot_row_at_the_transition(timeline, tempo_change_score):
    """tempo_change_score: quarter=100 (bar 1) -> quarter=200 (bar 2)."""
    md = timeline(tempo_change_score)

    assert md.get_performance_region_rows(0) == []  # bar 1: the opening tempo, no alert

    bar_2_index = md.first_event_index_of_measure(2)
    assert [r.label for r in md.get_performance_region_rows(bar_2_index)] == [
        "Tempo change: 200 quarter notes per minute"
    ]
    assert md.get_performance_region_rows(bar_2_index + 1) == []


def test_time_signature_and_tempo_change_rows_both_fire_when_they_land_on_the_same_slice(
    midi_test2,
):
    """midi_test2 changes both together at bar 9 (4/4->3/4, 120->80bpm)."""
    md = MusicData(file_path=midi_test2)

    bar_9_index = md.first_event_index_of_measure(9)
    assert [r.label for r in md.get_performance_region_rows(bar_9_index)] == [
        "Time signature change: 3/4",
        "Tempo change: 80 quarter notes per minute",
    ]


def test_tempo_change_row_reports_the_scores_own_number_not_the_playback_offset(
    timeline, tempo_change_score
):
    """The alert is about the SCORE's own tempo markings, not the user's
    live F/S/D playback offset (Ref 12) - the row must still read "200",
    not "220", and the offset alone (unchanged across bars 1 and 2) must
    not itself register as a "change"."""
    md = timeline(tempo_change_score)
    md.set_playback_tempo_offset(20)

    bar_2_index = md.first_event_index_of_measure(2)
    assert [r.label for r in md.get_performance_region_rows(bar_2_index)] == [
        "Tempo change: 200 quarter notes per minute"
    ]



def test_slice_index_at_or_after_quarters_resolves_a_hairpin_jump_target(
    timeline, hairpin_score
):
    """Ref 29: Region 5's Ctrl+Home/Ctrl+End on a hairpin row resolves via
    this quarters-based lookup, not the measure-only first/last_visible_
    event_index_of_measure lookups repeat/ending rows use."""
    md = timeline(hairpin_score)

    index = md.slice_index_at_or_after_quarters(2.0)
    assert md.timeline_slices[index].quarters_from_start == 2.0
    assert md.timeline_slices[index].notes[0].step_name == "E"


def test_last_visible_event_index_of_measure_finds_the_last_note(
    timeline, repeats_and_endings_score
):
    """Ref 29: Region 5's Ctrl+End on a repeat/ending row lands on the LAST
    sounding note of the end bar, not the first - the one place this app
    needs that "last event in a measure" concept."""
    md = timeline(repeats_and_endings_score)

    first = md.first_visible_event_index_of_measure(3)
    last = md.last_visible_event_index_of_measure(3)
    assert first == last, "this fixture's measure 3 has only one note"
    assert md.timeline_slices[last].notes[0].step_name == "E"


def test_quarters_from_start_is_continuous_across_the_pickup_boundary(timeline, score_duet):
    """E4: the pickup bar's real duration is however much of it is actually
    filled (pickup_filled_quarters), not a full bar - measure 1 must start
    exactly where the pickup's last event ends, with no gap or overlap."""
    md = timeline(score_duet)

    pickup_slices = [s for s in md.timeline_slices if s.measure == 0]
    measure_1_first = next(s for s in md.timeline_slices if s.measure == 1)

    last_pickup_slice = pickup_slices[-1]
    assert (
        last_pickup_slice.quarters_from_start + last_pickup_slice.quarter_length
        == measure_1_first.quarters_from_start
    )


def test_explicit_rest_becomes_its_own_timeline_event(timeline, rest_score):
    """Ref 16 AC2: an explicit <rest/> is a navigable event, not skipped."""
    md = timeline(rest_score)

    step_names = [s.notes[0].step_name for s in md.timeline_slices]
    assert step_names == ["C", "rest", "E", "F"]


def test_rest_note_has_no_octave_or_midi_pitch(timeline, rest_score):
    """Ref 16 AC2: a rest carries no pitch - octave/midi_pitch are None."""
    md = timeline(rest_score)

    rest_slice = next(s for s in md.timeline_slices if s.notes[0].step_name == "rest")
    rest_note = rest_slice.notes[0]

    assert rest_note.octave is None
    assert rest_note.midi_pitch is None


def test_notes_are_stamped_with_their_real_part_id_and_name(timeline, score_duet):
    """A4: part_id/part_name must reflect each note's own <part>, not part 1.

    Chessel Duet is Piano (P1) + Classical Guitar (P2). Before A4 every note
    was labelled "Piano" because part_name was hard-coded to parts_info[0].
    """
    md = timeline(score_duet)

    piano_notes = [n for s in md.timeline_slices for n in s.notes if n.part_id == "P1"]
    guitar_notes = [n for s in md.timeline_slices for n in s.notes if n.part_id == "P2"]

    assert piano_notes, "expected at least one Piano (P1) note"
    assert guitar_notes, "expected at least one Guitar (P2) note"
    assert all(n.part_name == "Piano" for n in piano_notes)
    assert all(n.part_name == "Classical Guitar" for n in guitar_notes)


def test_first_full_bar_after_zero_numbered_pickup_is_measure_one(timeline, score_duet):
    """Ref 17: the first full bar after a 0-numbered pickup must be measure 1

    starting at beat 1, not measure 0 starting at beat 4 (see A3 in tasks.txt
    for the mechanism of the bug).
    """
    md = timeline(score_duet)

    first_full_bar_note = next(
        n
        for s in md.timeline_slices
        for n in s.notes
        if n.step_name == "D" and n.octave == 5
    )
    assert first_full_bar_note.measure == 1
    assert first_full_bar_note.beat_position == 1.0


def test_note_part_names_come_from_parts_info_when_the_reader_supplied_it(score_duet):
    """R5: TimelineBuilder used to re-read <part-list>/<score-part>/
    <part-name> itself, independently of MusicXMLReader's own read of the
    same elements, and the two were required to agree exactly. They diverged
    once (one filtered non-ASCII names, the other didn't) and the Performance
    Report - which joins note.part_name to PartStructureInfo.name - silently
    reported 0 notes for a fully-noted part.

    Names are now derived from parts_info, so agreement is structural rather
    than a convention to remember. Proved here by handing TimelineBuilder a
    parts_info the file itself contradicts: if it were still reading the XML,
    the file's own names would win."""
    from models.parts_structure import PartStructureInfo
    from parsers.timeline_builder import TimelineBuilder

    supplied = [
        PartStructureInfo(part_id="P1", name="Renamed By Reader"),
        PartStructureInfo(part_id="P2", name="Also Renamed"),
    ]
    slices = TimelineBuilder(score_duet, supplied).build()

    names = {n.part_name for s in slices for n in s.notes}
    assert names == {"Renamed By Reader", "Also Renamed"}


def test_part_names_still_read_from_the_file_when_there_is_no_parts_info(score_duet):
    """The no-reader path (MusicData(file_path=...) built directly, which is
    how every timeline test and TimelineBuilder's own fast path work) has no
    parts_info at all, so the etree fallback must stay."""
    from parsers.timeline_builder import TimelineBuilder

    slices = TimelineBuilder(score_duet, []).build()

    names = {n.part_name for s in slices for n in s.notes}
    assert names == {"Piano", "Classical Guitar"}


# Synthetic Chords/Lyrics parts from <harmony>/<lyric> markup on a real
# MusicXML file, modelled on files/Three Blind Mice.mxl - the UG-import-
# style "an instrument called Chords" / "lyrics are also an instrument/part"
# UX, but bucketed into the SAME slices as the real notated part instead of
# fabricated one-bar-per-chord positions (see parsers/timeline_builder.py).

def _notes_by_part(slice_, part_id):
    return [n for n in slice_.notes if n.part_id == part_id]


def test_harmony_becomes_a_chords_part_note_in_the_same_slice(timeline, chords_and_lyrics_score):
    from parsers.timeline_builder import CHORDS_PART_ID, CHORDS_PART_NAME

    md = timeline(chords_and_lyrics_score)

    first_slice = md.timeline_slices[0]
    chord_notes = _notes_by_part(first_slice, CHORDS_PART_ID)
    assert len(chord_notes) == 1
    chord_note = chord_notes[0]
    assert chord_note.step_name == "A minor", "a bare 'm' reads as the letter to a screen reader, not 'minor'"
    assert chord_note.part_name == CHORDS_PART_NAME
    assert chord_note.chord_pitches == [45, 48, 52]  # A2, C3, E3 (music21's default triad octave)
    assert chord_note.midi_pitch == max(chord_note.chord_pitches)

    # Only the bar's one harmony - no Chords note anywhere else in the piece.
    later_chord_notes = [
        n for s in md.timeline_slices[1:] for n in _notes_by_part(s, CHORDS_PART_ID)
    ]
    assert later_chord_notes == []


def test_lyric_attaches_to_the_same_slice_as_its_melody_note(timeline, chords_and_lyrics_score):
    from parsers.timeline_builder import LYRICS_PART_ID, LYRICS_PART_NAME

    md = timeline(chords_and_lyrics_score)

    lyrics_by_slice = [
        (s.notes[0].step_name, [n.step_name for n in _notes_by_part(s, LYRICS_PART_ID)])
        for s in md.timeline_slices
    ]
    assert lyrics_by_slice == [
        ("C", ["Hel"]),
        ("D", ["lo"]),
        ("E", ["there"]),
        ("rest", []),  # the trailing rest has no <lyric> - no Lyrics entry at all
    ]

    lyric_note = _notes_by_part(md.timeline_slices[0], LYRICS_PART_ID)[0]
    assert lyric_note.part_name == LYRICS_PART_NAME
    assert lyric_note.midi_pitch is None, "the Lyrics part is silent, like a rest"


def test_arpeggiate_direction_becomes_strum_on_the_real_note(timeline, chords_and_lyrics_score):
    """A <notations/arpeggiate direction=.../> on a single (non-chord) note
    is read as a pick/strum-direction indicator, using the same "down
    stroke"/"up stroke" vocabulary Guitar Pro's synthetic Chords voice
    already established for NoteData.strum - never inferred when absent."""
    from parsers.timeline_builder import CHORDS_PART_ID

    md = timeline(chords_and_lyrics_score)

    piano_notes = [
        n for s in md.timeline_slices for n in s.notes
        if n.part_id != CHORDS_PART_ID and n.step_name not in ("Hel", "lo", "there")
    ]
    strums = {n.step_name: n.strum for n in piano_notes if n.midi_pitch is not None}
    assert strums == {"C": "down stroke", "D": "up stroke", "E": None}


def test_no_harmony_or_lyric_means_no_synthetic_parts(timeline, minimal_score):
    """An ordinary MusicXML file with no <harmony>/<lyric> markup gets no
    empty Chords/Lyrics rows."""
    from parsers.timeline_builder import CHORDS_PART_ID, LYRICS_PART_ID

    md = timeline(minimal_score)

    part_ids = {n.part_id for s in md.timeline_slices for n in s.notes}
    assert CHORDS_PART_ID not in part_ids
    assert LYRICS_PART_ID not in part_ids
