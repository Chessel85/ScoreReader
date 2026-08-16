# tests/parsers/test_gp_reader.py
from parsers.gp_reader import GP_CHORD_VOICE_ID, GpReader
from parsers.gp_timeline_builder import GP_CHORD_VOICE_ID as TIMELINE_CHORD_VOICE_ID


def test_load_returns_music_data_with_parts_info(gp_ripple):
    data = GpReader(gp_ripple).load()
    assert [p.name for p in data.parts_info] == [
        "Acoustic Lead", "Acoustic Capo VII", "Electric Bass (finger)", "Mandolin",
    ]
    assert [p.part_id for p in data.parts_info] == ["P0", "P1", "P2", "P3"]


def test_gmidi_program_is_1_indexed_in_the_model(gp_ripple):
    """GP's own Program value is 25 (0-indexed, "Acoustic Guitar (steel)") -
    the model convention used throughout this app is 1-indexed, same as
    MusicXML's <midi-program> and MidiReader's Program Change."""
    data = GpReader(gp_ripple).load()
    assert data.parts_info[0].gmidi_program == 26


def test_credits(gp_ripple):
    data = GpReader(gp_ripple).load()
    assert data.credits["Title"] == "Ripple"
    assert data.credits["Artist"] == "Grateful Dead"
    assert data.credits["Time Signature"] == "4/4"
    assert data.tempo_bpm == 126


def test_chord_qualifying_tracks_get_a_synthetic_chords_voice(gp_ripple):
    """Tracks 0 and 1 have real chord-name/brush data somewhere in the
    piece; tracks 2 (bass) and 3 (mandolin) have none - see
    test_gp_source.py's mandolin/bass cross-check."""
    data = GpReader(gp_ripple).load()
    by_id = {p.part_id: p for p in data.parts_info}
    assert GP_CHORD_VOICE_ID == TIMELINE_CHORD_VOICE_ID  # same sentinel, one source of truth
    assert GP_CHORD_VOICE_ID in by_id["P0"].staves_voices[1]
    assert GP_CHORD_VOICE_ID in by_id["P1"].staves_voices[1]
    assert GP_CHORD_VOICE_ID not in by_id["P2"].staves_voices[1]
    assert GP_CHORD_VOICE_ID not in by_id["P3"].staves_voices[1]


def test_synthetic_voice_gets_a_chords_display_name_override(gp_ripple):
    data = GpReader(gp_ripple).load()
    p1 = next(p for p in data.parts_info if p.part_id == "P1")
    assert p1.voice_names[(1, GP_CHORD_VOICE_ID)] == "Chords"


def test_synthetic_voice_defaults_to_step_beat_position_and_strum_visible(gp_ripple):
    """See CLAUDE.md / the GP import plan's "Default visibility" note - the
    real strike rhythm and any real strum direction must be audible
    immediately, without the user reaching for the F1 attribute menu."""
    data = GpReader(gp_ripple).load()
    wanted = data.voice_display_attributes[("P1", 1, GP_CHORD_VOICE_ID)]
    assert wanted == {"step", "beat position", "strum"}
    # An ordinary voice is untouched - still today's default.
    assert ("P1", 1, 1) not in data.voice_display_attributes
