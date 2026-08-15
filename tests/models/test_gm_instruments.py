# tests/models/test_gm_instruments.py
from models.gm_instruments import (
    GM_INSTRUMENT_NAMES,
    gm_instrument_name,
    gm_program_for_name,
)


def test_128_entries_1_indexed():
    assert len(GM_INSTRUMENT_NAMES) == 128
    assert gm_instrument_name(1) == "Acoustic Grand Piano"
    assert gm_instrument_name(25) == "Acoustic Guitar (nylon)"
    assert gm_instrument_name(128) == "Gunshot"


def test_out_of_range_program_clamps_instead_of_raising():
    assert gm_instrument_name(0) == "Acoustic Grand Piano"
    assert gm_instrument_name(999) == "Gunshot"


def test_name_round_trips_back_to_its_program_number():
    assert gm_program_for_name("Clarinet") == 72
    assert gm_program_for_name(gm_instrument_name(72)) == 72


def test_unknown_name_returns_none():
    assert gm_program_for_name("Not a real instrument") is None
