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
    assert "BPM" in region_1["Tempo"]


@pytest.mark.slow
def test_reader_captures_part_structure(minimal_score):
    data = MusicXMLReader(minimal_score).load()

    assert len(data.parts_info) == 1
    part = data.parts_info[0]
    assert part.name == "Test Part"
    assert part.staves_clefs[1] == "treble clef"
    assert part.staves_voices == {1: [1]}


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
    channel, program, _ = events[0]
    assert program == 24, "Classical Guitar is GM program 25, zero-indexed 24"
    assert channel == data.get_channel_for_part("P2")
    assert channel != data.get_channel_for_part("P1"), "parts must not share a channel"
