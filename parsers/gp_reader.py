# parsers/gp_reader.py
from pathlib import Path
from typing import Dict, List, Tuple

from models.key_signatures import FIFTHS_MAP, key_signature_display_name
from models.music_data import MusicData
from models.parts_structure import PartStructureInfo
from parsers.gp_source import GpSource, iter_track_positions, read_gp_source
from models.synthetic_parts import GP_CHORD_VOICE_ID, GP_CHORD_VOICE_NAME

# S2: GP's synthetic Chords voice name now comes from
# models/synthetic_parts.py, alongside its voice id.
CHORD_VOICE_NAME = GP_CHORD_VOICE_NAME


class GpReader:
    """Parses a Guitar Pro (.gp) file into MusicData - the GP counterpart of
    MusicXMLReader/MidiReader. Like MIDI, GP has one source of truth (the
    id-graph in Content/score.gpif), parsed once by gp_source.read_gp_source
    and shared with GpTimelineBuilder via MusicData.gp_source (mirroring
    midi_source)."""

    def __init__(self, file_path: str):
        self.file_path = file_path

    def load(self) -> MusicData:
        try:
            source = read_gp_source(self.file_path)
        except Exception as e:
            print(f"[ERROR] Failed to parse Guitar Pro file: {e}")
            source = GpSource()

        parts_info = self._build_parts_info(source)

        key_sig = FIFTHS_MAP.get(0, "0 sharps/flats")
        time_sig = "4/4"
        if source.master_bars:
            first = source.master_bars[0]
            time_sig = f"{first.time_sig[0]}/{first.time_sig[1]}"
            key_sig = key_signature_display_name(first.key_fifths)

        tempo_display = f"{source.tempo_bpm} quarter notes per minute"

        credits: Dict[str, str] = {
            "Title": source.title or Path(self.file_path).stem,
        }
        if source.artist:
            credits["Artist"] = source.artist
        credits["Key Signature"] = key_sig
        credits["Time Signature"] = time_sig
        credits["Tempo"] = tempo_display

        music_data = MusicData(
            credits=credits,
            parts_info=parts_info,
            file_path=self.file_path,
            score=None,
            tempo_bpm=source.tempo_bpm,
            tempo_beat_unit_quarter_length=1.0,
            tempo_beat_unit_name="quarter",
            gp_source=source,
        )

        # Ref 15 AC4-style default: the synthetic Chords voice should speak
        # its chord name (step) and real strike rhythm (beat position)
        # immediately, plus any real strum direction, without the user
        # having to reach for the F1 attribute menu first - see the GP
        # import plan's "Default visibility" note.
        for part in parts_info:
            for staff_id, voice_ids in part.staves_voices.items():
                if GP_CHORD_VOICE_ID in voice_ids:
                    music_data.voice_display_attributes[(part.part_id, staff_id, GP_CHORD_VOICE_ID)] = {
                        "step", "beat position", "strum",
                    }

        return music_data

    def _build_parts_info(self, source: GpSource) -> List[PartStructureInfo]:
        parts: List[PartStructureInfo] = []
        for track in source.tracks:
            part_id = f"P{track.index}"
            voice_slots, qualifies_for_chords = self._scan_track(source, track.index)

            # GP voice slots are 0-indexed positionally; NoteData/Region 2
            # use 1-indexed voice numbers (same convention MusicXML/MIDI
            # already use), so slot 0 -> voice 1, slot 1 -> voice 2, etc.
            voices = sorted(slot + 1 for slot in voice_slots) or [1]
            voice_names: Dict[Tuple[int, int], str] = {}
            if qualifies_for_chords:
                voices = voices + [GP_CHORD_VOICE_ID]
                voice_names[(1, GP_CHORD_VOICE_ID)] = CHORD_VOICE_NAME

            parts.append(
                PartStructureInfo(
                    part_id=part_id,
                    name=track.name,
                    # GM programs are 1-indexed in the model, 0-indexed on
                    # the wire - same convention MusicXMLReader's
                    # <midi-program> and MidiReader's Program Change already
                    # use.
                    gmidi_program=track.gmidi_program + 1,
                    staves_clefs={1: "Tab stave"},
                    staves_voices={1: voices},
                    voice_names=voice_names,
                )
            )
        return parts

    @staticmethod
    def _scan_track(source: GpSource, track_index: int) -> Tuple[set, bool]:
        """(voice slots actually used, whether this track qualifies for a
        synthetic Chords voice) - a lightweight pass over the same graph
        GpTimelineBuilder will walk in full, using iter_track_positions so
        the two can't disagree on what a "position" is. Qualification
        (CLAUDE.md / GP import plan): at least one beat anywhere on this
        track has a real chord-name reference or a real Brush direction -
        this is what let the mandolin (tremolo, no chord/brush data at all)
        fall out for free during discovery, with no instrument-type check."""
        voice_slots: set = set()
        qualifies = False
        for _measure_index, voice_slot, beat_id in iter_track_positions(source, track_index):
            voice_slots.add(voice_slot)
            beat = source.beats.get(beat_id)
            if beat is not None and (beat.chord_index is not None or beat.brush_direction is not None):
                qualifies = True
        return voice_slots, qualifies
