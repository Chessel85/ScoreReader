# tests/audio/test_pitch_detector.py
import numpy as np
import pytest

from audio.pitch_detector import detect_pitch
from models.tuner_instruments import cents_deviation

SAMPLE_RATE = 44100


def _sine(frequency_hz: float, duration_s: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    t = np.arange(int(sample_rate * duration_s)) / sample_rate
    return np.sin(2 * np.pi * frequency_hz * t)


@pytest.mark.parametrize(
    "frequency_hz",
    [
        30.87,   # double bass low B0 - the lowest string in the instrument list
        82.41,   # guitar low E2
        220.0,   # A3
        440.0,   # concert A4
        659.25,  # mandolin high E5, near the top of the instrument list
    ],
)
def test_in_tune_signal_detects_near_zero_cents(frequency_hz):
    samples = _sine(frequency_hz, duration_s=0.3)
    result = detect_pitch(samples, SAMPLE_RATE, expected_hz=frequency_hz, search_semitones=4.0)
    assert result is not None
    cents = cents_deviation(result.frequency_hz, frequency_hz)
    assert abs(cents) < 5


def test_sharp_signal_detects_positive_cents():
    target_hz = 220.0
    # +30 cents sharp
    actual_hz = target_hz * (2 ** (30 / 1200))
    samples = _sine(actual_hz, duration_s=0.3)
    result = detect_pitch(samples, SAMPLE_RATE, expected_hz=target_hz, search_semitones=4.0)
    assert result is not None
    cents = cents_deviation(result.frequency_hz, target_hz)
    assert 25 < cents < 35


def test_flat_signal_detects_negative_cents():
    target_hz = 220.0
    # -40 cents flat
    actual_hz = target_hz * (2 ** (-40 / 1200))
    samples = _sine(actual_hz, duration_s=0.3)
    result = detect_pitch(samples, SAMPLE_RATE, expected_hz=target_hz, search_semitones=4.0)
    assert result is not None
    cents = cents_deviation(result.frequency_hz, target_hz)
    assert -45 < cents < -35


def test_detects_true_fundamental_not_a_harmonic_in_a_harmonically_rich_tone():
    """A signal with real harmonic content (fundamental + partials, like a
    plucked string) - the scoped search band's whole point is avoiding a
    harmonic being mistaken for the fundamental (YIN's classic real-world
    failure mode with a full-range search). The 2nd/3rd harmonics here sit a
    full octave-plus above the target and outside the +/-4 semitone search
    band, so they shouldn't be locked onto instead of the true fundamental."""
    target_hz = 110.0  # A2, near the guitar's 5th string
    t = np.arange(int(SAMPLE_RATE * 0.3)) / SAMPLE_RATE
    samples = (
        1.0 * np.sin(2 * np.pi * target_hz * t)
        + 0.5 * np.sin(2 * np.pi * target_hz * 2 * t)
        + 0.25 * np.sin(2 * np.pi * target_hz * 3 * t)
    )
    result = detect_pitch(samples, SAMPLE_RATE, expected_hz=target_hz, search_semitones=4.0)
    assert result is not None
    cents = cents_deviation(result.frequency_hz, target_hz)
    assert abs(cents) < 5


def test_signal_far_from_expected_is_not_falsely_reported_as_in_tune():
    """300Hz has no simple integer-submultiple relationship landing inside a
    220Hz target's +/-4 semitone band, so the detector shouldn't collapse it
    onto "in tune" - whatever lag it does settle on within the band should
    read as far off, not near-zero cents."""
    target_hz = 220.0
    samples = _sine(300.0, duration_s=0.3)
    result = detect_pitch(samples, SAMPLE_RATE, expected_hz=target_hz, search_semitones=4.0)
    assert result is not None
    cents = cents_deviation(result.frequency_hz, target_hz)
    assert abs(cents) > 100


def test_buffer_too_short_for_the_search_band_returns_none():
    # A handful of samples can't cover even one full period at 220Hz, let
    # alone the lag range detect_pitch needs.
    samples = _sine(220.0, duration_s=0.3)[:50]
    result = detect_pitch(samples, SAMPLE_RATE, expected_hz=220.0, search_semitones=4.0)
    assert result is None


def test_silence_returns_low_confidence():
    samples = np.zeros(int(SAMPLE_RATE * 0.3))
    result = detect_pitch(samples, SAMPLE_RATE, expected_hz=220.0, search_semitones=4.0)
    # Pure silence has a zero difference function everywhere (cmnd stays at
    # its all-ones default outside the loop's own division-by-zero guard),
    # so no lag ever clears the threshold - detect_pitch still returns a
    # best-effort lag rather than None, but confidence should reflect that
    # nothing periodic was actually found.
    assert result is not None
    assert result.confidence <= 0.5
