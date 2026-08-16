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
MIDI_DIR = PROJECT_ROOT / "files" / "midi"
GP_DIR = PROJECT_ROOT / "files" / "GP"


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
def tempo_change_score() -> str:
    """One part, two complete 4/4 bars: quarter=100 (M1) -> quarter=200 (M2).

    Proves every tempo marking is tracked as the score plays through it,
    not just the first (Ref 12 "multi-tempo scope").
    """
    return _require(FIXTURES_DIR / "tempo_change.musicxml")


@pytest.fixture
def chord_score() -> str:
    """One part, one complete 4/4 bar with a two-note chord on the second beat."""
    return _require(FIXTURES_DIR / "chord.musicxml")


@pytest.fixture
def string_fret_score() -> str:
    """One part, one complete 4/4 bar of two notes carrying string/fret data."""
    return _require(FIXTURES_DIR / "string_fret.musicxml")


@pytest.fixture
def dynamics_articulation_fingering_score() -> str:
    """Piano (2 staves) + Guitar (1 staff), one complete 4/4 bar each: a
    forte direction before a two-note chord, staccato and trill on separate
    notes, piano fingering on both staves, and a guitar note carrying both
    left-hand fingering and right-hand pluck (F3/Ref 16 AC3)."""
    return _require(FIXTURES_DIR / "dynamics_articulation_fingering.musicxml")


@pytest.fixture
def multi_value_technical_score() -> str:
    """One guitar note carrying two <fingering> and three <pluck> marks in
    one notations/technical block (F3/Ref 16 AC3 regression - a naive
    .find() would silently drop everything after the first match)."""
    return _require(FIXTURES_DIR / "multi_value_technical.musicxml")


@pytest.fixture
def two_parts_chord_score() -> str:
    """Two parts, one complete 4/4 bar each: Piano C4 and Guitar E3 land on
    the same beat, so they bucket into a single EventSlice (A8, Ref 8)."""
    return _require(FIXTURES_DIR / "two_parts_chord.musicxml")


@pytest.fixture
def flute_crotchets_viola_semibreves_score() -> str:
    """Two complete 4/4 bars: Flute plays four crotchets per bar, Viola one
    semibreve per bar on beat 1 (same offset as the flute's first crotchet
    each bar, so they bucket into one EventSlice there)."""
    return _require(FIXTURES_DIR / "flute_crotchets_viola_semibreves.musicxml")


@pytest.fixture
def staggered_two_part_entry_score() -> str:
    """One 4/4 bar: Viola (P1) plays two half notes filling the bar; Violin I
    (P2) is silent on beat 1 and enters with a quarter note on beat 2 only -
    a later part's new attack, on its own EventSlice, while an earlier
    part's longer note from a previous EventSlice is still mid-ring."""
    return _require(FIXTURES_DIR / "staggered_two_part_entry.musicxml")


@pytest.fixture
def many_measures_score() -> str:
    """One part, twelve complete 1/4 bars, one quarter note each.

    Gives digit-entry bar jump (C4, Ref 6) a real multi-digit measure number
    (12) to target, without needing the user-provided 'Long tune' score.
    """
    return _require(FIXTURES_DIR / "many_measures.musicxml")


@pytest.fixture
def sparse_beat_score() -> str:
    """One part, two 4/4 bars: measure 1 is complete (C D E F, so pickup
    detection does not fire); measure 2 is a single quarter note G on beat
    1 then a <forward> skipping the rest of the bar - beats 2/3/4 of
    measure 2 are a genuine gap (no event, no note duration covering
    them), the case E9's synthetic beat markers exist for (Ref 14 AC4)."""
    return _require(FIXTURES_DIR / "sparse_beat.musicxml")


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
def score_bourree_full() -> str:
    """The full (not "short") bach-bourree-tab score - two real repeat +
    1st/2nd-ending passages (measures 1-8 and 10-25, Ref 29). The MIDI import
    ground-truth cross-check (test_midi_timeline_builder.py) uses this
    specific file because files/midi/bach-bourree-tab.mid is MuseScore's own
    MIDI export of exactly this MusicXML, unchanged.
    """
    return _require(SCORES_DIR / "bach-bourree-tab" / "score.xml")


@pytest.fixture
def score_duet() -> str:
    """6/8 two-part score: Piano (GM 1, 2 staves) + Classical Guitar (GM 25).

    Pickup is exported as number="0" implicit="yes" - the convention the
    parser currently mishandles (A3).
    """
    return _require(SCORES_DIR / "Chessel Duet" / "score.xml")


@pytest.fixture
def score_duet_mxl() -> str:
    """The same score as score_duet, but the real compressed .mxl the user
    would actually open - internally just META-INF/container.xml + a member
    named score.xml, same as every other real .mxl in files/, which is
    exactly the "every real file is internally called score.xml" case that
    per-file config naming (Ref 27) must key off the outer .mxl filename
    instead of."""
    return _require(SCORES_DIR / "Chessel Duet.mxl")


@pytest.fixture
def score_long_tune() -> str:
    """4/4, one part, 130 measures, no pickup - a real score with genuine
    multi-digit measure numbers, for C4's digit-entry bar jump (Ref 6).
    """
    return _require(SCORES_DIR / "long tune" / "score.xml")


