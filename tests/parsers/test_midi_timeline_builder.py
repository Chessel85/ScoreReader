# tests/parsers/test_midi_timeline_builder.py
from models.music_data import MusicData
from models.parts_structure import PartStructureInfo
from parsers.midi_source import MidiNoteEvent, MidiSource, MidiTrackData
from parsers.midi_timeline_builder import MidiTimelineBuilder


def _one_note_source(quarter_length: float, division: int = 480) -> MidiSource:
    """A minimal MidiSource: one usable track, one note of the given
    quarter-note duration starting at tick 0, 4/4 throughout."""
    end_tick = round(quarter_length * division)
    track = MidiTrackData(
        track_index=0,
        part_id="P0",
        name="Test",
        note_events=[MidiNoteEvent(channel=0, pitch=60, velocity=80, start_tick=0, end_tick=end_tick)],
        channels_used=[0],
    )
    return MidiSource(format=0, division=division, time_signature_changes=[(0, 4, 4)], tracks=[track])


def _track_source(quarter_lengths: list, division: int = 480) -> MidiSource:
    """A minimal MidiSource: one usable track, one note per quarter_length,
    placed back-to-back (each starting where the previous one ends)."""
    events = []
    tick = 0
    for ql in quarter_lengths:
        end_tick = tick + round(ql * division)
        events.append(MidiNoteEvent(channel=0, pitch=60, velocity=80, start_tick=tick, end_tick=end_tick))
        tick = end_tick
    track = MidiTrackData(
        track_index=0, part_id="P0", name="Test", note_events=events, channels_used=[0]
    )
    return MidiSource(format=0, division=division, time_signature_changes=[(0, 4, 4)], tracks=[track])


def test_pickup_bar_becomes_measure_0(midi_bach_bourree):
    """Ref 17, MIDI-native: bach-bourree-tab.mid's pickup is a real short
    1/4 time-signature span (see test_midi_source.py), not an
    implicit="yes" flag - MidiTimelineBuilder must still land it on measure
    0, same convention as the MusicXML path."""
    data = MusicData(file_path=midi_bach_bourree)
    assert data.timeline_slices[0].measure == 0


def test_pickup_beat_position_uses_the_governing_time_signature(midi_bach_bourree):
    """The pickup's own declared time signature (1/4) is an exporter
    artifact just sizing that one bar - Ref 17's "pickup notes sit at the
    end of a notional full bar" must measure against the real, governing
    4/4, landing the pickup's only beat at beat 4, not beat 1."""
    data = MusicData(file_path=midi_bach_bourree)
    first = data.timeline_slices[0]
    assert first.measure == 0
    assert first.beat_position == 4.0
    assert first.time_sig == (4, 4)


def test_no_pickup_starts_at_measure_1(midi_test2):
    data = MusicData(file_path=midi_test2)
    assert data.timeline_slices[0].measure == 1
    assert data.timeline_slices[0].beat_position == 1.0


def test_mid_piece_time_signature_change(midi_test2):
    """test2.mid changes 4/4 -> 3/4 at tick 30720 (division 960 -> bar 8
    boundary: 8 bars of 4/4 = 8*4*960 = 30720 ticks)."""
    data = MusicData(file_path=midi_test2)
    before = [s for s in data.timeline_slices if s.measure == 8]
    after = [s for s in data.timeline_slices if s.measure == 9]
    assert before and before[0].time_sig == (4, 4)
    assert after and after[0].time_sig == (3, 4)


def test_mid_piece_tempo_change_recorded(midi_test2):
    data = MusicData(file_path=midi_test2)
    assert len(data.tempo_changes) == 2
    assert data.tempo_changes[0].tempo_bpm == 120
    assert data.tempo_changes[1].tempo_bpm == 80


def test_near_miss_duration_falls_through_to_numeric_not_a_wrong_word():
    """Reported bug: a note at 0.98 of a crotchet (2% off) used to be called
    "quarter"/"crotchet" outright (the old 0.03 tolerance covered it) -
    duration_name_us must be None here so _note_attribute_pairs
    (models/music_data.py) falls back to showing the raw ts_duration number
    instead of a wrong word."""
    parts_info = [PartStructureInfo(part_id="P0", name="Test")]
    builder = MidiTimelineBuilder("x.mid", parts_info, source=_one_note_source(0.98))
    slices = builder.build()
    assert slices[0].notes[0].duration_name_us is None


def test_exactly_quantized_duration_still_resolves_to_a_word():
    """The tightened tolerance must not reject a genuinely exact duration -
    a programmatically-quantized file (test1.MID/test2.mid) still needs its
    durations named."""
    parts_info = [PartStructureInfo(part_id="P0", name="Test")]
    builder = MidiTimelineBuilder("x.mid", parts_info, source=_one_note_source(1.0))
    slices = builder.build()
    assert slices[0].notes[0].duration_name_us == "quarter"


