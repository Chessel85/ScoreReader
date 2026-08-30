# tests/models/test_section_spans.py
"""P2 - Ultimate Guitar song sections surfaced as markings (SectionSpan),
Region 5 rows, a Find target and Ctrl+Alt+Left/Right navigation."""
from controllers.navigation_controller import NavigationController
from models.strum_pattern import StrumPattern
from parsers.ug_reader import _build_music_data
from parsers.ug_source import UgSource

_CONTENT = (
    "[Intro]\n\n[ch]C[/ch]  [ch]G[/ch]\n"
    "[Verse 1]\n\n[tab][ch]Am[/ch]  [ch]F[/ch]\nHi there friend[/tab]\n"
    "[Chorus]\n\n[ch]C[/ch]  [ch]G[/ch]  [ch]Am[/ch]\n"
)


def _md():
    source = UgSource(
        song_name="S", artist_name="A", tonality="C", tuning="", difficulty="",
        content=_CONTENT, tab_id=1,
        source_url="https://tabs.ultimate-guitar.com/tab/a/s-chords-1",
        strum_patterns=[StrumPattern("", 120, 16, False, [])], capo=None,
    )
    return _build_music_data(source, "ultimate-guitar-1.ug")


def test_section_spans_populated_with_verbatim_labels_and_ranges():
    spans = _md().section_spans
    assert [(s.label, s.start_measure, s.end_measure) for s in spans] == [
        ("Intro", 1, 2),
        ("Verse 1", 3, 4),
        ("Chorus", 5, 7),
    ]


def test_region_5_shows_a_section_row_pair_for_the_cursor_position():
    md = _md()
    md.active_event_index = 3  # bar 4, inside "Verse 1"
    labels = [r.label for r in md.get_performance_region_rows()]
    assert "Section start: Verse 1: measure 3 to measure 4" in labels
    assert "Section end: Verse 1: measure 3 to measure 4" in labels
    starts = {r.label: r.jump_target_measure for r in md.get_performance_region_rows()}
    assert starts["Section start: Verse 1: measure 3 to measure 4"] == 3
    assert starts["Section end: Verse 1: measure 3 to measure 4"] == 4


def test_section_is_offered_as_a_find_target_with_the_right_count():
    md = _md()
    target = next(
        t for t in md.available_find_targets()
        if t.category == "marking" and t.key == "section"
    )
    assert target.label == "Section"
    assert md.find_index.sorted_candidate_indices(target) == [
        md.first_visible_event_index_of_measure(m) for m in (1, 3, 5)
    ]


def test_performance_report_lists_the_sections():
    lines = _md().get_performance_report_lines()
    assert "Sections: 3" in lines
    assert "Verse 1: Measure 3 to Measure 4" in lines


class _Session:
    def __init__(self, md):
        self.music_data = md


def test_ctrl_alt_arrows_step_between_section_starts_and_cue_the_boundary():
    md = _md()
    nav = NavigationController(_Session(md))
    moved, boundary = [], []
    nav.position_changed.connect(lambda *a: moved.append(md.active_event_index))
    nav.boundary_hit.connect(lambda: boundary.append(True))

    md.active_event_index = 0
    nav.next_section()  # -> Verse 1 start (bar 3)
    nav.next_section()  # -> Chorus start (bar 5)
    assert [md.timeline_slices[i].measure for i in moved] == [3, 5]

    nav.next_section()  # already in the last section -> boundary cue, no move
    assert boundary == [True]

    moved.clear()
    nav.previous_section()  # -> Verse 1 start
    assert md.timeline_slices[moved[-1]].measure == 3
