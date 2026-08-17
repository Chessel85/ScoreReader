# parsers/midi_source.py
"""Raw Standard MIDI File parsing: header + track chunks, delta-times
resolved to absolute ticks, running status resolved. A hand-rolled binary
walk (no mido - see CLAUDE.md) mirroring xml_source.py's role for the
MusicXML path: the one place a MIDI file becomes a typed intermediate
structure, so MidiReader and MidiTimelineBuilder both read the SAME parse
rather than each re-walking the bytes and risking drift (the exact bug class
noted in CLAUDE.md's TimelineBuilder._part_names comment)."""
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

PERCUSSION_CHANNEL = 9  # 0-indexed MIDI channel 10, General MIDI convention


@dataclass
class MidiNoteEvent:
    channel: int
    pitch: int
    velocity: int
    start_tick: int
    end_tick: int


@dataclass
class MidiTrackData:
    track_index: int
    part_id: str
    name: Optional[str]
    note_events: List[MidiNoteEvent] = field(default_factory=list)
    # channel -> sorted [(tick, program), ...], so a note can look up
    # whichever program was actually in force on its own channel at its own
    # start tick - Program Change can occur anywhere in a track, not just at
    # the start (confirmed against pachelbels-canon-in-d-string-quartet.mid,
    # whose string parts each multiplex 3 channels on one track).
    program_changes: Dict[int, List[Tuple[int, int]]] = field(default_factory=dict)
    # Sorted, stable ordering of the channels this track actually uses (after
    # percussion channel exclusion) - MidiTimelineBuilder maps these to
    # NoteData.voice numbers (1-indexed) so layered/multi-channel tracks like
    # pachelbels' fall out of Region 2's existing part/staff/voice filter for
    # free, with no new UI concept needed.
    channels_used: List[int] = field(default_factory=list)


@dataclass
class MidiSource:
    format: int
    division: int
    # (tick, numerator, denominator), sorted, deduped, always has a tick=0
    # entry (defaulting to 4/4 if the file never says otherwise - same
    # default TimelineBuilder uses for MusicXML).
    time_signature_changes: List[Tuple[int, int, int]] = field(default_factory=list)
    # (tick, sharps) - sharps positive/negative per the MusicXML fifths
    # convention (models.key_signatures.FIFTHS_MAP), so the same map serves
    # both readers.
    key_signature_changes: List[Tuple[int, int]] = field(default_factory=list)
    # (tick, microseconds_per_quarter_note)
    tempo_changes: List[Tuple[int, int]] = field(default_factory=list)
    # Usable note-carrying tracks only - conductor-only (zero notes) tracks
    # already excluded (percussion tracks are included, wishlist #8), part_id
    # assigned in file order over exactly this filtered list so MidiReader
    # and MidiTimelineBuilder agree on numbering without cross-talk.
    tracks: List[MidiTrackData] = field(default_factory=list)


def _read_vlq(data: bytes, i: int) -> Tuple[int, int]:
    value = 0
    while True:
        b = data[i]
        i += 1
        value = (value << 7) | (b & 0x7F)
        if not (b & 0x80):
            break
    return value, i


def _parse_track(data: bytes, start: int, length: int, track_index: int) -> Tuple[
    Optional[str],
    List[Tuple[int, int, int, int]],  # (tick, channel, pitch, velocity) note-on
    List[Tuple[int, int, int]],  # (tick, channel, pitch) note-off
    Dict[int, List[Tuple[int, int]]],  # channel -> [(tick, program), ...]
    List[Tuple[int, int, int]],  # (tick, num, den) time signature
    List[Tuple[int, int]],  # (tick, sharps)
    List[Tuple[int, int]],  # (tick, microseconds per quarter)
]:
    end = start + length
    i = start
    tick = 0
    running_status: Optional[int] = None
    track_name: Optional[str] = None
    note_ons: List[Tuple[int, int, int, int]] = []
    note_offs: List[Tuple[int, int, int]] = []
    programs: Dict[int, List[Tuple[int, int]]] = {}
    time_sigs: List[Tuple[int, int, int]] = []
    key_sigs: List[Tuple[int, int]] = []
    tempos: List[Tuple[int, int]] = []

    while i < end:
        delta, i = _read_vlq(data, i)
        tick += delta
        status = data[i]
        if status < 0x80:
            # Running status: this byte is actually the first data byte.
            status = running_status
        else:
            i += 1
            if status < 0xF0:
                running_status = status

        if status == 0xFF:
            mtype = data[i]
            i += 1
            mlen, i = _read_vlq(data, i)
            payload = data[i:i + mlen]
            i += mlen
            if mtype == 0x03 and track_name is None:
                track_name = payload.decode("utf-8", errors="replace").strip() or None
            elif mtype == 0x51 and mlen >= 3:
                tempos.append((tick, int.from_bytes(payload[:3], "big")))
            elif mtype == 0x58 and mlen >= 2:
                time_sigs.append((tick, payload[0], 2 ** payload[1]))
            elif mtype == 0x59 and mlen >= 2:
                sharps = payload[0] - 256 if payload[0] > 127 else payload[0]
                key_sigs.append((tick, sharps))
        elif status in (0xF0, 0xF7):
            mlen, i = _read_vlq(data, i)
            i += mlen
        elif 0xC0 <= status <= 0xCF:
            channel = status & 0x0F
            program = data[i]
            i += 1
            programs.setdefault(channel, []).append((tick, program))
        elif 0xD0 <= status <= 0xDF:
            i += 1
        elif 0x80 <= status <= 0xEF:
            channel = status & 0x0F
            d1, d2 = data[i], data[i + 1]
            i += 2
            if 0x90 <= status <= 0x9F:
                if d2 > 0:
                    note_ons.append((tick, channel, d1, d2))
                else:
                    note_offs.append((tick, channel, d1))
            elif 0x80 <= status <= 0x8F:
                note_offs.append((tick, channel, d1))
            # 0xA0-0xAF poly pressure, 0xB0-0xBF control change, 0xE0-0xEF
            # pitch bend - two data bytes already consumed above, nothing
            # else read from them.
        else:
            raise ValueError(f"Unrecognised MIDI status byte {status:#x} in track {track_index}")

    return track_name, note_ons, note_offs, programs, time_sigs, key_sigs, tempos


