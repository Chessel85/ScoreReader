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
    TAB_PART_ID,
    UgTimelineBuilder,
    content_part_summary,
    count_tablature_blocks,
)


def _tab_notes(slices):
    return [n for s in slices for n in s.notes if n.part_id == TAB_PART_ID]


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


def test_ascii_tablature_block_is_imported_as_a_tablature_part():
    content = (
        "[Intro]\n\n"
        "[tab]e|--0--2--3--|\nB|--1--1--0--|[/tab]\n"
        "[tab][ch]C[/ch]  [ch]G[/ch]\nreal lyric[/tab]\n"
    )
    builder = UgTimelineBuilder("ultimate-guitar-1.ug", [], source=_source(content))
    slices = builder.build()

    # the chord/lyric block still contributes its own slices
    assert [n.step_name for s in slices for n in s.notes if n.part_id == CHORDS_PART_ID] == ["C", "G"]

    tab_notes = _tab_notes(slices)
    # three struck columns, two strings each -> six notes
    assert len(tab_notes) == 6
    # top row is string 1 (high E4): open, 2nd fret, 3rd fret
    top = [n for n in tab_notes if n.string == 1]
    assert [n.fret for n in top] == [0, 2, 3]
    assert [n.midi_pitch for n in top] == [64, 66, 67]
    assert all(n.duration_name_us == "eighth" for n in tab_notes)
    # one imported bar, no interior barline
    assert count_tablature_blocks(content) == 1


def test_tab_block_splits_into_bars_on_barline_columns():
    content = (
        "[tab]e|--0--2--|--3--|\n"
        "B|--1--1--|--0--|\n"
        "G|--0--0--|--0--|\n"
        "D|--2--2--|--0--|\n"
        "A|--3--3--|--2--|\n"
        "E|--x--x--|--3--|[/tab]\n"
    )
    slices = UgTimelineBuilder("ultimate-guitar-1.ug", [], source=_source(content)).build()
    measures = sorted({n.measure for n in _tab_notes(slices)})
    assert measures == [1, 2]
    assert content_part_summary(content) == (False, True)


def test_multi_digit_fret_slide_and_muted_hit():
    content = (
        "[tab]e|--12/14--x--|\n"
        "B|-----------|[/tab]\n"
    )
    slices = UgTimelineBuilder("ultimate-guitar-1.ug", [], source=_source(content)).build()
    notes = _tab_notes(slices)
    frets = [n.fret for n in notes if n.midi_pitch is not None]
    assert 12 in frets and 14 in frets           # both multi-digit frets read
    slid = [n for n in notes if n.glissando == "slide"]
    assert slid and slid[0].fret == 12           # '/' after 12 marks a slide
    muted = [n for n in notes if n.articulation == "muted"]
    assert muted and muted[0].midi_pitch is None
    assert muted[0].step_name == "muted"


def test_capo_raises_every_tab_pitch():
    content = "[tab]e|--0--3--|\nB|--1--0--|[/tab]\n"
    plain = UgTimelineBuilder("x.ug", [], source=_source(content, capo=None)).build()
    capoed = UgTimelineBuilder("x.ug", [], source=_source(content, capo=2)).build()
    plain_p = [n.midi_pitch for n in _tab_notes(plain)]
    capoed_p = [n.midi_pitch for n in _tab_notes(capoed)]
    assert capoed_p == [p + 2 for p in plain_p]


def test_hybrid_page_produces_chords_lyrics_and_tablature_in_document_order():
    content = (
        "[Verse]\n\n[tab][ch]Am[/ch]  [ch]F[/ch]\nhi there[/tab]\n"
        "[Intro]\n\n[tab]e|--0--2--|\nB|--1--1--|[/tab]\n"
    )
    builder = UgTimelineBuilder("x.ug", [], source=_source(content))
    slices = builder.build()

    assert content_part_summary(content) == (True, True)
    chord_measures = sorted({n.measure for s in slices for n in s.notes if n.part_id == CHORDS_PART_ID})
    tab_measures = sorted({n.measure for n in _tab_notes(slices)})
    assert chord_measures == [1, 2]     # chord bars come first
    assert tab_measures == [3]          # tab bar follows
    assert builder.total_measures == 3


def test_tab_block_opening_with_a_chord_name_header_still_imports_its_rows():
    # UG very often opens a tablature system with a line naming the chords
    # played over it - the real string rows sit under a non-tab header.
    content = (
        "[tab]               D                       F#m\n"
        "e|--0--2--|\n"
        "B|--1--1--|\n"
        "G|--0--0--|[/tab]\n"
    )
    slices = UgTimelineBuilder("x.ug", [], source=_source(content)).build()
    tab_notes = _tab_notes(slices)
    assert len(tab_notes) == 6                       # 2 columns x 3 strings
    assert {n.string for n in tab_notes} == {1, 2, 3}


