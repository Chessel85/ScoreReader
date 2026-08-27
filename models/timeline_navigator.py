# models/timeline_navigator.py
"""S1 extraction: moving the cursor along the timeline - Left/Right,
Ctrl+Left/Right by measure, Home/End, and a typed measure jump (Refs 2/3/5/6),
plus the per-measure index lookups Region 5's span jumps and Find share.

Owns the visibility caches these lookups depend on. They key off
active_voice_filter alone, so set_active_voice_filter dropping them (through
MusicData._invalidate_visibility_cache, which delegates here) is the whole
invalidation story - the timeline itself is never reassigned after
construction.

Two rules worth keeping straight, because three near-identical predicates
sit next to each other here:

- _slice_has_visible_notes: passes the Region 2 filter. Rests included.
- slice_is_navigable: the above, OR a whole beat when the metronome is on
  (Ref 14 AC4) - what every step lands on.
- _slice_has_visible_sounding_note: actually makes a sound. Only
  sounding_bounds uses it, so trailing rest-only padding stays outside the
  navigable range while an interior rest stays reachable (Ref 16).

MusicData keeps a delegator for every method here, including the private
ones tests drive directly (_sounding_bounds, _slice_is_navigable).
"""
import bisect
from typing import Dict, List, Optional, Tuple


