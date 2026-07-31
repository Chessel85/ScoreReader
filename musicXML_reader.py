# musicXML_reader.py
import xml.etree.ElementTree as ET
from collections import defaultdict
import music21
from music_data import MusicData


class MusicXMLReader:
    """Reads a MusicXML file, extracting dynamic credits via ElementTree

    and score structure using music21 and XML inspection.
    """

    PLACEHOLDERS = {"Untitled score", "Composer / arranger", "Subtitle"}

    def __init__(self, file_path: str):
        self.file_path = file_path

    def load(self) -> MusicData:
        credits_dict = self._extract_credits()

        try:
            score = music21.converter.parse(self.file_path)
        except Exception as e:
            print(f"Error parsing score with music21: {e}")
            score = None

        structure_dict = self._extract_structure(score)

        return MusicData(credits=credits_dict, structure=structure_dict, score=score)

    def _extract_credits(self) -> dict[str, str]:
        credits_found = {}
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

                if type_elem is not None and type_elem.text:
                    key = type_elem.text.strip().capitalize()
                else:
                    key = f"Credit {untyped_count}"
                    untyped_count += 1

                if text:
                    if key in credits_found:
                        existing = credits_found[key]
                        if existing in self.PLACEHOLDERS:
                            credits_found[key] = text
                        elif text not in self.PLACEHOLDERS and text not in existing:
                            credits_found[key] += f" | {text}"
                    else:
                        credits_found[key] = text

        except Exception as e:
            print(f"Error parsing credits from XML: {e}")

        return credits_found

    def _extract_structure(self, score: music21.stream.Score | None) -> dict:
        """Extracts part -> staff -> voice hierarchy from score."""
        structure = {}

        if score is None:
            return structure

        for idx, part in enumerate(score.parts):
            part_name = part.partName or f"Part {idx + 1}"
            staves_dict = defaultdict(set)

            # Recurse notes to find staff and voice tags
            for element in part.recurse().notes:
                staff_num = getattr(element, "staff", 1) or 1
                voice_num = int(element.voice) if getattr(element, "voice", None) else 1
                staves_dict[staff_num].add(voice_num)

            # Fallback for empty parts or simple parts without explicit staff numbers
            if not staves_dict:
                staves_dict[1].add(1)

            # Convert sets to sorted lists for clean ordering
            structure[part_name] = {
                staff: sorted(list(voices)) for staff, voices in staves_dict.items()
            }

        return structure