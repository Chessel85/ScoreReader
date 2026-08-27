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
import subprocess
import threading
import time

from audio.voice_commands import (
    ATTRIBUTE,
    COMMAND_PHRASES,
    GO_TO_BAR,
    LOOP_LENGTH,
    attribute_phrases,
    go_to_bar_phrases,
    loop_length_phrases,
)
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


def test_build_grammar_phrases_includes_the_unknown_token():
    """Re-enabled for the large-model A/B test - see UNKNOWN_TOKEN's own
    comment in audio/voice_recognition.py for the history (broke
    finalization on an earlier live test, not reproduced since)."""
    assert UNKNOWN_TOKEN in _build_grammar_phrases(total_measures=5)


def test_build_grammar_phrases_includes_go_to_bar_phrases_for_the_current_score():
    phrases = _build_grammar_phrases(total_measures=5)
    for phrase, _ in go_to_bar_phrases(5):
        assert phrase in phrases


def test_build_grammar_phrases_has_no_go_to_bar_phrases_with_no_score_loaded():
    phrases = _build_grammar_phrases(total_measures=0)
    assert not any(p.startswith("go to bar") or p.startswith("go to measure") for p in phrases)


def test_build_grammar_phrases_includes_loop_length_phrases_regardless_of_score():
    """Fixed vocabulary, unlike go_to_bar - present even with no score
    loaded."""
    phrases = _build_grammar_phrases(total_measures=0)
    for phrase, _ in loop_length_phrases():
        assert phrase in phrases


def test_build_grammar_phrases_includes_attribute_phrases_regardless_of_score():
    """Fixed vocabulary, unlike go_to_bar - present even with no score
    loaded."""
    phrases = _build_grammar_phrases(total_measures=0)
    for phrase, _ in attribute_phrases():
        assert phrase in phrases


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


def test_handle_final_result_resolves_loop_length_with_the_bar_count():
    manager, accepted, diagnostics = _manager_with_recording_callbacks(confidence_threshold=0.0)

    manager._handle_final_result({
        "words": [{"conf": 0.9, "word": w} for w in ["loop", "length", "four"]],
        "text": "loop length four",
    })

    assert accepted == [(LOOP_LENGTH, 90.0, 4)]
    assert diagnostics == [("loop length four", 90.0, True)]


def test_handle_final_result_resolves_attribute_with_the_row_number():
    manager, accepted, diagnostics = _manager_with_recording_callbacks(confidence_threshold=0.0)

    manager._handle_final_result({
        "words": [{"conf": 0.9, "word": w} for w in ["attribute", "five"]],
        "text": "attribute five",
    })

    assert accepted == [(ATTRIBUTE, 90.0, 5)]
    assert diagnostics == [("attribute five", 90.0, True)]


# --- stop() must not block the calling (Qt main) thread - S4 ------------


class _FakeStdin:
    def __init__(self):
        self.written = []

    def write(self, s):
        self.written.append(s)

    def flush(self):
        pass


class _FakeProcess:
    """Stand-in for subprocess.Popen in stop() tests. wait() honours its
    timeout the way Popen.wait does (raises TimeoutExpired on expiry), so
    the bounded synchronous path can be timed without a real child."""

    def __init__(self, exit_delay: float):
        self._deadline = time.monotonic() + exit_delay
        self.stdin = _FakeStdin()
        self.kill_count = 0

    def wait(self, timeout=None):
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            return 0
        if timeout is not None and timeout < remaining:
            raise subprocess.TimeoutExpired(cmd="fake-worker", timeout=timeout)
        time.sleep(remaining)
        return 0

    def kill(self):
        self.kill_count += 1
        self._deadline = time.monotonic()

    def poll(self):
        return 0 if time.monotonic() >= self._deadline else None


def _manager_with_fake_worker(exit_delay: float):
    manager = VoiceRecognitionManager()
    process = _FakeProcess(exit_delay)
    reader = threading.Thread(target=lambda: None)
    reader.start()
    manager._process = process
    manager._reader_thread = reader
    return manager, process


def test_stop_sends_the_stop_command_and_detaches_the_worker_promptly():
    manager, process = _manager_with_fake_worker(exit_delay=0.0)

    started = time.monotonic()
    manager.stop()
    elapsed = time.monotonic() - started

    assert elapsed < 0.5
    assert process.stdin.written == ['{"cmd": "stop"}\n']
    assert manager._process is None
    assert manager._reader_thread is None
    assert process.kill_count == 0


def test_stop_does_not_block_on_a_wedged_worker_and_reaps_it_in_the_background():
    manager, process = _manager_with_fake_worker(exit_delay=60.0)

    started = time.monotonic()
    manager.stop()
    elapsed = time.monotonic() - started

    # The old inline path blocked here for up to 6s (3s wait + 3s join).
    assert elapsed < 1.0
    assert manager._process is None
    assert manager._reader_thread is None

    deadline = time.monotonic() + 3.0
    while process.kill_count == 0 and time.monotonic() < deadline:
        time.sleep(0.02)
    assert process.kill_count == 1


def test_stop_is_a_noop_with_no_worker():
    manager = VoiceRecognitionManager()
    manager.stop()  # must not raise
    assert manager._process is None
