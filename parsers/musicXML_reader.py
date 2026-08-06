# parsers/musicXML_reader.py
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

import music21

from models.music_data import MusicData
from models.parts_structure import PartStructureInfo

class MusicXMLReader:
    """Parses MusicXML metadata via ElementTree and streams via music21 into MusicData."""

    PLACEHOLDERS = {"untitled score", "composer / arranger", "subtitle"}

    DURATION_TYPE_NAMES = {
        "whole": "whole",
        "half": "half",
        "quarter": "quarter",
        "eighth": "eighth",
        "16th": "sixteenth",
        "32nd": "thirty-second",
        "64th": "sixty-fourth",
        "128th": "hundred-twenty-eighth",
        "breve": "double whole",
        "longa": "longa",
    }

    DOTS_PREFIX = {0: "", 1: "dotted ", 2: "double-dotted ", 3: "triple-dotted "}

    FIFTHS_MAP = {
        0: "C major / A minor",
        1: "G major / E minor",
        2: "D major / B minor",
        3: "A major / F# minor",
        4: "E major / C# minor",
        5: "B major / G# minor",
        6: "F# major / D# minor",
        7: "C# major / A# minor",
        -1: "F major / D minor",
        -2: "Bb major / G minor",
        -3: "Eb major / C minor",
        -4: "Ab major / F minor",
        -5: "Db major / Bb minor",
        -6: "Gb major / Eb minor",
        -7: "Cb major / Ab minor",
    }

    def __init__(self, file_path: str):
        self.file_path = file_path

    def load(self) -> MusicData:
        print(f"[DEBUG] Loading file: {self.file_path}")

        credits_dict = self._extract_credits_etree()
        etree_key, etree_time = self._extract_key_and_time_etree()
        etree_parts_info = self._extract_part_structure_etree()

        score = None
        try:
            score = music21.converter.parse(self.file_path)
            print("[DEBUG] music21 parse completed.")
        except Exception as e:
            print(f"[ERROR] music21 parse failed: {e}")

        tempo_bpm, tempo_display = self._extract_tempo(score) if score else (120, "120 quarter notes per minute")
        key_sig = self._extract_key(score) or etree_key
        time_sig = self._extract_time(score) or etree_time

        credits_dict["Key Signature"] = key_sig
        credits_dict["Time Signature"] = time_sig
        credits_dict["Tempo"] = tempo_display

        return MusicData(
            credits=credits_dict,
            parts_info=etree_parts_info,
            file_path=self.file_path,
            score=score,
            tempo_bpm=tempo_bpm,
        )

    def _extract_tempo(self, score: music21.stream.Score) -> Tuple[int, str]:
        """Returns (quarter-note BPM for playback timing, display string in the
        score's own beat unit - e.g. "96 eighth notes per minute" for a score
        marked eighth=96, rather than music21's quarter-converted "48 BPM")."""
        try:
            tempos = score.flatten().getElementsByClass(music21.tempo.MetronomeMark)
            if tempos:
                mm = tempos[0]
                quarter_bpm = mm.getQuarterBPM()
                if quarter_bpm and mm.number and mm.referent:
                    beat_unit = self._beat_unit_name(mm.referent)
                    number = self._format_number(mm.number)
                    return int(quarter_bpm), f"{number} {beat_unit} notes per minute"
        except Exception as e:
            print(f"[WARN] Error reading tempo: {e}")
        return 120, "120 quarter notes per minute"

    def _beat_unit_name(self, duration: music21.duration.Duration) -> str:
        base = self.DURATION_TYPE_NAMES.get(duration.type, duration.type)
        dots_prefix = self.DOTS_PREFIX.get(duration.dots, f"{duration.dots}x-dotted ")
        return f"{dots_prefix}{base}"

    @staticmethod
    def _format_number(n: float) -> str:
        return str(int(n)) if float(n).is_integer() else str(n)

    def _extract_key(self, score: music21.stream.Score) -> Optional[str]:
        try:
            keys = score.flatten().getElementsByClass(music21.key.KeySignature)
            if keys:
                ks = keys[0]
                return self.FIFTHS_MAP.get(ks.sharps, f"{ks.sharps} sharps/flats")
            
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

    def _extract_key_and_time_etree(self) -> Tuple[str, str]:
        key_sig = "C major / A minor"
        time_sig = "4/4"

        try:
            tree = ET.parse(self.file_path)
            root = tree.getroot()

            fifths_elem = root.find(".//attributes/key/fifths")
            if fifths_elem is not None and fifths_elem.text:
                fifths = int(fifths_elem.text.strip())
                key_sig = self.FIFTHS_MAP.get(fifths, f"{fifths} sharps/flats")

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

    def _extract_credits_etree(self) -> Dict[str, str]:
        credits_found: Dict[str, str] = {}
        untyped_count = 1

        try:
            tree = ET.parse(self.file_path)
            root = tree.getroot()

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

    def _extract_part_structure_etree(self) -> List[PartStructureInfo]:
        parts_list: List[PartStructureInfo] = []

        try:
            tree = ET.parse(self.file_path)
            root = tree.getroot()

            part_names = {}
            for sp in root.findall(".//part-list/score-part"):
                p_id = sp.attrib.get("id", "")
                p_name_elem = sp.find("part-name")
                p_name = p_name_elem.text.strip() if p_name_elem is not None and p_name_elem.text else "Classical Guitar"

                if any(ord(c) > 127 for c in p_name):
                    p_name = "Classical Guitar"
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
                        staves_clefs[staff_num] = "guitar tab standard tuning"
                    elif sign == "G":
                        staves_clefs[staff_num] = "treble clef"
                    elif sign == "F":
                        staves_clefs[staff_num] = "bass clef"
                    else:
                        staves_clefs[staff_num] = f"{sign} clef"

                if 1 not in staves_clefs:
                    staves_clefs[1] = "treble clef"

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

        except Exception as e:
            print(f"[ERROR] Parsing part structure XML: {e}")

        return parts_list