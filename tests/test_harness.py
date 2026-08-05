# tests/test_harness.py
"""Guards on the test harness itself.

If these fail, later test results cannot be trusted: something is opening
a real window or real audio hardware.
"""
import pytest

from audio.synth_engine import SynthEngine


def test_qt_runs_offscreen(qapp):
    """No window should ever appear during a test run."""
    assert qapp.platformName() == "offscreen"


def test_constructing_a_real_synth_engine_is_blocked():
    """The autouse guard in conftest must stop accidental audio access."""
    with pytest.raises(AssertionError, match="real SynthEngine"):
        SynthEngine()
