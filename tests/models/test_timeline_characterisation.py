# tests/models/test_timeline_characterisation.py
"""Characterisation tests for _build_timeline_from_xml - A2.

These pin down behaviour that A3-A6 must not break: they all rewrite
_build_timeline_from_xml, and this file is what proves nothing regressed.
Written against hand-crafted fixtures (see tests/fixtures/) so each test
isolates one behaviour, per D-8.
"""
import pytest


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

    step_names = [s.notes[0].step_name for s in md.timeline_slices]
    assert step_names == ["C", "D", "G", "A"]


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
