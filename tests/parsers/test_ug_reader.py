# tests/parsers/test_ug_reader.py
from parsers.ug_reader import UgFileReader, _build_music_data
from parsers.ug_source import UgSource, strumming_pattern_text, write_ug_source


def _source(**overrides) -> UgSource:
    defaults = dict(
        song_name="Test Song",
        artist_name="Test Artist",
        tonality="C",
        tuning="E A D G B E",
        difficulty="novice",
        content="[ch]C[/ch]\n",
        bpm=115,
        is_triplet=True,
        tab_id=1,
        source_url="https://tabs.ultimate-guitar.com/tab/test/test-chords-1",
        strum_codes=[],
    )
    defaults.update(overrides)
    return UgSource(**defaults)


def test_strumming_pattern_text_decodes_known_codes():
    assert strumming_pattern_text([1, 202, 101]) == "downstroke, muted strum, upstroke"


def test_strumming_pattern_text_falls_back_to_raw_number_for_an_unknown_code():
    assert strumming_pattern_text([1, 999]) == "downstroke, 999"


def test_strumming_pattern_text_is_none_when_no_codes():
    assert strumming_pattern_text([]) is None


def test_credits_include_strumming_pattern_when_present():
    source = _source(strum_codes=[1, 202, 101])
    music_data = _build_music_data(source, "ultimate-guitar-1.ug")
    assert music_data.credits["Strumming Pattern"] == "downstroke, muted strum, upstroke"


def test_credits_omit_strumming_pattern_when_absent():
    source = _source(strum_codes=[])
    music_data = _build_music_data(source, "ultimate-guitar-1.ug")
    assert "Strumming Pattern" not in music_data.credits


def test_ug_file_reader_loads_a_saved_file_with_the_real_path(tmp_path):
    source = _source(strum_codes=[1, 202])
    path = str(tmp_path / "Test Song.ug")
    write_ug_source(source, path)

    music_data = UgFileReader(path).load()

    assert music_data.file_path == path
    assert music_data.is_ug
    assert music_data.credits["Title"] == "Test Song"
    assert music_data.credits["Strumming Pattern"] == "downstroke, muted strum"
