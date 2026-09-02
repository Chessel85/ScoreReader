# tests/parsers/test_ug_source.py
import html
import json

import parsers.ug_source as ug_source
from models.strum_pattern import StrumPattern
from parsers.ug_source import (
    FORMAT_TAG,
    FORMAT_VERSION,
    UgSource,
    read_ug_source,
    read_ug_source_file,
    write_ug_source,
)


class _FakeResponse:
    def __init__(self, body: str):
        self._body = body.encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _page_html(tab_type: str) -> str:
    store = {
        "store": {
            "page": {
                "data": {
                    "tab": {
                        "type": tab_type,
                        "song_name": "The Song",
                        "artist_name": "The Artist",
                        "id": 12345,
                        "difficulty": "novice",
                    },
                    "tab_view": {
                        "wiki_tab": {"content": "[ch]C[/ch]\nla la[/tab]\n"},
                        "meta": {"tonality": "C", "tuning": {"value": "E A D G B E"}},
                        "strummings": [],
                    },
                }
            }
        }
    }
    payload = html.escape(json.dumps(store), quote=True)
    return f'<div class="js-store" data-content="{payload}"></div>'


def _patch_fetch(monkeypatch, tab_type: str):
    monkeypatch.setattr(
        ug_source.urllib.request,
        "urlopen",
        lambda *a, **k: _FakeResponse(_page_html(tab_type)),
    )


def test_read_ug_source_accepts_a_tab_type_page(monkeypatch):
    _patch_fetch(monkeypatch, "Tab")
    source = read_ug_source("https://tabs.ultimate-guitar.com/tab/x/y-tabs-12345")
    assert source.tab_type == "Tab"
    assert source.song_name == "The Song"


def test_read_ug_source_normalises_the_plural_tabs_type(monkeypatch):
    # UG's real pages report "Tabs" (plural) for an ASCII-tablature page.
    _patch_fetch(monkeypatch, "Tabs")
    source = read_ug_source("https://tabs.ultimate-guitar.com/tab/x/y-tabs-12345")
    assert source.tab_type == "Tab"


def test_read_ug_source_still_rejects_a_pro_tab(monkeypatch):
    _patch_fetch(monkeypatch, "Pro")
    try:
        read_ug_source("https://tabs.ultimate-guitar.com/tab/x/y-tabs-12345")
        assert False, "expected a ValueError"
    except ValueError as e:
        assert "Pro" in str(e)


def _source(**overrides) -> UgSource:
    defaults = dict(
        song_name="Test Song",
        artist_name="Test Artist",
        tonality="C",
        tuning="E A D G B E",
        difficulty="novice",
        content="[ch]C[/ch]\n",
        tab_id=46064,
        source_url="https://tabs.ultimate-guitar.com/tab/test/test-chords-46064",
        strum_patterns=[
            StrumPattern(name="Verse", bpm=115, denominator=16, is_triplet=False, codes=[1, 202, 101]),
            StrumPattern(name="Chorus", bpm=115, denominator=4, is_triplet=False, codes=[1, 203]),
        ],
        capo=2,
    )
    defaults.update(overrides)
    return UgSource(**defaults)


def test_write_then_read_round_trips_every_field(tmp_path):
    source = _source()
    path = str(tmp_path / "song.ug")
    write_ug_source(source, path)

    assert read_ug_source_file(path) == source


def test_write_sets_the_expected_format_tag_and_version(tmp_path):
    path = tmp_path / "song.ug"
    write_ug_source(_source(), str(path))

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["format"] == FORMAT_TAG
    assert payload["version"] == FORMAT_VERSION == 3


def test_tab_type_round_trips_and_defaults_to_chords_for_older_files(tmp_path):
    path = str(tmp_path / "song.ug")
    write_ug_source(_source(tab_type="Tab"), path)
    assert read_ug_source_file(path).tab_type == "Tab"

    # A v2 payload has no tab_type key - it reads back as "Chords".
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    payload["version"] = 2
    del payload["tab_type"]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    assert read_ug_source_file(path).tab_type == "Chords"


def test_read_rejects_a_file_with_the_wrong_format_tag(tmp_path):
    path = tmp_path / "not_ours.ug"
    path.write_text('{"format": "some_other_app", "version": 2}', encoding="utf-8")

    try:
        read_ug_source_file(str(path))
        assert False, "expected a ValueError"
    except ValueError as e:
        assert "not a Recall Score" in str(e)


def test_read_rejects_an_unsupported_version(tmp_path):
    path = str(tmp_path / "song.ug")
    write_ug_source(_source(), path)
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    payload["version"] = 999
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)

    try:
        read_ug_source_file(path)
        assert False, "expected a ValueError"
    except ValueError as e:
        assert "version" in str(e)


def test_a_v1_file_migrates_to_a_single_unnamed_pattern(tmp_path):
    path = tmp_path / "old.ug"
    path.write_text(
        json.dumps(
            {
                "format": FORMAT_TAG,
                "version": 1,
                "song_name": "Old Song",
                "artist_name": "Old Artist",
                "tonality": "C",
                "tuning": "E A D G B E",
                "difficulty": "novice",
                "content": "[ch]C[/ch]\n",
                "bpm": 115,
                "is_triplet": True,
                "tab_id": 1,
                "source_url": "https://tabs.ultimate-guitar.com/tab/x/y-chords-1",
                "strum_codes": [1, 202, 101],
            }
        ),
        encoding="utf-8",
    )

    loaded = read_ug_source_file(str(path))

    assert len(loaded.strum_patterns) == 1
    pattern = loaded.strum_patterns[0]
    assert pattern.name == ""
    assert pattern.bpm == 115
    assert pattern.denominator is None  # v1 never stored it - honestly unknown
    assert pattern.is_triplet is True
    assert pattern.codes == [1, 202, 101]
    assert loaded.capo is None
