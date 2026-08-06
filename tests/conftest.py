# tests/conftest.py
"""Shared fixtures.

Two rules this file exists to enforce:

1. No window ever opens. QT_QPA_PLATFORM is forced to "offscreen" before
   PySide6 is imported by any test.
2. No audio device is ever opened. Tests construct MainWindow with a
   NullSynth (see D-7 in tasks.txt); the real SynthEngine starts WASAPI.
"""
import os

# Must run before anything imports PySide6.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest

from models.music_data import MusicData
from tests.support.null_synth import NullSynth

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCORES_DIR = PROJECT_ROOT / "files"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _require(path: Path) -> str:
    if not path.exists():
        pytest.skip(f"sample score not found: {path}")
    return str(path)


@pytest.fixture
def minimal_score() -> str:
    """One part, one full 4/4 bar, four quarter notes C D E F.

    Hand-written so each test can isolate a single behaviour. Deliberately
    a complete bar so pickup detection does not fire.
    """
    return _require(FIXTURES_DIR / "minimal_4_4.musicxml")


@pytest.fixture
def six_eight_score() -> str:
    """One part, one complete 6/8 bar: quarter C, quarter D, eighth E, eighth F."""
    return _require(FIXTURES_DIR / "six_eight.musicxml")


@pytest.fixture
def rest_score() -> str:
    """One part, one complete 4/4 bar: quarter C, quarter rest, quarter E, F.

    The rest is explicit (<note><rest/></note>) - it must become its own
    timeline event between C and E (A5, Ref 16 AC2).
    """
    return _require(FIXTURES_DIR / "rest.musicxml")


@pytest.fixture
def ts_change_score() -> str:
    """One part, three complete bars: 4/4 (div=4) -> 6/8 (div=4) -> 4/4 (div=8).

    Proves divisions and time signature are tracked as they change through
    the score rather than read once from the first match (A6, Ref 18).
    """
    return _require(FIXTURES_DIR / "ts_change.musicxml")


@pytest.fixture
def chord_score() -> str:
    """One part, one complete 4/4 bar with a two-note chord on the second beat."""
    return _require(FIXTURES_DIR / "chord.musicxml")


@pytest.fixture
def string_fret_score() -> str:
    """One part, one complete 4/4 bar of two notes carrying string/fret data."""
    return _require(FIXTURES_DIR / "string_fret.musicxml")


@pytest.fixture
def two_parts_chord_score() -> str:
    """Two parts, one complete 4/4 bar each: Piano C4 and Guitar E3 land on
    the same beat, so they bucket into a single EventSlice (A8, Ref 8)."""
    return _require(FIXTURES_DIR / "two_parts_chord.musicxml")


@pytest.fixture
def slice_ordering_score() -> str:
    """One complete 4/4 bar written out of offset order via forward/backup."""
    return _require(FIXTURES_DIR / "slice_ordering.musicxml")


@pytest.fixture
def score_bourree() -> str:
    """4/4 guitar score: notation staff plus a TAB staff duplicating it.

    Pickup is exported as number="1", so measure re-indexing applies.
    """
    return _require(SCORES_DIR / "bach-bourree-tab short" / "score.xml")


@pytest.fixture
def score_duet() -> str:
    """6/8 two-part score: Piano (GM 1, 2 staves) + Classical Guitar (GM 25).

    Pickup is exported as number="0" implicit="yes" - the convention the
    parser currently mishandles (A3).
    """
    return _require(SCORES_DIR / "Chessel Duet" / "score.xml")


@pytest.fixture
def score_way_to_go() -> str:
    """4/4 two-part score: Flute (GM 74) + Viola (GM 42), no pickup.

    Time signature changes 4/4 -> 3/4 -> 4/4 and key signature changes
    mid-piece. The parser currently reads both from the first match only
    (A6), so this is the fixture that exercises the bug.
    """
    return _require(SCORES_DIR / "Way To Go" / "score.xml")


@pytest.fixture
def timeline():
    """Build a MusicData timeline straight from a path, skipping music21.

    MusicData.__post_init__ walks the XML with ElementTree only (~1ms).
    Going through MusicXMLReader.load() would also run music21 (~460ms),
    which timeline tests do not need. Use the reader only when testing
    header metadata - and mark those tests `slow`.
    """
    def _build(path: str, **kwargs) -> MusicData:
        return MusicData(file_path=str(path), **kwargs)

    return _build


@pytest.fixture
def null_synth() -> NullSynth:
    """Recording stand-in for SynthEngine. Never touches audio hardware."""
    return NullSynth()


@pytest.fixture(autouse=True)
def _forbid_real_audio(monkeypatch):
    """Fail loudly if any test constructs a real SynthEngine (D-7).

    Opening WASAPI inside a test suite is slow, audible, and fails outright
    on a machine without the FluidSynth DLLs. Importing the module is fine -
    that only resolves DLLs; it is starting the engine that we block.
    """
    from audio import synth_engine

    def _blocked(self, soundfont_path=None):
        raise AssertionError(
            "This test constructed a real SynthEngine. Inject a stand-in "
            "instead, e.g. MainWindow(synth=null_synth). See D-7 in tasks.txt."
        )

    monkeypatch.setattr(synth_engine.SynthEngine, "_init_engine", _blocked)
