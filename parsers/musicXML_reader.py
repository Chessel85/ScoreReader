# parsers/musicXML_reader.py
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

import music21

from models.duration_units import beat_unit_display_name
from models.key_signatures import FIFTHS_MAP
from models.music_data import MusicData
from models.parts_structure import PartStructureInfo
from parsers.timeline_builder import (
    CHORDS_PART_ID,
    CHORDS_PART_NAME,
    LYRICS_PART_ID,
    LYRICS_PART_NAME,
    has_harmony_elements,
    has_lyric_elements,
)
from parsers.xml_source import read_musicxml_root

class MusicXMLReader:
    """Parses MusicXML metadata via ElementTree and streams via music21 into MusicData."""

    PLACEHOLDERS = {"untitled score", "composer / arranger", "subtitle"}

    def __init__(self, file_path: str):
        self.file_path = file_path

    def load(self) -> MusicData:
        root = self._parse_xml_root()

        credits_dict = self._extract_credits_etree(root)
        etree_key, etree_time = self._extract_key_and_time_etree(root)
        etree_parts_info = self._extract_part_structure_etree(root)

        score = None
        try:
            score = music21.converter.parse(self.file_path)
        except Exception as e:
            print(f"[ERROR] music21 parse failed: {e}")

        tempo_bpm, tempo_display, tempo_beat_unit_quarter_length, tempo_beat_unit_name = (
            self._extract_tempo(score) if score else (120, "120 quarter notes per minute", 1.0, "quarter")
        )
        key_sig = self._extract_key(score) or etree_key
        time_sig = self._extract_time(score) or etree_time

        credits_dict["Key Signature"] = key_sig
        credits_dict["Time Signature"] = time_sig
        credits_dict["Tempo"] = tempo_display

        music_data = MusicData(
            credits=credits_dict,
            parts_info=etree_parts_info,
            file_path=self.file_path,
            score=score,
            tempo_bpm=tempo_bpm,
            tempo_beat_unit_quarter_length=tempo_beat_unit_quarter_length,
            tempo_beat_unit_name=tempo_beat_unit_name,
            xml_root=root,
        )

        # Ref 15 AC4-style default, same as GpReader's synthetic Chords
        # voice: the chord name (step), the beat it falls on (so repeated
        # "A minor" strokes within a bar aren't ambiguous - see
        # parsers/timeline_builder.py's chord-stroke entries) and any real
        # strum direction should be audible immediately, without the user
        # having to reach for the attribute context menu first.
        if any(p.part_id == CHORDS_PART_ID for p in etree_parts_info):
            music_data.voice_display_attributes[(CHORDS_PART_ID, 1, 1)] = {
                "step", "beat position", "strum",
            }

        return music_data

    def _parse_xml_root(self) -> Optional[ET.Element]:
        """Parses the file once; every etree-based extractor below reads
        from this same root rather than re-parsing."""
        try:
            return read_musicxml_root(self.file_path)
        except Exception as e:
            print(f"[ERROR] Failed to parse XML file: {e}")
            return None

    def _extract_tempo(self, score: music21.stream.Score) -> Tuple[int, str, float, str]:
        """(quarter-note BPM for playback timing, display string in the
        score's OWN beat unit, that unit's quarter-length ratio, its name).

        A score marked eighth=96 yields 48 BPM internally but must display
        as "96 eighth notes per minute" - the ratio and name are what let
        the status bar and tempo dialog convert back live (Ref 12)."""
        try:
            tempos = score.flatten().getElementsByClass(music21.tempo.MetronomeMark)
            if tempos:
                mm = tempos[0]
                quarter_bpm = mm.getQuarterBPM()
                if quarter_bpm and mm.number and mm.referent:
                    beat_unit = self._beat_unit_name(mm.referent)
                    number = self._format_number(mm.number)
                    return (
                        int(quarter_bpm),
                        f"{number} {beat_unit} notes per minute",
                        float(mm.referent.quarterLength),
                        beat_unit,
                    )
        except Exception as e:
            print(f"[WARN] Error reading tempo: {e}")
        return 120, "120 quarter notes per minute", 1.0, "quarter"

    def _beat_unit_name(self, duration: music21.duration.Duration) -> str:
        return beat_unit_display_name(duration.type, duration.dots)

    @staticmethod
    def _format_number(n: float) -> str:
        return str(int(n)) if float(n).is_integer() else str(n)

    def _extract_key(self, score: music21.stream.Score) -> Optional[str]:
        try:
            keys = score.flatten().getElementsByClass(music21.key.KeySignature)
            if keys:
                ks = keys[0]
                return FIFTHS_MAP.get(ks.sharps, f"{ks.sharps} sharps/flats")
            
            explicit_keys = score.flatten().getElementsByClass(music21.key.Key)
            if explicit_keys:
                k = explicit_keys[0]
                return f"{k.tonic.name} {k.mode}"
        except Exception as e:
            print(f"[WARN] Error extracting key via music21: {e}")
        return None

    def _extract_time(self, score: music21.stream.Score) -> Optional[str]:
        try:
            times = score.flatten().getElementsByClass(music21.meter.TimeSignature)
            if times:
                ts = times[0]
                return f"{ts.numerator}/{ts.denominator}"
        except Exception as e:
            print(f"[WARN] Error extracting time via music21: {e}")
        return None

    def _extract_key_and_time_etree(self, root: Optional[ET.Element]) -> Tuple[str, str]:
        key_sig = "C major / A minor"
        time_sig = "4/4"

        if root is None:
            return key_sig, time_sig

        try:
            fifths_elem = root.find(".//attributes/key/fifths")
            if fifths_elem is not None and fifths_elem.text:
                fifths = int(fifths_elem.text.strip())
                key_sig = FIFTHS_MAP.get(fifths, f"{fifths} sharps/flats")

            beats_elem = root.find(".//attributes/time/beats")
            beat_type_elem = root.find(".//attributes/time/beat-type")

            if (
                beats_elem is not None
                and beats_elem.text
                and beat_type_elem is not None
                and beat_type_elem.text
            ):
                time_sig = f"{beats_elem.text.strip()}/{beat_type_elem.text.strip()}"

        except Exception as e:
            print(f"[ERROR] Parsing Key/Time XML: {e}")

        return key_sig, time_sig

    def _extract_credits_etree(self, root: Optional[ET.Element]) -> Dict[str, str]:
        credits_found: Dict[str, str] = {}
        if root is None:
            return credits_found

        untyped_count = 1

        try:
            for credit in root.findall("credit"):
                type_elem = credit.find("credit-type")
                words_texts = [
                    w.text.strip()
                    for w in credit.findall(".//credit-words")
                    if w.text and w.text.strip()
                ]
                text = " ".join(words_texts) if words_texts else ""

                if not text:
                    continue

                if type_elem is not None and type_elem.text:
                    key = type_elem.text.strip().capitalize()
                else:
                    key = f"Credit {untyped_count}"
                    untyped_count += 1

                if key in credits_found:
                    existing = credits_found[key]
                    if existing.lower() in self.PLACEHOLDERS:
                        credits_found[key] = text
                    elif (
                        text.lower() not in self.PLACEHOLDERS
                        and text not in existing
                    ):
                        credits_found[key] += f" | {text}"
                else:
                    credits_found[key] = text

        except Exception as e:
            print(f"[ERROR] Parsing credits XML: {e}")

        return credits_found

    def _extract_part_structure_etree(self, root: Optional[ET.Element]) -> List[PartStructureInfo]:
        parts_list: List[PartStructureInfo] = []
        if root is None:
            return parts_list

        try:
            part_names = {}
            for sp in root.findall(".//part-list/score-part"):
                p_id = sp.attrib.get("id", "")
                p_name_elem = sp.find("part-name")
                p_name = p_name_elem.text.strip() if p_name_elem is not None and p_name_elem.text else "Classical Guitar"
                part_names[p_id] = p_name

            for part_elem in root.findall("part"):
                p_id = part_elem.attrib.get("id", "")
                p_info = PartStructureInfo(part_id=p_id, name=part_names.get(p_id, "Classical Guitar"))

                midi_prog_elem = root.find(f".//score-part[@id='{p_id}']//midi-program")
                if midi_prog_elem is not None and midi_prog_elem.text:
                    p_info.gmidi_program = int(midi_prog_elem.text.strip())
                else:
                    p_info.gmidi_program = 25

                staves_clefs: Dict[int, str] = {}
                staves_voices: Dict[int, List[int]] = {}

                for c in part_elem.findall(".//attributes/clef"):
                    staff_num = int(c.attrib.get("number", "1"))
                    sign_elem = c.find("sign")
                    sign = sign_elem.text.strip() if sign_elem is not None and sign_elem.text else "G"

                    if sign == "TAB":
                        staves_clefs[staff_num] = "Tab stave"
                    elif sign == "G":
                        staves_clefs[staff_num] = "Treble stave"
                    elif sign == "F":
                        staves_clefs[staff_num] = "Bass stave"
                    else:
                        staves_clefs[staff_num] = f"{sign} stave"

                if 1 not in staves_clefs:
                    staves_clefs[1] = "Treble stave"

                for note in part_elem.findall(".//note"):
                    staff_id = int(note.find("staff").text.strip()) if note.find("staff") is not None else 1
                    voice_id = int(note.find("voice").text.strip()) if note.find("voice") is not None else 1

                    if staff_id not in staves_voices:
                        staves_voices[staff_id] = []
                    if voice_id not in staves_voices[staff_id]:
                        staves_voices[staff_id].append(voice_id)

                for s_id in staves_voices:
                    staves_voices[s_id].sort()

                p_info.staves_clefs = staves_clefs
                p_info.staves_voices = staves_voices
                parts_list.append(p_info)

            # A real notated score (piano/guitar lead sheet, e.g.) can carry
            # <harmony>/<lyric> markup alongside its real notes - added here
            # as two more parts, the same "an instrument called Chords" /
            # "the lyrics are also an instrument/part" UX
            # parsers/ug_timeline_builder.py already established for a pure
            # Ultimate Guitar import. One staff, one voice each - not zero,
            # which would make Region2HierarchyModel.get_active_voice_tuples()
            # treat the part as having nothing to show regardless of its
            # on/off state (the same gotcha CLAUDE.md documents for MIDI's
            # collapse_to_parts and UgReader). Added only when the file
            # actually has the markup, so an ordinary score gets no empty
            # "Chords"/"Lyrics" rows.
            if has_harmony_elements(root):
                parts_list.append(
                    PartStructureInfo(
                        part_id=CHORDS_PART_ID,
                        name=CHORDS_PART_NAME,
                        gmidi_program=25,  # Acoustic Guitar (nylon), same as UG's Chords part
                        staves_clefs={1: "Chord chart"},
                        staves_voices={1: [1]},
                    )
                )
            if has_lyric_elements(root):
                parts_list.append(
                    PartStructureInfo(
                        part_id=LYRICS_PART_ID,
                        name=LYRICS_PART_NAME,
                        gmidi_program=25,  # unused - the Lyrics part never carries a real midi_pitch
                        staves_clefs={1: "Lyrics"},
                        staves_voices={1: [1]},
                    )
                )

        except Exception as e:
            print(f"[ERROR] Parsing part structure XML: {e}")

        return parts_list