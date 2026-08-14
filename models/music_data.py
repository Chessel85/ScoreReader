# models/music_data.py
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from models import vocabulary
from models.ending_span import EndingSpan
from models.event_slice import EventSlice
from models.hairpin_span import HairpinSpan
from models.key_signatures import FIFTHS_MAP
from models.note_data import NoteData
from models.parts_structure import PartStructureInfo
from models.performance_region_row import PerformanceRegionRow
from models.repeat_span import RepeatSpan
from models.score_config_data import ScoreConfig
from models.tempo_change import TempoChange
from parsers.timeline_builder import TimelineBuilder


@dataclass
class MusicData:
    score: Optional[Any] = None
    credits: Dict[str, str] = field(default_factory=dict)
    parts_info: List[PartStructureInfo] = field(default_factory=list)
    file_path: str = ""
    tempo_bpm: int = 120

    # A9: tempo_bpm is ALWAYS quarter-note BPM (playback timing).
    # tempo_beat_unit_* are the ratio and label converting it back to the
    # score's own beat unit - a score marked eighth=96 has tempo_bpm=48 and
    # quarter_length=0.5, so 48/0.5 = 96, the number the user actually
    # reads. Anything user-facing (Region 1, status bar, tempo dialog, F/S/D)
    # must go through the display units, never the raw quarter BPM.
    tempo_beat_unit_quarter_length: float = 1.0
    tempo_beat_unit_name: str = "quarter"

    # Ref 12 AC1: a temporary offset from the score's tempo, never a
    # mutation of tempo_bpm - Region 1 keeps showing the score's own tempo.
    # Stored in DISPLAY units (see above) so F/S's "+10" means +10 of what
    # the user reads.
    playback_tempo_offset: float = 0.0

    # Ref 12 multi-tempo scope: every tempo marking after the first, sorted
    # by position, from TimelineBuilder. tempo_bpm above stays the OPENING
    # tempo (Region 1's summary); this list is what lets the status bar,
    # dialog and Sequencer use the tempo actually in effect at a position.
    tempo_changes: List[TempoChange] = field(default_factory=list)

    # Pre-parsed ElementTree root from MusicXMLReader, so TimelineBuilder
    # need not re-parse. None when MusicData(file_path=...) is built
    # directly, in which case TimelineBuilder parses the file itself.
    xml_root: Optional[Any] = None

    timeline_slices: List[EventSlice] = field(default_factory=list)
    active_event_index: int = 0

    # (part_id, staff, voice) tuples currently shown/played (Ref 7).
    # None means unfiltered. Must default to None, NOT an empty set - an
    # empty set means "nothing visible", and callers that never set a filter
    # expect the full note list.
    active_voice_filter: Optional[Set[Tuple[str, int, int]]] = None

    # Ref 15 AC4: which optional attributes each voice shows in Region 3.
    # A voice absent from this dict falls back to DEFAULT_DISPLAY_ATTRIBUTES,
    # NOT an empty set - most voices are never touched by the context menu
    # and must keep showing the plain note name.
    voice_display_attributes: Dict[Tuple[str, int, int], Set[str]] = field(default_factory=dict)

    # F2/Ref 15 AC4: the live, mutable rendering order Region 3/4 both read.
    # Defaults empty rather than to DISPLAY_ATTRIBUTE_ORDER because that
    # constant is defined further down the class body and isn't bound yet
    # here; __post_init__ fills it in, so "empty" never escapes.
    attribute_order: List[str] = field(default_factory=list)

    # Ref 14: gates both whether a beat sounds a click and whether a beat
    # with no note counts as a navigable event at all (_slice_is_navigable,
    # AC4). Off by default per load - MusicData is rebuilt on every load, so
    # nothing needs an explicit reset.
    metronome_enabled: bool = False

    # Ref 28: unlike metronome_enabled, toggling this never touches
    # timeline_slices - AC5 requires the announcer to speak only where an
    # event already exists and never create one, so there is nothing to
    # splice in or out.
    position_announcer_enabled: bool = False

    # F4/D-6: UK vs US terminology. main_window.py owns the real startup
    # default (OS-locale-detected) and re-applies it after every load, since
    # MusicData is wholly replaced then and this is a session preference,
    # not a per-score one like metronome_enabled.
    uk_terms: bool = False

    # Ref 29: repeat-barline pairs, 1st/2nd endings and hairpins, from
    # TimelineBuilder, same side-channel pattern as tempo_changes above.
    # total_measures is the whole-score bar count for the Performance
    # Report - NOT derived from timeline_slices, which would undercount a
    # trailing all-rest measure.
    repeat_spans: List[RepeatSpan] = field(default_factory=list)
    ending_spans: List[EndingSpan] = field(default_factory=list)
    hairpin_spans: List[HairpinSpan] = field(default_factory=list)
    total_measures: int = 0

    def __post_init__(self):
        # DISPLAY_ATTRIBUTE_ORDER is the fixed default; attribute_order is
        # the live copy the reorder dialog mutates. A caller-supplied order
        # is honoured as-is.
        if not self.attribute_order:
            self.attribute_order = list(self.DISPLAY_ATTRIBUTE_ORDER)
        if self.file_path:
            builder = TimelineBuilder(self.file_path, self.parts_info, root=self.xml_root)
            self.timeline_slices = builder.build()
            self.tempo_changes = builder.tempo_changes
            self._beat_markers = builder.beat_markers
            self.repeat_spans = builder.repeat_spans
            self.ending_spans = builder.ending_spans
            self.hairpin_spans = builder.hairpin_spans
            self.total_measures = builder.total_measures
            self.active_event_index = 0
        else:
            self._beat_markers: List[EventSlice] = []
        # The real, marker-free timeline, kept stable so
        # set_metronome_enabled can restore exactly this when the metronome
        # goes off again.
        self._real_timeline_slices = self.timeline_slices
        # Safe to cache forever: timeline_slices is never reassigned after
        # this point. The filter-dependent caches are separate, below.
        self._measure_numbers_cache: Optional[List[int]] = None
        self._invalidate_visibility_cache()

    def _invalidate_visibility_cache(self) -> None:
        """These lookups run on every navigation keypress, and the
        by-measure ones once per measure scanned - O(N*M) uncached across a
        long run of filtered-out measures. They depend only on
        active_voice_filter, so they are computed on demand and dropped
        whenever it changes."""
        self._sounding_bounds_cache: Optional[Tuple[int, int]] = None
        self._sounding_bounds_computed: bool = False
        self._first_visible_index_by_measure_cache: Optional[Dict[int, int]] = None
        # Ref 29: same caching rationale, for Region 5's Ctrl+End ("last
        # note of the end bar") lookup.
        self._last_visible_index_by_measure_cache: Optional[Dict[int, int]] = None

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
        """Ref 14 toggle.

        timeline_slices is rebuilt rather than permanently merged, so with
        the metronome off it holds exactly "one entry per (measure, offset)
        with at least one sounding note" - the invariant the rest of the
        codebase assumes. Turning it on splices in TimelineBuilder's
        synthetic beat markers; turning it off restores the untouched real
        list. Indices shift either way, so the cursor is relocated to the
        equivalent real position rather than left on an arbitrary slice.
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
            # Last slice at or before the current position: an exact match
            # where one exists, else the nearest preceding real event (which
            # is the case when toggling off while sitting on a marker, since
            # markers have no counterpart in the real-only list).
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

    def set_position_announcer_enabled(self, enabled: bool) -> None:
        """Ref 28 toggle. No timeline rebuild/cursor relocation needed,
        unlike set_metronome_enabled - see position_announcer_enabled's own
        comment for why."""
        self.position_announcer_enabled = enabled

    def toggle_position_announcer(self) -> None:
        self.set_position_announcer_enabled(not self.position_announcer_enabled)

    def _slice_is_navigable(self, index: int) -> bool:
        """Ref 14 AC4: with the metronome on, a whole beat is steppable even
        with no note there (whole beats are integers in ts-relative units,
        Ref 18). Used at every navigation/stepping call site, but NOT by
        _sounding_bounds below, which stays anchored to real sounding notes
        so metronome mode can't resurrect trailing rest-only padding."""
        if self._slice_has_visible_notes(index):
            return True
        # Own bounds check: _slice_has_visible_notes returns False both for
        # "out of range" and "nothing visible", so it can't be relied on to
        # have validated the index.
        if not self.metronome_enabled or not (0 <= index < len(self.timeline_slices)):
            return False
        return float(self.timeline_slices[index].beat_position).is_integer()

    def _slice_has_visible_sounding_note(self, index: int) -> bool:
        """True if this slice has a visible note that actually sounds (not a
        rest). Bounds navigation via _sounding_bounds(): a rest between two
        sounding notes stays individually reachable (Ref 16), but a run of
        rests padding the final bar out to full length is not a further
        event to step onto (Ref 2/3/5).
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
        """Index of the first timeline event in the measure, or None if it
        has none - Ref 6 turns that into a boundary cue and no movement."""
        for i, s in enumerate(self.timeline_slices):
            if s.measure == measure_number:
                return i
        return None

    def last_event_index(self) -> int:
        """Index of the last timeline event, or -1 if the timeline is empty."""
        return len(self.timeline_slices) - 1

    def _first_visible_index_by_measure(self) -> Dict[int, int]:
        """measure_number -> index of its first visible event, cached per
        filter state so move_timeline_*_by_measure's walk is O(1) per
        measure instead of re-scanning the timeline for each one."""
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

    def _last_visible_index_by_measure(self) -> Dict[int, int]:
        """measure_number -> index of its LAST visible event. Region 5's
        Ctrl+End jumps to the last sounding note of a span's end bar; this
        is the only place in the app with that concept."""
        if self._last_visible_index_by_measure_cache is None:
            cache: Dict[int, int] = {}
            for i, s in enumerate(self.timeline_slices):
                if self._slice_is_navigable(i):
                    cache[s.measure] = i
            self._last_visible_index_by_measure_cache = cache
        return self._last_visible_index_by_measure_cache

    def last_visible_event_index_of_measure(self, measure_number: int) -> Optional[int]:
        """Ref 29: like first_visible_event_index_of_measure, but the LAST
        visible event of the measure - Region 5's Ctrl+End target."""
        return self._last_visible_index_by_measure().get(measure_number)

    def slice_index_at_or_after_quarters(self, quarters_from_start: float) -> Optional[int]:
        """First slice index at or after an elapsed-quarters position -
        resolves a hairpin row's jump target, which the measure-only
        lookups can't since a wedge may start or stop mid-measure."""
        for i, s in enumerate(self.timeline_slices):
            if s.quarters_from_start >= quarters_from_start:
                return i
        return None

    def move_timeline_left_by_measure(self) -> bool:
        """Ctrl+Left (Ref 3): to the first visible event of this measure, or
        the previous measure's if already there. The pickup bar needs no
        special case - it is just the first entry in measure_numbers().
        Bounded by _sounding_bounds() like plain Left, so a trailing
        rest-only measure is never a target."""
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
        """Home (Ref 5): to the first event with a real sounding note.

        Unlike Left/Right this can never mean "moved past a boundary" - it
        jumps to a known limit - so callers never sound the boundary cue off
        this return value.
        """
        bounds = self._sounding_bounds()
        if bounds is None:
            return False
        self.active_event_index = bounds[0]
        return True

    def last_sounding_event_index(self) -> Optional[int]:
        """The true end of playable content, excluding trailing rest-only
        padding - bounds how far a phrase audition can run, as Home/End
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
        """credits' "Tempo" entry is baked at parse time in US units, so it
        is rebuilt here to reflect a live UK/US toggle without a reload.
        Built from tempo_bpm directly, not the cursor-aware
        tempo_beat_unit_name_at, because Region 1 always shows the score's
        OPENING tempo (A9)."""
        data = dict(self.credits)
        if "Tempo" in data:
            number = self.tempo_bpm / self.tempo_beat_unit_quarter_length
            number_str = str(int(number)) if float(number).is_integer() else str(round(number, 2))
            unit = vocabulary.duration_name(self.tempo_beat_unit_name, self.uk_terms)
            data["Tempo"] = f"{number_str} {unit} notes per minute"
        return data

    def get_score_structure(self) -> List[Dict[str, Any]]:
        """The parts/staves/voices shape Region2HierarchyModel expects
        (Ref 7). A pure transform of parts_info, no XML access."""
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

    def _all_voice_tuples(self) -> Set[Tuple[str, int, int]]:
        """Every (part_id, staff, voice) the score has - the universe
        export_config/apply_config filter saved keys against. Scans the
        notes rather than parts_info, which is only populated by
        MusicXMLReader.load() and so is empty for a directly-built
        MusicData even though the notes are all there."""
        return {
            (n.part_id, n.staff, n.voice)
            for event_slice in self._real_timeline_slices
            for n in event_slice.notes
        }

    def _visible_notes(self, index: Optional[int] = None) -> List[NoteData]:
        """Notes at the given slice passing the Region 2 filter (Ref 7), or
        at the cursor when index is None.

        Every UI-facing accessor reads through this, which is what makes a
        row index mean the same note in Region 3, Region 4 and playback
        alike. The explicit-index form is for the Sequencer, which plays by
        absolute index without disturbing the cursor or Region 3's
        selection (so phrase audition can leave the cursor untouched).
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

    # Ref 15 AC4: the fixed DEFAULT rendering order for Region 3's optional
    # extra attributes and Region 4's rows - every fresh MusicData starts
    # attribute_order (see __post_init__) as a copy of this. F2's
    # attribute-order dialog mutates that live copy, never this constant.
    DISPLAY_ATTRIBUTE_ORDER = [
        "step", "octave", "midi", "measure", "beat position", "duration",
        "part", "stave", "voice", "string", "fret",
        "dynamic", "articulation", "fingering", "pluck",
    ]
    # A voice with no entry in voice_display_attributes uses this - today's
    # plain-note-name behaviour, not an empty display.
    DEFAULT_DISPLAY_ATTRIBUTES = frozenset({"step"})

    def notes_for_indices(self, selected_indices: List[int]) -> List[NoteData]:
        """The NoteData behind Region 3's selected rows, for callers needing
        the notes themselves rather than indices or pitches."""
        notes = self._visible_notes()
        return [notes[i] for i in selected_indices if 0 <= i < len(notes)]

    def _note_attribute_pairs(self, note: NoteData) -> Dict[str, str]:
        """Attribute name -> value for one note, shared by Region 3 and
        Region 4 so the two can never disagree on a name or value.

        Only keys the note actually has a value for are included (a rest has
        no octave or midi). That absence is the mechanism that stops either
        region rendering a row for data that doesn't exist."""
        if note.duration_name_us is not None:
            dur_str = vocabulary.duration_name(note.duration_name_us, self.uk_terms)
        else:
            # No <type> in the source XML (rare) - fall back to the raw
            # time-signature-relative number rather than guessing a name.
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
        if note.dynamic is not None:
            pairs["dynamic"] = note.dynamic
        if note.articulation is not None:
            pairs["articulation"] = note.articulation
        if note.fingering is not None:
            pairs["fingering"] = note.fingering
        if note.pluck is not None:
            pairs["pluck"] = note.pluck
        return pairs

    def _region_4_rows(self, selected_notes: List[NoteData]) -> List[Tuple[str, str, NoteData, str]]:
        """(display_key, attribute_key, note, value) per Region 4 row.
        display_key carries the "note N " prefix used for a chord;
        attribute_key never does. Shared by the rendering dict and the
        context menu's row->target mapping. Order follows attribute_order -
        the same live order Region 3 uses - not _note_attribute_pairs'
        insertion order, so the two regions can't disagree on sequence."""
        is_chord = len(selected_notes) > 1
        rows = []
        for idx, n in enumerate(selected_notes, start=1):
            prefix = f"note {idx} " if is_chord else ""
            pairs = self._note_attribute_pairs(n)
            for attribute_key in self.attribute_order:
                if attribute_key not in pairs:
                    continue
                label = vocabulary.attribute_label(attribute_key, self.uk_terms)
                rows.append((f"{prefix}{label}", attribute_key, n, pairs[attribute_key]))
        return rows

    # Attribute keys whose value alone is self-explanatory in Region 3's
    # comma-joined note text, so the "<Label> " prefix _format_note_for_region_3
    # adds for every other attribute is dropped: "step" ("F sharp") needs no
    # "Step" prefix, and per user request "duration" doesn't either - a word
    # like "quaver" already says what it is without "Duration quaver".
    # Region 4's table still labels its "Duration" row normally; only this
    # inline rendering omits the prefix.
    REGION_3_UNPREFIXED_ATTRIBUTES = frozenset({"step", "duration"})

    def _format_note_for_region_3(self, note: NoteData) -> str:
        """Ref 15 AC4: the note name plus whichever extras its voice has
        switched on, comma-separated. An attribute renders only when it is
        both configured on AND present on the note. A voice with everything
        off renders "" - a blank but still selectable, still audible row."""
        voice_key = (note.part_id, note.staff, note.voice)
        wanted = self.voice_display_attributes.get(voice_key, self.DEFAULT_DISPLAY_ATTRIBUTES)
        pairs = self._note_attribute_pairs(note)
        parts = []
        for key in self.attribute_order:
            if key not in wanted or key not in pairs:
                continue
            if key in self.REGION_3_UNPREFIXED_ATTRIBUTES:
                parts.append(pairs[key])
            else:
                label = vocabulary.attribute_label(key, self.uk_terms)
                parts.append(f"{label} {pairs[key]}")
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
        """Ref 15 AC4: add or remove `attribute_key` for every voice `scope`
        reaches from each note. Plural because a chord selection unions the
        scope across all selected notes - a stave-scope action from a
        two-part chord affects both parts' staves, not just the one the menu
        was opened on."""
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

    def move_attribute_order(self, attribute_key: str, up: bool, within: Optional[List[str]] = None) -> bool:
        """F2/Ref 15 AC4: move `attribute_key` one step earlier (up) or later
        in attribute_order, the single global order Region 3 and 4 both
        render from. Returns False at a boundary or for an unknown key,
        matching move_timeline_left/right's convention.

        `within`, if given, is a subset of attribute_order (the dialog's
        per-node filtered list) and the move is relative to the nearest
        neighbour IN THAT SUBSET. Entries not in `within` that sit between
        the two are carried along, keeping their order relative to each
        other. That is what lets a filtered dialog move its visible list by
        exactly one row per click without knowing about hidden attributes.

        Taking the neighbour's index BEFORE popping attribute_key, then
        inserting at that same index, is what makes one pop/insert pair
        correct in both directions with no branching."""
        order = self.attribute_order
        if attribute_key not in order:
            return False
        sequence = within if within is not None else order
        if attribute_key not in sequence:
            return False
        pos = sequence.index(attribute_key)
        neighbor_pos = pos - 1 if up else pos + 1
        if not (0 <= neighbor_pos < len(sequence)):
            return False
        neighbor_key = sequence[neighbor_pos]
        source_index = order.index(attribute_key)
        target_index = order.index(neighbor_key)
        order.pop(source_index)
        order.insert(target_index, attribute_key)
        return True

    def attribute_keys_for_voices(self, voice_tuples: Set[Tuple[str, int, int]]) -> List[str]:
        """Every attribute key that has a value on at least one note
        belonging to one of `voice_tuples`, anywhere in the score (not just
        the current slice), ordered per attribute_order. Powers the F2
        attribute-order dialog's per-Region-2-node list - scans
        _real_timeline_slices (the stable, marker-free timeline) rather than
        timeline_slices, since the metronome can temporarily replace the
        latter with a merged view that includes marker-only slices."""
        present: Set[str] = set()
        for event_slice in self._real_timeline_slices:
            for note in event_slice.notes:
                if (note.part_id, note.staff, note.voice) in voice_tuples:
                    present |= self._note_attribute_pairs(note).keys()
        return [key for key in self.attribute_order if key in present]

    def export_config(self) -> ScoreConfig:
        """Ref 27: this score's state as a ScoreConfig. voices_off is the
        complement of active_voice_filter, not the ON-list - an OFF-list is
        what lets a changed score still load best-effort (see apply_config).
        MainWindow overwrites it with Region 2's own per-node state, which
        is lossless where this derived version is not."""
        voices_off: Set[Tuple[str, int, int]] = set()
        if self.active_voice_filter is not None:
            voices_off = self._all_voice_tuples() - self.active_voice_filter
        return ScoreConfig(
            voices_off=voices_off,
            metronome_enabled=self.metronome_enabled,
            position_announcer_enabled=self.position_announcer_enabled,
            voice_display_attributes={
                k: set(v) for k, v in self.voice_display_attributes.items()
            },
            attribute_order=list(self.attribute_order),
        )

    def apply_config(self, config: ScoreConfig) -> None:
        """Ref 27: restore a saved ScoreConfig, best-effort. An entry that no
        longer matches anything in THIS score (renamed part, deleted voice,
        unknown attribute key) is dropped silently rather than rejecting the
        whole config, so a stale .rsc still applies everything it can."""
        known_voices = self._all_voice_tuples()
        active = known_voices - (config.voices_off & known_voices)
        self.set_active_voice_filter(active)

        self.voice_display_attributes = {
            voice_key: set(attrs)
            for voice_key, attrs in config.voice_display_attributes.items()
            if voice_key in known_voices
        }

        known_attribute_keys = set(self.DISPLAY_ATTRIBUTE_ORDER)
        ordered = [key for key in config.attribute_order if key in known_attribute_keys]
        ordered += [key for key in self.DISPLAY_ATTRIBUTE_ORDER if key not in ordered]
        self.attribute_order = ordered

        self.set_metronome_enabled(config.metronome_enabled)
        self.set_position_announcer_enabled(config.position_announcer_enabled)

    def get_midi_notes_for_indices(self, selected_indices: List[int]) -> List[int]:
        notes = self._visible_notes()
        if not notes or not selected_indices:
            return []
        return [
            notes[i].midi_pitch
            for i in selected_indices
            if 0 <= i < len(notes) and notes[i].midi_pitch is not None
        ]

    def get_performance_region_rows(self, index: Optional[int] = None) -> List[PerformanceRegionRow]:
        """Ref 29: Region 5's rows - a start and an end line per span active
        at the given position (default: the cursor).

        Repeat/ending containment is a measure-number range check (barlines
        fall at measure boundaries); hairpins compare quarters_from_start,
        since a wedge can start or stop mid-measure. The order (repeats,
        endings, hairpins, each in span-list order) must stay stable -
        MainWindow diffs the resulting label list to detect a real change.
        Wording goes through vocabulary.bar_word, never a hardcoded
        "bar"/"measure"."""
        slice_ = (
            self.get_current_slice()
            if index is None
            else (self.timeline_slices[index] if 0 <= index < len(self.timeline_slices) else None)
        )
        if slice_ is None:
            return []

        bar_word = vocabulary.bar_word(self.uk_terms)
        rows: List[PerformanceRegionRow] = []

        for span in self.repeat_spans:
            if span.start_measure <= slice_.measure <= span.end_measure:
                rows.append(
                    PerformanceRegionRow(
                        label=f"Repeat start: {bar_word} {span.start_measure}",
                        jump_target_measure=span.start_measure,
                    )
                )
                rows.append(
                    PerformanceRegionRow(
                        label=f"Repeat end: {bar_word} {span.end_measure}",
                        jump_target_measure=span.end_measure,
                    )
                )

        for span in self.ending_spans:
            if span.start_measure <= slice_.measure <= span.end_measure:
                rows.append(
                    PerformanceRegionRow(
                        label=f"Ending {span.number} start: {bar_word} {span.start_measure}",
                        jump_target_measure=span.start_measure,
                    )
                )
                rows.append(
                    PerformanceRegionRow(
                        label=f"Ending {span.number} end: {bar_word} {span.end_measure}",
                        jump_target_measure=span.end_measure,
                    )
                )

        for span in self.hairpin_spans:
            if span.start_quarters_from_start <= slice_.quarters_from_start <= span.end_quarters_from_start:
                kind_label = span.kind.capitalize()
                rows.append(
                    PerformanceRegionRow(
                        label=(
                            f"{kind_label} start: "
                            f"{self._bar_beat_label(bar_word, span.start_measure, span.start_beat_position)}"
                        ),
                        jump_target_measure=span.start_measure,
                        jump_target_quarters=span.start_quarters_from_start,
                    )
                )
                rows.append(
                    PerformanceRegionRow(
                        label=(
                            f"{kind_label} end: "
                            f"{self._bar_beat_label(bar_word, span.end_measure, span.end_beat_position)}"
                        ),
                        jump_target_measure=span.end_measure,
                        jump_target_quarters=span.end_quarters_from_start,
                    )
                )

        return rows

    @staticmethod
    def _bar_beat_label(bar_word: str, measure: int, beat_position: float) -> str:
        """"bar N" on the downbeat (the bar number already pins it down, and
        repeat/ending rows are always this case since barlines fall at
        measure boundaries); "bar N beat B" otherwise, worded exactly as
        get_status_bar_fields does so it reads the same everywhere. Only
        markers actually falling mid-bar name a beat (user's decision)."""
        if float(beat_position) == 1.0:
            return f"{bar_word} {measure}"
        beat_str = str(int(beat_position)) if float(beat_position).is_integer() else str(beat_position)
        return f"{bar_word} {measure} beat {beat_str}"

    def get_performance_report_lines(self) -> List[str]:
        """Ref 29: the Performance Report's content - a whole-score summary,
        deliberately independent of the Region 2 filter (unlike every other
        accessor here), since it describes the piece, not the current view."""
        # Reuses get_region_1_data() wholesale rather than cherry-picking
        # keys like "Title"/"Composer": credit keys come from each file's own
        # <credit-type> text, so no fixed name is guaranteed to exist.
        lines: List[str] = [f"{k}: {v}" for k, v in self.get_region_1_data().items()]

        bar_word = vocabulary.bar_word(self.uk_terms).capitalize()
        anacrusis_present = any(s.measure == 0 for s in self.timeline_slices)
        lines.append(f"Anacrusis: {'Present' if anacrusis_present else 'Not present'}")
        lines.append(f"Number of {bar_word.lower()}s: {self.total_measures}")

        note_counts: Dict[str, int] = {}
        for s in self._real_timeline_slices:
            for n in s.notes:
                if n.midi_pitch is not None:
                    note_counts[n.part_name] = note_counts.get(n.part_name, 0) + 1
        lines.append(f"Instruments: {len(self.parts_info)}")
        for p in self.parts_info:
            lines.append(f"{p.name}: {note_counts.get(p.name, 0)} notes")

        lines.append(f"Repeated sections: {len(self.repeat_spans)}")
        for span in self.repeat_spans:
            lines.append(
                f"Repeat: {bar_word} {span.start_measure} to {bar_word} {span.end_measure}"
            )

        lines.append(f"Endings: {len(self.ending_spans)}")
        for span in self.ending_spans:
            lines.append(
                f"Ending {span.number}: {bar_word} {span.start_measure} to {bar_word} {span.end_measure}"
            )

        lines.append(f"Performance markers: {len(self.hairpin_spans)}")
        for span in self.hairpin_spans:
            lines.append(
                f"{span.kind.capitalize()}: {bar_word} {span.start_measure} to {bar_word} {span.end_measure}"
            )

        return lines

    # Ref 12 AC2: hard bounds, in the score's DISPLAY units - what the user
    # reads and types, not the internal quarter-note equivalent.
    MIN_TEMPO_BPM = 30
    MAX_TEMPO_BPM = 300

    def _tempo_change_at(self, index: Optional[int] = None) -> Tuple[int, float, str]:
        """(tempo_bpm, beat_unit_quarter_length, beat_unit_name) in effect at
        an index, or the cursor. Falls back to the score's opening tempo
        before the first marking. tempo_changes is sorted by position
        (TimelineBuilder's job), so the last entry not past it wins."""
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
        """The beat unit label (e.g. "eighth"/"quaver") in effect at `index`
        (or the cursor) - lets the status bar show the right unit even where
        a mid-score tempo marking changes beat unit, not just the number.
        F4/D-6: translated per self.uk_terms - both current callers
        (_tempo_status_field below, and main_window.py's Tempo Offset dialog
        construction) are display-only, so this is the single change point
        that covers both."""
        _, _, name = self._tempo_change_at(index)
        return vocabulary.duration_name(name, self.uk_terms)

    def set_playback_tempo_offset(self, offset: float) -> None:
        """Clamp so effective_tempo_display_bpm() stays within
        [MIN_TEMPO_BPM, MAX_TEMPO_BPM] (Ref 12 AC2) - bounds on what the
        user reads and types, not on tempo_bpm's quarter-note equivalent -
        without touching tempo_bpm itself (AC1). Clamped against the tempo
        at the cursor, which can change mid-score."""
        base = self.score_tempo_display_bpm()
        min_offset = self.MIN_TEMPO_BPM - base
        max_offset = self.MAX_TEMPO_BPM - base
        self.playback_tempo_offset = max(min_offset, min(max_offset, offset))

    def reset_playback_tempo(self) -> None:
        """Ref 12 AC4: reset control returns to the score's own tempo."""
        self.playback_tempo_offset = 0.0

    # Channels no real part may use. Each value is duplicated from the
    # audio/ module that owns it rather than imported - models/ must not
    # depend on audio/. Keeping parts off these is what stops an instrument
    # colliding with the click, the spoken position word or the change cue.
    PERCUSSION_CHANNEL = 9          # audio/metronome.py METRONOME_CHANNEL
    POSITION_ANNOUNCER_CHANNEL = 8  # audio/position_announcer.py
    PERFORMANCE_CUE_CHANNEL = 7     # audio/performance_cue.py
    RESERVED_CHANNELS = {POSITION_ANNOUNCER_CHANNEL, PERCUSSION_CHANNEL, PERFORMANCE_CUE_CHANNEL}
    MAX_MIDI_CHANNELS = 16

    def get_channel_for_part(self, part_id: str) -> int:
        """One MIDI channel per part, in part-list order, skipping
        RESERVED_CHANNELS. Wraps if a score has more melodic parts than the
        16 channels minus reservations allow.

        The usable list is built per call, not as a class attribute: only a
        comprehension's outermost iterable is evaluated in the enclosing
        class scope, not its condition, so referring to RESERVED_CHANNELS
        there raises NameError. 16 elements is too cheap to be worth caching
        another way.
        """
        usable_channels = [
            c for c in range(self.MAX_MIDI_CHANNELS) if c not in self.RESERVED_CHANNELS
        ]
        for idx, p in enumerate(self.parts_info):
            if p.part_id == part_id:
                return usable_channels[idx % len(usable_channels)]
        return 0

    def get_gmidi_program_for_part(self, part_id: str) -> int:
        for p in self.parts_info:
            if p.part_id == part_id:
                return p.gmidi_program
        return 25

    def get_stave_name_for_part(self, part_id: str, staff: int) -> str:
        """Spoken-friendly stave name for Region 4 ("Treble stave"), worded
        exactly as Region 2 does so a note matches the stave it was toggled
        under. D-15: deliberately NOT translated by the uk_terms toggle."""
        for p in self.parts_info:
            if p.part_id == part_id:
                return p.staves_clefs.get(staff, "Standard stave")
        return "Standard stave"

    def get_playback_events_for_indices(
        self, selected_indices: List[int], index: Optional[int] = None
    ) -> List[Tuple[int, Optional[int], List[int], int]]:
        """Group selected notes by part for simultaneous multi-part playback.

        Each group is (channel, zero-indexed GM program, midi pitches,
        duration_ms), so a chord spanning two parts sounds both instruments
        rather than collapsing onto parts_info[0]'s (Ref 8). duration_ms is
        PER PART - the max quarter_length among that part's own notes here,
        not the slice-wide minimum - so no part is clamped to whichever
        other part happens to have the shortest note at this instant
        (Ref 9 AC2, Ref 13 AC2). The max, not the min, so a chord with
        slightly inconsistent source data rings for its longest member.

        index: read an explicit slice instead of the cursor (Sequencer).
        """
        notes = self._visible_notes(index)
        if not notes:
            return []

        notes_by_part: Dict[str, List[int]] = {}
        quarter_length_by_part: Dict[str, float] = {}
        part_order: List[str] = []
        for i in selected_indices:
            if not (0 <= i < len(notes)):
                continue
            note = notes[i]
            if note.midi_pitch is None:
                continue
            if note.part_id not in notes_by_part:
                notes_by_part[note.part_id] = []
                quarter_length_by_part[note.part_id] = 0.0
                part_order.append(note.part_id)
            notes_by_part[note.part_id].append(note.midi_pitch)
            quarter_length_by_part[note.part_id] = max(
                quarter_length_by_part[note.part_id], note.quarter_length
            )

        events = []
        for part_id in part_order:
            channel = self.get_channel_for_part(part_id)
            program = max(0, self.get_gmidi_program_for_part(part_id) - 1)
            duration_ms = self._quarters_to_ms(quarter_length_by_part[part_id], index)
            events.append((channel, program, notes_by_part[part_id], duration_ms))
        return events

    def get_current_duration_ms(self) -> int:
        return self.get_duration_ms_for_index(self.active_event_index)

    def get_duration_ms_for_index(self, index: int) -> int:
        """Slice-wide duration at an arbitrary index - used only by the
        Sequencer to know how long to stay playing after the final step.
        Real per-note note-off timing is per group; see
        get_playback_events_for_indices."""
        if not (0 <= index < len(self.timeline_slices)):
            return 500
        quarter_length = self.timeline_slices[index].quarter_length
        return self._quarters_to_ms(quarter_length, index)

    def _quarters_to_ms(self, quarter_length: float, index: Optional[int]) -> int:
        ms = (quarter_length * 60000.0) / float(self.effective_tempo_bpm(index))
        return max(100, int(ms))

    def get_playback_events_at_index(self, index: int) -> List[Tuple[int, Optional[int], List[int], int]]:
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
        """Next index after `index` passing the Region 2 filter - rests
        INCLUDED, unlike _sounding_bounds()'s navigation range, because
        playback must advance through a rest and take up its time rather
        than skip it. Visits metronome beat markers too when the metronome
        is on, which is what makes the Sequencer click on a silent beat with
        no extra scheduling. None means the end of playback."""
        limit = end_index if end_index is not None else len(self.timeline_slices) - 1
        idx = index
        while idx < limit:
            idx += 1
            if self._slice_is_navigable(idx):
                return idx
        return None

    def get_status_bar_fields(self) -> List[str]:
        """The first four status-bar fields in Tab order: position, key,
        time signature, playback tempo. All read the CURRENT slice, not the
        score's opening values - any of them can change mid-score, unlike
        Region 1's one-off summary. The tempo field is the only way a
        screen-reader user can check playback tempo without an
        announcement."""
        bar_word = vocabulary.bar_word(self.uk_terms).capitalize()
        current = self.get_current_slice()
        if current is None:
            return [f"{bar_word} - beat -", "Key: -", "Time: -", self._tempo_status_field()]

        beat = current.beat_position
        beat_str = str(int(beat)) if float(beat).is_integer() else str(beat)
        ts_num, ts_den = current.time_sig
        key_name = FIFTHS_MAP.get(current.key_fifths, f"{current.key_fifths} sharps/flats")

        return [
            f"{bar_word} {current.measure} beat {beat_str}",
            f"Key: {key_name}",
            f"Time: {ts_num}/{ts_den}",
            self._tempo_status_field(),
        ]

    def _tempo_status_field(self) -> str:
        """Reads effective_tempo_display_bpm(), i.e. the score's own units
        (96 for eighth=96), never effective_tempo_bpm()'s internal
        quarter-note equivalent (48) - see the tempo_bpm field comment."""
        effective = self.effective_tempo_display_bpm()
        effective_str = str(int(effective)) if float(effective).is_integer() else str(round(effective, 2))
        unit = f"{self.tempo_beat_unit_name_at()} notes per minute"
        if self.playback_tempo_offset == 0.0:
            return f"Playback tempo: {effective_str} {unit} (score default)"
        return f"Playback tempo: {effective_str} {unit}"