def test_no_barline_block_is_one_bar():
    content = "[tab]e|-0-2-3-5-|\nB|-1-1-0-2-|[/tab]\n"
    builder = UgTimelineBuilder("x.ug", [], source=_source(content))
    builder.build()
    assert builder.total_measures == 1


# --- P2: plain-text (un-[ch]-marked) chord/lyric body of a "Tab" page -------

def test_bare_plaintext_chord_line_over_lyric_line():
    """A UG "Tab" song sheet has no [ch] markup: bare chord names sit above
    the lyric line by character column. Only parsed inside a [Section]."""
    content = (
        "[Verse 1]\n"
        "\n"
        "   D        F#m\n"
        "I know they say you can't\n"
    )
    b = UgTimelineBuilder("x.ug", [], source=_source(content))
    slices = b.build()
    chords = [n for s in slices for n in s.notes if n.part_id == CHORDS_PART_ID]
    lyrics = [n for s in slices for n in s.notes if n.part_id == LYRICS_PART_ID]
    # "F#m" is spelled out for the screen reader, same as the [ch] path.
    assert [n.step_name for n in chords] == ["D", "F# minor"]
    assert [n.chord_symbol for n in chords] == ["D", "F# minor"]
    assert lyrics[0].step_name.startswith("I know")
    assert [sp.label for sp in b.section_spans] == ["Verse 1"]


def test_lyric_line_with_no_chord_above_is_a_lyrics_only_bar():
    """symbol == "" -> a Lyrics note, no Chords note (the melody carries on
    under the previous chord)."""
    content = (
        "[Verse 2]\n"
        "\n"
        "      D\n"
        "Mama cut out pictures of houses\n"
        "And nail by nail and board by board\n"
    )
    slices = UgTimelineBuilder("x.ug", [], source=_source(content)).build()
    assert len(slices) == 2
    # bar 1: chord + lyric; bar 2: lyric only, no chord note
    assert any(n.part_id == CHORDS_PART_ID for n in slices[0].notes)
    assert not any(n.part_id == CHORDS_PART_ID for n in slices[1].notes)
    lyric2 = [n for n in slices[1].notes if n.part_id == LYRICS_PART_ID]
    assert len(lyric2) == 1
    assert lyric2[0].step_name.startswith("And nail")
    assert lyric2[0].midi_pitch is None


def test_lone_bare_chord_line_then_lyric_line_pairs_them():
    content = "[Chorus]\n\nG\nOut here it's like I'm someone else\n"
    slices = UgTimelineBuilder("x.ug", [], source=_source(content)).build()
    assert len(slices) == 1
    chords = [n for n in slices[0].notes if n.part_id == CHORDS_PART_ID]
    lyrics = [n for n in slices[0].notes if n.part_id == LYRICS_PART_ID]
    assert [n.step_name for n in chords] == ["G"]
    assert lyrics[0].step_name.startswith("Out here")


def test_prose_before_the_first_section_label_produces_no_events():
    """The tabber's intro paragraph and the trailing chord-shape legend both
    sit outside any [Section] - neither should become chord/lyric bars."""
    content = (
        "Miranda Lambert varies the way she picks each chord.\n"
        "That will take a little improv or you could play just the chords.\n"
        "\n"
        "[Verse 1]\n"
        "\n"
        "D\n"
        "Real words here\n"
    )
    slices = UgTimelineBuilder("x.ug", [], source=_source(content)).build()
    assert len(slices) == 1
    assert slices[0].measure == 1


def test_section_less_tab_block_gets_a_picking_library_label():
    """A [tab] fingerpicking block before the first [Section] becomes its
    own navigable section: a chord-named header -> "Picking: D -> F#m",
    otherwise "Intro" for the first, "Picking pattern N" after."""
    content = (
        "[tab]e|--0--2--|\nB|--1--1--|\nG|--0--0--|[/tab]\n"
        "\n"
        "[tab]               D                       F#m\n"
        "e|--0--2--|\nB|--1--1--|\nG|--0--0--|[/tab]\n"
    )
    b = UgTimelineBuilder("x.ug", [], source=_source(content))
    b.build()
    labels = [sp.label for sp in b.section_spans]
    assert labels == ["Intro", "Picking: D \u2192 F#m"]
