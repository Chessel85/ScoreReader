# music_data.py
from dataclasses import dataclass, field
from typing import Any, Dict, List
import music21


@dataclass
class MusicData:
    # Region 1: Dynamic dictionary of all credit-type entries
    credits: Dict[str, str] = field(default_factory=dict)

    # Region 2 structural data: {part_name: {staff_id: [voice_ids]}}
    structure: Dict[str, Dict[int, List[int]]] = field(default_factory=dict)

    # Internal music21 score reference
    score: music21.stream.Score | None = None

    # Timeline event state tracking
    timeline_notes: List[music21.note.Note] = field(default_factory=list)
    active_note_index: int = 0

    def __post_init__(self):
        self._build_timeline()

    def _build_timeline(self):
        """Flattens all note elements in the score into a sequential timeline list."""
        if self.score is None:
            self.timeline_notes = []
            return

        notes = []
        for element in self.score.recurse().notes:
            if element.isChord:
                notes.append(element.notes[0])
            elif element.isNote:
                notes.append(element)

        self.timeline_notes = notes
        self.active_note_index = 0

    def get_current_note(self) -> music21.note.Note | None:
        """Returns the note element at the current active timeline index."""
        if 0 <= self.active_note_index < len(self.timeline_notes):
            return self.timeline_notes[self.active_note_index]
        return None

    def move_timeline_left(self) -> bool:
        """Move one event backward along the timeline. Returns True if position changed."""
        if self.active_note_index > 0:
            self.active_note_index -= 1
            return True
        return False

    def move_timeline_right(self) -> bool:
        """Move one event forward along the timeline. Returns True if position changed."""
        if self.active_note_index < len(self.timeline_notes) - 1:
            self.active_note_index += 1
            return True
        return False

    def get_region_1_data(self) -> Dict[str, str]:
        return self.credits

    def get_region_2_data(self) -> Dict[str, str]:
        region_2_dict = {}
        for part_name, staves in self.structure.items():
            if staves:
                staff_labels = [f"Staff {s}" for s in sorted(staves.keys())]
                region_2_dict[part_name] = ", ".join(staff_labels)
            else:
                region_2_dict[part_name] = "Staff 1"

            for staff_id in sorted(staves.keys()):
                voices = staves[staff_id]
                voice_label = (
                    f"Voices {', '.join(map(str, voices))}"
                    if len(voices) > 1
                    else f"Voice {voices[0]}" if voices else "Voice 1"
                )
                region_2_dict[f"  └─ Staff {staff_id}"] = voice_label

        return region_2_dict

    def _format_note_name_for_speech(self, note: music21.note.Note) -> str:
        """Formats pitch name with explicit words ('sharp', 'flat') for screen reader clarity."""
        step = note.pitch.step
        accidental = note.pitch.accidental

        if accidental is None or accidental.name == "natural":
            return step

        accidental_name = accidental.name.lower()
        if accidental_name == "sharp":
            return f"{step} sharp"
        elif accidental_name == "flat":
            return f"{step} flat"
        else:
            return f"{step} {accidental_name}"

    def get_region_3_data(self) -> List[str]:
        """Returns a single clean note name string for Region 3."""
        note = self.get_current_note()
        if note is None:
            return ["No events"]

        return [self._format_note_name_for_speech(note)]

    def get_region_4_data(self) -> Dict[str, str]:
        """Returns detailed metadata properties for the active timeline note."""
        note = self.get_current_note()
        if note is None:
            return {"Status": "No note selected"}

        pitch = note.pitch

        # 1-based measure calculation
        measure_num = note.measureNumber
        if measure_num is None:
            measure_num = 1

        # 1-based position offset calculation
        one_based_position = note.offset + 1.0

        return {
            "Step": pitch.step,
            "Octave": str(pitch.octave),
            "MIDI Pitch": str(pitch.midi),
            "Measure": str(measure_num),
            "Position (Beats)": str(one_based_position),
            "Duration (Quarter)": str(note.duration.quarterLength),
            "Type": note.duration.type.capitalize(),
        }