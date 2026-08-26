# tests/parsers/test_musicxml_reader.py
"""Header metadata extraction. These go through music21, so they are slow."""
import pytest

from parsers.musicXML_reader import MusicXMLReader


@pytest.mark.slow
def test_reader_extracts_key_time_and_tempo(minimal_score):
    data = MusicXMLReader(minimal_score).load()
    region_1 = data.get_region_1_data()

    assert region_1["Key Signature"] == "C major / A minor"
    assert region_1["Time Signature"] == "4/4"
    assert "notes per minute" in region_1["Tempo"]


@pytest.mark.slow
def test_reader_captures_part_structure(minimal_score):
    data = MusicXMLReader(minimal_score).load()

    assert len(data.parts_info) == 1
    part = data.parts_info[0]
    assert part.name == "Test Part"
    assert part.staves_clefs[1] == "Treble stave"
    assert part.staves_voices == {1: [1]}


@pytest.mark.slow
def test_reader_keeps_a_non_ascii_part_name_instead_of_discarding_it(score_bourree):
    """Reported bug: parts_info's own part-list parse used to replace any
    non-ASCII part name with the hardcoded "Classical Guitar" fallback -
    this fixture's real <part-name> is Korean ("클래식 기타 ", itself the
    literal translation of "Classical Guitar"). TimelineBuilder's separate
    part-list read for NoteData.part_name has no such filter, so the two
    diverged and every part_name-keyed lookup against parts_info (e.g. the
    Performance Report's per-instrument note counts) silently found nothing
    - the report showed "0 notes" for a real, fully-noted part."""
    data = MusicXMLReader(score_bourree).load()

    assert len(data.parts_info) == 1
    assert data.parts_info[0].name == "클래식 기타"

    matching_notes = [
        n for s in data._real_timeline_slices for n in s.notes if n.part_name == data.parts_info[0].name
    ]
    assert matching_notes, "parts_info.name must match the same notes' own part_name"


@pytest.mark.slow
def test_reader_handles_compressed_mxl_the_same_as_the_uncompressed_score(score_duet, score_duet_mxl):
    """Both MusicXMLReader's own ElementTree pass and TimelineBuilder's
    (invoked via MusicData(file_path=...), see the `timeline` fixture used
    elsewhere) previously did a raw ET.parse() that can't open a .mxl zip
    container - this is the regression test for that fix."""
    from models.music_data import MusicData

    uncompressed = MusicXMLReader(score_duet).load()
    compressed = MusicXMLReader(score_duet_mxl).load()

    assert [p.name for p in compressed.parts_info] == [p.name for p in uncompressed.parts_info]
    assert len(compressed.timeline_slices) == len(uncompressed.timeline_slices)

    # TimelineBuilder's own fallback ET.parse (no pre-parsed root), the path
    # a direct MusicData(file_path=...) construction takes.
    direct = MusicData(file_path=score_duet_mxl)
    assert len(direct.timeline_slices) == len(uncompressed.timeline_slices)


@pytest.mark.slow
def test_tempo_display_reflects_the_scores_own_beat_unit(score_duet):
    """A9: reported bug - Chessel Duet is eighth=96 and music21's
    getQuarterBPM() converts that to 48, so the old code displayed "48 BPM"
    instead of the tempo marking the score actually shows."""
    data = MusicXMLReader(score_duet).load()
    region_1 = data.get_region_1_data()

    assert region_1["Tempo"] == "96 eighth notes per minute"
    assert data.tempo_bpm == 48, "playback timing must still use quarter-note BPM"


@pytest.mark.slow
def test_status_bar_tempo_matches_region_1_not_the_internal_quarter_bpm(score_duet):
    """E1/E2 fix - reported bug, live-tested: the status bar's "Playback
    tempo" field showed the raw quarter-note-equivalent value (48) instead
    of the score's own beat unit (96), inconsistent with Region 1's tempo
    display right above it (A9)."""
    data = MusicXMLReader(score_duet).load()

    assert data.get_status_bar_fields()[3] == "Playback tempo: 96 eighth notes per minute (score default)"
    assert data.score_tempo_display_bpm() == 96
    assert data.tempo_beat_unit_name == "eighth"


@pytest.mark.slow
def test_reader_adds_chords_and_lyrics_parts_for_a_score_with_harmony_and_lyric_markup(score_three_blind_mice):
    """Real MuseScore export: chord symbols and lyrics alongside a real
    notated Piano part get the same "instrument called Chords"/"lyrics are
    also a part" UX Ultimate Guitar import already established, with a
    channel and GM program of their own so they mix in alongside the real
    instrument during playback (Ref 8)."""
    data = MusicXMLReader(score_three_blind_mice).load()

    names = [p.name for p in data.parts_info]
    assert names == ["Piano", "Chords", "Lyrics"]

    channels = {p.part_id: data.get_channel_for_part(p.part_id) for p in data.parts_info}
    assert len(set(channels.values())) == 3, "each part must get its own MIDI channel"


@pytest.mark.slow
def test_reader_defaults_the_chords_part_to_show_beat_position_and_strum(chords_and_lyrics_score):
    """Reported: strum/pick-direction data (see parsers/timeline_builder.py's
    chord-stroke entries) wasn't showing up anywhere the user actually
    looked, because an ordinary voice's Region 3 display defaults to just
    the note name. The Chords part is synthetic, not an ordinary voice, so -
    the same "audible immediately, no F1/context-menu first" default
    GpReader already established for GP's synthetic Chords voice - it shows
    its chord name, beat position (so repeated same-bar strokes aren't
    ambiguous) and any strum direction with no toggle needed. The Piano
    part's own voice is untouched, still today's plain step-name default."""
    from parsers.timeline_builder import CHORDS_PART_ID

    data = MusicXMLReader(chords_and_lyrics_score).load()

    assert data.voice_display_attributes[(CHORDS_PART_ID, 1, 1)] == {"step", "beat position", "strum"}
    assert ("P1", 1, 1) not in data.voice_display_attributes, "the real Piano voice's default is untouched"