class TimelineNavigator:
    def __init__(self, data):
        self.data = data
        # Timeline-only caches (no active_voice_filter dependency), so they
        # live outside invalidate_cache() and are built once, lazily -
        # timeline_slices is never reassigned after construction.
        self._first_index_by_measure_cache: Optional[Dict[int, int]] = None
        self._quarters_from_start_cache: Optional[List[float]] = None
        self.invalidate_cache()

    # --- caches --------------------------------------------------------

    def invalidate_cache(self) -> None:
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

    # --- what counts as a step ------------------------------------------

    def slice_is_navigable(self, index: int) -> bool:
        """Ref 14 AC4: with the metronome on, a whole beat is steppable even
        with no note there (whole beats are integers in ts-relative units,
        Ref 18). Used at every navigation/stepping call site, but NOT by
        sounding_bounds below, which stays anchored to real sounding notes
        so metronome mode can't resurrect trailing rest-only padding."""
        data = self.data
        if data._slice_has_visible_notes(index):
            return True
        # Own bounds check: _slice_has_visible_notes returns False both for
        # "out of range" and "nothing visible", so it can't be relied on to
        # have validated the index.
        if not data.metronome_enabled or not (0 <= index < len(data.timeline_slices)):
            return False
        return float(data.timeline_slices[index].beat_position).is_integer()

    def slice_has_visible_sounding_note(self, index: int) -> bool:
        """True if this slice has a visible note that actually sounds (not a
        rest). Bounds navigation via sounding_bounds(): a rest between two
        sounding notes stays individually reachable (Ref 16), but a run of
        rests padding the final bar out to full length is not a further
        event to step onto (Ref 2/3/5).
        """
        data = self.data
        if not (0 <= index < len(data.timeline_slices)):
            return False
        notes = data.timeline_slices[index].notes
        if data.active_voice_filter is not None:
            notes = [
                n for n in notes
                if (n.part_id, n.staff, n.voice) in data.active_voice_filter
            ]
        return any(n.midi_pitch is not None for n in notes)

    def sounding_bounds(self) -> Optional[Tuple[int, int]]:
        """(first, last) index of a visible event with a real sounding note.

        This is the true navigable range for Left/Right/Ctrl+Left/Right/
        Home/End - leading or trailing rest-only padding sits outside it.
        None if nothing currently visible sounds at all. Cached per
        active_voice_filter state - see invalidate_cache.
        """
        if not self._sounding_bounds_computed:
            bounds = self._scan_bounds(self.slice_has_visible_sounding_note)
            if bounds is None:
                # Nothing in the current filter actually sounds - e.g. a UG
                # import with only its Lyrics part visible (silent by
                # design, see parsers/ug_timeline_builder.py) and its
                # Chords part switched off in Region 2. Falling back to
                # "has any visible note" bounds means there's still
                # something to navigate - a part with real, visible
                # content should never become entirely unreachable just
                # because none of it makes sound. This is strictly a
                # fallback: whenever anything does sound, the stricter
                # pass above already found real bounds and this branch
                # never runs, so every existing format's trailing-rest-
                # padding exclusion (Ref 2/3/5) is unaffected.
                bounds = self._scan_bounds(self.data._slice_has_visible_notes)
            self._sounding_bounds_cache = bounds
            self._sounding_bounds_computed = True
        return self._sounding_bounds_cache

    def _scan_bounds(self, predicate) -> Optional[Tuple[int, int]]:
        """(first, last) index satisfying `predicate`, or None for no match."""
        first_idx = None
        last_idx = None
        for i in range(len(self.data.timeline_slices)):
            if predicate(i):
                if first_idx is None:
                    first_idx = i
                last_idx = i
        return (first_idx, last_idx) if first_idx is not None else None

    # --- note-by-note movement -------------------------------------------

    def move_left(self) -> bool:
        return self._step(-1)

    def move_right(self) -> bool:
        return self._step(1)

    def _step(self, direction: int) -> bool:
        """One navigable slice in `direction`, or False at the bound - the
        boundary cue callers play (Ref 6) keys off that False. Left and
        right differ only in which end of sounding_bounds() stops them."""
        bounds = self.sounding_bounds()
        if bounds is None:
            return False
        limit = bounds[0] if direction < 0 else bounds[1]
        idx = self.data.active_event_index
        while (idx > limit) if direction < 0 else (idx < limit):
            idx += direction
            if self.slice_is_navigable(idx):
                self.data.active_event_index = idx
                return True
        return False

    # --- measure lookups --------------------------------------------------

    def measure_numbers(self) -> List[int]:
        """Distinct measure numbers present in the timeline, in ascending
        order. Cached forever - timeline_slices is fixed after construction."""
        data = self.data
        if data._measure_numbers_cache is None:
            data._measure_numbers_cache = list(
                dict.fromkeys(s.measure for s in data.timeline_slices)
            )
        return data._measure_numbers_cache

    def first_event_index_of_measure(self, measure_number: int) -> Optional[int]:
        """Index of the first timeline event in the measure, or None if it
        has none - Ref 6 turns that into a boundary cue and no movement.
        Unfiltered, unlike first_visible_event_index_of_measure below - so
        this one cache is built once and never invalidated."""
        if self._first_index_by_measure_cache is None:
            cache: Dict[int, int] = {}
            for i, s in enumerate(self.data.timeline_slices):
                if s.measure not in cache:
                    cache[s.measure] = i
            self._first_index_by_measure_cache = cache
        return self._first_index_by_measure_cache.get(measure_number)

    def first_visible_event_index_of_measure(self, measure_number: int) -> Optional[int]:
        """Like first_event_index_of_measure, but skips slices with no note
        passing the active Region 2 filter (Ref 7) - keeps Ctrl+Left/Right
        (C2) sympathetic to what's actually visible, the same way plain
        Left/Right already are via _slice_has_visible_notes."""
        if self._first_visible_index_by_measure_cache is None:
            cache: Dict[int, int] = {}
            for i, s in enumerate(self.data.timeline_slices):
                if s.measure not in cache and self.slice_is_navigable(i):
                    cache[s.measure] = i
            self._first_visible_index_by_measure_cache = cache
        return self._first_visible_index_by_measure_cache.get(measure_number)

    def last_visible_event_index_of_measure(self, measure_number: int) -> Optional[int]:
        """Ref 29: the LAST visible event of the measure - Region 5's
        Ctrl+End target ("the end of it" means the last sounding note of the
        end bar, not the first). Nothing else in the app needed a "last
        event in a measure" concept before that."""
        if self._last_visible_index_by_measure_cache is None:
            cache: Dict[int, int] = {}
            for i, s in enumerate(self.data.timeline_slices):
                if self.slice_is_navigable(i):
                    cache[s.measure] = i
            self._last_visible_index_by_measure_cache = cache
        return self._last_visible_index_by_measure_cache.get(measure_number)

    def slice_index_at_or_after_quarters(self, quarters_from_start: float) -> Optional[int]:
        """First slice index at or after an elapsed-quarters position -
        resolves a hairpin row's jump target, which the measure-only
        lookups can't since a wedge may start or stop mid-measure.

        quarters_from_start is monotonically non-decreasing across the
        timeline, so a bisect over a once-built list of those values is
        sound; the list has no filter dependency, hence no invalidation."""
        if self._quarters_from_start_cache is None:
            self._quarters_from_start_cache = [
                s.quarters_from_start for s in self.data.timeline_slices
            ]
        i = bisect.bisect_left(self._quarters_from_start_cache, quarters_from_start)
        return i if i < len(self._quarters_from_start_cache) else None

    # --- measure-by-measure movement ---------------------------------------

    def move_left_by_measure(self) -> bool:
        """Ctrl+Left (Ref 3): to the first visible event of this measure, or
        the previous measure's if already there. The pickup bar needs no
        special case - it is just the first entry in measure_numbers().
        Bounded by sounding_bounds() like plain Left, so a trailing
        rest-only measure is never a target."""
        context = self._measure_walk_context()
        if context is None:
            return False
        measures, pos, bounds = context

        first_in_current = self.first_visible_event_index_of_measure(
            self.data.get_current_slice().measure
        )
        if (
            first_in_current is not None
            and self._within(first_in_current, bounds)
            and self.data.active_event_index != first_in_current
        ):
            self.data.active_event_index = first_in_current
            return True

        return self._first_reachable(reversed(measures[:pos]), bounds)

    def move_right_by_measure(self) -> bool:
        """Ctrl+Right (Ref 3): jump to the first visible event of the next
        measure, skipping any measure left with no visible events or bounded
        out by sounding_bounds() (e.g. a trailing rest-only final bar)."""
        context = self._measure_walk_context()
        if context is None:
            return False
        measures, pos, bounds = context
        return self._first_reachable(measures[pos + 1:], bounds)

    def _measure_walk_context(self):
        """(measure list, this measure's position in it, bounds) - the three
        things both Ctrl+Left and Ctrl+Right need before they can walk, or
        None if any of them is unavailable (no cursor, nothing sounding, or
        a cursor on a measure not in the list)."""
        current = self.data.get_current_slice()
        if current is None:
            return None
        bounds = self.sounding_bounds()
        if bounds is None:
            return None
        measures = self.measure_numbers()
        try:
            pos = measures.index(current.measure)
        except ValueError:
            return None
        return measures, pos, bounds

    def _first_reachable(self, measures, bounds) -> bool:
        """Move to the first of `measures` with a visible event inside
        `bounds`, in the order given. False if none qualifies."""
        for measure in measures:
            target = self.first_visible_event_index_of_measure(measure)
            if target is not None and self._within(target, bounds):
                self.data.active_event_index = target
                return True
        return False

    @staticmethod
    def _within(index: int, bounds: Tuple[int, int]) -> bool:
        return bounds[0] <= index <= bounds[1]

    def jump_to_measure(self, measure_number: int) -> bool:
        """Ref 6: jump to the first visible event of measure_number, typed
        digit-by-digit in the Note region (C4). Bounded by sounding_bounds()
        the same way move_*_by_measure is, so a measure that exists only as
        trailing rest-only padding is not a valid target either. False
        (position unchanged) for an unknown measure number - callers play
        the boundary cue (AC4)."""
        bounds = self.sounding_bounds()
        if bounds is None:
            return False
        target = self.first_visible_event_index_of_measure(measure_number)
        if target is None or not self._within(target, bounds):
            return False
        self.data.active_event_index = target
        return True

    # --- ends of the piece --------------------------------------------------

    def move_home(self) -> bool:
        """Home (Ref 5): to the first event with a real sounding note.

        Unlike Left/Right this can never mean "moved past a boundary" - it
        jumps to a known limit - so callers never sound the boundary cue off
        this return value.
        """
        return self._move_to_bound(0)

    def move_end(self) -> bool:
        """End (Ref 5): jump to the last event with a real sounding note -
        e.g. a final bar padded out with rests in every voice does not push
        this past the piece's actual last note."""
        return self._move_to_bound(1)

    def _move_to_bound(self, which: int) -> bool:
        bounds = self.sounding_bounds()
        if bounds is None:
            return False
        self.data.active_event_index = bounds[which]
        return True

    def last_sounding_event_index(self) -> Optional[int]:
        """The true end of playable content, excluding trailing rest-only
        padding - bounds how far a phrase audition can run, as Home/End
        already bound navigation."""
        bounds = self.sounding_bounds()
        return bounds[1] if bounds else None
