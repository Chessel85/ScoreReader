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

from main_window import MainWindow
from models.music_data import MusicData
from tests.support.null_live_midi_input import NullMidiInputManager
from tests.support.null_synth import NullSynth
from tests.support.null_tuner_capture import NullTunerCapture
from tests.support.null_voice_recognizer import NullVoiceRecognizer

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
def key_change_score() -> str:
    """One part, two complete 4/4 bars: C major (M1) -> D major (M2).

    Proves a mid-score key-signature change is tracked and fires a Region 5
    one-shot alert (S7 follow-up), the same pattern ts_change_score/
    tempo_change_score already establish for time signature and tempo.
    """
    return _require(FIXTURES_DIR / "key_change.musicxml")


@pytest.fixture
def chord_score() -> str:
    """One part, one complete 4/4 bar with a two-note chord on the second beat."""
    return _require(FIXTURES_DIR / "chord.musicxml")


@pytest.fixture
def string_fret_score() -> str:
    """One part, one complete 4/4 bar of two notes carrying string/fret data."""
    return _require(FIXTURES_DIR / "string_fret.musicxml")


@pytest.fixture
def grace_note_score() -> str:
    """One complete 4/4 bar: a single acciaccatura (<grace slash="yes"/>)
    B4 leading into a quarter A4, then C4/D4/E4 filling out the bar."""
    return _require(FIXTURES_DIR / "grace_note.musicxml")


@pytest.fixture
def grace_note_group_score() -> str:
    """One complete 4/4 bar: two consecutive grace notes (B4, C5) leading
    into a half-note A4, then D4/E4 filling out the bar."""
    return _require(FIXTURES_DIR / "grace_note_group.musicxml")


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
def chords_and_lyrics_score() -> str:
    """One part, one complete 4/4 bar: an A-minor <harmony> at the start of
    the bar, "Hel"/"lo"/"there" lyrics on the first three notes, arpeggiate
    direction down/up on notes 1/2 (none on note 3), and a trailing rest
    with no lyric - the synthetic Chords/Lyrics parts fixture (Ref 30-ish,
    see CLAUDE.md's MusicXML harmony/lyric entry), modelled on the real-world
    shape of files/Three Blind Mice.mxl."""
    return _require(FIXTURES_DIR / "chords_and_lyrics.musicxml")


@pytest.fixture
def chord_and_stroke_same_note_score() -> str:
    """One part, one complete 4/4 bar: a <harmony> lands at the same beat as
    the bar's only note, which itself carries an arpeggiate mark - the
    coincidence files/Three Blind Mice.mxl's bar 4 has (see CLAUDE.md's
    "Reported, redesigned" note on the synthetic Chords/Lyrics feature)."""
    return _require(FIXTURES_DIR / "chord_and_stroke_same_note.musicxml")


@pytest.fixture
def stave_text_score() -> str:
    """Two parts, one 4/4 bar each. P1 carries every generic-stave-text case
    on its own four notes: a bare tempo word with no metronome sibling
    ("Allegro"), a qualifying position mark ("III"), a SMuFL-glyph-only
    <words> that must produce no entry, and a jump-mark word ("D.S.") that
    must also produce no entry (while still registering as its own
    NavigationJump via the existing, untouched path). P2 has real notes but
    no <direction> elements at all - the guitar-duet/flute+guitar-duet
    cross-contamination case: stave text must never leak onto it."""
    return _require(FIXTURES_DIR / "stave_text.musicxml")


@pytest.fixture
def score_three_blind_mice() -> str:
    """A real MuseScore 4.7.4 export: one Piano part (2 staves), a chord
    symbol on every bar with content, a lyric on every melody note, and
    per-note arpeggiate up/down marks on most (not all) notes - the file the
    Chords/Lyrics import feature was built against. 28 of its 32 measures
    are trailing rest-only padding (a MuseScore "more bars than the tune
    needs" export artifact, not a bug in this app)."""
    return _require(SCORES_DIR / "Three Blind Mice.mxl")


