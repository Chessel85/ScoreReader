# audio/pitch_detector.py
"""Pure-function pitch detection for Tools > Tuner (widgets/tuner_dialog.py).
No Qt, no audio hardware - directly unit-testable against synthetic sine
waves the same way audio/strum_schedule.py's build_strum_schedule already
is, and for the same reason: keep DSP-shaped logic Qt-free and testable.

Uses YIN (de Cheveigne & Kawahara, 2002), but restricted to search only
within a narrow band around an EXPECTED frequency, rather than the whole
audible range - the tuner's own key derisking insight (see the tuner plan's
feasibility forecast). Because the instrument/string is already known
(models/tuner_instruments.py) before a single sample is captured, this
sidesteps YIN's classic real-world failure mode (octave errors - locking
onto a harmonic instead of the fundamental) instead of needing a
general-purpose detector to solve it.
"""
from typing import NamedTuple, Optional

import numpy as np

# de Cheveigne & Kawahara's own suggested default absolute threshold for the
# cumulative mean normalized difference function - a value below this at a
# lag is accepted as a genuine periodicity rather than noise.
YIN_THRESHOLD = 0.15

# "Nearly as good" tolerance for the acquisition-mode octave-down sanity
# check in detect_pitch (prefer_lower_octave) - the octave-below candidate
# doesn't need to beat the originally-chosen lag's own CMND dip, just come
# close to it, since a missed fundamental's own dip is often shallower than
# a strong harmonic's. FLAGGED FOR LIVE TUNING like every other threshold
# in this feature.
OCTAVE_DOWN_CMND_SLACK = 0.05


class PitchResult(NamedTuple):
    frequency_hz: float
    confidence: float  # 0..1 - 1 minus the YIN dip's own remaining "aperiodicity"


def detect_pitch(
    samples: np.ndarray,
    sample_rate: int,
    expected_hz: float,
    search_semitones: float = 4.0,
    prefer_lower_octave: bool = False,
) -> Optional[PitchResult]:
    """samples: mono float audio, most-recent buffer (see
    audio/tuner_capture.py). expected_hz/search_semitones bound the lag
    search to the frequency range
    [expected_hz * 2**(-search_semitones/12), expected_hz * 2**(+search_semitones/12)]
    - deliberately NOT the whole audible range. Returns None if the buffer
    is too short for the lags this band needs, or expected_hz/sample_rate
    aren't usable.

    prefer_lower_octave (default False - every existing caller/test is
    unaffected): an acquisition-mode-only sanity check (see
    audio/tuner_capture.py's ACQUISITION_* constants and
    controllers/tuner_controller.py) for a wide search band with no known
    per-string target to anchor it - a wide band is exactly where YIN's
    classic harmonic-instead-of-fundamental failure mode becomes likely
    again, since the "first CMND dip below YIN_THRESHOLD" scan walks from
    min_lag (highest frequency in the band) upward, biasing it toward the
    *shortest* periodic lag that clears the threshold. When set, and the
    chosen candidate's own octave-DOWN alternative (double the lag = half
    the frequency) has a CMND dip within OCTAVE_DOWN_CMND_SLACK of the
    chosen one, that lower-frequency candidate is preferred instead - a
    missed fundamental is far more common in practice than a phantom
    sub-harmonic. Never triggers in tracking mode's narrow per-string band,
    which never had a harmonic living inside it to begin with."""
    if expected_hz <= 0 or sample_rate <= 0:
        return None

    samples = np.asarray(samples, dtype=np.float64).reshape(-1)

    min_hz = expected_hz * (2 ** (-search_semitones / 12))
    max_hz = expected_hz * (2 ** (search_semitones / 12))
    min_lag = max(1, int(sample_rate / max_hz))
    max_lag = int(sample_rate / min_hz) + 1

    # YIN's difference function at lag tau needs samples out to 2*tau (it
    # compares the signal against itself shifted by tau, over a window the
    # same length as the shift) - the buffer must cover the largest lag in
    # the search band twice over, or there's nothing to compare.
    if len(samples) < 2 * max_lag:
        return None

    # Difference function d(tau) (YIN eq. 6), computed ONLY over the narrow
    # search band - the main reason this stays cheap enough to run several
    # times a second.
    diff = np.zeros(max_lag + 1)
    for tau in range(min_lag, max_lag + 1):
        delta = samples[: len(samples) - tau] - samples[tau:]
        diff[tau] = np.dot(delta, delta)

    # Cumulative mean normalized difference function (YIN eq. 8), restricted
    # to the same band - running_sum accumulates from min_lag, not 1, since
    # diff[] below min_lag was never computed (out of the search band).
    cmnd = np.ones(max_lag + 1)
    running_sum = 0.0
    for tau in range(min_lag, max_lag + 1):
        running_sum += diff[tau]
        cmnd[tau] = diff[tau] * (tau - min_lag + 1) / running_sum if running_sum > 0 else 1.0

    # Absolute threshold (YIN step 4): the first local minimum below
    # YIN_THRESHOLD, else the global minimum in range as a lower-confidence
    # fallback - reporting a best guess rather than nothing.
    tau_estimate = None
    for tau in range(min_lag, max_lag + 1):
        if cmnd[tau] < YIN_THRESHOLD:
            while tau + 1 <= max_lag and cmnd[tau + 1] < cmnd[tau]:
                tau += 1
            tau_estimate = tau
            break
    if tau_estimate is None:
        tau_estimate = int(np.argmin(cmnd[min_lag: max_lag + 1])) + min_lag

    if prefer_lower_octave:
        lower_octave_tau = 2 * tau_estimate
        if lower_octave_tau <= max_lag and cmnd[lower_octave_tau] <= cmnd[tau_estimate] + OCTAVE_DOWN_CMND_SLACK:
            tau_estimate = lower_octave_tau

    # Parabolic interpolation around tau_estimate for sub-sample precision
    # (YIN step 5) - skipped at either edge of the search band, where there's
    # no neighbour on one side to interpolate against.
    if min_lag < tau_estimate < max_lag:
        s0, s1, s2 = cmnd[tau_estimate - 1], cmnd[tau_estimate], cmnd[tau_estimate + 1]
        denom = s0 - 2 * s1 + s2
        shift = 0.0 if denom == 0 else 0.5 * (s0 - s2) / denom
        refined_tau = tau_estimate + shift
    else:
        refined_tau = float(tau_estimate)

    if refined_tau <= 0:
        return None

    frequency_hz = sample_rate / refined_tau
    confidence = max(0.0, 1.0 - cmnd[tau_estimate])
    return PitchResult(frequency_hz=frequency_hz, confidence=confidence)
