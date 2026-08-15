# parsers/midi_reader.py
from pathlib import Path
from typing import Dict, List

from models.gm_instruments import gm_instrument_name
from models.key_signatures import FIFTHS_MAP
from models.music_data import MusicData
from models.parts_structure import PartStructureInfo
from parsers.midi_source import MidiSource, read_midi_source


class MidiReader:
    """Parses a Standard MIDI File into MusicData - the MIDI counterpart of
    MusicXMLReader. Unlike MusicXML, MIDI has only one source of truth (the
    raw byte stream), so there's no etree/music21 reconciliation pass - one
    parse (parsers/midi_source.py) feeds both this class and
    MidiTimelineBuilder (via MusicData.midi_source, mirroring how xml_root is
    shared with TimelineBuilder)."""

    def __init__(self, file_path: str):
        self.file_path = file_path

    def load(self) -> MusicData:
        try:
            source = read_midi_source(self.file_path)
        except Exception as e:
            print(f"[ERROR] Failed to parse MIDI file: {e}")
            source = MidiSource(format=0, division=480)

        parts_info = self._build_parts_info(source)

        tempo_bpm = 120
        if source.tempo_changes:
            _, usec = source.tempo_changes[0]
            tempo_bpm = round(60000000 / usec) if usec > 0 else 120
        tempo_display = f"{tempo_bpm} quarter notes per minute"

        key_fifths = source.key_signature_changes[0][1] if source.key_signature_changes else 0
        key_sig = FIFTHS_MAP.get(key_fifths, f"{key_fifths} sharps/flats")

        num, den = self._credits_time_signature(source.time_signature_changes)
        time_sig = f"{num}/{den}"

        # MIDI has no <credit> equivalent - composer stays unpopulated, same
        # as any MusicXML score that omits it. Title falls back to the
        # filename (extension stripped) per the user's explicit request,
        # rather than showing nothing at all.
        credits: Dict[str, str] = {
            "Title": Path(self.file_path).stem,
            "Key Signature": key_sig,
            "Time Signature": time_sig,
            "Tempo": tempo_display,
        }

        return MusicData(
            credits=credits,
            parts_info=parts_info,
            file_path=self.file_path,
            score=None,
            tempo_bpm=tempo_bpm,
            tempo_beat_unit_quarter_length=1.0,
            tempo_beat_unit_name="quarter",
            midi_source=source,
        )

    @staticmethod
    def _credits_time_signature(time_signature_changes) -> "tuple[int, int]":
        """Region 1's summary time signature - the SECOND entry when the
        first is a pickup-bar artifact (a genuinely shorter span than the
        one following it, same signal MidiTimelineBuilder._detect_pickup
        uses for Ref 17), else the first/only entry. Mirrors what a
        MusicXML load of the same piece would show (the governing time
        signature, not the pickup bar's own)."""
        if not time_signature_changes:
            return 4, 4
        if len(time_signature_changes) >= 2:
            _, num1, den1 = time_signature_changes[0]
            _, num2, den2 = time_signature_changes[1]
            if (num1, den1) != (num2, den2) and num1 * 4.0 / den1 < num2 * 4.0 / den2:
                return num2, den2
        _, num, den = time_signature_changes[0]
        return num, den

    def _build_parts_info(self, source: MidiSource) -> List[PartStructureInfo]:
        parts: List[PartStructureInfo] = []
        for track in source.tracks:
            track_number = int(track.part_id[1:]) + 1 if track.part_id[1:].isdigit() else 1

            program = 0
            has_program = False
            for ch in track.channels_used:
                changes = track.program_changes.get(ch)
                if changes:
                    program = changes[0][1]
                    has_program = True
                    break

            # Reported: BluePeter.mid (an internet-sourced file) has no
            # track names at all, so every part showed as a bare "Track N" -
            # not something a user unfamiliar with the file can act on. A
            # Program Change event, when present, gives a real instrument
            # name to suggest instead; still just a naming fallback, not an
            # override - S5's instrument dialog is the actual, user-facing
            # way to fix a wrong or missing name.
            if track.name:
                name = track.name
            elif has_program:
                name = gm_instrument_name(program + 1)
            else:
                name = f"Track {track_number}"

            voice_count = len(track.channels_used) or 1
            parts.append(
                PartStructureInfo(
                    part_id=track.part_id,
                    name=name,
                    # GM programs are 1-indexed in the model, 0-indexed on
                    # the wire (same convention MusicXMLReader's
                    # <midi-program> read already uses).
                    gmidi_program=program + 1,
                    staves_clefs={},
                    staves_voices={1: list(range(1, voice_count + 1))},
                )
            )
        return parts
