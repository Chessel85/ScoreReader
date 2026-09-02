# tests/models/test_guitar_tuning.py
from models import guitar_tuning as gt


def test_standard_tuning_text_matches_the_canonical_table():
    assert gt.parse_tuning_text("E A D G B E") == gt.STANDARD_TUNING_HIGH_TO_LOW


def test_tuning_text_is_ordered_high_to_low():
    midis = gt.parse_tuning_text("E A D G B E")
    assert midis[0] == 64  # high E4 first
    assert midis[-1] == 40  # low E2 last


def test_drop_d_lowers_only_the_sixth_string():
    standard = gt.parse_tuning_text("E A D G B E")
    drop_d = gt.parse_tuning_text("D A D G B E")
    assert drop_d[:-1] == standard[:-1]
    assert drop_d[-1] == standard[-1] - 2  # D2


def test_half_step_down_lowers_every_string_by_one():
    down = gt.parse_tuning_text("Eb Ab Db Gb Bb Eb")
    assert down == [m - 1 for m in gt.STANDARD_TUNING_HIGH_TO_LOW]


def test_malformed_tuning_text_returns_none():
    assert gt.parse_tuning_text("") is None
    assert gt.parse_tuning_text("E A D") is None          # too few
    assert gt.parse_tuning_text("E A D G B Z") is None    # not a note letter


def test_open_string_midis_from_row_labels():
    labels = ["e", "B", "G", "D", "A", "E"]  # top row -> bottom row
    assert gt.open_string_midis_from_rows(labels) == gt.STANDARD_TUNING_HIGH_TO_LOW


def test_open_string_midis_from_rows_rejects_a_bad_label():
    assert gt.open_string_midis_from_rows(["e", "B", "G", "?"]) is None


def test_midi_for_adds_fret_and_capo():
    assert gt.midi_for(64, 0, 0) == 64
    assert gt.midi_for(64, 3, 0) == 67
    assert gt.midi_for(64, 3, 2) == 69
