# tests/models/test_key_signatures.py
from models.key_signatures import (
    FIFTHS_MAP,
    NO_KEY_OVERRIDE_LABEL,
    key_override_options,
    key_signature_display_name,
)


def test_mode_none_keeps_the_joined_major_minor_text():
    assert key_signature_display_name(1, None) == "G major / E minor"


def test_mode_major_or_minor_splits_to_just_that_half():
    assert key_signature_display_name(1, "major") == "G major"
    assert key_signature_display_name(1, "minor") == "E minor"
    assert key_signature_display_name(-3, "major") == "E flat major"
    assert key_signature_display_name(-3, "minor") == "C minor"


def test_accidentals_are_spelled_out_as_words_not_symbols_or_letters():
    """Reported, live-tested: NVDA read "Bb major" as just "b major" (the
    accidental letter silently dropped/misread) and "F# minor" lost the "#"
    entirely rather than saying "sharp" - the same spoken-friendly
    convention already used for note names (CLAUDE.md) had never been
    applied to FIFTHS_MAP itself."""
    assert key_signature_display_name(-2, "major") == "B flat major"
    assert key_signature_display_name(6, "major") == "F sharp major"
    assert "#" not in FIFTHS_MAP[6]
    assert "Bb" not in FIFTHS_MAP[-2] and "F#" not in FIFTHS_MAP[6]


def test_out_of_range_fifths_falls_back_regardless_of_mode():
    assert key_signature_display_name(99, None) == "99 sharps/flats"
    assert key_signature_display_name(99, "major") == "99 sharps/flats"


def test_key_override_options_has_31_entries_sentinel_first():
    options = key_override_options()

    assert len(options) == 31
    assert options[0] == (NO_KEY_OVERRIDE_LABEL, None, None)
    assert all(fifths is not None and mode in ("major", "minor") for _, fifths, mode in options[1:])


def test_key_override_options_are_internally_consistent_with_fifths_map():
    options = key_override_options()
    majors = {fifths: label for label, fifths, mode in options if mode == "major"}
    minors = {fifths: label for label, fifths, mode in options if mode == "minor"}

    assert len(majors) == len(FIFTHS_MAP)
    assert len(minors) == len(FIFTHS_MAP)
    for fifths, joined in FIFTHS_MAP.items():
        major, minor = joined.split(" / ", 1)
        assert majors[fifths] == major
        assert minors[fifths] == minor