@pytest.fixture
def score_bourree_full() -> str:
    """The full (not "short") bach-bourree-tab score - two real repeat +
    1st/2nd-ending passages (measures 1-8 and 10-25, Ref 29). The MIDI import
    ground-truth cross-check (test_midi_timeline_builder.py) uses this
    specific file because files/midi/bach-bourree-tab.mid is MuseScore's own
    MIDI export of exactly this MusicXML, unchanged.

    Points at the compressed .mxl - the loose extracted META-INF/score.xml
    copy this used to point at was pruned from files/ as redundant (the
    .mxl already carries the identical content).

    Also now the fixture for what used to be the separate "short" sample
    (score_bourree, removed): "short" turned out to just be a truncated copy
    of this same piece with an identical opening - same one-beat pickup
    (measure 0, beat 4.0, notation+TAB E/E/G/G) and the same Korean
    <part-name> ("클래식 기타 ") - once its own files were pruned with no
    surviving replacement, every test that only needed those shared
    characteristics was repointed here instead of staying skipped.
    """
    return _require(SCORES_DIR / "bach-bourree-tab.mxl")


@pytest.fixture
def score_duet() -> str:
    """6/8 two-part score: Piano (GM 1, 2 staves) + Classical Guitar (GM 25).

    Pickup is exported as number="0" implicit="yes" - the convention the
    parser currently mishandles (A3).

    Same file as score_duet_mxl below - the loose extracted copy this used
    to point at independently was pruned from files/ as redundant, leaving
    the compressed .mxl as the only surviving copy of this score. Kept as
    its own fixture (rather than folding every call site over to
    score_duet_mxl) purely so test_reader_handles_compressed_mxl_the_same_
    as_the_uncompressed_score's "compare an uncompressed parse against the
    compressed one" premise stays legible even though it can now only ever
    skip (no independent uncompressed sample survives to compare against).
    """
    return _require(SCORES_DIR / "Chessel Duet.mxl")


@pytest.fixture
def score_duet_mxl() -> str:
    """The real compressed .mxl the user would actually open for this score
    - internally just META-INF/container.xml + a member named score.xml,
    same as every other real .mxl in files/, which is exactly the "every
    real file is internally called score.xml" case that per-file config
    naming (Ref 27) must key off the outer .mxl filename instead of."""
    return _require(SCORES_DIR / "Chessel Duet.mxl")


@pytest.fixture
def score_etude_1_tablature() -> str:
    """A real Carcassi guitar etude export: two real parts, "Classical
    Guitar" (standard notation) and "Guitare classique [Tablature]" (a
    linked tab staff), grouped by a part-group brace with matching
    instrument-sound but no other formal MusicXML link. From bar 29
    onwards, the notation part carries <direction><words> roman-numeral
    left-hand position marks ("III"/"V"/"VIII"/"IV") - the real file the
    generic stave-text feature (STAVE_TEXT_VOICE_ID) was built against. Also
    carries 12 <words> elements that are SMuFL Private-Use-Area glyphs
    (font-family="Leland Text", MuseScore's own redundant visual rendering
    of pluck-fingering marks already captured via NoteData.pluck) - the
    real-file exercise of the glyph-noise filter."""
    return _require(SCORES_DIR / "etude 1 tablature.mxl")


@pytest.fixture
def score_hit_it() -> str:
    """Wishlist #8: a real MuseScore percussion-clef export with TWO drum
    parts (Drum Kit + Tambourine), every note an <unpitched> with
    <instrument id> refs into each score-part's own
    <score-instrument>/<midi-instrument> children - the fixture for real
    percussion support (a percussion note used to be silently dropped
    entirely, since TimelineBuilder required a <pitch> element)."""
    return _require(SCORES_DIR / "Hit It.mxl")