@pytest.fixture
def repeats_and_endings_score() -> str:
    """Ref 29: one part, 4 complete 4/4 bars reproducing the real
    files/bach-bourree-tab/score.xml fixture's repeat/ending barline shape
    at small scale - forward repeat (m2), 1st ending + backward repeat
    (m3), 2nd ending with no trailing repeat (m4)."""
    return _require(FIXTURES_DIR / "repeats_and_endings.musicxml")


@pytest.fixture
def unmatched_backward_repeat_score() -> str:
    """Ref 29: one part, 2 complete 4/4 bars - a backward repeat with no
    preceding forward repeat, exercising the "default start to measure 1"
    fallback neither real fixture exercises."""
    return _require(FIXTURES_DIR / "unmatched_backward_repeat.musicxml")


@pytest.fixture
def hairpin_score() -> str:
    """Ref 29: one part, 3 complete 4/4 bars of quarter notes - a crescendo
    spanning a measure boundary (m1 beat 3 -> m2 beat 2) and a diminuendo
    fully contained within one measure (m3 beat 1 -> m3 beat 3)."""
    return _require(FIXTURES_DIR / "hairpin.musicxml")


@pytest.fixture
def score_way_to_go() -> str:
    """4/4 two-part score: Flute (GM 74) + Viola (GM 42), no pickup.

    Time signature changes 4/4 -> 3/4 -> 4/4 and key signature changes
    mid-piece. The parser currently reads both from the first match only
    (A6), so this is the fixture that exercises the bug.
    """
    return _require(SCORES_DIR / "Way To Go" / "score.xml")


@pytest.fixture
def midi_test1() -> str:
    """Format 0, single track, no track name/program change/other meta data
    at all - the bare-minimum baseline (files/midi/readme.md.txt)."""
    return _require(MIDI_DIR / "test1.MID")


@pytest.fixture
def midi_test2() -> str:
    """Format 1, 4 tracks (1 empty conductor track + Piano/Bass/Cool Violin),
    starts 120bpm/4/4 and changes at bar 9 to 80bpm/3/4 - exercises a
    mid-piece time signature AND tempo change together, no pickup."""
    return _require(MIDI_DIR / "test2.mid")


@pytest.fixture
def midi_test3() -> str:
    """Format 0, single track, hand-recorded freehand (NOT quantized) - real
    positions land anywhere, real durations are any length. The fixture for
    S3's per-track "too many weird duration names" fallback
    (files/midi/readme.md.txt)."""
    return _require(MIDI_DIR / "test3.MID")


@pytest.fixture
def midi_bach_bourree() -> str:
    """MuseScore's own MIDI export of files/bach-bourree-tab/score.xml,
    unchanged - lets a test diff the MIDI-derived timeline against the
    already-correct MusicXML one. The pickup is encoded as a real, short
    (1/4) time-signature span for bar 1 only, not an implicit="yes" flag -
    MidiTimelineBuilder._detect_pickup's MIDI-native signal. Repeats are
    realised (played out in full) in the MIDI export, unlike the MusicXML's
    repeat barlines, so only the measures before the first repeat (0-8) are
    expected to match the MusicXML note-for-note; diverges from there on by
    design, not by bug.
    """
    return _require(MIDI_DIR / "bach-bourree-tab.mid")


@pytest.fixture
def midi_pachelbel() -> str:
    """MuseScore's MIDI export of Pachelbel's Canon (string quartet + piano),
    unrelated to any MusicXML fixture in this repo. 6 tracks, no pickup, a
    real mid-piece tempo dip (70 -> 35 -> 70 bpm) and D major key signature -
    exercises multi-part GM program assignment at scale (990 notes on the
    busiest track) without an implicit="yes"-flagged pickup to trip the
    detector."""
    return _require(MIDI_DIR / "pachelbels-canon-in-d-string-quartet.mid")


@pytest.fixture
def midi_blue_peter() -> str:
    """A 9-usable-track (10 raw tracks: one empty conductor track) real-world
    MIDI file with a genuine channel-10 percussion track (track index 2) -
    the fixture for "percussion is skipped cleanly, not misread as
    pitches"."""
    return _require(MIDI_DIR / "BluePeter.mid")


@pytest.fixture
def gp_ripple() -> str:
    """Guitar Pro 8 (internally GPVersion 8.1.3; the container/schema is
    shared with GP7 - see CLAUDE.md), 4 tracks (Acoustic Lead, Acoustic Capo
    VII, Electric Bass (finger), Mandolin), 102 measures, all 4/4. Tracks 0
    and 1 carry real chord-name (C/F/G/Dm/G7 on track 1) and/or strum-
    direction annotations - the fixture for the synthetic "Chords" voice;
    tracks 2/3 (bass/mandolin) carry neither and must get no synthetic voice
    at all, confirmed by ear against the real recording (mandolin plays
    tremolo, not strums) during the GP import discovery pass."""
    return _require(GP_DIR / "Grateful Dead-Ripple-12-20-2025.gp")


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
def _isolate_persistence(monkeypatch, tmp_path):
    """Phase G: redirects app_settings/score_config's on-disk locations into
    a per-test tmp_path, the same reasoning as MainWindow's uk_terms
    constructor override (D-7) - without this, tests would read and write
    the real developer machine's %LOCALAPPDATA%\\Recall Score\\ folder,
    both polluting real user data and making test behaviour depend on
    whatever that machine's settings.json/*.rsc files already contain."""
    from persistence import app_settings, score_config

    monkeypatch.setattr(app_settings, "settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(score_config, "config_dir", lambda: tmp_path / "scores")


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
