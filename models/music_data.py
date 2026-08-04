# models/music_data.py
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET

from models.event_slice import EventSlice
from models.note_data import NoteData
from models.parts_structure import PartStructureInfo


@dataclass
class MusicData:
    score: Optional[Any] = None
    credits: Dict[str, str] = field(default_factory=dict)
    parts_info: List[PartStructureInfo] = field(default_factory=list)
    file_path: str = ""
    tempo_bpm: int = 120

    timeline_slices: List[EventSlice] = field(default_factory=list)
    active_event_index: int = 0

    def __post_init__(self):
        if self.file_path:
            self._build_timeline_from_xml()

    def _build_timeline_from_xml(self):
        try:
            tree = ET.parse(self.file_path)
            root = tree.getroot()
        except Exception as e:
            print(f"[ERROR] Failed to parse XML for timeline: {e}")
            return

        default_part_name = self.parts_info[0].name if self.parts_info else "Classical Guitar"

        time_sig_num = 4
        time_sig_den = 4
        ts_elem = root.find(".//attributes/time")
        if ts_elem is not None:
            b = ts_elem.find("beats")
            bt = ts_elem.find("beat-type")
            if b is not None and b.text:
                time_sig_num = int(b.text.strip())
            if bt is not None and bt.text:
                time_sig_den = int(bt.text.strip())

        divisions = 1
        div_elem = root.find(".//attributes/divisions")
        if div_elem is not None and div_elem.text:
            divisions = int(div_elem.text.strip())

        beat_unit_quarter_len = 4.0 / time_sig_den
        full_bar_quarters = time_sig_num * beat_unit_quarter_len

        first_measure = root.find(".//part/measure")
        is_pickup = False
        pickup_filled_quarters = 0.0

        if first_measure is not None:
            if first_measure.attrib.get("implicit") == "yes":
                is_pickup = True

            curr_offset = 0
            max_offset = 0

            for elem in first_measure:
                if elem.tag == "backup":
                    dur = elem.find("duration")
                    if dur is not None and dur.text:
                        curr_offset -= int(dur.text.strip())
                elif elem.tag == "forward":
                    dur = elem.find("duration")
                    if dur is not None and dur.text:
                        curr_offset += int(dur.text.strip())
                elif elem.tag == "note":
                    staff = elem.find("staff")
                    staff_id = int(staff.text.strip()) if staff is not None and staff.text else 1
                    
                    dur_el = elem.find("duration")
                    dur_divs = int(dur_el.text.strip()) if (dur_el is not None and dur_el.text) else 0
                    
                    is_chord = elem.find("chord") is not None
                    if not is_chord:
                        curr_offset += dur_divs
                        if staff_id == 1:
                            max_offset = max(max_offset, curr_offset)

            pickup_filled_quarters = max_offset / divisions

            if 0 < pickup_filled_quarters < full_bar_quarters:
                is_pickup = True

        buckets: Dict[Tuple[int, float], List[NoteData]] = {}

        for part in root.findall("part"):
            for m in part.findall("measure"):
                m_attr_num = m.attrib.get("number", "1")
                try:
                    raw_m_num = int(m_attr_num)
                except ValueError:
                    raw_m_num = 1

                m_num = raw_m_num - 1 if is_pickup else raw_m_num
                current_offset_divs = 0

                for elem in m:
                    if elem.tag == "forward":
                        dur = elem.find("duration")
                        if dur is not None and dur.text:
                            current_offset_divs += int(dur.text.strip())
                    elif elem.tag == "backup":
                        dur = elem.find("duration")
                        if dur is not None and dur.text:
                            current_offset_divs -= int(dur.text.strip())
                    elif elem.tag == "note":
                        is_rest = elem.find("rest") is not None
                        is_chord = elem.find("chord") is not None
                        dur_el = elem.find("duration")
                        dur_divs = int(dur_el.text.strip()) if (dur_el is not None and dur_el.text) else 0

                        if is_chord:
                            note_offset_divs = current_offset_divs - dur_divs
                        else:
                            note_offset_divs = current_offset_divs
                            current_offset_divs += dur_divs

                        if is_rest:
                            continue

                        pitch_el = elem.find("pitch")
                        if pitch_el is None:
                            continue

                        step = pitch_el.find("step").text.strip() if pitch_el.find("step") is not None else "C"
                        octave = int(pitch_el.find("octave").text.strip()) if pitch_el.find("octave") is not None else 4
                        alter_el = pitch_el.find("alter")
                        alter = int(alter_el.text.strip()) if (alter_el is not None and alter_el.text) else 0

                        acc_words = {1: " sharp", -1: " flat", 2: " double sharp", -2: " double flat", 0: ""}
                        step_name = f"{step}{acc_words.get(alter, '')}"

                        step_offsets = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
                        midi_pitch = (octave + 1) * 12 + step_offsets.get(step, 0) + alter

                        staff = int(elem.find("staff").text.strip()) if elem.find("staff") is not None else 1
                        voice = int(elem.find("voice").text.strip()) if elem.find("voice") is not None else 1

                        fret = None
                        string_num = None
                        tech_el = elem.find("notations/technical")
                        if tech_el is not None:
                            f_el = tech_el.find("fret")
                            s_el = tech_el.find("string")
                            if f_el is not None and f_el.text:
                                fret = int(f_el.text.strip())
                            if s_el is not None and s_el.text:
                                string_num = int(s_el.text.strip())

                        offset_q = note_offset_divs / divisions
                        quarter_len = dur_divs / divisions
                        ts_duration = round(quarter_len / beat_unit_quarter_len, 2)

                        if m_num == 0:
                            start_beat = 1.0 + ((full_bar_quarters - pickup_filled_quarters) / beat_unit_quarter_len)
                            beat_pos = start_beat + (offset_q / beat_unit_quarter_len)
                        else:
                            beat_pos = 1.0 + (offset_q / beat_unit_quarter_len)

                        note_obj = NoteData(
                            step_name=step_name,
                            octave=octave,
                            midi_pitch=midi_pitch,
                            measure=m_num,
                            beat_position=round(beat_pos, 2),
                            ts_duration=ts_duration,
                            quarter_length=quarter_len,
                            part_name=default_part_name,
                            staff=staff,
                            voice=voice,
                            fret=fret,
                            string=string_num,
                        )

                        key = (m_num, round(offset_q, 4))
                        if key not in buckets:
                            buckets[key] = []
                        buckets[key].append(note_obj)

        sorted_keys = sorted(buckets.keys(), key=lambda k: (k[0], k[1]))

        slices = []
        for m_num, offset_q in sorted_keys:
            notes = buckets[(m_num, offset_q)]
            q_len = min(n.quarter_length for n in notes) if notes else 1.0
            beat_pos = notes[0].beat_position if notes else 1.0

            slices.append(
                EventSlice(
                    measure=m_num,
                    beat_position=beat_pos,
                    quarter_length=q_len,
                    notes=notes,
                )
            )

        self.timeline_slices = slices
        self.active_event_index = 0

    def get_current_slice(self) -> Optional[EventSlice]:
        if 0 <= self.active_event_index < len(self.timeline_slices):
            return self.timeline_slices[self.active_event_index]
        return None

    def move_timeline_left(self) -> bool:
        if self.active_event_index > 0:
            self.active_event_index -= 1
            return True
        return False

    def move_timeline_right(self) -> bool:
        if self.active_event_index < len(self.timeline_slices) - 1:
            self.active_event_index += 1
            return True
        return False

    def get_region_1_data(self) -> Dict[str, str]:
        return self.credits

    def get_region_2_data(self) -> Dict[str, str]:
        region_2_dict = {}
        for p_idx, p_info in enumerate(self.parts_info, start=1):
            region_2_dict[f"Part {p_idx}"] = f"{p_info.name} (GM Prog {p_info.gmidi_program})"
            for s_id in sorted(p_info.staves_voices.keys()):
                clef_desc = p_info.staves_clefs.get(s_id, "Standard Clef")
                voices = p_info.staves_voices[s_id]
                region_2_dict[f"Staff {s_id}"] = clef_desc
                for v in voices:
                    region_2_dict[f"  Voice {v}"] = "on"
        return region_2_dict

    def get_region_3_data(self) -> List[str]:
        current = self.get_current_slice()
        if not current or not current.notes:
            return ["None"]
        return [n.step_name for n in current.notes]

    def get_region_4_data_for_indices(self, selected_indices: List[int]) -> Dict[str, str]:
        current = self.get_current_slice()
        if not current or not current.notes or not selected_indices:
            return {"Status": "No note selected"}

        selected_notes = [
            current.notes[i] for i in selected_indices if 0 <= i < len(current.notes)
        ]
        if not selected_notes:
            return {"Status": "No note selected"}

        data = {}
        is_chord = len(selected_notes) > 1

        for idx, n in enumerate(selected_notes, start=1):
            prefix = f"note {idx} " if is_chord else ""
            dur_str = str(int(n.ts_duration)) if n.ts_duration.is_integer() else str(n.ts_duration)

            data[f"{prefix}step"] = n.step_name
            data[f"{prefix}octave"] = str(n.octave)
            data[f"{prefix}midi"] = str(n.midi_pitch)
            data[f"{prefix}measure"] = str(n.measure)
            data[f"{prefix}beat position"] = str(n.beat_position)
            data[f"{prefix}duration"] = dur_str
            data[f"{prefix}part"] = n.part_name
            data[f"{prefix}stave"] = str(n.staff)
            data[f"{prefix}voice"] = str(n.voice)

            if n.string is not None:
                data[f"{prefix}string"] = str(n.string)
            if n.fret is not None:
                data[f"{prefix}fret"] = str(n.fret)

        return data

    def get_midi_notes_for_indices(self, selected_indices: List[int]) -> List[int]:
        current = self.get_current_slice()
        if not current or not selected_indices:
            return []
        return [
            current.notes[i].midi_pitch 
            for i in selected_indices 
            if 0 <= i < len(current.notes)
        ]

    def get_current_gmidi_program(self) -> int:
        if self.parts_info:
            return self.parts_info[0].gmidi_program
        return 25

    def get_current_duration_ms(self) -> int:
        current = self.get_current_slice()
        if not current:
            return 500
        ms = (current.quarter_length * 60000.0) / float(self.tempo_bpm)
        return max(100, int(ms))