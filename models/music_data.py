# models/music_data.py
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from models.event_slice import EventSlice
from models.parts_structure import PartStructureInfo
from parsers.timeline_builder import TimelineBuilder


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
            self.timeline_slices = TimelineBuilder(self.file_path, self.parts_info).build()
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

    def measure_numbers(self) -> List[int]:
        """Distinct measure numbers present in the timeline, in ascending order."""
        return list(dict.fromkeys(s.measure for s in self.timeline_slices))

    def first_event_index_of_measure(self, measure_number: int) -> Optional[int]:
        """Index of the first timeline event in the given measure.

        None if that measure has no events - e.g. Ref 6: an unknown bar
        plays an error sound and does not move.
        """
        for i, s in enumerate(self.timeline_slices):
            if s.measure == measure_number:
                return i
        return None

    def last_event_index(self) -> int:
        """Index of the last timeline event, or -1 if the timeline is empty."""
        return len(self.timeline_slices) - 1

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
            if n.octave is not None:
                data[f"{prefix}octave"] = str(n.octave)
            if n.midi_pitch is not None:
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
            if 0 <= i < len(current.notes) and current.notes[i].midi_pitch is not None
        ]

    # MIDI channel 10 (0-indexed 9) is reserved for percussion and must be
    # skipped when allocating one channel per part (D-5).
    PERCUSSION_CHANNEL = 9
    MAX_MIDI_CHANNELS = 16

    def get_channel_for_part(self, part_id: str) -> int:
        """One MIDI channel per part, in part-list order, skipping percussion.

        Wraps past the percussion channel if a score has more than 15
        melodic parts - the hard ceiling is 16 channels (D-5).
        """
        for idx, p in enumerate(self.parts_info):
            if p.part_id == part_id:
                channel = idx if idx < self.PERCUSSION_CHANNEL else idx + 1
                return channel % self.MAX_MIDI_CHANNELS
        return 0

    def get_gmidi_program_for_part(self, part_id: str) -> int:
        for p in self.parts_info:
            if p.part_id == part_id:
                return p.gmidi_program
        return 25

    def get_playback_events_for_indices(
        self, selected_indices: List[int]
    ) -> List[Tuple[int, int, List[int]]]:
        """Group selected notes by part for simultaneous multi-instrument playback.

        Each group is (channel, zero-indexed GM program, midi pitches) so a
        chord spanning two parts sounds both instruments together instead
        of collapsing onto parts_info[0]'s instrument (Ref 8, Ref 9 AC2).
        """
        current = self.get_current_slice()
        if not current or not current.notes:
            return []

        notes_by_part: Dict[str, List[int]] = {}
        part_order: List[str] = []
        for i in selected_indices:
            if not (0 <= i < len(current.notes)):
                continue
            note = current.notes[i]
            if note.midi_pitch is None:
                continue
            if note.part_id not in notes_by_part:
                notes_by_part[note.part_id] = []
                part_order.append(note.part_id)
            notes_by_part[note.part_id].append(note.midi_pitch)

        events = []
        for part_id in part_order:
            channel = self.get_channel_for_part(part_id)
            program = max(0, self.get_gmidi_program_for_part(part_id) - 1)
            events.append((channel, program, notes_by_part[part_id]))
        return events

    def get_current_duration_ms(self) -> int:
        current = self.get_current_slice()
        if not current:
            return 500
        ms = (current.quarter_length * 60000.0) / float(self.tempo_bpm)
        return max(100, int(ms))