# models/music_data.py
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from models.event_slice import EventSlice
from models.key_signatures import FIFTHS_MAP
from models.note_data import NoteData
from models.parts_structure import PartStructureInfo
from models.tempo_change import TempoChange
from parsers.timeline_builder import TimelineBuilder


@dataclass
class MusicData:
    score: Optional[Any] = None
    credits: Dict[str, str] = field(default_factory=dict)
    parts_info: List[PartStructureInfo] = field(default_factory=list)
    file_path: str = ""
    tempo_bpm: int = 120

    # A9: tempo_bpm is always quarter-note BPM (music21's getQuarterBPM()),
    # for playback timing. tempo_beat_unit_quarter_length/name are the ratio
    # and label needed to convert that back to the score's OWN beat unit -
    # e.g. a score marked eighth=96 has tempo_bpm=48,
    # tempo_beat_unit_quarter_length=0.5, tempo_beat_unit_name="eighth", so
    # 48 / 0.5 = 96, matching what Region 1 already displays (A9's
    # tempo_display string) instead of the internal 48. Needed live (not
    # just once for Region 1's summary) by E1-E3's tempo offset/F/S/D/dialog
    # - reported bug, live-tested: the status bar and Tempo Offset dialog
    # were showing/accepting the raw quarter-BPM number, not the score's own
    # displayed tempo.
    tempo_beat_unit_quarter_length: float = 1.0
    tempo_beat_unit_name: str = "quarter"

    # Ref 12: playback tempo is a temporary offset from the score's own
    # tempo, never a mutation of tempo_bpm itself (AC1) - Region 1 keeps
    # showing the score-defined tempo unchanged regardless of this offset.
    # Stored in the score's own DISPLAY units (see above), not quarter-note
    # terms, so F/S's "+10" means +10 in what the user actually sees/reads.
    playback_tempo_offset: float = 0.0

    # Ref 12 "multi-tempo scope": every tempo marking after the first,
    # sorted by position - populated from TimelineBuilder as a side effect
    # of build() (see __post_init__). tempo_bpm/tempo_beat_unit_* above
    # remain the score's opening tempo (what Region 1's one-off summary
    # shows); this list is what makes the status bar/dialog/Sequencer look
    # up the tempo actually in effect at a given position instead of always
    # that opening one.
    tempo_changes: List[TempoChange] = field(default_factory=list)

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

    # Ref 15 AC4: extra Region 4 attributes (beyond the always-toggleable
    # "step") appended to a note's Region 3 display, keyed the same way
    # active_voice_filter is. A voice absent from this dict uses
    # DEFAULT_DISPLAY_ATTRIBUTES, NOT an empty set - most voices are never
    # touched by the F-phase context menu and must keep showing today's
    # plain note name.
    voice_display_attributes: Dict[Tuple[str, int, int], Set[str]] = field(default_factory=dict)

    # E8/Ref 14: off by default per score load (MusicData is reconstructed
    # fresh on every _on_score_loaded, so no explicit reset code is needed
    # elsewhere, same as playback_tempo_offset above). Gates both whether a
    # beat position sounds a click (Sequencer, MainWindow) and whether a
    # beat position with no note counts as a navigable event at all
    # (_slice_is_navigable, Ref 14 AC4).
    metronome_enabled: bool = False

    def __post_init__(self):
        if self.file_path:
            builder = TimelineBuilder(self.file_path, self.parts_info, root=self.xml_root)
            self.timeline_slices = builder.build()
            self.tempo_changes = builder.tempo_changes
            self._beat_markers = builder.beat_markers
            self.active_event_index = 0
        else:
            self._beat_markers: List[EventSlice] = []
        # The real, marker-free timeline - kept stable so
        # set_metronome_enabled can always restore exactly this when the
        # metronome turns back off, even after self.timeline_slices has been
        # replaced with a merged (real + marker) view while it was on.
        self._real_timeline_slices = self.timeline_slices
        # measure_numbers() is safe to cache forever - timeline_slices is
        # never reassigned after this point. The other two are keyed off
        # active_voice_filter and are invalidated in
        # _invalidate_visibility_cache below.
        self._measure_numbers_cache: Optional[List[int]] = None
        self._invalidate_visibility_cache()

    def _invalidate_visibility_cache(self) -> None:
        """_sounding_bounds() and first_visible_event_index_of_measure() used
        to re-walk the whole timeline from scratch on every single
        navigation keypress (and move_timeline_*_by_measure called the
        latter once per measure scanned, i.e. O(N) per measure => O(N*M)
        worst case for a long run of filtered-out measures). Both are
        cached here instead and only recomputed the first time they're
        needed after active_voice_filter changes."""
        self._sounding_bounds_cache: Optional[Tuple[int, int]] = None
        self._sounding_bounds_computed: bool = False
        self._first_visible_index_by_measure_cache: Optional[Dict[int, int]] = None

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

    def set_metronome_enabled(self, enabled: bool) -> None:
        """E8/Ref 14 toggle.

        timeline_slices itself is rebuilt here rather than being a
        permanently-merged list: with the metronome off (the default),
        timeline_slices stays exactly "one entry per (measure, offset) with
        at least one sounding note" - the invariant the rest of the codebase
        (and a good number of existing tests) already assume, unaffected by
        this feature ever existing. Only turning the metronome on splices in
        the synthetic beat markers TimelineBuilder computed separately
        (_beat_markers); turning it back off restores the untouched real
        list. The cursor is relocated to the same real position across the
        rebuild (indices shift once markers are spliced in) rather than
        left pointing at an arbitrary slice.
        """
        if enabled == self.metronome_enabled:
            return

        current = self.get_current_slice()
        self.metronome_enabled = enabled

        if enabled:
            merged = list(self._real_timeline_slices) + list(self._beat_markers)
            merged.sort(key=lambda s: (s.measure, s.quarters_from_start))
            self.timeline_slices = merged
        else:
            self.timeline_slices = self._real_timeline_slices

        if current is not None and self.timeline_slices:
            # Last slice at or before the current position - exact match
            # when one exists (toggling on, or off from a real slice),
            # nearest preceding real event when it doesn't (toggling off
            # while sitting on a marker, which has no counterpart at all in
            # the real-only list) - i.e. wherever the cursor would be had
            # the metronome never been turned on.
            match_index = 0
            for i, s in enumerate(self.timeline_slices):
                if s.quarters_from_start <= current.quarters_from_start:
                    match_index = i
                else:
                    break
            self.active_event_index = match_index

        self._invalidate_visibility_cache()

    def toggle_metronome(self) -> None:
        self.set_metronome_enabled(not self.metronome_enabled)

    def _slice_is_navigable(self, index: int) -> bool:
        """Ref 14 AC4: with the metronome on, a beat position counts as a
        navigable/steppable event even where no note sounds there - a whole
        beat is always a whole number in the score's own ts-relative units
        (Ref 18), whether it's a real note's own beat_position or one of the
        synthetic click-only markers TimelineBuilder bakes in for exactly
        this purpose. Used in place of _slice_has_visible_notes at every
        navigation/stepping call site (Left/Right, Ctrl+Left/Right,
        jump-to-measure, and the Sequencer's own step walk) - NOT at
        _slice_has_visible_sounding_note/_sounding_bounds below, which stay
        anchored to real sounding notes only so metronome mode can't
        resurrect trailing rest-only padding as navigable."""
        if self._slice_has_visible_notes(index):
            return True
        if not self.metronome_enabled:
            return False
        return float(self.timeline_slices[index].beat_position).is_integer()

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
        None if nothing currently visible sounds at all. Cached per
        active_voice_filter state - see _invalidate_visibility_cache.
        """
        if not self._sounding_bounds_computed:
            first_idx = None
            last_idx = None
            for i in range(len(self.timeline_slices)):
                if self._slice_has_visible_sounding_note(i):
                    if first_idx is None:
                        first_idx = i
                    last_idx = i
            self._sounding_bounds_cache = (
                (first_idx, last_idx) if first_idx is not None else None
            )
            self._sounding_bounds_computed = True
        return self._sounding_bounds_cache

    def move_timeline_left(self) -> bool:
        bounds = self._sounding_bounds()
        if bounds is None:
            return False
        first_idx, _ = bounds
        idx = self.active_event_index
        while idx > first_idx:
            idx -= 1
            if self._slice_is_navigable(idx):
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
            if self._slice_is_navigable(idx):
                self.active_event_index = idx
                return True
        return False

    def measure_numbers(self) -> List[int]:
        """Distinct measure numbers present in the timeline, in ascending
        order. Cached forever - timeline_slices is fixed after construction."""
        if self._measure_numbers_cache is None:
            self._measure_numbers_cache = list(
                dict.fromkeys(s.measure for s in self.timeline_slices)
            )
        return self._measure_numbers_cache

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

    def _first_visible_index_by_measure(self) -> Dict[int, int]:
        """measure_number -> index of its first visible event. Cached per
        active_voice_filter state (see _invalidate_visibility_cache) so
        move_timeline_*_by_measure's walk over several measures is O(1) per
        measure instead of re-scanning the whole timeline each time."""
        if self._first_visible_index_by_measure_cache is None:
            cache: Dict[int, int] = {}
            for i, s in enumerate(self.timeline_slices):
                if s.measure not in cache and self._slice_is_navigable(i):
                    cache[s.measure] = i
            self._first_visible_index_by_measure_cache = cache
        return self._first_visible_index_by_measure_cache

    def first_visible_event_index_of_measure(self, measure_number: int) -> Optional[int]:
        """Like first_event_index_of_measure, but skips slices with no note
        passing the active Region 2 filter (Ref 7) - keeps Ctrl+Left/Right
        (C2) sympathetic to what's actually visible, the same way plain
        Left/Right already are via _slice_has_visible_notes."""
        return self._first_visible_index_by_measure().get(measure_number)

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

    def jump_to_measure(self, measure_number: int) -> bool:
        """Ref 6: jump to the first visible event of measure_number, typed
        digit-by-digit in the Note region (C4). Bounded by _sounding_bounds()
        the same way move_timeline_*_by_measure is, so a measure that exists
        only as trailing rest-only padding is not a valid target either.
        False (position unchanged) for an unknown measure number - callers
        play the boundary cue (AC4)."""
        bounds = self._sounding_bounds()
        if bounds is None:
            return False
        first_idx, last_idx = bounds

        target = self.first_visible_event_index_of_measure(measure_number)
        if target is None or not (first_idx <= target <= last_idx):
            return False

        self.active_event_index = target
        return True

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

    def last_sounding_event_index(self) -> Optional[int]:
        """Index of the last visible event with a real sounding note, or
        None if nothing currently sounds - the true end of playable content
        (C5), excluding trailing rest-only padding. Used by phrase audition
        (E6) to bound how far a run can play, the same way Home/End (C3)
        already bound navigation."""
        bounds = self._sounding_bounds()
        return bounds[1] if bounds else None

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
        self._invalidate_visibility_cache()

    def _visible_notes(self, index: Optional[int] = None) -> List[NoteData]:
        """Notes at the given slice that pass the Region 2 filter (Ref 7),
        or at the current cursor position when index is None (the default,
        used by every UI-facing accessor).

        All of get_region_3_data/get_region_4_data_for_indices/
        get_midi_notes_for_indices/get_playback_events_for_indices read
        through this so a row index always means the same note everywhere -
        Region 3 only ever displays what this returns. The explicit-index
        form is for the Sequencer (E4), which plays slices by absolute
        timeline index without disturbing active_event_index/Region 3's
        selection (so phrase audition, E6, can leave the cursor untouched).
        """
        if index is None:
            current = self.get_current_slice()
        else:
            current = self.timeline_slices[index] if 0 <= index < len(self.timeline_slices) else None
        if not current or not current.notes:
            return []
        if self.active_voice_filter is None:
            return current.notes
        return [
            n for n in current.notes
            if (n.part_id, n.staff, n.voice) in self.active_voice_filter
        ]

    # Ref 15 AC4: fixed rendering order for Region 3's optional extra
    # attributes - same key set/order Region 4's rows already use.
    # Attribute-ordering customization (F2) is deferred; this list is the
    # only order that exists for now.
    DISPLAY_ATTRIBUTE_ORDER = [
        "step", "octave", "midi", "measure", "beat position", "duration",
        "part", "stave", "voice", "string", "fret",
    ]
    # A voice with no entry in voice_display_attributes uses this - today's
    # plain-note-name behaviour, not an empty display.
    DEFAULT_DISPLAY_ATTRIBUTES = frozenset({"step"})

    def notes_for_indices(self, selected_indices: List[int]) -> List[NoteData]:
        """The real NoteData objects behind Region 3's selected row indices -
        shared by get_region_4_row_targets and the Ref 15 AC4 attribute-scope
        actions (main_window.py), which need the notes themselves rather
        than just indices or playback pitches."""
        notes = self._visible_notes()
        return [notes[i] for i in selected_indices if 0 <= i < len(notes)]

    def _note_attribute_pairs(self, note: NoteData) -> Dict[str, str]:
        """Un-prefixed attribute-name -> value for one note. Shared by
        _region_4_rows (Region 4, "note N "-prefixed when more than one note
        is selected) and _format_note_for_region_3 (Ref 15 AC4's optional
        extra attributes) so the two regions can never disagree on an
        attribute's name or value. Only includes keys that actually have a
        value for this note (e.g. a rest has no octave/midi) - the absence
        of a key here is what keeps both a Region 4 row and a Region 3
        attribute from ever being rendered for data that doesn't exist."""
        dur_str = str(int(note.ts_duration)) if note.ts_duration.is_integer() else str(note.ts_duration)
        pairs = {"step": note.step_name}
        if note.octave is not None:
            pairs["octave"] = str(note.octave)
        if note.midi_pitch is not None:
            pairs["midi"] = str(note.midi_pitch)
        pairs["measure"] = str(note.measure)
        pairs["beat position"] = str(note.beat_position)
        pairs["duration"] = dur_str
        pairs["part"] = note.part_name
        pairs["stave"] = self.get_stave_name_for_part(note.part_id, note.staff)
        pairs["voice"] = str(note.voice)
        if note.string is not None:
            pairs["string"] = str(note.string)
        if note.fret is not None:
            pairs["fret"] = str(note.fret)
        return pairs

    def _region_4_rows(self, selected_notes: List[NoteData]) -> List[Tuple[str, str, NoteData, str]]:
        """(display_key, attribute_key, note, value) per Region 4 row, in
        display order - display_key carries the "note N " prefix used when
        more than one note is selected (a chord), attribute_key never does.
        Shared source for get_region_4_data_for_indices (the dict Region 4
        renders) and get_region_4_row_targets (which row maps to which
        note/attribute, for the Ref 15 AC4 context menu)."""
        is_chord = len(selected_notes) > 1
        rows = []
        for idx, n in enumerate(selected_notes, start=1):
            prefix = f"note {idx} " if is_chord else ""
            for attribute_key, value in self._note_attribute_pairs(n).items():
                rows.append((f"{prefix}{attribute_key}", attribute_key, n, value))
        return rows

    def _format_note_for_region_3(self, note: NoteData) -> str:
        """Ref 15 AC4: the note's name plus whichever extra attributes are
        configured on for its voice, comma-separated. An attribute is
        skipped both when it's not in the voice's configured set AND when
        the note has no value for it (e.g. octave on a rest) - the latter is
        what stops a missing attribute from leaving a dangling/double comma.
        An all-off voice (including "step" removed) renders "" - a blank but
        still selectable, still-audible Region 3 row."""
        voice_key = (note.part_id, note.staff, note.voice)
        wanted = self.voice_display_attributes.get(voice_key, self.DEFAULT_DISPLAY_ATTRIBUTES)
        pairs = self._note_attribute_pairs(note)
        parts = []
        for key in self.DISPLAY_ATTRIBUTE_ORDER:
            if key not in wanted or key not in pairs:
                continue
            parts.append(pairs[key] if key == "step" else f"{key} {pairs[key]}")
        return ", ".join(parts)

    def get_region_3_data(self) -> List[str]:
        notes = self._visible_notes()
        if not notes:
            current = self.get_current_slice()
            if (
                self.metronome_enabled
                and current is not None
                and float(current.beat_position).is_integer()
            ):
                return ["Click"]
            return ["None"]
        return [self._format_note_for_region_3(n) for n in notes]

    def get_region_4_data_for_indices(self, selected_indices: List[int]) -> Dict[str, str]:
        selected_notes = self.notes_for_indices(selected_indices)
        if not selected_notes:
            return {"Status": "No note selected"}
        return {
            display_key: value
            for display_key, _, _, value in self._region_4_rows(selected_notes)
        }

    def get_region_4_row_targets(self, selected_indices: List[int]) -> List[Tuple[str, NoteData]]:
        """(attribute_key, note) per Region 4 row, in the same order as
        get_region_4_data_for_indices - lets MainWindow map "the Region 4 row
        the context menu was opened on" back to what it should toggle
        (Ref 15 AC4)."""
        selected_notes = self.notes_for_indices(selected_indices)
        if not selected_notes:
            return []
        return [
            (attribute_key, note)
            for _, attribute_key, note, _ in self._region_4_rows(selected_notes)
        ]

    def note_has_display_attribute(self, note: NoteData, attribute_key: str) -> bool:
        """Whether `note`'s own voice currently shows `attribute_key` in
        Region 3 - drives the Add-vs-Remove variant of the Ref 15 AC4
        context menu."""
        voice_key = (note.part_id, note.staff, note.voice)
        return attribute_key in self.voice_display_attributes.get(voice_key, self.DEFAULT_DISPLAY_ATTRIBUTES)

    def _voice_tuples_for_scope(self, note: NoteData, scope: str) -> Set[Tuple[str, int, int]]:
        """Every (part_id, staff, voice) tuple `scope` fans out to from
        `note`'s own position - "voice" is just the note's own tuple,
        "stave"/"part" walk parts_info's staves_voices for siblings, "score"
        is every voice in every part. Ref 15 AC4."""
        if scope == "voice":
            return {(note.part_id, note.staff, note.voice)}
        if scope == "score":
            return {
                (p.part_id, s, v)
                for p in self.parts_info
                for s, vs in p.staves_voices.items()
                for v in vs
            }
        part = next((p for p in self.parts_info if p.part_id == note.part_id), None)
        if part is None:
            return {(note.part_id, note.staff, note.voice)}
        if scope == "stave":
            return {(note.part_id, note.staff, v) for v in part.staves_voices.get(note.staff, [])}
        if scope == "part":
            return {
                (note.part_id, s, v)
                for s, vs in part.staves_voices.items()
                for v in vs
            }
        raise ValueError(f"Unknown display-attribute scope: {scope!r}")

    def set_display_attribute(
        self, attribute_key: str, scope: str, notes: List[NoteData], add: bool
    ) -> None:
        """Ref 15 AC4: add or remove `attribute_key` from Region 3's display
        for every voice `scope` ("voice"/"stave"/"part"/"score") reaches from
        each note in `notes` - plural because a multi-note Region 3 selection
        (a chord) unions the scope across every selected note, e.g. a
        stave-scope action from a two-part chord affects both parts' staves,
        not just the one the context menu happened to be opened on."""
        voice_keys: Set[Tuple[str, int, int]] = set()
        for note in notes:
            voice_keys |= self._voice_tuples_for_scope(note, scope)
        for voice_key in voice_keys:
            current = set(self.voice_display_attributes.get(voice_key, self.DEFAULT_DISPLAY_ATTRIBUTES))
            if add:
                current.add(attribute_key)
            else:
                current.discard(attribute_key)
            self.voice_display_attributes[voice_key] = current

    def get_midi_notes_for_indices(self, selected_indices: List[int]) -> List[int]:
        notes = self._visible_notes()
        if not notes or not selected_indices:
            return []
        return [
            notes[i].midi_pitch
            for i in selected_indices
            if 0 <= i < len(notes) and notes[i].midi_pitch is not None
        ]

    # Ref 12 AC2: hard playback tempo boundaries, expressed in the score's
    # own DISPLAY units (tempo_beat_unit_name) - what the user actually
    # reads and types, not the internal quarter-note equivalent.
    MIN_TEMPO_BPM = 30
    MAX_TEMPO_BPM = 300

    def _tempo_change_at(self, index: Optional[int] = None) -> Tuple[int, float, str]:
        """(tempo_bpm, beat_unit_quarter_length, beat_unit_name) actually in
        effect at the given timeline index, or the cursor (active_event_index)
        when index is None - the same default-to-cursor convention
        _visible_notes uses. Falls back to the score's opening tempo
        (tempo_bpm/tempo_beat_unit_*) when tempo_changes is empty or the
        position is before the first marking (Ref 12 "multi-tempo scope").
        tempo_changes is kept sorted by quarters_from_start (TimelineBuilder's
        job), so the last entry not past the position wins."""
        idx = self.active_event_index if index is None else index
        quarters = self.timeline_slices[idx].quarters_from_start if 0 <= idx < len(self.timeline_slices) else 0.0

        result = (self.tempo_bpm, self.tempo_beat_unit_quarter_length, self.tempo_beat_unit_name)
        for change in self.tempo_changes:
            if change.quarters_from_start > quarters:
                break
            result = (change.tempo_bpm, change.beat_unit_quarter_length, change.beat_unit_name)
        return result

    def score_tempo_display_bpm(self, index: Optional[int] = None) -> float:
        """The tempo actually in effect at `index` (or the cursor), in the
        beat unit it was authored in (A9) - e.g. 96 for a passage marked
        eighth=96, not the quarter-note-equivalent BPM used internally for
        playback timing."""
        bpm, beat_unit_ql, _ = self._tempo_change_at(index)
        return bpm / beat_unit_ql

    def effective_tempo_display_bpm(self, index: Optional[int] = None) -> float:
        """score_tempo_display_bpm() plus the current offset - what F/S/D,
        the status bar and the Tempo Offset dialog show and read (Ref 12),
        in the same units Region 1 already displays the score's tempo in
        (A9). playback_tempo_offset is stored in these display units
        directly (not quarter-note terms) precisely so this is a plain sum."""
        return self.score_tempo_display_bpm(index) + self.playback_tempo_offset

    def effective_tempo_bpm(self, index: Optional[int] = None) -> float:
        """Quarter-note BPM for real playback timing (Sequencer,
        get_duration_ms_for_index) - converts the display-unit offset back
        to quarter-note terms via whichever beat unit is in effect at
        `index`."""
        bpm, beat_unit_ql, _ = self._tempo_change_at(index)
        display = bpm / beat_unit_ql + self.playback_tempo_offset
        return display * beat_unit_ql

    def tempo_beat_unit_name_at(self, index: Optional[int] = None) -> str:
        """The beat unit label (e.g. "eighth") in effect at `index` (or the
        cursor) - lets the status bar show the right unit even where a
        mid-score tempo marking changes beat unit, not just the number."""
        _, _, name = self._tempo_change_at(index)
        return name

    def set_playback_tempo_offset(self, offset: float) -> None:
        """Clamp offset so effective_tempo_display_bpm() always stays within
        [MIN_TEMPO_BPM, MAX_TEMPO_BPM] (Ref 12 AC2) - the boundary the user
        actually reads/types, not tempo_bpm's internal quarter-note
        equivalent - without ever touching tempo_bpm itself (AC1). Clamped
        against whichever tempo is in effect at the cursor right now (Ref 12
        "multi-tempo scope": F/S/D and this dialog add/subtract from
        "whatever the current tempo is", which can change mid-score)."""
        base = self.score_tempo_display_bpm()
        min_offset = self.MIN_TEMPO_BPM - base
        max_offset = self.MAX_TEMPO_BPM - base
        self.playback_tempo_offset = max(min_offset, min(max_offset, offset))

    def reset_playback_tempo(self) -> None:
        """Ref 12 AC4: reset control returns to the score's own tempo."""
        self.playback_tempo_offset = 0.0

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
        self, selected_indices: List[int], index: Optional[int] = None
    ) -> List[Tuple[int, int, List[int]]]:
        """Group selected notes by part for simultaneous multi-instrument playback.

        Each group is (channel, zero-indexed GM program, midi pitches) so a
        chord spanning two parts sounds both instruments together instead
        of collapsing onto parts_info[0]'s instrument (Ref 8, Ref 9 AC2).

        index: an explicit timeline slice to read from instead of the
        current cursor (see _visible_notes) - used by
        get_playback_events_at_index (E4/Sequencer).
        """
        notes = self._visible_notes(index)
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
        return self.get_duration_ms_for_index(self.active_event_index)

    def get_duration_ms_for_index(self, index: int) -> int:
        """Like get_current_duration_ms, but for an arbitrary timeline index
        rather than the cursor - used by the Sequencer (E4)."""
        if not (0 <= index < len(self.timeline_slices)):
            return 500
        quarter_length = self.timeline_slices[index].quarter_length
        ms = (quarter_length * 60000.0) / float(self.effective_tempo_bpm(index))
        return max(100, int(ms))

    def get_playback_events_at_index(self, index: int) -> List[Tuple[int, int, List[int]]]:
        """All visible notes at timeline index `index`, grouped by part
        (Ref 8) - the Sequencer (E4) equivalent of
        get_playback_events_for_indices for Region 3's selection, playing a
        slice by absolute index independent of active_event_index."""
        notes = self._visible_notes(index)
        if not notes:
            return []
        return self.get_playback_events_for_indices(list(range(len(notes))), index=index)

    def next_visible_event_index(
        self, index: int, end_index: Optional[int] = None
    ) -> Optional[int]:
        """Next timeline index after `index` with at least one note passing
        the active Region 2 filter (Ref 7) - rests included, unlike
        _sounding_bounds()'s navigation range, since real playback (E4)
        should advance through and take up the time of a rest, not skip
        over it. Also visits metronome-only beat markers when the metronome
        is on (_slice_is_navigable, Ref 14 AC1) - this is what makes the
        Sequencer's own step walk sound a click on a silent beat with no
        extra scheduling logic. Bounded by end_index (inclusive) if given,
        else the whole timeline. None if there is no further visible event -
        the Sequencer treats that as the end of playback."""
        limit = end_index if end_index is not None else len(self.timeline_slices) - 1
        idx = index
        while idx < limit:
            idx += 1
            if self._slice_is_navigable(idx):
                return idx
        return None

    def get_status_bar_fields(self) -> List[str]:
        """C6/E2: four fields in Tab order for the status bar - measure/beat
        position, key signature, time signature and playback tempo. All four
        read from the *current* slice/position rather than the score's
        opening values, since any of them can change mid-score (D-11, Ref 12
        "multi-tempo scope") unlike Region 1's one-off summary. The tempo
        field is the one place a screen-reader user can check the current
        playback tempo without a forced announcement (Phase D deliberately
        skipped for now)."""
        current = self.get_current_slice()
        if current is None:
            return ["Measure - beat -", "Key: -", "Time: -", self._tempo_status_field()]

        beat = current.beat_position
        beat_str = str(int(beat)) if float(beat).is_integer() else str(beat)
        ts_num, ts_den = current.time_sig
        key_name = FIFTHS_MAP.get(current.key_fifths, f"{current.key_fifths} sharps/flats")

        return [
            f"Measure {current.measure} beat {beat_str}",
            f"Key: {key_name}",
            f"Time: {ts_num}/{ts_den}",
            self._tempo_status_field(),
        ]

    def _tempo_status_field(self) -> str:
        """Reported bug, live-tested: this used to show effective_tempo_bpm()
        (the internal quarter-note-equivalent value, e.g. 48 for a score
        marked eighth=96) instead of the score's own display units (96) -
        the same units Region 1's tempo credit already uses (A9). Now reads
        through effective_tempo_display_bpm() so the two stay consistent."""
        effective = self.effective_tempo_display_bpm()
        effective_str = str(int(effective)) if float(effective).is_integer() else str(round(effective, 2))
        unit = f"{self.tempo_beat_unit_name_at()} notes per minute"
        if self.playback_tempo_offset == 0.0:
            return f"Playback tempo: {effective_str} {unit} (score default)"
        return f"Playback tempo: {effective_str} {unit}"