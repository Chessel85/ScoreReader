# tests/test_voice_recognition.py
"""audio/voice_recognition.py - only the pure, no-real-worker-process logic
is testable here (see tests/conftest.py's _forbid_real_voice_recognition):
grammar-phrase building, confidence-percentage math, and
_handle_final_result's own parsing/dispatch/diagnostic-callback behaviour,
which touches no subprocess/vosk/sounddevice API at all - just plain dicts
and callables, exactly the shape audio/voice_recognition_worker.py's
"result" event has.

Real recognition accuracy needs a live microphone, the real model, and the
real worker process - see CLAUDE.md's own note on manual verification for
this feature.
"""
from audio.voice_commands import COMMAND_PHRASES, GO_TO_BAR, go_to_bar_phrases
from audio.voice_recognition import (
    UNKNOWN_TOKEN,
    VoiceRecognitionManager,
    _build_grammar_phrases,
    _confidence_percent,
)


def test_build_grammar_phrases_includes_every_fixed_phrase():
    phrases = _build_grammar_phrases(total_measures=0)
    for phrase in COMMAND_PHRASES:
        assert phrase in phrases


def test_build_grammar_phrases_never_includes_the_unknown_token():
    """GOTCHA (see audio/voice_recognition.py's own comment): including
    "[unk]" in the grammar broke Vosk finalization entirely on the model
    this was built against - confirmed reproducible via live testing."""
    assert UNKNOWN_TOKEN not in _build_grammar_phrases(total_measures=5)


def test_build_grammar_phrases_includes_go_to_bar_phrases_for_the_current_score():
    phrases = _build_grammar_phrases(total_measures=5)
    for phrase, _ in go_to_bar_phrases(5):
        assert phrase in phrases


def test_build_grammar_phrases_has_no_go_to_bar_phrases_with_no_score_loaded():
    phrases = _build_grammar_phrases(total_measures=0)
    assert not any(p.startswith("go to bar") or p.startswith("go to measure") for p in phrases)


def test_confidence_percent_averages_per_word_confidence():
    assert _confidence_percent({"words": [{"conf": 1.0, "word": "stop"}], "text": "stop"}) == 100.0

    result = {"words": [{"conf": 0.5, "word": "go"}, {"conf": 1.0, "word": "back"}], "text": "go back"}
    assert _confidence_percent(result) == 75.0


def test_confidence_percent_is_zero_for_an_empty_result():
    assert _confidence_percent({}) == 0.0
    assert _confidence_percent({"words": [], "text": ""}) == 0.0


def _manager_with_recording_callbacks(confidence_threshold=50.0):
    manager = VoiceRecognitionManager()
    accepted = []
    diagnostics = []
    manager.set_callback(lambda *args: accepted.append(args))
    manager.set_diagnostic_callback(lambda *args: diagnostics.append(args))
    manager._confidence_threshold = confidence_threshold
    return manager, accepted, diagnostics


def test_handle_final_result_dispatches_a_recognized_command_above_threshold():
    manager, accepted, diagnostics = _manager_with_recording_callbacks()

    manager._handle_final_result({"words": [{"conf": 0.9, "word": "stop"}], "text": "stop"})

    assert accepted == [("stop", 90.0, None)]
    assert diagnostics == [("stop", 90.0, True)]


def test_handle_final_result_rejects_below_threshold_without_dispatching():
    manager, accepted, diagnostics = _manager_with_recording_callbacks()

    manager._handle_final_result({"words": [{"conf": 0.2, "word": "stop"}], "text": "stop"})

    assert accepted == []
    assert diagnostics == [("stop", 20.0, False)]


def test_handle_final_result_treats_the_unknown_token_as_no_match():
    manager, accepted, diagnostics = _manager_with_recording_callbacks(confidence_threshold=0.0)

    manager._handle_final_result({"text": UNKNOWN_TOKEN})

    assert accepted == []
    assert diagnostics == [(UNKNOWN_TOKEN, 0.0, False)]


def test_handle_final_result_ignores_silence():
    manager, accepted, diagnostics = _manager_with_recording_callbacks(confidence_threshold=0.0)

    manager._handle_final_result({"text": ""})

    assert accepted == []
    assert diagnostics == [("(silence)", 0.0, False)]


def test_handle_final_result_resolves_go_to_bar_with_the_measure_number():
    manager, accepted, diagnostics = _manager_with_recording_callbacks(confidence_threshold=0.0)
    manager._total_measures = 12

    manager._handle_final_result({
        "words": [{"conf": 0.9, "word": w} for w in ["go", "to", "bar", "twelve"]],
        "text": "go to bar twelve",
    })

    assert accepted == [(GO_TO_BAR, 90.0, 12)]
    assert diagnostics == [("go to bar twelve", 90.0, True)]