def read_midi_source(file_path: str) -> MidiSource:
    with open(file_path, "rb") as f:
        data = f.read()

    if data[0:4] != b"MThd":
        raise ValueError("Not a Standard MIDI File (missing MThd header)")
    header_len, fmt, ntracks, division = struct.unpack(">IHHH", data[4:14])
    if division & 0x8000:
        raise ValueError("SMPTE time-code division is not supported")

    pos = 14 + (header_len - 6)
    all_time_sigs: List[Tuple[int, int, int]] = []
    all_key_sigs: List[Tuple[int, int]] = []
    all_tempos: List[Tuple[int, int]] = []
    raw_tracks: List[Tuple[int, Optional[str], list, list, Dict[int, List[Tuple[int, int]]]]] = []

    for track_index in range(ntracks):
        if data[pos:pos + 4] != b"MTrk":
            raise ValueError(f"Expected MTrk chunk at track {track_index}, found {data[pos:pos + 4]!r}")
        (tlen,) = struct.unpack(">I", data[pos + 4:pos + 8])
        track_start = pos + 8
        name, note_ons, note_offs, programs, time_sigs, key_sigs, tempos = _parse_track(
            data, track_start, tlen, track_index
        )
        all_time_sigs.extend(time_sigs)
        all_key_sigs.extend(key_sigs)
        all_tempos.extend(tempos)
        raw_tracks.append((track_index, name, note_ons, note_offs, programs))
        pos = track_start + tlen

    time_signature_changes = sorted(set(all_time_sigs), key=lambda t: t[0])
    if not time_signature_changes or time_signature_changes[0][0] != 0:
        time_signature_changes.insert(0, (0, 4, 4))
    key_signature_changes = sorted(set(all_key_sigs), key=lambda t: t[0])
    tempo_changes = sorted(set(all_tempos), key=lambda t: t[0])

    tracks: List[MidiTrackData] = []
    for track_index, name, note_ons, note_offs, programs in raw_tracks:
        # Match each note-on to the next note-off (or same-pitch retrigger)
        # on the same (channel, pitch) - a FIFO queue per pair handles the
        # rare case of overlapping same-pitch retriggers in performance
        # order.
        pending: Dict[Tuple[int, int], List[int]] = {}
        offs_by_key: Dict[Tuple[int, int], List[int]] = {}
        for off_tick, channel, pitch in note_offs:
            offs_by_key.setdefault((channel, pitch), []).append(off_tick)
        for key_ in offs_by_key:
            offs_by_key[key_].sort()
        off_cursor: Dict[Tuple[int, int], int] = {}

        note_events: List[MidiNoteEvent] = []
        channels_with_notes: set = set()
        for on_tick, channel, pitch, velocity in sorted(note_ons, key=lambda e: e[0]):
            # Wishlist #8: percussion (channel 10/index 9) notes are no
            # longer dropped here - MidiTimelineBuilder/MidiReader detect a
            # percussion-only track via channels_used == {PERCUSSION_CHANNEL}
            # and name/route its notes accordingly instead of this reader
            # silently discarding the whole track (BluePeter.mid, reported:
            # its drum track came out as silence).
            key_ = (channel, pitch)
            offs = offs_by_key.get(key_, [])
            cursor = off_cursor.get(key_, 0)
            end_tick = on_tick
            while cursor < len(offs) and offs[cursor] <= on_tick:
                cursor += 1
            if cursor < len(offs):
                end_tick = offs[cursor]
                cursor += 1
            else:
                end_tick = on_tick  # no matching off found - zero-length fallback
            off_cursor[key_] = cursor
            note_events.append(MidiNoteEvent(channel, pitch, velocity, on_tick, max(end_tick, on_tick)))
            channels_with_notes.add(channel)

        if not note_events:
            continue  # conductor-only track

        channels_used = sorted(channels_with_notes)
        filtered_programs = {
            ch: sorted(events) for ch, events in programs.items() if ch in channels_with_notes
        }
        part_id = f"P{len(tracks)}"
        tracks.append(
            MidiTrackData(
                track_index=track_index,
                part_id=part_id,
                name=name,
                note_events=sorted(note_events, key=lambda e: (e.start_tick, e.channel, -e.pitch)),
                program_changes=filtered_programs,
                channels_used=channels_used,
            )
        )

    return MidiSource(
        format=fmt,
        division=division,
        time_signature_changes=time_signature_changes,
        key_signature_changes=key_signature_changes,
        tempo_changes=tempo_changes,
        tracks=tracks,
    )
