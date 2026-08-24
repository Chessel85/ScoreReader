# tests/test_voice_commands.py
"""audio/voice_commands.py - pure vocabulary/grammar-building logic, no
Qt/COM involved at all."""
import pytest

from audio.voice_commands import (
    COMMAND_PHRASES,
    DEFAULT_SPEED,
    END,
    FASTER,
    GO_TO_BAR,
    HOME,
    LOOP_LENGTH,
    MAX_LOOP_LENGTH_BARS,
    NEXT_BAR,
    PAUSE,
    PLAY,
    PREVIEW,
    PREVIOUS_BAR,
    SLOWER,
    STOP,
    go_to_bar_phrases,
    go_to_bar_reverse_lookup,
    loop_length_phrases,
    loop_length_reverse_lookup,
    number_to_words,
    parse_command,
)
from models.preview_settings import MIN_PREVIEW_BARS


@pytest.mark.parametrize("n,words", [
    (0, "zero"),
    (1, "one"),
    (9, "nine"),
    (10, "ten"),
    (19, "nineteen"),
    (20, "twenty"),
    (21, "twenty one"),
    (99, "ninety nine"),
    (100, "one hundred"),
    (105, "one hundred five"),
    (130, "one hundred thirty"),
    (999, "nine hundred ninety nine"),
    (1000, "one thousand"),
    (1001, "one thousand one"),
])
def test_number_to_words(n, words):
    assert number_to_words(n) == words


def test_number_to_words_rejects_negative():
    with pytest.raises(ValueError):
        number_to_words(-1)


def test_every_required_command_maps_to_a_distinct_canonical_name():
    """Every command from the original request has a phrase - a missing
    entry here would silently mean that command can never be recognized."""
    required = {
        "preview": PREVIEW, "play": PLAY, "stop": STOP, "pause": PAUSE,
        "forward": "forward", "back": "back",
        "next bar": NEXT_BAR, "next measure": NEXT_BAR,
        "previous bar": PREVIOUS_BAR, "previous measure": PREVIOUS_BAR,
        "home": HOME, "end": END,
        "slower": SLOWER, "faster": FASTER, "default speed": DEFAULT_SPEED,
    }
    for phrase, command in required.items():
        assert COMMAND_PHRASES[phrase] == command


def test_go_to_bar_phrases_covers_zero_through_total_measures():
    phrases = go_to_bar_phrases(3)
    numbers = sorted({n for _, n in phrases})
    assert numbers == [0, 1, 2, 3]
    assert ("go to bar three", 3) in phrases
    assert ("go to measure three", 3) in phrases


def test_go_to_bar_phrases_empty_when_no_real_measures():
    assert go_to_bar_phrases(0) == []
    assert go_to_bar_phrases(-1) == []


def test_parse_command_resolves_fixed_phrases_case_and_space_insensitively():
    assert parse_command("Play") == (PLAY, None)
    assert parse_command("  next   bar  ") == (NEXT_BAR, None)


def test_parse_command_resolves_go_to_bar_via_lookup():
    lookup = go_to_bar_reverse_lookup(12)
    assert parse_command("go to bar twelve", lookup) == (GO_TO_BAR, 12)
    assert parse_command("go to measure twelve", lookup) == (GO_TO_BAR, 12)


def test_parse_command_returns_none_for_unrecognized_text():
    assert parse_command("banana") is None
    assert parse_command("go to bar one hundred", go_to_bar_reverse_lookup(5)) is None


def test_parse_command_go_to_bar_without_lookup_is_unrecognized():
    assert parse_command("go to bar twelve") is None


def test_loop_length_phrases_covers_min_through_max_bars():
    phrases = loop_length_phrases()
    numbers = sorted({n for _, n in phrases})
    assert numbers == list(range(MIN_PREVIEW_BARS, MAX_LOOP_LENGTH_BARS + 1))
    assert ("loop length four", 4) in phrases
    assert ("loop length one", MIN_PREVIEW_BARS) in phrases


def test_parse_command_resolves_loop_length_via_lookup():
    lookup = loop_length_reverse_lookup()
    assert parse_command("loop length four", loop_length_lookup=lookup) == (LOOP_LENGTH, 4)


def test_parse_command_loop_length_without_lookup_is_unrecognized():
    assert parse_command("loop length four") is None


def test_parse_command_loop_length_out_of_range_is_unrecognized():
    assert parse_command("loop length one hundred", loop_length_lookup=loop_length_reverse_lookup()) is None
