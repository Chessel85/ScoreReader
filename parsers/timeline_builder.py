# parsers/timeline_builder.py
import xml.etree.ElementTree as ET
from typing import Dict, List, Tuple

from models.event_slice import EventSlice
from models.note_data import NoteData
from models.parts_structure import PartStructureInfo


class TimelineBuilder:
    """Builds the flat, sorted EventSlice timeline for a MusicXML file.

    A hand-rolled ElementTree pass, not music21 - it is the source of truth
    for notes because it handles <backup>/<forward> offsets, <chord>
    grouping, and notations/technical string/fret data explicitly, and it is
    ~460x faster than routing through music21.converter.parse.
    """

    def __init__(self, file_path: str, parts_info: List[PartStructureInfo]):
        self.file_path = file_path
        self.parts_info = parts_info

    def build(self) -> List[EventSlice]:
        try:
            tree = ET.parse(self.file_path)
            root = tree.getroot()
        except Exception as e:
            print(f"[ERROR] Failed to parse XML for timeline: {e}")
            return []

        default_part_name = self.parts_info[0].name if self.parts_info else "Classical Guitar"

        part_names: Dict[str, str] = {}
        for sp in root.findall(".//part-list/score-part"):
            sp_id = sp.attrib.get("id", "")
            name_elem = sp.find("part-name")
            part_names[sp_id] = (
                name_elem.text.strip() if name_elem is not None and name_elem.text else default_part_name
            )

        def apply_attributes(attrs_elem, divisions, ts_num, ts_den):
            """Ref 18: divisions/time signature can change mid-score, so this
            is called every time an <attributes> element is encountered
            walking in document order, not just once for the whole file."""
            div_elem = attrs_elem.find("divisions")
            if div_elem is not None and div_elem.text:
                divisions = int(div_elem.text.strip())

            time_elem = attrs_elem.find("time")
            if time_elem is not None:
                b = time_elem.find("beats")
                bt = time_elem.find("beat-type")
                if b is not None and b.text:
                    ts_num = int(b.text.strip())
                if bt is not None and bt.text:
                    ts_den = int(bt.text.strip())

            return divisions, ts_num, ts_den

        first_measure = root.find(".//part/measure")
        is_pickup = False
        pickup_filled_quarters = 0.0
        first_measure_number = 1

        if first_measure is not None:
            try:
                first_measure_number = int(first_measure.attrib.get("number", "1"))
            except ValueError:
                first_measure_number = 1

            if first_measure.attrib.get("implicit") == "yes":
                is_pickup = True

            det_divisions, det_ts_num, det_ts_den = 1, 4, 4
            curr_offset = 0
            max_offset = 0

            for elem in first_measure:
                if elem.tag == "attributes":
                    det_divisions, det_ts_num, det_ts_den = apply_attributes(
                        elem, det_divisions, det_ts_num, det_ts_den
                    )
                elif elem.tag == "backup":
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

            det_full_bar_quarters = det_ts_num * (4.0 / det_ts_den)
            pickup_filled_quarters = max_offset / det_divisions

            if 0 < pickup_filled_quarters < det_full_bar_quarters:
                is_pickup = True

        # Two exporter conventions for the pickup: numbered 1 (re-index every
        # measure down by one so it lands on 0) or already numbered 0 (leave
        # numbering alone - subtracting again would land it on -1).
        needs_reindex = is_pickup and first_measure_number != 0

        buckets: Dict[Tuple[int, float], List[NoteData]] = {}

        for part in root.findall("part"):
            part_id = part.attrib.get("id", "")
            part_name = part_names.get(part_id, default_part_name)

            divisions, time_sig_num, time_sig_den = 1, 4, 4
            beat_unit_quarter_len = 4.0 / time_sig_den
            full_bar_quarters = time_sig_num * beat_unit_quarter_len

            for m in part.findall("measure"):
                m_attr_num = m.attrib.get("number", "1")
                try:
                    raw_m_num = int(m_attr_num)
                except ValueError:
                    raw_m_num = 1

                m_num = raw_m_num - 1 if needs_reindex else raw_m_num
                current_offset_divs = 0

                for elem in m:
                    if elem.tag == "attributes":
                        divisions, time_sig_num, time_sig_den = apply_attributes(
                            elem, divisions, time_sig_num, time_sig_den
                        )
                        beat_unit_quarter_len = 4.0 / time_sig_den
                        full_bar_quarters = time_sig_num * beat_unit_quarter_len
                    elif elem.tag == "forward":
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

                        staff = int(elem.find("staff").text.strip()) if elem.find("staff") is not None else 1
                        voice = int(elem.find("voice").text.strip()) if elem.find("voice") is not None else 1

                        if is_rest:
                            step_name = "rest"
                            octave = None
                            midi_pitch = None
                            fret = None
                            string_num = None
                        else:
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
                            part_id=part_id,
                            part_name=part_name,
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

        return slices
