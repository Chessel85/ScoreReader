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

    # F2/Ref 15 AC4: the live, per-instance, mutable rendering order Region
    # 3/4 both read. R14: a declared field, not something __post_init__
    # conjures onto the instance - it is public API (MainWindow and
    # apply_config both assign to it), so leaving it undeclared kept it out
    # of the dataclass's own repr/eq and out of reach of type checkers.
    # Empty default rather than DISPLAY_ATTRIBUTE_ORDER: that constant is
    # defined further down the class body and isn't bound yet at field-
    # definition time. __post_init__ fills it in, so "empty" never escapes.
    attribute_order: List[str] = field(default_factory=list)

    # E8/Ref 14: off by default per score load (MusicData is reconstructed
    # fresh on every _on_score_loaded, so no explicit reset code is needed
    # elsewhere, same as playback_tempo_offset above). Gates both whether a
    # beat position sounds a click (Sequencer, MainWindow) and whether a
    # beat position with no note counts as a navigable event at all
    # (_slice_is_navigable, Ref 14 AC4).
    metronome_enabled: bool = False

    # Ref 28: off by default, same reasoning as metronome_enabled above.
    # Unlike metronome_enabled, toggling this never touches timeline_slices
    # - AC5 requires the position announcer to only ever speak at positions
    # that already have an event (a real note/rest, or one of the
    # metronome's own beat markers when that's on too) and never create
    # further events of its own, so no synthetic-marker splicing is needed
    # here at all.
    position_announcer_enabled: bool = False

    # F4/D-6: UK vs US music terminology (bar/measure, duration names,
    # stave/staff). Off (US-leaning defaults) is required here, not
    # arbitrary - it preserves every existing test's current English-text
    # assertions unchanged. main_window.py decides the real app-level
    # startup default (OS-locale-detected, UK unless confidently US) and
    # applies it explicitly, including re-applying it after each file load
    # since MusicData is wholly replaced then and this is a session
    # preference, not a per-score one like metronome_enabled above.
    uk_terms: bool = False

    # Ref 29 "Performance region": repeat-barline pairs, 1st/2nd-ending
    # brackets, and crescendo/diminuendo hairpins - populated from
    # TimelineBuilder as a side effect of build() (see __post_init__), same
    # pattern as tempo_changes above. total_measures is the whole-score bar
    # count (for the Performance Report), sourced the same way.
    repeat_spans: List[RepeatSpan] = field(default_factory=list)
    ending_spans: List[EndingSpan] = field(default_factory=list)
    hairpin_spans: List[HairpinSpan] = field(default_factory=list)
    total_measures: int = 0

    def __post_init__(self):
        # DISPLAY_ATTRIBUTE_ORDER (defined below, alongside the rest of the
        # attribute system) stays the fixed default every fresh MusicData
        # starts from; attribute_order is the live copy F2's dialog mutates.
        # MainWindow reapplies its own session-level copy after every load
        # (MusicData is wholly replaced then), the same pattern already used
        # for uk_terms. Honours a caller-supplied order if one was passed.
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

    def set_position_announcer_enabled(self, enabled: bool) -> None:
        """Ref 28 toggle. No timeline rebuild/cursor relocation needed,
        unlike set_metronome_enabled - see position_announcer_enabled's own
        comment for why."""
        self.position_announcer_enabled = enabled

    def toggle_position_announcer(self) -> None:
        self.set_position_announcer_enabled(not self.position_announcer_enabled)

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
        # R10: the bounds check is this method's own, not inherited from the
        # call above - _slice_has_visible_notes returns False both for "out
        # of range" and for "in range but nothing visible", so falling
        # through to index timeline_slices directly would raise IndexError
        # on the first case whenever the metronome happens to be on. Every
        # current caller passes a bounded index, so this is a latent crash
        # rather than a live one; guarding here keeps it that way.
        if not self.metronome_enabled or not (0 <= index < len(self.timeline_slices)):
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

    def _last_visible_index_by_measure(self) -> Dict[int, int]:
        """measure_number -> index of its LAST visible event. Ref 29:
        Region 5's Ctrl+End on a repeat/ending row jumps to the last
        sounding note of the span's end bar, not the first - nothing else
        in the app had this "last event in a measure" concept before, so it
        gets its own cache alongside _first_visible_index_by_measure's."""
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
        """Ref 29: first timeline_slices index at/after the given elapsed-
        quarters position - resolves a HairpinSpan row's jump target, since
        a wedge can start/stop mid-measure and the measure-only
        first/last_visible_event_index_of_measure lookups aren't
        fine-grained enough. timeline_slices is already sorted by
        (measure, quarters_from_start)."""
        for i, s in enumerate(self.timeline_slices):
            if s.quarters_from_start >= quarters_from_start:
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
        """self.credits' "Tempo" entry was baked once at parse time in US
        units (MusicXMLReader._extract_tempo) - override it here with a
        freshly-built string so a live vocabulary toggle (F4) is reflected
        without needing to reload the file. Rebuilt from tempo_bpm/
        tempo_beat_unit_quarter_length directly (not tempo_beat_unit_name_at,
        which is cursor-position-aware) since Region 1 always shows the
        score's OPENING tempo (A9), never the live/cursor one."""
        data = dict(self.credits)
        if "Tempo" in data:
            number = self.tempo_bpm / self.tempo_beat_unit_quarter_length
            number_str = str(int(number)) if float(number).is_integer() else str(round(number, 2))
            unit = vocabulary.duration_name(self.tempo_beat_unit_name, self.uk_terms)
            data["Tempo"] = f"{number_str} {unit} notes per minute"
        return data

    def get_score_structure(self) -> List[Dict[str, Any]]:
        """Parts/staves/voices shape Region2HierarchyModel.build_from_score()
        documents - drives Region 2 (Ref 7). Pure transform of parts_info,
        no XML access. D-15: stave names are NOT translated by F4's
        uk_terms toggle - deliberate decision, see tasks.txt."""
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
        """Every (part_id, staff, voice) this score actually has - the
        universe export_config/apply_config (Ref 27) filter saved voice keys
        against. Scans _real_timeline_slices' actual notes (same source
        attribute_keys_for_voices uses) rather than parts_info, since
        parts_info is only populated by MusicXMLReader.load() - a MusicData
        built directly via MusicData(file_path=...) (the timeline test
        fixture, and TimelineBuilder's own fast path) leaves it empty even
        though the notes themselves are already there."""
        return {
            (n.part_id, n.staff, n.voice)
            for event_slice in self._real_timeline_slices
            for n in event_slice.notes
        }

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
        """(display_key, attribute_key, note, value) per Region 4 row, in
        display order - display_key carries the "note N " prefix used when
        more than one note is selected (a chord), attribute_key never does.
        Shared source for get_region_4_data_for_indices (the dict Region 4
        renders) and get_region_4_row_targets (which row maps to which
        note/attribute, for the Ref 15 AC4 context menu). Row order follows
        attribute_order (F2) - the same live order Region 3's optional extras
        render in - rather than _note_attribute_pairs' own dict-insertion
        order, so reordering attributes can't leave the two regions
        disagreeing about sequence."""
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
        for key in self.attribute_order:
            if key not in wanted or key not in pairs:
                continue
            if key == "step":
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

    def move_attribute_order(self, attribute_key: str, up: bool, within: Optional[List[str]] = None) -> bool:
        """F2/Ref 15 AC4: move `attribute_key` one step earlier (up=True) or
        later (up=False) in attribute_order - the single global rendering
        order Region 3/4 both read (_format_note_for_region_3,
        _region_4_rows). Returns False (no-op) at a boundary or if
        attribute_key isn't present, mirroring move_timeline_left/right's
        boundary-bool convention.

        `within`, if given, is a subset of attribute_order (e.g. the
        attribute-order dialog's per-Region-2-node filtered list) - the move
        is then relative to attribute_key's nearest neighbour IN THAT SUBSET,
        not its immediate neighbour in the full order. Any attribute_order
        entries that aren't in `within` and sit between attribute_key and
        that neighbour are carried along for the ride: their positions
        relative to each other are untouched, only their position relative to
        the moved attribute shifts. This is what makes a dialog filtered down
        to "attributes present for this voice" still move its visible list by
        exactly one row per click, without the caller needing to know
        anything about the attributes it can't see.

        Implementation note: computing the neighbour's index in the full
        order BEFORE popping attribute_key out of it, then inserting
        attribute_key at that same (now-still-valid) index, is what makes one
        pop/insert pair correct for both directions - no separate branching
        needed for "neighbour was before" vs "neighbour was after"."""
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
        """Ref 27: this score's current state as a ScoreConfig, for
        persistence/score_config.save(). voices_off is the complement of
        active_voice_filter (empty when active_voice_filter is None, since
        None already means "everything visible") rather than the ON-list
        itself - see apply_config for why that's what makes reloading
        best-effort."""
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
        """Ref 27: restores a previously saved ScoreConfig, best-effort - a
        saved entry that no longer corresponds to anything in THIS score
        (different part names, a voice that's gone, an attribute key this
        build doesn't know) is silently dropped rather than rejecting the
        whole config, so a stale or partially-matching .rsc still applies
        everything it can instead of falling back to all-defaults."""
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
        """Ref 29: Region 5's rows - two per RepeatSpan/EndingSpan/
        HairpinSpan active at the given position (defaults to the cursor,
        active_event_index): a start line and an end line. Repeat/ending
        containment is a plain measure-number range check (barlines only
        occur at measure boundaries); hairpins compare quarters_from_start,
        since a wedge can start/stop mid-measure. Stable order (repeats,
        then endings, then hairpins, each in span-list order) so
        MainWindow's active-set diff (comparing label lists) is
        deterministic. bar/measure wording goes through vocabulary.bar_word
        (F4's uk_terms dialect toggle) rather than a hardcoded literal, the
        same as get_status_bar_fields."""
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
        """"bar N" alone when beat_position is beat 1 (the marker lands
        exactly on the downbeat, so the bar number alone already pins it
        down - repeat/ending rows are always this case, since barlines only
        occur at measure boundaries); "bar N beat B" otherwise, same wording
        as get_status_bar_fields's own "Bar N beat B" so a beat position
        reads identically everywhere in the app. User-requested (Ref 29
        follow-up): only markers that actually fall mid-bar need a beat
        called out at all."""
        if float(beat_position) == 1.0:
            return f"{bar_word} {measure}"
        beat_str = str(int(beat_position)) if float(beat_position).is_integer() else str(beat_position)
        return f"{bar_word} {measure} beat {beat_str}"

    def get_performance_report_lines(self) -> List[str]:
        """Ref 29: the read-only Performance Report's content - a flat,
        whole-score summary independent of the current Region 2 filter
        state (unlike get_region_3_data etc., which follow
        active_voice_filter) since the report describes the shape of the
        piece, not the current filtered view."""
        # Reuses get_region_1_data() wholesale (same dict Region 1 itself
        # displays) rather than cherry-picking assumed keys like "Title"/
        # "Composer" - credits_dict's keys come from each file's own
        # <credit-type> text (MusicXMLReader._extract_credits_etree), so
        # they aren't guaranteed to match any fixed name.
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
    # Ref 28: also reserved, for the position announcer - same number as
    # audio/position_announcer.py's POSITION_ANNOUNCER_CHANNEL, duplicated
    # rather than imported (models/ doesn't depend on audio/, same as
    # PERCUSSION_CHANNEL's own relationship to audio/metronome.py's
    # METRONOME_CHANNEL). Needed so a real instrument part can never land on
    # the channel SynthEngine.play_word() uses, the same guarantee
    # PERCUSSION_CHANNEL already gives the click.
    POSITION_ANNOUNCER_CHANNEL = 8
    # Ref 29: also reserved, for the Performance region's "something
    # changed" cue - same number as audio/performance_cue.py's
    # PERFORMANCE_CUE_CHANNEL, duplicated for the same reason
    # POSITION_ANNOUNCER_CHANNEL's own comment gives.
    PERFORMANCE_CUE_CHANNEL = 7
    RESERVED_CHANNELS = {POSITION_ANNOUNCER_CHANNEL, PERCUSSION_CHANNEL, PERFORMANCE_CUE_CHANNEL}
    MAX_MIDI_CHANNELS = 16

    def get_channel_for_part(self, part_id: str) -> int:
        """One MIDI channel per part, in part-list order, skipping the
        reserved channels above.

        Wraps past the end of the usable-channel list if a score has more
        melodic parts than it has room for - the hard ceiling is 16
        channels minus the two reservations (D-5, Ref 28). Computed fresh
        each call rather than cached: a class-body comprehension can't see
        RESERVED_CHANNELS (only a comprehension's outermost iterable is
        evaluated in the enclosing class scope, not its condition - the
        two constants above would each raise NameError if this were built
        at class-definition time instead), and this is far too cheap
        (16 elements) to be worth a real cache.
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
        """Screen-reader-friendly stave name for Region 4, e.g. "Treble
        stave" or "C stave" - same wording Region 2 uses (Ref 7), so a note
        looked up in Region 4 matches the stave it was toggled under. D-15:
        NOT translated by F4's uk_terms toggle - deliberate decision, see
        tasks.txt."""
        for p in self.parts_info:
            if p.part_id == part_id:
                return p.staves_clefs.get(staff, "Standard stave")
        return "Standard stave"

    def get_playback_events_for_indices(
        self, selected_indices: List[int], index: Optional[int] = None
    ) -> List[Tuple[int, Optional[int], List[int], int]]:
        """Group selected notes by part for simultaneous multi-instrument playback.

        Each group is (channel, zero-indexed GM program, midi pitches,
        duration_ms) so a chord spanning two parts sounds both instruments
        together instead of collapsing onto parts_info[0]'s instrument (Ref
        8, Ref 9 AC2), AND each part rings for its own notated length
        instead of every part being clamped to whichever part happens to
        have the shortest note at this instant (Ref 9 AC2 "matches note
        duration", Ref 13 AC2 "hold for their marked length" - reported
        bug: Pachelbel's Canon cello minims were being cut short to match
        faster-moving upper parts sounding at the same beat). duration_ms
        is the MAX quarter_length within that part's own notes here (not
        an average/min) so a same-voice chord with slightly inconsistent
        source data still rings for its longest member rather than cutting
        early.

        index: an explicit timeline slice to read from instead of the
        current cursor (see _visible_notes) - used by
        get_playback_events_at_index (E4/Sequencer).
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
        """Like get_current_duration_ms, but for an arbitrary timeline index
        rather than the cursor - used by the Sequencer (E4) to know how long
        to keep is_playing True after the last step's longest note (see
        get_playback_events_for_indices for actual per-note note-off
        timing, which no longer reads this slice-wide scalar)."""
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