@pytest.fixture
def score_long_tune() -> str:
    """4/4, one part, 130 measures, no pickup - a real score with genuine
    multi-digit measure numbers, for C4's digit-entry bar jump (Ref 6).

    Points at the compressed .mxl - the loose extracted copy this used to
    point at was pruned from files/ as redundant.
    """
    return _require(SCORES_DIR / "long tune.mxl")


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
def dc_plain_score() -> str:
    """Bare D.C. (Da Capo), no Fine/Coda - see the fixture's own doc
    comment for the expected next_playback_index step sequence."""
    return _require(FIXTURES_DIR / "dc_plain.musicxml")


@pytest.fixture
def dc_al_fine_score() -> str:
    """D.C. al Fine - see the fixture's own doc comment for the expected
    next_playback_index step sequence."""
    return _require(FIXTURES_DIR / "dc_al_fine.musicxml")


@pytest.fixture
def dc_al_coda_score() -> str:
    """D.C. al Coda - see the fixture's own doc comment for the expected
    next_playback_index step sequence."""
    return _require(FIXTURES_DIR / "dc_al_coda.musicxml")


@pytest.fixture
def dc_with_pickup_score() -> str:
    """D.C. in a piece with a pickup bar - proves the dacapo target is
    measure 0 (the pickup), not a hardcoded 1."""
    return _require(FIXTURES_DIR / "dc_with_pickup.musicxml")


@pytest.fixture
def ds_plain_score() -> str:
    """Plain D.S. (Dal Segno), segno on measure 2 - proves the jump target
    is the segno, not the piece's start."""
    return _require(FIXTURES_DIR / "ds_plain.musicxml")


@pytest.fixture
def ds_al_fine_score() -> str:
    """D.S. al Fine - see the fixture's own doc comment for the expected
    next_playback_index step sequence."""
    return _require(FIXTURES_DIR / "ds_al_fine.musicxml")


@pytest.fixture
def ds_al_coda_score() -> str:
    """D.S. al Coda - see the fixture's own doc comment for the expected
    next_playback_index step sequence."""
    return _require(FIXTURES_DIR / "ds_al_coda.musicxml")


@pytest.fixture
def multi_coda_labels_score() -> str:
    """Two codas disambiguated by <sound> label matching - proves label
    matching wins over "nearest coda after this point"."""
    return _require(FIXTURES_DIR / "multi_coda_labels.musicxml")


@pytest.fixture
def text_only_jump_marks_score() -> str:
    """D.S. al Coda with no <sound> element anywhere - exercises the
    text/glyph-only fallback parse path."""
    return _require(FIXTURES_DIR / "text_only_jump_marks.musicxml")


@pytest.fixture
def repeat_ending_then_dc_al_coda_score() -> str:
    """repeats_and_endings.musicxml's repeat/1st-2nd-ending shape followed
    by a D.C. al Coda - proves repeats/endings are not retaken on the
    D.C. pass, end-to-end."""
    return _require(FIXTURES_DIR / "repeat_ending_then_dc_al_coda.musicxml")


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

    Points at the compressed .mxl - the loose extracted copy this used to
    point at was pruned from files/ as redundant.
    """
    return _require(SCORES_DIR / "Way To Go.mxl")


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
    MIDI file with a genuine channel-10 percussion track (track index 2,
    "Low Floor Tom" among others) - the fixture for wishlist #8's percussion
    support (reported: this file's drum track used to come out as silence)."""
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


@pytest.fixture
def window(qtbot, null_synth):
    # uk_terms=False: deterministic regardless of the machine's own OS
    # locale (F4/D-6) - every existing assertion here expects US wording.
    w = MainWindow(synth=null_synth, uk_terms=False)
    qtbot.addWidget(w)
    return w


@pytest.fixture
def null_live_midi_manager() -> NullMidiInputManager:
    """Recording/injectable stand-in for audio.midi_input.MidiInputManager.
    Never touches a real MIDI device. Pass to
    MainWindow(live_midi_manager=...) for tests exercising live-MIDI-input
    behaviour."""
    return NullMidiInputManager()


@pytest.fixture
def null_voice_recognizer() -> NullVoiceRecognizer:
    """Recording/injectable stand-in for audio.voice_recognition.
    VoiceRecognitionManager. Never touches a real Vosk model or microphone.
    Pass to MainWindow(voice_control_manager=...) for tests exercising
    voice-control behaviour."""
    return NullVoiceRecognizer()


