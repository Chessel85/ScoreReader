# audio/voice_commands.py
"""Hands-free voice control (feature/voice-control): the fixed command
vocabulary for the SAPI command-and-control grammar, plus "go to bar N"'s
number-word generation.

Pure Python, no Qt/COM anywhere in this file - independently unit-testable
without a real SAPI recognizer. audio/voice_recognition.py (the COM wrapper)
imports this to build the grammar XML and to resolve recognized text back to
a command.

Restricting the grammar to this fixed vocabulary (no open dictation) is the
main accuracy lever for this feature: the user's instrument and any
background speech have nothing phonetically plausible to match against a
small closed set of commands, so SAPI's own CFG rejection model does most of
the work.
"""
from typing import Dict, List, Optional, Tuple

from models.play_settings import MIN_LOOP_LENGTH_BARS

# Canonical command names dispatched by controllers/voice_control_controller.py.
# GO_TO_BAR, LOOP_LENGTH and ATTRIBUTE are all parameterized (each carries a
# single int - a measure number / a bar count / a Region 4 row number
# respectively) and are therefore NOT keys in COMMAND_PHRASES below - see
# go_to_bar_phrases()/loop_length_phrases()/attribute_phrases()/
# parse_command().
PLAY = "play"
STOP = "stop"
PAUSE = "pause"
FORWARD = "forward"
BACK = "back"
NEXT_BAR = "next_bar"
PREVIOUS_BAR = "previous_bar"
HOME = "home"
END = "end"
GO_TO_BAR = "go_to_bar"
SLOWER = "slower"
FASTER = "faster"
DEFAULT_SPEED = "default_speed"
LOOP_LENGTH = "loop_length"
LOOPING_ON = "looping_on"
LOOPING_OFF = "looping_off"
LEAD_IN_ON = "lead_in_on"
LEAD_IN_OFF = "lead_in_off"
ATTRIBUTE = "attribute"

# Every fixed (non-parameterized) spoken phrase, lowercase, mapped to its
# canonical command name. Synonyms ("next bar"/"next measure") map to the
# same command - "bar" vs "measure" is a dialect choice, not two different
# behaviours (mirrors models/vocabulary.py's bar_word reasoning elsewhere in
# this app). "left"/"right" are synonyms for "back"/"forward" - same
# direction as the Left/Right arrow keys they mirror.
COMMAND_PHRASES: Dict[str, str] = {
    "play": PLAY,
    "stop": STOP,
    "pause": PAUSE,
    "forward": FORWARD,
    "right": FORWARD,
    "back": BACK,
    "left": BACK,
    "next bar": NEXT_BAR,
    "next measure": NEXT_BAR,
    "previous bar": PREVIOUS_BAR,
    "previous measure": PREVIOUS_BAR,
    "home": HOME,
    "end": END,
    "slower": SLOWER,
    "faster": FASTER,
    "default speed": DEFAULT_SPEED,
    "looping on": LOOPING_ON,
    "loop on": LOOPING_ON,
    "looping off": LOOPING_OFF,
    "loop off": LOOPING_OFF,
    "lead in on": LEAD_IN_ON,
    "lead in off": LEAD_IN_OFF,
}

# "go to bar"/"go to measure" precede a spoken number - see
# go_to_bar_phrases() below, which pairs each prefix with every number word
# up to the current score's own total_measures.
GO_TO_BAR_PREFIXES: List[str] = ["go to bar", "go to measure"]

# "loop length" precedes a spoken number - see loop_length_phrases() below.
# Unlike go_to_bar, this isn't bounded by anything score-specific (a loop
# length is just a bar count, not a real measure number), so the vocabulary
# is fixed rather than rebuilt per score.
LOOP_LENGTH_PREFIX = "loop length"

# Bounds the spoken numeric vocabulary for "loop length N". Matches
# PlaySettings.MAX_LOOP_LENGTH_BARS (64) - the unified cap across the
# dialog, Alt+PageUp/PageDown, the typed Ctrl+Enter buffer and this voice
# command.
MAX_LOOP_LENGTH_BARS = 64

# "attribute" precedes a spoken number - see attribute_phrases() below. The
# hands-free counterpart of Ctrl+1..Ctrl+9 in the Note region
# (widgets/timeline_list_widget.py), which speaks Region 4's Nth row without
# moving focus off Region 3 - see controllers/region_presenter.py's
# announce_attribute_by_number. Bounded to the same 1-9 range as that
# keystroke (a single digit), not per-score like go_to_bar - Region 4's row
# count depends on which attributes are switched on, not on the score
# itself, so there's no meaningful score-derived bound to use instead.
ATTRIBUTE_PREFIX = "attribute"
MAX_ATTRIBUTE_NUMBER = 9

_ONES = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
]
_TENS = [
    "", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
    "eighty", "ninety",
]


