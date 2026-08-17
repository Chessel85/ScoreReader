# tests/models/test_gm_percussion_map.py
from models.gm_percussion_map import (
    detect_percussion_key_shift,
    gm_percussion_key_for_name,
    gm_percussion_name,
)


def test_gm_percussion_name_known_key():
    assert gm_percussion_name(42) == "Closed Hi-Hat"


def test_gm_percussion_name_unknown_key_degrades_gracefully():
    assert gm_percussion_name(1) == "Percussion note 1"


def test_gm_percussion_key_for_name_exact_match_case_insensitive():
    assert gm_percussion_key_for_name("closed hi-hat") == 42
    assert gm_percussion_key_for_name("  Tambourine  ") == 54


def test_gm_percussion_key_for_name_unknown_name_returns_none():
    """A short/custom name with no exact GM match (e.g. MuseScore's own
    "Snare", not GM's "Acoustic Snare"/"Electric Snare") - see
    detect_percussion_key_shift for why this deliberately isn't fuzzy."""
    assert gm_percussion_key_for_name("Snare") is None


def test_detect_percussion_key_shift_from_hit_it_mxl_real_data():
    """Confirmed against Hit It.mxl: every item is declared exactly one key
    higher than GM's real key for its own name."""
    items = [
        ("Closed Hi-Hat", 43),  # exact match: GM 42, shift +1
        ("Tambourine", 55),     # exact match: GM 54, shift +1
        ("Snare", 39),          # no exact match - along for the ride
        ("Bass Drum", 37),      # no exact match - along for the ride
    ]
    assert detect_percussion_key_shift(items) == 1


def test_detect_percussion_key_shift_no_exact_matches_returns_none():
    items = [("Snare", 39), ("Bass Drum", 37)]
    assert detect_percussion_key_shift(items) is None


def test_detect_percussion_key_shift_disagreeing_exact_matches_returns_none():
    """A file where two unambiguous items imply different shifts isn't safe
    to auto-correct with a single number."""
    items = [("Closed Hi-Hat", 43), ("Tambourine", 60)]
    assert detect_percussion_key_shift(items) is None


def test_detect_percussion_key_shift_no_items_returns_none():
    assert detect_percussion_key_shift([]) is None
