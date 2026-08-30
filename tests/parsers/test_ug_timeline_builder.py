# tests/parsers/test_ug_timeline_builder.py
"""Exercises UgTimelineBuilder against small, hand-authored UgSource
fixtures (no real network call - the same "build the model layer directly"
fast-test pattern the other timeline-builder tests use). Content strings
below mirror the real markup shape confirmed against a live Ultimate Guitar
page during the import feature's discovery/planning phase."""
from models.strum_pattern import StrumPattern
from parsers.ug_source import UgSource
from parsers.ug_timeline_builder import (
    CHORDS_PART_ID,
    LYRICS_PART_ID,
    UgTimelineBuilder,
    count_tablature_blocks,
)


def _source(content: str, **overrides) -> UgSource:
    defaults = dict(
        song_name="Test Song",
        artist_name="Test Artist",
        tonality="C",
        tuning="E A D G B E",
        difficulty="novice",
        content=content,
        tab_id=1,
        source_url="https://tabs.ultimate-guitar.com/tab/test/test-chords-1",
        strum_patterns=[
            StrumPattern(name="", bpm=115, denominator=16, is_triplet=True, codes=[])
        ],
        capo=None,
    )
    defaults.update(overrides)
    return UgSource(**defaults)


def test_build_raises_without_a_source():
    builder = UgTimelineBuilder("ultimate-guitar-1.ug", [], source=None)
    try:
        builder.build()
        assert False, "expected a ValueError"
    except ValueError:
        pass


def test_chord_lyric_column_slicing_on_a_two_chord_line():
    content = "[Verse 1]\n\n[tab][ch]C[/ch]     [ch]G[/ch]\nHello world[/tab]\n"
    source = _source(content)
    slices = UgTimelineBuilder("ultimate-guitar-1.ug", [], source=source).build()

    assert len(slices) == 2
    chords = [n for s in slices for n in s.notes if n.part_id == CHORDS_PART_ID]
    lyrics = [n for s in slices for n in s.notes if n.part_id == LYRICS_PART_ID]

    assert [n.step_name for n in chords] == ["C", "G"]
    # P2 (find_feature_plan.md): the findable `chord symbol` key mirrors
    # step_name on every UG chord entry.
    assert [n.chord_symbol for n in chords] == ["C", "G"]
    # "C" at column 0, "G" at column 6 in "Hello world" (0-indexed) ->
    # fragments "Hello " and "world".
    assert [n.step_name for n in lyrics] == ["Hello", "world"]


def test_bare_instrumental_line_shows_a_no_lyrics_placeholder():
    """Reported: a user who checks the wordless intro bars first has no way
    to tell "no lyrics here" apart from "the feature is broken" if the
    Lyrics part's row is just absent - an explicit placeholder fixes that."""
    content = "[Intro]\n\n[ch]C[/ch]  [ch]Fmaj7[/ch]\n"
    source = _source(content)
    slices = UgTimelineBuilder("ultimate-guitar-1.ug", [], source=source).build()

    assert len(slices) == 2
    for s in slices:
        lyric_notes = [n for n in s.notes if n.part_id == LYRICS_PART_ID]
        assert len(lyric_notes) == 1
        assert lyric_notes[0].step_name == "No lyrics"
        assert lyric_notes[0].midi_pitch is None
        assert any(n.part_id == CHORDS_PART_ID for n in s.notes)


def test_lead_in_text_before_the_first_chords_own_column_is_not_dropped():
    """Reported: a real UG line often indents its first chord past column 0
    ("   [ch]C[/ch]      [ch]C/B[/ch]...") - the first chord must own that
    lead-in text ("And "), not silently lose it."""
    content = "[tab]   [ch]C[/ch]      [ch]C/B[/ch]\nAnd I can feel[/tab]\n"
    source = _source(content)
    slices = UgTimelineBuilder("ultimate-guitar-1.ug", [], source=source).build()

    lyrics = [n for s in slices for n in s.notes if n.part_id == LYRICS_PART_ID]
    assert lyrics[0].step_name.startswith("And")


def test_a_chord_boundary_landing_mid_word_snaps_to_the_whole_word():
    """Reported/hand-verified against a real UG page: a chord change at
    column 20 of "And I can feel the warning signs..." lands between the
    "w" and "arning" of "warning" - majority of the word's letters (6 of 7)
    are on the Am side, so the whole word must go there, not split."""
    content = (
        "[tab]   [ch]C[/ch]      [ch]C/B[/ch]       [ch]Am[/ch]            [ch]D7[/ch]"
        "                 [ch]Fmaj7[/ch]\n"
        "And I can feel the warning signs running around my mind[/tab]\n"
    )
    source = _source(content)
    slices = UgTimelineBuilder("ultimate-guitar-1.ug", [], source=source).build()

    lyrics = [n.step_name for s in slices for n in s.notes if n.part_id == LYRICS_PART_ID]
    assert "warning" not in lyrics[1]  # C/B's fragment must not end mid-word
    assert lyrics[2].startswith("warning")  # Am's fragment gets the whole word


def test_unparseable_chord_symbol_falls_back_to_root_pitch():
    # "Xyz7#11b5(add9)" isn't a real chord symbol - only its leading "C"
    # root letter should resolve, not the whole thing.
    content = "[ch]Cxyzzy[/ch]\n"
    source = _source(content)
    slices = UgTimelineBuilder("ultimate-guitar-1.ug", [], source=source).build()

    assert len(slices) == 1
    note = slices[0].notes[0]
    assert note.step_name == "Cxyzzy"
    assert note.midi_pitch is not None
    assert note.chord_pitches  # non-empty - stays audible/navigable


def test_bar_counter_increments_once_per_chord_event():
    content = (
        "[Verse 1]\n\n"
        "[tab][ch]C[/ch]  [ch]G[/ch]\nAB[/tab]\n"
        "[tab][ch]Am[/ch]  [ch]F[/ch]\nCD[/tab]\n"
    )
    source = _source(content)
    builder = UgTimelineBuilder("ultimate-guitar-1.ug", [], source=source)
    slices = builder.build()

    assert [s.measure for s in slices] == [1, 2, 3, 4]
    assert builder.total_measures == 4


def test_section_spans_are_built_from_section_labels():
    content = (
        "[Intro]\n\n[ch]C[/ch]  [ch]G[/ch]\n"
        "[Verse 1]\n\n[tab][ch]Am[/ch]  [ch]F[/ch]\nHi there[/tab]\n"
        "[ch]C[/ch]\n"
    )
    builder = UgTimelineBuilder("ultimate-guitar-1.ug", [], source=_source(content))
    builder.build()

    spans = builder.section_spans
    assert [(s.label, s.start_measure, s.end_measure) for s in spans] == [
        ("Intro", 1, 2),
        ("Verse 1", 3, 5),
    ]


def test_ascii_tablature_blocks_are_skipped_and_counted():
    content = (
        "[Intro]\n\n"
        "[tab]e|--0--2--3--|\nB|--1--1--0--|[/tab]\n"
        "[tab][ch]C[/ch]  [ch]G[/ch]\nreal lyric[/tab]\n"
    )
    builder = UgTimelineBuilder("ultimate-guitar-1.ug", [], source=_source(content))
    slices = builder.build()

    # only the real chord/lyric block contributes slices
    assert [n.step_name for s in slices for n in s.notes if n.part_id == CHORDS_PART_ID] == ["C", "G"]
    assert count_tablature_blocks(content) == 1