def test_track_mostly_weird_durations_reverts_the_whole_track_to_numeric():
    """Reported, live-tested against a real freehand (non-quantized) MIDI
    recording (files/midi/test3.mid): most durations landed near SOME
    type/dots combination purely by numeric coincidence, producing odd
    names like "double-dotted 32nd" - and a mix of named/numbered durations
    within one part read as inconsistent even where each value was
    individually defensible. 19 double-dotted-quarter (weird) + 1 plain
    quarter (simple) = 95% weird, over the 5% threshold - every note in the
    track, including the individually-simple one, must revert to numeric."""
    parts_info = [PartStructureInfo(part_id="P0", name="Test")]
    quarter_lengths = [2.25] * 19 + [1.0]  # 2.25 = double-dotted quarter
    builder = MidiTimelineBuilder("x.mid", parts_info, source=_track_source(quarter_lengths))
    slices = builder.build()
    all_notes = [n for s in slices for n in s.notes]
    assert len(all_notes) == 20
    assert all(n.duration_name_us is None for n in all_notes)


def test_track_with_few_weird_durations_keeps_the_named_ones():
    """1 weird note among 25 (4%) stays under the 5% threshold - no
    reversion, so the 24 simple ones keep their names and even the one
    weird one keeps whatever name it matched (reverting only happens at the
    track level, not per-note)."""
    parts_info = [PartStructureInfo(part_id="P0", name="Test")]
    quarter_lengths = [1.0] * 24 + [2.25]
    builder = MidiTimelineBuilder("x.mid", parts_info, source=_track_source(quarter_lengths))
    slices = builder.build()
    all_notes = [n for s in slices for n in s.notes]
    assert len(all_notes) == 25
    named = [n for n in all_notes if n.duration_name_us is not None]
    assert len(named) == 25


def test_real_freehand_recording_reverts_to_numeric_durations(midi_test3):
    """Ground-truth version of the two synthetic tests above, against the
    actual reported file: a real freehand (non-quantized) MIDI recording
    where several durations happen to land near a rare type/dots
    combination (e.g. "double-dotted thirty-second") purely by numeric
    coincidence. Confirmed by inspection: 3 of 16 notes matched something
    (2 weird, 1 "sixteenth"), 18.75% weird - over the 5% threshold, so all
    16 must come out numeric, including the one that individually matched a
    simple name."""
    data = MusicData(file_path=midi_test3)
    notes = [n for s in data.timeline_slices for n in s.notes]
    assert len(notes) == 16
    assert all(n.duration_name_us is None for n in notes)


def test_percussion_notes_appear_and_are_named_from_the_gm_percussion_map(midi_blue_peter):
    """Wishlist #8: BluePeter.mid's drum track (reported: came out as
    silence) now has real notes in the timeline, named via
    models.gm_percussion_map instead of a pitch-class spelling, and never
    re-spelled by a key-signature override (file_key_fifths stays None)."""
    data = MusicData(file_path=midi_blue_peter)
    for s in data.timeline_slices:
        assert all(n.part_id != "" for n in s.notes)
    # 9 parts: 8 pitched + 1 percussion, matching MidiReader's parts_info
    # count (test_midi_reader.py's test_percussion_track_included_...).
    part_ids = {n.part_id for s in data.timeline_slices for n in s.notes}
    assert len(part_ids) == 9

    percussion_notes = [
        n
        for s in data.timeline_slices
        for n in s.notes
        if n.midi_pitch is not None and 27 <= n.midi_pitch <= 87 and n.octave is None
    ]
    assert percussion_notes
    assert any(n.step_name == "Low Floor Tom" for n in percussion_notes)
    assert all(n.file_key_fifths is None for n in percussion_notes)


def test_repeat_ending_hairpin_spans_are_always_empty_for_midi(midi_pachelbel):
    """Raw MIDI has no repeat-barline/ending/hairpin notation at all."""
    data = MusicData(file_path=midi_pachelbel)
    assert data.repeat_spans == []
    assert data.ending_spans == []
    assert data.hairpin_spans == []


def test_matches_musicxml_ground_truth_for_the_unrepeated_prefix(midi_bach_bourree, score_bourree_full):
    """The gold cross-check: bach-bourree-tab.mid is MuseScore's own MIDI
    export of files/bach-bourree-tab/score.xml. Measures 0-8 come before
    that score's first repeat barline (repeat_spans start_measure=1), so the
    MIDI and MusicXML timelines must agree on every (measure, beat) -> set
    of MIDI pitches exactly there. They diverge from measure 9 onward by
    design, not by bug: MIDI export realises (plays out) repeats in full,
    while MusicXML keeps them as repeat barlines - not something this test
    tries to reconcile.
    """
    xml_data = MusicData(file_path=score_bourree_full)
    midi_data = MusicData(file_path=midi_bach_bourree)

    def pitches_by_position(data, staff_filter=None):
        out = {}
        for s in data.timeline_slices:
            if s.measure > 8:
                continue
            for n in s.notes:
                if staff_filter is not None and n.staff != staff_filter:
                    continue
                if n.midi_pitch is None:
                    continue
                key = (n.measure, round(n.beat_position, 2))
                out.setdefault(key, set()).add(n.midi_pitch)
        return out

    # XML fixture has a notation staff (1) + a duplicating TAB staff (2) -
    # compare against staff 1 only, since MIDI has no staff duplication.
    xml_positions = pitches_by_position(xml_data, staff_filter=1)
    midi_positions = pitches_by_position(midi_data)

    assert xml_positions == midi_positions
