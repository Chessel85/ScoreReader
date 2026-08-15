# tests/parsers/test_midi_source.py
from parsers.midi_source import PERCUSSION_CHANNEL, read_midi_source


def test_reads_format_and_division(midi_test1):
    source = read_midi_source(midi_test1)
    assert source.format == 0
    assert source.division == 960


def test_no_meta_events_falls_back_to_4_4(midi_test1):
    """test1.MID has no time-signature meta event at all - the header parser
    must still hand back a usable default rather than an empty list, so
    every downstream consumer can assume time_signature_changes[0] exists."""
    source = read_midi_source(midi_test1)
    assert source.time_signature_changes == [(0, 4, 4)]
    assert source.key_signature_changes == []
    assert source.tempo_changes == []


def test_mid_piece_time_signature_and_tempo_change(midi_test2):
    source = read_midi_source(midi_test2)
    assert source.time_signature_changes == [(0, 4, 4), (30720, 3, 4)]
    assert source.tempo_changes == [(0, 500000), (30720, 750000)]


def test_conductor_only_track_excluded(midi_test2):
    """test2.mid's track 0 ("Recall Midi 1") carries only meta events, no
    notes - it must not become a zero-note "part"."""
    source = read_midi_source(midi_test2)
    assert all(t.note_events for t in source.tracks)
    assert [t.name for t in source.tracks] == ["Piano", "Bass", "Cool Violin"]


def test_part_ids_assigned_in_order_over_usable_tracks_only(midi_test2):
    source = read_midi_source(midi_test2)
    assert [t.part_id for t in source.tracks] == ["P0", "P1", "P2"]


def test_percussion_channel_excluded_entirely(midi_blue_peter):
    """BluePeter.mid has a real channel-10 (0-indexed 9) percussion track -
    it must not appear as a usable track, and no surviving track's note
    events may use that channel."""
    source = read_midi_source(midi_blue_peter)
    for track in source.tracks:
        assert PERCUSSION_CHANNEL not in track.channels_used
        assert all(ev.channel != PERCUSSION_CHANNEL for ev in track.note_events)
    # 10 raw tracks: 1 empty conductor track + 1 pure-percussion track
    # excluded, 8 real instrument tracks remain.
    assert len(source.tracks) == 8


def test_note_on_note_off_pairs_produce_positive_duration_events(midi_bach_bourree):
    source = read_midi_source(midi_bach_bourree)
    assert source.tracks
    for track in source.tracks:
        for ev in track.note_events:
            assert ev.end_tick >= ev.start_tick


def test_program_change_recorded_per_channel(midi_bach_bourree):
    source = read_midi_source(midi_bach_bourree)
    track = source.tracks[0]
    assert track.program_changes[0][0] == (0, 24)  # nylon guitar, GM program 25 (0-indexed 24)


def test_bach_bourree_pickup_is_a_real_short_time_signature_span(midi_bach_bourree):
    """Confirms the MIDI-native pickup signal this project's importer relies
    on actually exists in a real MuseScore export: a genuinely short 1/4 span
    for bar 1 that reverts to the piece's real 4/4 at bar 2 - not an
    implicit="yes" flag, which MIDI has no equivalent of."""
    source = read_midi_source(midi_bach_bourree)
    assert source.time_signature_changes[0] == (0, 1, 4)
    assert source.time_signature_changes[1][1:] == (4, 4)
