# tests/parsers/test_gp_source.py
from parsers.gp_source import iter_track_positions, read_gp_source


def test_reads_title_artist_tempo(gp_ripple):
    source = read_gp_source(gp_ripple)
    assert source.title == "Ripple"
    assert source.artist == "Grateful Dead"
    assert source.tempo_bpm == 126


def test_reads_tracks_tuning_capo_and_chord_names(gp_ripple):
    source = read_gp_source(gp_ripple)
    assert [t.name for t in source.tracks] == [
        "Acoustic Lead", "Acoustic Capo VII", "Electric Bass (finger)", "Mandolin",
    ]
    # GM programs are 0-indexed as GP stores them (GpReader does the +1
    # conversion to the model's 1-indexed convention).
    assert [t.gmidi_program for t in source.tracks] == [25, 25, 33, 107]
    assert source.tracks[0].tuning_pitches == [40, 45, 50, 55, 59, 64]
    assert source.tracks[1].capo_fret == 7
    assert source.tracks[0].capo_fret == 0
    assert source.tracks[1].chord_names == {0: "C", 1: "F", 2: "G", 3: "Dm", 4: "G7"}
    # Bass and mandolin have no chord library at all.
    assert source.tracks[2].chord_names == {}
    assert source.tracks[3].chord_names == {}


def test_102_measures_all_4_4(gp_ripple):
    source = read_gp_source(gp_ripple)
    assert len(source.master_bars) == 102
    assert all(mb.time_sig == (4, 4) for mb in source.master_bars)


def test_master_bar_track_bar_ids_align_to_tracks_order(gp_ripple):
    """The direct, authoritative track->bar mapping every measure carries -
    not an inferred contiguous id range per track (nothing in the schema
    guarantees that shape)."""
    source = read_gp_source(gp_ripple)
    assert source.master_bars[0].track_bar_ids == [0, 102, 204, 306]
    assert source.master_bars[1].track_bar_ids == [1, 103, 205, 307]


def test_note_carries_string_fret_and_resolved_midi_pitch(gp_ripple):
    source = read_gp_source(gp_ripple)
    # The first note in the Notes container (id 0), hand-verified during
    # discovery: B3, fret 2 on string 1.
    note = source.notes[0]
    assert (note.string, note.fret, note.midi_pitch) == (1, 2, 47)
    assert note.step == "B"
    assert note.accidental == ""
    assert note.octave == 3


def test_iter_track_positions_walks_bar_2_of_track_1_in_order(gp_ripple):
    """Hand-verified during discovery: track 1 ("Acoustic Capo VII") holds
    the same 5-string "C" voicing across bar 2, re-struck at beats
    1, 2, 2.5, 3, 4, 4.5 - a real, syncopated, non-uniform strike rhythm,
    not an artefact of how the graph is walked. Also exercises GP's beat-id
    reuse (the same <Beat id> shared by more than one position when its
    content is identical, confirmed for this exact bar) - iter_track_positions
    must yield one entry per POSITION, not collapse by id."""
    source = read_gp_source(gp_ripple)
    positions = [
        (m, v, b) for m, v, b in iter_track_positions(source, track_index=1) if m == 1
    ]
    beat_ids = [b for _, _, b in positions]
    assert beat_ids == [152, 153, 154, 155, 153, 154]

    offset = 0.0
    onsets = []
    for _, _, beat_id in positions:
        onsets.append(1.0 + offset)
        offset += source.beats[beat_id].quarter_length
    assert onsets == [1.0, 2.0, 2.5, 3.0, 4.0, 4.5]


def test_mandolin_and_bass_have_no_chord_or_brush_beats(gp_ripple):
    """Cross-check from the GP import discovery pass: the user confirmed by
    ear that the mandolin plays tremolo, not strums - this is the data-level
    fact that lets GpReader exclude it from the synthetic Chords voice with
    no instrument-type special-casing."""
    source = read_gp_source(gp_ripple)
    for track_index in (2, 3):
        for _, _, beat_id in iter_track_positions(source, track_index):
            beat = source.beats[beat_id]
            assert beat.chord_index is None
            assert beat.brush_direction is None
