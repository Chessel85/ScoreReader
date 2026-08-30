# tests/parsers/test_ug_reader.py
from models.strum_codes import strumming_pattern_text
from models.strum_pattern import StrumPattern
from parsers.ug_reader import UgFileReader, _build_music_data
from parsers.ug_source import UgSource, write_ug_source


def _pattern(name="", codes=None, bpm=115, denominator=16):
    return StrumPattern(
        name=name, bpm=bpm, denominator=denominator, is_triplet=False, codes=codes or []
    )


def _source(**overrides) -> UgSource:
    defaults = dict(
        song_name="Test Song",
        artist_name="Test Artist",
        tonality="C",
        tuning="E A D G B E",
        difficulty="novice",
        content="[ch]C[/ch]\n",
        tab_id=1,
        source_url="https://tabs.ultimate-guitar.com/tab/test/test-chords-1",
        strum_patterns=[],
        capo=None,
    )
    defaults.update(overrides)
    return UgSource(**defaults)


def test_strumming_pattern_text_decodes_the_full_code_vocabulary():
    assert strumming_pattern_text([1, 202, 101]) == "down, pause, up"
    assert strumming_pattern_text([2, 103, 201, 203]) == "down muted, up accented, palm mute, real pause"


def test_strumming_pattern_text_names_an_unknown_code():
    assert strumming_pattern_text([1, 999]) == "down, code 999"


def test_strumming_pattern_text_is_none_when_no_codes():
    assert strumming_pattern_text([]) is None


def test_credits_show_the_decoded_word_list_for_a_single_unnamed_pattern():
    music_data = _build_music_data(_source(strum_patterns=[_pattern(codes=[1, 202, 101])]), "ultimate-guitar-1.ug")
    assert music_data.credits["Strumming Pattern"] == "down, pause, up"


def test_credits_list_the_names_when_there_are_several_patterns():
    source = _source(strum_patterns=[_pattern("Verse", [1]), _pattern("Chorus", [101]), _pattern("", [202])])
    music_data = _build_music_data(source, "ultimate-guitar-1.ug")
    assert music_data.credits["Strumming Pattern"] == "Verse, Chorus, Unnamed"


def test_credits_include_the_ultimate_guitar_id():
    music_data = _build_music_data(_source(tab_id=46064), "ultimate-guitar-46064.ug")
    assert music_data.credits["Ultimate Guitar ID"] == "46064"
    # last row, so it renders at the bottom of Region 1
    assert list(music_data.credits)[-1] == "Ultimate Guitar ID"


def test_credits_omit_the_ultimate_guitar_id_when_zero():
    music_data = _build_music_data(_source(tab_id=0), "ultimate-guitar-0.ug")
    assert "Ultimate Guitar ID" not in music_data.credits


def test_credits_omit_strumming_pattern_when_absent():
    music_data = _build_music_data(_source(strum_patterns=[]), "ultimate-guitar-1.ug")
    assert "Strumming Pattern" not in music_data.credits


def test_credits_include_capo_when_present():
    music_data = _build_music_data(_source(capo=2), "ultimate-guitar-1.ug")
    assert music_data.credits["Capo"] == "2nd fret"


def test_credits_omit_capo_when_absent():
    music_data = _build_music_data(_source(capo=None), "ultimate-guitar-1.ug")
    assert "Capo" not in music_data.credits


def test_ug_file_reader_loads_a_saved_file_with_the_real_path(tmp_path):
    source = _source(strum_patterns=[_pattern(codes=[1, 202])])
    path = str(tmp_path / "Test Song.ug")
    write_ug_source(source, path)

    music_data = UgFileReader(path).load()

    assert music_data.file_path == path
    assert music_data.is_ug
    assert music_data.credits["Title"] == "Test Song"
    assert music_data.credits["Strumming Pattern"] == "down, pause"