@pytest.mark.slow
def test_reader_adds_a_stave_text_voice_to_the_real_part_that_carries_it(stave_text_score):
    """Generic stave text (parsers/timeline_builder.py's STAVE_TEXT_VOICE_ID)
    is a fabricated voice on the SAME real part its <direction><words> was
    found on - P1 here - never a new top-level part, and never P2 (which has
    no <direction> of its own, the guitar-duet cross-contamination case)."""
    from parsers.timeline_builder import STAVE_TEXT_VOICE_ID, STAVE_TEXT_VOICE_NAME

    data = MusicXMLReader(stave_text_score).load()

    names = [p.name for p in data.parts_info]
    assert names == ["Classical Guitar", "Second Guitar"], "no new top-level part is added"

    p1 = next(p for p in data.parts_info if p.part_id == "P1")
    assert p1.staves_voices[1][0] == STAVE_TEXT_VOICE_ID, (
        "user-requested: Stave Text is listed first, above the real voices, "
        "matching how a position mark sits above the stave on the printed score"
    )
    assert p1.voice_names[(1, STAVE_TEXT_VOICE_ID)] == STAVE_TEXT_VOICE_NAME

    p2 = next(p for p in data.parts_info if p.part_id == "P2")
    assert STAVE_TEXT_VOICE_ID not in p2.staves_voices.get(1, [])

    # Region 3's default is minimal - just the text itself, same as an
    # ordinary note's bare "step" default. Region 4 shows the fuller
    # measure/beat position/part/stave breakdown regardless of this toggle
    # (see test_stave_text_attribute_pairs_use_text_not_step_and_omit_duration_and_voice).
    assert data.voice_display_attributes[("P1", 1, STAVE_TEXT_VOICE_ID)] == {"text"}
    assert ("P1", 1, 1) not in data.voice_display_attributes, "the real notation voice's default is untouched"


@pytest.mark.slow
def test_stave_text_region_3_default_shows_only_the_text(stave_text_score):
    """Reported: the richer default (text+measure+beat position+part+stave)
    put every one of those fields into Region 3's single row, which read as
    "all the attributes crammed onto one entry" - Region 3 must show just
    the words themselves by default, same as any other note's bare step."""
    from parsers.timeline_builder import STAVE_TEXT_VOICE_ID

    data = MusicXMLReader(stave_text_score).load()

    note = next(
        n for s in data.timeline_slices for n in s.notes
        if n.part_id == "P1" and n.voice == STAVE_TEXT_VOICE_ID and n.step_name == "III"
    )
    assert data._format_note_for_region_3(note) == "III"


@pytest.mark.slow
def test_guitar_notes_play_the_guitar_program_not_the_piano_program(score_duet):
    """A8, Ref 8: reported bug - Chessel Duet's guitar (P2) used to play as
    piano because playback always read parts_info[0]'s program."""
    data = MusicXMLReader(score_duet).load()

    guitar_index = next(
        i for i, s in enumerate(data.timeline_slices)
        if any(n.part_id == "P2" for n in s.notes)
    )
    data.active_event_index = guitar_index
    current = data.get_current_slice()
    guitar_indices = [i for i, n in enumerate(current.notes) if n.part_id == "P2"]

    events = data.get_playback_events_for_indices(guitar_indices)

    assert len(events) == 1
    channel, program, _, _ = events[0]
    assert program == 24, "Classical Guitar is GM program 25, zero-indexed 24"
    assert channel == data.get_channel_for_part("P2")
    assert channel != data.get_channel_for_part("P1"), "parts must not share a channel"


@pytest.mark.slow
def test_percussion_clef_flags_the_part_as_percussion(score_hit_it):
    """Wishlist #8: Hit It.mxl's two parts both use <clef><sign>percussion,
    so both parts_info entries must come back is_percussion=True with a
    "Percussion stave" label - not the default "Treble stave"."""
    data = MusicXMLReader(score_hit_it).load()

    assert len(data.parts_info) == 2
    for part in data.parts_info:
        assert part.is_percussion is True
        assert part.staves_clefs[1] == "Percussion stave"
    assert {p.name for p in data.parts_info} == {"Drum Kit", "Tambourine"}


@pytest.mark.slow
def test_percussion_parts_play_on_separate_channels_at_the_gm_percussion_bank(score_hit_it):
    """Two real percussion parts (Drum Kit + Tambourine) in one score must
    not collide on one channel - each gets its OWN channel like any other
    part, program-selected to bank 128 (GM's percussion bank) instead of
    each part's own meaningless gmidi_program."""
    data = MusicXMLReader(score_hit_it).load()

    drum_kit_id = next(p.part_id for p in data.parts_info if p.name == "Drum Kit")
    tambourine_id = next(p.part_id for p in data.parts_info if p.name == "Tambourine")
    assert data.get_channel_for_part(drum_kit_id) != data.get_channel_for_part(tambourine_id)

    first_slice = data.timeline_slices[0]
    events = data.get_playback_events_for_indices(list(range(len(first_slice.notes))), index=0)
    assert events
    for channel, program, midi_notes, duration_ms, bank in events:
        assert bank == 128
        assert program == 0
