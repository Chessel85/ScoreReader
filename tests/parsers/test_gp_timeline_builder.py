# tests/parsers/test_gp_timeline_builder.py
"""Exercises GpTimelineBuilder through GpReader.load() against the real
sample file - the synthetic Chords voice only gets built for a track
GpReader already flagged as chord/strum-qualifying (GP_CHORD_VOICE_ID
present in that track's staves_voices), so testing the builder in isolation
from a bare parts_info=[] would just prove it does nothing, not that it
works correctly.
"""
from parsers.gp_reader import GpReader
from parsers.gp_timeline_builder import GP_CHORD_VOICE_ID


def _chord_notes(data, part_id=None):
    notes = [n for s in data.timeline_slices for n in s.notes if n.voice == GP_CHORD_VOICE_ID]
    if part_id is not None:
        notes = [n for n in notes if n.part_id == part_id]
    return notes


def test_total_measures_and_slice_count(gp_ripple):
    data = GpReader(gp_ripple).load()
    assert data.total_measures == 102
    assert len(data.timeline_slices) > 0


def test_real_tab_note_matches_hand_verified_first_note(gp_ripple):
    """Ripple's very first sounding note, hand-verified during discovery:
    B3, fret 2 on string 1, an eighth note at beat 2 of bar 1 on the lead
    guitar (P0), forte-fortissimo dynamic."""
    data = GpReader(gp_ripple).load()
    note = data.timeline_slices[0].notes[0]
    assert note.part_id == "P0"
    assert note.step_name == "B"
    assert note.octave == 3
    assert note.midi_pitch == 47
    assert (note.string, note.fret) == (1, 2)
    assert note.measure == 1
    assert note.beat_position == 2.0
    assert note.duration_name_us == "eighth"
    assert note.dynamic == "fortississimo"


def test_no_synthetic_voice_for_bass_or_mandolin(gp_ripple):
    data = GpReader(gp_ripple).load()
    assert _chord_notes(data, "P2") == []
    assert _chord_notes(data, "P3") == []


def test_chords_voice_step_name_is_the_sticky_chord_name(gp_ripple):
    """Track 1 holds a "C" chord (diagram id 0) across bar 2 - the sticky
    name must read "C" at every re-strike position in that bar, not just the
    one beat that actually carries the <Chord> reference (hand-verified
    during discovery: 6 identical-content re-onsets at beats
    1, 2, 2.5, 3, 4, 4.5)."""
    data = GpReader(gp_ripple).load()
    bar2 = [n for n in _chord_notes(data, "P1") if n.measure == 2]
    assert len(bar2) == 6
    assert all(n.step_name == "C" for n in bar2)
    assert [n.beat_position for n in bar2] == [1.0, 2.0, 2.5, 3.0, 4.0, 4.5]


def test_chords_voice_visits_every_named_chord_in_order(gp_ripple):
    data = GpReader(gp_ripple).load()
    names = [n.step_name for n in _chord_notes(data, "P1")]
    # Every named chord that appears must actually show up somewhere in the
    # sticky sequence - the exact library from test_gp_source.py.
    assert set(names) == {"C", "F", "G", "Dm", "G7"}


def test_track_0_unnamed_chord_shaped_beats_fall_back_to_strum(gp_ripple):
    """Track 0 has chord-shaped (2+ note) beats but almost no chord-name
    labels - the sticky name has nothing to carry forward from until the
    first (and only) one is hit, so those beats must read "Strum", not a
    blank or a crash."""
    data = GpReader(gp_ripple).load()
    names = {n.step_name for n in _chord_notes(data, "P0")}
    assert "Strum" in names


def test_explicit_strum_direction_is_never_fabricated(gp_ripple):
    """Exactly 2 real Brush-marked beats in the whole file (hand-verified
    during discovery, both "Down", both on track 0) - every other
    chord-voice event, however dense the real strike rhythm is, must carry
    strum=None rather than an invented direction (the user's explicit
    "leave unstated" decision)."""
    data = GpReader(gp_ripple).load()
    chord_notes = _chord_notes(data)
    marked = [n for n in chord_notes if n.strum is not None]
    assert len(marked) == 2
    assert all(n.strum == "down stroke" for n in marked)
    assert all(n.part_id == "P0" for n in marked)
    assert len(chord_notes) > len(marked) + 100  # the real strike rate is far denser


def test_chord_pitches_carries_the_full_voicing_for_playback(gp_ripple):
    """The synthetic note's own midi_pitch is a single representative pitch
    (for sort order); chord_pitches is what full-chord audition actually
    uses - must contain every real string's pitch at that beat, not just
    one."""
    data = GpReader(gp_ripple).load()
    bar2 = [n for n in _chord_notes(data, "P1") if n.measure == 2]
    for n in bar2:
        assert sorted(n.chord_pitches) == [48, 52, 55, 60, 64]
        assert n.midi_pitch == max(n.chord_pitches)


def test_chords_voice_note_sorts_after_the_real_notes_regardless_of_pitch(gp_ripple):
    """Region 3/4 sort real notes within an instrument highest pitch first
    (see CLAUDE.md). The synthetic Chords-voice note carries a
    representative pitch (max(chord_pitches)) that would otherwise
    interleave it among the real fretted notes by pitch - it's a different
    kind of entry, not another note in the voicing, so it must always sort
    last within its instrument regardless of that pitch."""
    data = GpReader(gp_ripple).load()
    bar2 = [s for s in data.timeline_slices if s.measure == 2]
    checked = 0
    for s in bar2:
        p1_notes = [n for n in s.notes if n.part_id == "P1"]
        if len(p1_notes) < 2:
            continue
        assert p1_notes[-1].voice == GP_CHORD_VOICE_ID
        real_notes = p1_notes[:-1]
        assert all(n.voice != GP_CHORD_VOICE_ID for n in real_notes)
        assert [n.midi_pitch for n in real_notes] == sorted(
            (n.midi_pitch for n in real_notes), reverse=True
        )
        checked += 1
    assert checked > 0


def test_playback_events_sound_the_whole_chord_not_one_note(gp_ripple):
    """models.music_data.get_playback_events_for_indices must expand a
    chord-voice note's chord_pitches into the part's pitch group, not just
    append its single representative midi_pitch."""
    data = GpReader(gp_ripple).load()
    data.active_voice_filter = {("P1", 1, GP_CHORD_VOICE_ID)}
    index = next(
        i for i, s in enumerate(data.timeline_slices)
        if any(n.voice == GP_CHORD_VOICE_ID and n.part_id == "P1" for n in s.notes)
    )
    events = data.get_playback_events_for_indices([0], index=index)
    assert len(events) == 1
    _channel, _program, pitches, _duration_ms = events[0]
    assert len(pitches) >= 4
