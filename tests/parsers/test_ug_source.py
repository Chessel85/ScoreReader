# tests/parsers/test_ug_source.py
from parsers.ug_source import FORMAT_TAG, UgSource, read_ug_source_file, write_ug_source


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
        tab_id=46064,
        source_url="https://tabs.ultimate-guitar.com/tab/test/test-chords-46064",
        strum_codes=[1, 202, 101],
    )
    defaults.update(overrides)
    return UgSource(**defaults)


def test_write_then_read_round_trips_every_field(tmp_path):
    source = _source()
    path = str(tmp_path / "song.ug")
    write_ug_source(source, path)

    loaded = read_ug_source_file(path)

    assert loaded == source


def test_read_rejects_a_file_with_the_wrong_format_tag(tmp_path):
    path = tmp_path / "not_ours.ug"
    path.write_text('{"format": "some_other_app", "version": 1}', encoding="utf-8")

    try:
        read_ug_source_file(str(path))
        assert False, "expected a ValueError"
    except ValueError as e:
        assert "not a Recall Score" in str(e)


def test_read_rejects_a_mismatched_version(tmp_path):
    source = _source()
    path = str(tmp_path / "song.ug")
    write_ug_source(source, path)

    # Corrupt the version to simulate a future/older format.
    import json
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    payload["version"] = 999
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)

    try:
        read_ug_source_file(path)
        assert False, "expected a ValueError"
    except ValueError as e:
        assert "format version" in str(e)


def test_write_sets_the_expected_format_tag(tmp_path):
    path = tmp_path / "song.ug"
    write_ug_source(_source(), str(path))

    import json
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["format"] == FORMAT_TAG
