# tests/test_harness.py
"""Guards on the test harness itself, and on the layering it depends on.

If these fail, later test results cannot be trusted: something is opening
a real window or real audio hardware, or the model layer has quietly grown
a Qt dependency.
"""
import subprocess
import sys
from pathlib import Path

import pytest

from audio.synth_engine import SynthEngine

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_qt_runs_offscreen(qapp):
    """No window should ever appear during a test run."""
    assert qapp.platformName() == "offscreen"


def test_constructing_a_real_synth_engine_is_blocked():
    """The autouse guard in conftest must stop accidental audio access."""
    with pytest.raises(AssertionError, match="real SynthEngine"):
        SynthEngine()


def test_models_package_does_not_import_qt():
    """R2: "models/ stays Qt-free" is a stated invariant, not just a
    preference - main_window.detect_default_uk_terms() lives in the UI layer
    specifically because it needs QLocale. It had already been broken
    transitively: MusicData imported ScoreConfig, which lived beside
    persistence/score_config.py's QStandardPaths use, so importing anything
    from models/ loaded the whole of Qt. The data shape now lives in
    models/score_config_data.py and persistence keeps the I/O.

    Runs in a subprocess because this test session has PySide6 loaded
    already (conftest imports it before anything else) - sys.modules in-
    process can't tell who imported it. Imports every models/ module, not
    just music_data, so a future Qt import anywhere in the package is
    caught."""
    script = (
        "import importlib, pkgutil, sys\n"
        "import models\n"
        "for m in pkgutil.iter_modules(models.__path__):\n"
        "    importlib.import_module(f'models.{m.name}')\n"
        "qt = sorted(n for n in sys.modules if n.startswith('PySide6'))\n"
        "print(','.join(qt))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr
    leaked = result.stdout.strip()
    assert leaked == "", f"models/ imported Qt: {leaked}"
