# tests/test_region_presenter_region5.py
"""P2: Region 5's live Section/Chord/Lyric context rows (UG "Tab" import).

An intra-section chord or lyric change relabels the context rows in place
and does NOT re-fire the performance-change cue; crossing a section
boundary is a structural change and rebuilds the list with a cue.
"""
from controllers.region_presenter import RegionPresenter
from models.event_slice import EventSlice
from models.music_data import MusicData
from models.note_data import NoteData
from models.parts_structure import PartStructureInfo
from models.section_span import SectionSpan
from models.synthetic_parts import CHORDS_PART_ID, LYRICS_PART_ID
from widgets.region5_list_widget import Region5ListWidget


class _FakeSession:
    def __init__(self, music_data, synth):
        self.music_data = music_data
        self.synth = synth
        self.uk_terms = False


def _chord_slice(measure, quarters, sym, words):
    return EventSlice(
        measure=measure, beat_position=1.0, quarter_length=4.0,
        quarters_from_start=quarters, time_sig=(4, 4),
        notes=[
            NoteData(step_name=sym, measure=measure, beat_position=1.0,
                     ts_duration=4.0, quarter_length=4.0, part_id=CHORDS_PART_ID,
                     part_name="Chords", staff=1, voice=1, midi_pitch=60,
                     chord_symbol=sym),
            NoteData(step_name=words, measure=measure, beat_position=1.0,
                     ts_duration=4.0, quarter_length=4.0, part_id=LYRICS_PART_ID,
                     part_name="Lyrics", staff=1, voice=1, midi_pitch=None),
        ],
    )


def _music_data():
    return MusicData(
        parts_info=[
            PartStructureInfo(part_id=CHORDS_PART_ID, name="Chords"),
            PartStructureInfo(part_id=LYRICS_PART_ID, name="Lyrics"),
        ],
        timeline_slices=[
            _chord_slice(1, 0.0, "D", "one"),
            _chord_slice(2, 4.0, "G", "two"),
            _chord_slice(3, 8.0, "A", "three"),
        ],
        section_spans=[
            SectionSpan(label="Verse 1", start_measure=1, end_measure=2),
            SectionSpan(label="Chorus", start_measure=3, end_measure=3),
        ],
    )


def _presenter(qtbot, null_synth):
    md = _music_data()
    region_5 = Region5ListWidget()
    qtbot.addWidget(region_5)
    presenter = RegionPresenter(
        _FakeSession(md, null_synth),
        None, None, None, None, region_5, None, lambda: ("", "", ""),
    )
    return presenter, md, region_5


def _row_texts(region_5):
    return [region_5.item(i).text() for i in range(region_5.count())]


def test_intra_section_chord_change_relabels_in_place_with_no_cue(qtbot, null_synth):
    presenter, md, region_5 = _presenter(qtbot, null_synth)

    md.active_event_index = 0
    presenter.refresh_region_5()
    assert len(null_synth.performance_cues) == 1  # first render always cues
    assert "Chord: D" in _row_texts(region_5)

    null_synth.performance_cues.clear()
    md.active_event_index = 1  # bar 2 - still Verse 1, chord D -> G
    presenter.refresh_region_5()

    assert null_synth.performance_cues == []  # no cue for an intra-section change
    texts = _row_texts(region_5)
    assert "Chord: G" in texts and "Lyric: two" in texts
    assert "Chord: D" not in texts


def test_crossing_a_section_boundary_rebuilds_with_a_cue(qtbot, null_synth):
    presenter, md, region_5 = _presenter(qtbot, null_synth)

    md.active_event_index = 1
    presenter.refresh_region_5()
    null_synth.performance_cues.clear()

    md.active_event_index = 2  # bar 3 - Verse 1 -> Chorus
    presenter.refresh_region_5()

    assert len(null_synth.performance_cues) == 1
    texts = _row_texts(region_5)
    assert "Section: Chorus" in texts
    assert any(t.startswith("Section start: Chorus") for t in texts)
