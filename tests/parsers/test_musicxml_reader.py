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
