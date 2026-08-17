# tests/parsers/test_midi_reader.py
from parsers.midi_reader import MidiReader
from parsers.midi_source import MidiNoteEvent, MidiSource, MidiTrackData


def test_load_returns_music_data_with_parts_info(midi_test2):
    data = MidiReader(midi_test2).load()
    assert [p.name for p in data.parts_info] == ["Piano", "Bass", "Cool Violin"]
    assert [p.part_id for p in data.parts_info] == ["P0", "P1", "P2"]


def test_gmidi_program_is_1_indexed_in_the_model(midi_bach_bourree):
    """The file's MIDI program is 24 (0-indexed, nylon guitar) - the model
    convention used throughout this app is 1-indexed, same as a MusicXML
    <midi-program> value."""
    data = MidiReader(midi_bach_bourree).load()
    assert data.parts_info[0].gmidi_program == 25


def test_title_falls_back_to_filename_stem(midi_test1):
    data = MidiReader(midi_test1).load()
    assert data.credits["Title"] == "test1"


def test_untitled_track_falls_back_to_track_number(midi_test1):
    data = MidiReader(midi_test1).load()
    assert data.parts_info[0].name == "Track 1"


def test_tempo_bpm_from_first_tempo_event(midi_test2):
    data = MidiReader(midi_test2).load()
    assert data.tempo_bpm == 120
    assert data.tempo_beat_unit_quarter_length == 1.0
    assert data.tempo_beat_unit_name == "quarter"


def test_no_tempo_event_falls_back_to_120(midi_test1):
    data = MidiReader(midi_test1).load()
    assert data.tempo_bpm == 120


def test_credits_time_signature_is_the_governing_one_not_the_pickup_artifact(midi_bach_bourree):
    """bach-bourree-tab.mid's own first declared time signature is a fake
    1/4 span sized just for the pickup bar (see midi_timeline_builder's
    _detect_pickup) - Region 1 should show the piece's real 4/4, matching
    what a MusicXML load of the same piece shows, not the exporter
    artifact."""
    data = MidiReader(midi_bach_bourree).load()
    assert data.credits["Time Signature"] == "4/4"


def test_credits_key_signature(midi_pachelbel):
    data = MidiReader(midi_pachelbel).load()
    assert data.credits["Key Signature"] == "D major / B minor"


def test_percussion_track_included_as_a_percussion_part(midi_blue_peter):
    """Wishlist #8: BluePeter.mid's drum track (reported: came out as
    silence) now appears as its own part, flagged is_percussion=True so
    playback routes it to the GM percussion bank instead of reading its
    (meaningless) gmidi_program."""
    data = MidiReader(midi_blue_peter).load()
    assert len(data.parts_info) == 9
    # GM program 72 (0-indexed 71) = Clarinet, the first real track.
    assert data.parts_info[0].gmidi_program == 72
    assert data.parts_info[0].is_percussion is False
    percussion_parts = [p for p in data.parts_info if p.is_percussion]
    assert len(percussion_parts) == 1
    assert percussion_parts[0].name == "Drum Kit"


def test_staves_voices_shape_matches_channel_count(midi_bach_bourree):
    """A single-channel track gets exactly one voice, numbered 1 - matching
    what Region2HierarchyModel.get_score_structure expects."""
    data = MidiReader(midi_bach_bourree).load()
    assert data.parts_info[0].staves_voices == {1: [1]}


def _synthetic_source(name, program) -> MidiSource:
    """One usable track, one note, an optional track name and/or a Program
    Change - for exercising _build_parts_info's name fallback without a
    real file (S5's BluePeter.mid quick win: an unnamed track with a
    Program Change suggests the GM instrument name instead of a bare
    "Track N")."""
    events = [MidiNoteEvent(channel=0, pitch=60, velocity=80, start_tick=0, end_tick=480)]
    programs = {0: [(0, program)]} if program is not None else {}
    track = MidiTrackData(
        track_index=0, part_id="P0", name=name, note_events=events,
        program_changes=programs, channels_used=[0],
    )
    return MidiSource(format=0, division=480, time_signature_changes=[(0, 4, 4)], tracks=[track])


def test_untitled_track_with_a_program_change_suggests_the_gm_instrument_name():
    reader = MidiReader("x.mid")
    parts = reader._build_parts_info(_synthetic_source(name=None, program=71))  # 0-indexed Clarinet

    assert parts[0].name == "Clarinet"


def test_untitled_track_with_no_program_change_still_falls_back_to_track_number():
    reader = MidiReader("x.mid")
    parts = reader._build_parts_info(_synthetic_source(name=None, program=None))

    assert parts[0].name == "Track 1"


def test_a_real_track_name_is_never_overridden_by_a_program_change_suggestion():
    reader = MidiReader("x.mid")
    parts = reader._build_parts_info(_synthetic_source(name="Track1", program=71))

    assert parts[0].name == "Track1"