@pytest.fixture
def null_tuner_capture() -> NullTunerCapture:
    """Recording/injectable stand-in for audio.tuner_capture.TunerCapture.
    Never touches a real microphone. Pass to MainWindow(tuner_manager=...)
    for tests exercising Tools > Tuner behaviour."""
    return NullTunerCapture()


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


@pytest.fixture(autouse=True)
def _forbid_real_midi_input(monkeypatch):
    """Fail loudly if any test opens a real MIDI input device or enumerates
    real ports - the live-MIDI-input counterpart of _forbid_real_audio
    above. A test that needs this behaviour should inject a
    NullMidiInputManager (the null_live_midi_manager fixture) via
    MainWindow(live_midi_manager=...) instead.

    Belt-and-braces alongside that injectable stand-in: a test could still
    construct MainWindow(synth=null_synth) without ever passing
    live_midi_manager=, which would otherwise fall through to a real
    MidiInputManager()."""
    from audio import midi_input

    def _blocked_open(self, device_name):
        raise AssertionError(
            "This test tried to open a real MIDI input device. Inject a "
            "NullMidiInputManager instead - see "
            "tests/support/null_live_midi_input.py."
        )

    def _blocked_list_ports():
        raise AssertionError("This test tried to enumerate real MIDI input ports.")

    monkeypatch.setattr(midi_input.MidiInputManager, "open", _blocked_open)
    monkeypatch.setattr(midi_input, "list_input_ports", _blocked_list_ports)


@pytest.fixture(autouse=True)
def _forbid_real_voice_recognition(monkeypatch):
    """Fail loudly if any test starts a real Vosk recognizer/microphone
    capture or enumerates real audio input devices - the voice-control
    counterpart of _forbid_real_midi_input above. A test that needs this
    behaviour should inject a NullVoiceRecognizer (the null_voice_recognizer
    fixture) via MainWindow(voice_control_manager=...) instead.

    Belt-and-braces alongside that injectable stand-in: a test could still
    construct MainWindow(synth=null_synth) without ever passing
    voice_control_manager=, which would otherwise fall through to a real
    VoiceRecognitionManager()."""
    from audio import voice_recognition

    def _blocked_start(self, device_name, confidence_threshold):
        raise AssertionError(
            "This test tried to start a real Vosk voice recognizer. Inject a "
            "NullVoiceRecognizer instead - see "
            "tests/support/null_voice_recognizer.py."
        )

    def _blocked_list_devices():
        raise AssertionError("This test tried to enumerate real voice control input devices.")

    monkeypatch.setattr(voice_recognition.VoiceRecognitionManager, "start", _blocked_start)
    monkeypatch.setattr(voice_recognition, "list_input_devices", _blocked_list_devices)


@pytest.fixture(autouse=True)
def _forbid_real_tuner_capture(monkeypatch):
    """Fail loudly if any test opens a real tuner audio input stream or
    enumerates real audio input devices - the Tools > Tuner counterpart of
    _forbid_real_midi_input/_forbid_real_voice_recognition above. A test
    that needs this behaviour should inject a NullTunerCapture (the
    null_tuner_capture fixture) via MainWindow(tuner_manager=...) instead.

    Belt-and-braces alongside that injectable stand-in: a test could still
    construct MainWindow(synth=null_synth) without ever passing
    tuner_manager=, which would otherwise fall through to a real
    TunerCapture()."""
    from audio import tuner_capture

    def _blocked_open(self, device_name):
        raise AssertionError(
            "This test tried to open a real tuner audio input device. "
            "Inject a NullTunerCapture instead - see "
            "tests/support/null_tuner_capture.py."
        )

    def _blocked_list_devices():
        raise AssertionError("This test tried to enumerate real tuner audio input devices.")

    monkeypatch.setattr(tuner_capture.TunerCapture, "open", _blocked_open)
    monkeypatch.setattr(tuner_capture, "list_input_devices", _blocked_list_devices)
