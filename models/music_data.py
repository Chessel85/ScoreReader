# models/music_data.py
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from models.event_slice import EventSlice
from models.note_data import NoteData
from models.parts_structure import PartStructureInfo
from parsers.timeline_builder import TimelineBuilder


@dataclass
class MusicData:
    score: Optional[Any] = None
    credits: Dict[str, str] = field(default_factory=dict)
    parts_info: List[PartStructureInfo] = field(default_factory=list)
    file_path: str = ""
    tempo_bpm: int = 120

    # Pre-parsed ElementTree root from MusicXMLReader, if it already parsed
    # the file - lets TimelineBuilder skip a second parse of the same file
    # (R2). None when a test builds MusicData(file_path=...) directly, in
    # which case TimelineBuilder parses the file itself as before.
    xml_root: Optional[Any] = None

    timeline_slices: List[EventSlice] = field(default_factory=list)
    active_event_index: int = 0

    # (part_id, staff, voice) tuples currently shown/played, set by Region 2
    # toggling (Ref 7). None means unfiltered - show everything. Must default
    # to None, not an empty set: most tests build MusicData directly or via
    # MusicXMLReader.load() without ever calling set_active_voice_filter, and
    # expect the full note list.
    active_voice_filter: Optional[Set[Tuple[str, int, int]]] = None

    def __post_init__(self):
        if self.file_path:
            self.timeline_slices = TimelineBuilder(
                self.file_path, self.parts_info, root=self.xml_root
            ).build()
            self.active_event_index = 0

    def get_current_slice(self) -> Optional[EventSlice]:
        if 0 <= self.active_event_index < len(self.timeline_slices):
            return self.timeline_slices[self.active_event_index]
        return None

    def _slice_has_visible_notes(self, index: int) -> bool:
        """True if timeline_slices[index] has at least one note passing the
        Region 2 filter (Ref 7). Lets timeline navigation skip slices that
        only contain notes from deactivated parts/staves/voices, so e.g.
        stepping through a still-active semibreve viola part isn't
        interrupted by a deactivated flute's crotchet-rate slices."""
        if not (0 <= index < len(self.timeline_slices)):
            return False
        notes = self.timeline_slices[index].notes
        if not notes:
            return False
        if self.active_voice_filter is None:
            return True
        return any(
            (n.part_id, n.staff, n.voice) in self.active_voice_filter for n in notes
        )

    def _slice_has_visible_sounding_note(self, index: int) -> bool:
        """True if timeline_slices[index] has at least one visible note that
        actually sounds (midi_pitch is not None) - i.e. is not a rest.

        Used to bound navigation to _sounding_bounds() below. A rest still
        counts as "visible" for _slice_has_visible_notes and remains
        individually reachable when it sits between two sounding notes
        (Ref 16), but a run of rests that only exists to pad the score's
        final bar out to a complete measure - live-tested on Chessel Duet's
        last bar, all voices resting after the final dotted crotchet - is
        not a further "active event" to step onto (Ref 2/3/5).
        """
        if not (0 <= index < len(self.timeline_slices)):
            return False
        notes = self.timeline_slices[index].notes
        if self.active_voice_filter is not None:
            notes = [
                n for n in notes
                if (n.part_id, n.staff, n.voice) in self.active_voice_filter
            ]
        return any(n.midi_pitch is not None for n in notes)

    def _sounding_bounds(self) -> Optional[Tuple[int, int]]:
        """(first, last) index of a visible event with a real sounding note.

        This is the true navigable range for Left/Right/Ctrl+Left/Right/
        Home/End - leading or trailing rest-only padding sits outside it.
        None if nothing currently visible sounds at all.
        """
        first_idx = None
        last_idx = None
        for i in range(len(self.timeline_slices)):
            if self._slice_has_visible_sounding_note(i):
                if first_idx is None:
                    first_idx = i
                last_idx = i
        if first_idx is None:
            return None
        return first_idx, last_idx

    def move_timeline_left(self) -> bool:
        bounds = self._sounding_bounds()
        if bounds is None:
            return False
        first_idx, _ = bounds
        idx = self.active_event_index
        while idx > first_idx:
            idx -= 1
            if self._slice_has_visible_notes(idx):
                self.active_event_index = idx
                return True
        return False

    def move_timeline_right(self) -> bool:
        bounds = self._sounding_bounds()
        if bounds is None:
            return False
        _, last_idx = bounds
        idx = self.active_event_index
        while idx < last_idx:
            idx += 1
            if self._slice_has_visible_notes(idx):
                self.active_event_index = idx
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

    def first_visible_event_index_of_measure(self, measure_number: int) -> Optional[int]:
        """Like first_event_index_of_measure, but skips slices with no note
        passing the active Region 2 filter (Ref 7) - keeps Ctrl+Left/Right
        (C2) sympathetic to what's actually visible, the same way plain
        Left/Right already are via _slice_has_visible_notes."""
        for i, s in enumerate(self.timeline_slices):
            if s.measure == measure_number and self._slice_has_visible_notes(i):
                return i
        return None

    def move_timeline_left_by_measure(self) -> bool:
        """Ctrl+Left (Ref 3): jump to the first visible event of the current
        measure, or the preceding measure's if already there. The pickup
        bar (measure 0, if present) falls out of this for free - it's just
        the first entry in measure_numbers(). Bounded by _sounding_bounds()
        the same way plain Left is, so a trailing rest-only measure (or the
        rest-only tail of one) is never a valid target."""
        current = self.get_current_slice()
        if current is None:
            return False

        bounds = self._sounding_bounds()
        if bounds is None:
            return False
        first_idx, last_idx = bounds

        measures = self.measure_numbers()
        try:
            pos = measures.index(current.measure)
        except ValueError:
            return False

        first_in_current = self.first_visible_event_index_of_measure(current.measure)
        if (
            first_in_current is not None
            and first_idx <= first_in_current <= last_idx
            and self.active_event_index != first_in_current
        ):
            self.active_event_index = first_in_current
            return True

        for prev_measure in reversed(measures[:pos]):
            target = self.first_visible_event_index_of_measure(prev_measure)
            if target is not None and first_idx <= target <= last_idx:
                self.active_event_index = target
                return True
        return False

    def move_timeline_right_by_measure(self) -> bool:
        """Ctrl+Right (Ref 3): jump to the first visible event of the next
        measure, skipping any measure left with no visible events or bounded
        out by _sounding_bounds() (e.g. a trailing rest-only final bar)."""
        current = self.get_current_slice()
        if current is None:
            return False

        bounds = self._sounding_bounds()
        if bounds is None:
            return False
        first_idx, last_idx = bounds

        measures = self.measure_numbers()
        try:
            pos = measures.index(current.measure)
        except ValueError:
            return False

        for next_measure in measures[pos + 1:]:
            target = self.first_visible_event_index_of_measure(next_measure)
            if target is not None and first_idx <= target <= last_idx:
                self.active_event_index = target
                return True
        return False

    def move_timeline_home(self) -> bool:
        """Home (Ref 5): jump to the first event with a real sounding note.

        Unlike Left/Right/Ctrl+Left/Right, this never represents "moving
        past a boundary" - it jumps to a known limit - so callers never play
        the boundary sound off this return value.
        """
        bounds = self._sounding_bounds()
        if bounds is None:
            return False
        self.active_event_index = bounds[0]
        return True

    def move_timeline_end(self) -> bool:
        """End (Ref 5): jump to the last event with a real sounding note -
        e.g. a final bar padded out with rests in every voice does not push
        this past the piece's actual last note."""
        bounds = self._sounding_bounds()
        if bounds is None:
            return False
        self.active_event_index = bounds[1]
        return True

    def get_region_1_data(self) -> Dict[str, str]:
        return self.credits

    def get_score_structure(self) -> List[Dict[str, Any]]:
        """Parts/staves/voices shape Region2HierarchyModel.build_from_score()
        documents - drives Region 2 (Ref 7). Pure transform of parts_info,
        no XML access."""
        structure = []
        for p in self.parts_info:
            staves = [
                {
                    "id": s_id,
                    "name": p.staves_clefs.get(s_id, "Standard stave"),
                    "voices": p.staves_voices[s_id],
                }
                for s_id in sorted(p.staves_voices.keys())
            ]
            structure.append({"id": p.part_id, "name": p.name, "staves": staves})
        return structure

    def set_active_voice_filter(self, active_tuples: Set[Tuple[str, int, int]]) -> None:
        self.active_voice_filter = set(active_tuples)

    def _visible_notes(self) -> List[NoteData]:
        """Notes at the current slice that pass the Region 2 filter (Ref 7).

        All of get_region_3_data/get_region_4_data_for_indices/
        get_midi_notes_for_indices/get_playback_events_for_indices read
        through this so a row index always means the same note everywhere -
        Region 3 only ever displays what this returns.
        """
        current = self.get_current_slice()
        if not current or not current.notes:
            return []
        if self.active_voice_filter is None:
            return current.notes
        return [
            n for n in current.notes
            if (n.part_id, n.staff, n.voice) in self.active_voice_filter
        ]

    def get_region_3_data(self) -> List[str]:
        notes = self._visible_notes()
        if not notes:
            return ["None"]
        return [n.step_name for n in notes]

    def get_region_4_data_for_indices(self, selected_indices: List[int]) -> Dict[str, str]:
        notes = self._visible_notes()
        if not notes or not selected_indices:
            return {"Status": "No note selected"}

        selected_notes = [
            notes[i] for i in selected_indices if 0 <= i < len(notes)
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
            data[f"{prefix}stave"] = self.get_stave_name_for_part(n.part_id, n.staff)
            data[f"{prefix}voice"] = str(n.voice)

            if n.string is not None:
                data[f"{prefix}string"] = str(n.string)
            if n.fret is not None:
                data[f"{prefix}fret"] = str(n.fret)

        return data

    def get_midi_notes_for_indices(self, selected_indices: List[int]) -> List[int]:
        notes = self._visible_notes()
        if not notes or not selected_indices:
            return []
        return [
            notes[i].midi_pitch
            for i in selected_indices
            if 0 <= i < len(notes) and notes[i].midi_pitch is not None
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

    def get_stave_name_for_part(self, part_id: str, staff: int) -> str:
        """Screen-reader-friendly stave name for Region 4, e.g. "Treble
        stave" or "C stave" - same wording Region 2 uses (Ref 7), so a note
        looked up in Region 4 matches the stave it was toggled under."""
        for p in self.parts_info:
            if p.part_id == part_id:
                return p.staves_clefs.get(staff, "Standard stave")
        return "Standard stave"

    def get_playback_events_for_indices(
        self, selected_indices: List[int]
    ) -> List[Tuple[int, int, List[int]]]:
        """Group selected notes by part for simultaneous multi-instrument playback.

        Each group is (channel, zero-indexed GM program, midi pitches) so a
        chord spanning two parts sounds both instruments together instead
        of collapsing onto parts_info[0]'s instrument (Ref 8, Ref 9 AC2).
        """
        notes = self._visible_notes()
        if not notes:
            return []

        notes_by_part: Dict[str, List[int]] = {}
        part_order: List[str] = []
        for i in selected_indices:
            if not (0 <= i < len(notes)):
                continue
            note = notes[i]
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