def number_to_words(n: int) -> str:
    """Spoken word-form of a non-negative integer - bounded to what a real
    measure number needs (every score this app has seen tops out in the
    hundreds), not a general-purpose number-to-words library. "And" is
    deliberately omitted ("one hundred five", not "one hundred and five") -
    a SAPI grammar phrase must match what is actually said, and the shorter
    form is unambiguous either way."""
    if n < 0:
        raise ValueError(f"number_to_words does not support negative numbers: {n}")
    if n < 20:
        return _ONES[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return _TENS[tens] if ones == 0 else f"{_TENS[tens]} {_ONES[ones]}"
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        prefix = f"{_ONES[hundreds]} hundred"
        return prefix if rest == 0 else f"{prefix} {number_to_words(rest)}"
    thousands, rest = divmod(n, 1000)
    prefix = f"{number_to_words(thousands)} thousand"
    return prefix if rest == 0 else f"{prefix} {number_to_words(rest)}"


def go_to_bar_phrases(total_measures: int) -> List[Tuple[str, int]]:
    """(phrase, measure_number) for every "go to bar N"/"go to measure N"
    grammar entry, N ranging over every real measure number in the currently
    loaded score: 0..total_measures (0 covers Ref 17's pickup-bar
    convention, where the pickup is measure 0).

    Rebuilt whenever a new score loads (VoiceControlController.
    rebuild_grammar) so the numeric vocabulary is always bounded to real
    measure numbers in the CURRENT score - an accuracy win, not just
    tidiness: nothing spoken can be misheard as a bar that doesn't exist.

    Returns [] when total_measures is 0 or negative (no score loaded yet, or
    one with no real measures) - "go to bar" simply has nothing to recognize
    until then."""
    if total_measures <= 0:
        return []
    phrases: List[Tuple[str, int]] = []
    for measure in range(0, total_measures + 1):
        words = number_to_words(measure)
        for prefix in GO_TO_BAR_PREFIXES:
            phrases.append((f"{prefix} {words}", measure))
    return phrases


def loop_length_phrases() -> List[Tuple[str, int]]:
    """(phrase, bar_count) for every "loop length N" grammar entry, N
    ranging over MIN_LOOP_LENGTH_BARS..MAX_LOOP_LENGTH_BARS - the
    voice-control counterpart of Playback > Play Settings...'s "Loop length
    in bars" field / Alt+PageUp/PageDown / the typed Ctrl+Enter buffer
    (models/play_settings.py, controllers/playback_controller.py's
    set_loop_length_bars), letting a player set that same value hands-free
    mid-practice.

    Fixed, unlike go_to_bar_phrases() - a loop length has no real per-score
    bound, so this list never needs rebuilding when a new score loads."""
    return [
        (f"{LOOP_LENGTH_PREFIX} {number_to_words(n)}", n)
        for n in range(MIN_LOOP_LENGTH_BARS, MAX_LOOP_LENGTH_BARS + 1)
    ]


def parse_command(
    heard_text: str,
    go_to_bar_lookup: Optional[Dict[str, int]] = None,
    loop_length_lookup: Optional[Dict[str, int]] = None,
    attribute_lookup: Optional[Dict[str, int]] = None,
) -> Optional[Tuple[str, Optional[int]]]:
    """Resolves SAPI's recognized text to (command_name, number_value).
    number_value is None for every command except GO_TO_BAR (a measure
    number), LOOP_LENGTH (a bar count) and ATTRIBUTE (a Region 4 row
    number) - the three parameterized commands. Returns None for anything
    unrecognized - a caller should treat that exactly like a rejected/
    low-confidence result and never dispatch it.

    go_to_bar_lookup is the reverse of go_to_bar_phrases() (phrase text ->
    measure number) for whichever score is currently loaded. loop_length_
    lookup and attribute_lookup are the reverse of loop_length_phrases()/
    attribute_phrases() (phrase text -> bar count / row number) - both
    fixed, so callers can pass loop_length_reverse_lookup()/attribute_
    reverse_lookup() unconditionally rather than tracking any per-score
    state for them. Any of the three omitted (or a miss) simply means that
    parameterized command can't be resolved right now - not an error."""
    text = " ".join(heard_text.lower().split())
    if text in COMMAND_PHRASES:
        return COMMAND_PHRASES[text], None
    if go_to_bar_lookup and text in go_to_bar_lookup:
        return GO_TO_BAR, go_to_bar_lookup[text]
    if loop_length_lookup and text in loop_length_lookup:
        return LOOP_LENGTH, loop_length_lookup[text]
    if attribute_lookup and text in attribute_lookup:
        return ATTRIBUTE, attribute_lookup[text]
    return None


def go_to_bar_reverse_lookup(total_measures: int) -> Dict[str, int]:
    """phrase -> measure_number, for parse_command's go_to_bar_lookup.
    Kept as a separate function (rather than folding into go_to_bar_phrases)
    since the grammar builder wants the list form (it needs every phrase,
    duplicates and all, to build <P> entries) while the recognition-side
    lookup wants the dict form - same underlying data, two shapes."""
    return dict(go_to_bar_phrases(total_measures))


def loop_length_reverse_lookup() -> Dict[str, int]:
    """phrase -> bar_count, for parse_command's loop_length_lookup. Same
    list-vs-dict split as go_to_bar_reverse_lookup, above."""
    return dict(loop_length_phrases())


def attribute_phrases() -> List[Tuple[str, int]]:
    """(phrase, row_number) for every "attribute N" grammar entry, N
    ranging 1..MAX_ATTRIBUTE_NUMBER - the voice-control counterpart of
    Ctrl+1..Ctrl+9 in the Note region, replicating that same quick
    attribute lookup hands-free. Fixed, like loop_length_phrases - not
    bound by anything score-specific, unlike go_to_bar_phrases."""
    return [
        (f"{ATTRIBUTE_PREFIX} {number_to_words(n)}", n)
        for n in range(1, MAX_ATTRIBUTE_NUMBER + 1)
    ]


def attribute_reverse_lookup() -> Dict[str, int]:
    """phrase -> row_number, for parse_command's attribute_lookup. Same
    list-vs-dict split as go_to_bar_reverse_lookup, above."""
    return dict(attribute_phrases())
