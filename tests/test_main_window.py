# tests/test_main_window.py
"""Widget wiring, driven entirely offscreen with an injected synth.

If any test here opens a window or an audio device, the harness is broken.
"""
import pytest

from main_window import MainWindow


@pytest.fixture
def window(qtbot, null_synth):
    w = MainWindow(synth=null_synth)
    qtbot.addWidget(w)
    return w


def test_constructs_without_touching_audio(window, null_synth):
    assert window.synth is null_synth
    assert null_synth.played == []
    assert not null_synth.closed


def test_four_distinct_regions_are_tab_focusable(window):
    """Groundwork for Ref 1 AC2/AC3. Verifying the cycle actually wraps needs
    a shown window, so that assertion waits for the Ref 4 work in C1."""
    regions = [window.region_1, window.region_2, window.region_3, window.region_4]

    assert len(set(id(r) for r in regions)) == 4
    for region in regions:
        assert region.focusPolicy().name in ("TabFocus", "StrongFocus")


def test_loading_a_score_populates_regions_and_plays(window, null_synth, minimal_score):
    window.load_score_from_file(minimal_score)

    assert window.region_1.rowCount() > 0, "score metadata"
    assert [
        window.region_3.item(i).text() for i in range(window.region_3.count())
    ] == ["C"]
    assert window.region_4.rowCount() > 0, "note attributes"

    assert null_synth.last_played is not None
    assert null_synth.last_played["midi_notes"] == [60], "middle C"


def test_navigating_right_auditions_the_new_slice(window, null_synth, minimal_score):
    window.load_score_from_file(minimal_score)
    null_synth.played.clear()

    window.navigate_timeline_right()

    assert [
        window.region_3.item(i).text() for i in range(window.region_3.count())
    ] == ["D"]
    assert null_synth.last_played["midi_notes"] == [62]


def test_playback_stops_previous_notes_before_starting_new_ones(
    window, null_synth, minimal_score
):
    """Ref 8 AC2."""
    window.load_score_from_file(minimal_score)
    stops_before = null_synth.stop_count

    window.navigate_timeline_right()

    assert null_synth.stop_count > stops_before


def test_gm_program_is_converted_to_zero_based_on_the_wire(
    window, null_synth, minimal_score
):
    """The model holds 1-indexed GM programs; the synth takes 0-indexed."""
    window.load_score_from_file(minimal_score)

    assert window._music_data.parts_info[0].gmidi_program == 1
    assert null_synth.last_played["program"] == 0
