# models/find_index.py
"""S1 extraction: the Find dialog's occurrence scanner, lifted out of
MusicData as its own collaborator.

Holds a reference back to the MusicData it scans rather than owning any
state of its own - every lookup here reads the score live, because the
active voice filter (Ref 7), the key signature override (S6) and the
attribute display system all change what counts as an occurrence without
the timeline itself changing. MusicData keeps one-line delegators for
available_find_targets/find_occurrence, so call sites and tests are
unchanged.
"""
import bisect
from typing import Dict, List, Optional, Set, Tuple

from models import vocabulary
from models.find_target import MARKING_KINDS, VALUE_EXPANDED_KEYS, FindTarget


class FindIndex:
    def __init__(self, data):
        self.data = data
        # M1: for an attribute target, candidate_indices_for_target runs
        # _note_attribute_pairs (real per-note string formatting) over
        # every visible note of every slice - the single most expensive
        # thing on the Alt+Right/Alt+Left hot path, discarded and rebuilt
        # on every keypress. Cache the sorted occurrence list per
        # attribute key. It depends only on the active voice filter (Ref 7)
        # and on the metronome toggle rebuilding timeline_slices, both of
        # which already route through MusicData._invalidate_visibility_
        # cache - which now calls invalidate_cache() here too (the S7
        # pattern). Marking targets stay uncached: their scans are span
        # iterations or one tuple-comparison pass with no per-note
        # formatting, and key_signature_change additionally depends on the
        # S6 key override, which does not flow through that hook.
        #
        # D1: keyed on (key, value) - value None is the "any" target, a set
        # value is one per-value refinement - so the per-value targets each
        # get their own cached list rather than sharing the key's.
        self._attribute_candidate_cache: Dict[Tuple[str, Optional[str]], List[int]] = {}

    def invalidate_cache(self) -> None:
        """Drop the cached attribute-target occurrence lists - see
        __init__. Called from MusicData._invalidate_visibility_cache
        whenever the active voice filter changes or the metronome toggle
        rebuilds timeline_slices."""
        self._attribute_candidate_cache.clear()

    # --- signature/tempo change points --------------------------------

    def key_signature_change_indices(self) -> List[int]:
        """Every timeline_slices index whose key signature differs from the
        one before it - the same comparison get_performance_region_rows
        makes at a single index, walked here across the whole score for
        Find's "next/previous key signature change" target. A key
        signature override forces one constant display key score-wide, so
        there are no change points to find while one is active."""
        data = self.data
        if data.key_signature_override_fifths is not None:
            return []
        slices = data.timeline_slices
        return [
            i for i in range(1, len(slices))
            if slices[i - 1].key_fifths != slices[i].key_fifths
        ]

    def time_signature_change_indices(self) -> List[int]:
        """Time-signature counterpart of key_signature_change_indices."""
        slices = self.data.timeline_slices
        return [
            i for i in range(1, len(slices))
            if slices[i - 1].time_sig != slices[i].time_sig
        ]

    def tempo_change_indices(self) -> List[int]:
        """Tempo counterpart of key_signature_change_indices, via the same
        _tempo_change_at comparison get_performance_region_rows uses."""
        data = self.data
        return [
            i for i in range(1, len(data.timeline_slices))
            if data._tempo_change_at(i - 1) != data._tempo_change_at(i)
        ]

    # --- occurrence scanning ------------------------------------------

    def candidate_indices_for_target(self, target: FindTarget) -> List[Optional[int]]:
        """Every timeline_slices index that is an occurrence of `target`,
        unsorted and possibly containing None (an unresolvable span/mark -
        filtered out by callers). Attribute targets scan note presence
        directly; marking targets resolve through the same
        first_visible_event_index_of_measure/last_visible_event_index_of_
        measure/slice_index_at_or_after_quarters lookups
        NavigationController.jump_to_span already uses for Region 5, so a
        Find result and a Region 5 jump can never disagree on where a
        marking "is". This single method also decides presence for
        available_targets() below - a target is offered only when this list
        has at least one real occurrence - so the catalog and the scanner
        can't drift apart."""
        data = self.data

        if target.category == "attribute":
            key = target.key
            want = target.value
            result: List[Optional[int]] = []
            for i in range(len(data.timeline_slices)):
                for n in data._visible_notes(index=i):
                    pairs = data._note_attribute_pairs(n)
                    raw = pairs.get(key)
                    if raw is None:
                        continue
                    if want is None:
                        result.append(i)
                        break
                    # Several keys hold a comma-joined list (articulation,
                    # fingering, technique, ...) - match membership over the
                    # split values, never == on the whole string (D1).
                    if want in [v.strip() for v in raw.split(",")]:
                        result.append(i)
                        break
            return result

        kind = target.key
        first_of = data.first_visible_event_index_of_measure
        last_of = data.last_visible_event_index_of_measure
        at_quarters = data.slice_index_at_or_after_quarters

        if kind == "repeat_start":
            return [first_of(s.start_measure) for s in data.repeat_spans]
        if kind == "repeat_end":
            return [last_of(s.end_measure) for s in data.repeat_spans]
        if kind == "ending_start":
            return [first_of(s.start_measure) for s in data.ending_spans]
        if kind == "ending_end":
            return [last_of(s.end_measure) for s in data.ending_spans]
        # crescendo/diminuendo differ only in which hairpin kind and which
        # endpoint they read, so the four separate branches this replaced
        # were four copies of one lookup.
        if kind in ("crescendo_start", "diminuendo_start"):
            hairpin_kind = kind[: -len("_start")]
            return [
                at_quarters(s.start_quarters_from_start)
                for s in data.hairpin_spans if s.kind == hairpin_kind
            ]
        if kind in ("crescendo_end", "diminuendo_end"):
            hairpin_kind = kind[: -len("_end")]
            return [
                at_quarters(s.end_quarters_from_start)
                for s in data.hairpin_spans if s.kind == hairpin_kind
            ]
        if kind == "segno":
            return [first_of(m.measure) for m in data.segno_marks]
        if kind == "coda":
            return [first_of(m.measure) for m in data.coda_marks]
        if kind == "to_coda":
            return [first_of(m.measure) for m in data.to_coda_marks]
        if kind == "fine":
            return [first_of(m.measure) for m in data.fine_marks]
        # navigation_jumps.kind uses these exact two ids, so the target key
        # is the filter - no mapping table needed.
        if kind in ("dacapo", "dalsegno"):
            return [
                first_of(m.measure)
                for m in data.navigation_jumps if m.kind == kind
            ]
        # P3: <direction> spans resolve through slice_index_at_or_after_
        # quarters (a direction can start/stop mid-measure, like a hairpin);
        # points resolve through first_visible_event_index_of_measure.
        if kind == "pedal_start":
            return [at_quarters(s.start_quarters_from_start)
                    for s in data.direction_spans if s.kind == "pedal"]
        if kind == "pedal_end":
            return [at_quarters(s.end_quarters_from_start)
                    for s in data.direction_spans if s.kind == "pedal"]
        if kind == "pedal_change":
            return [first_of(m.measure)
                    for m in data.direction_marks if m.kind == "pedal_change"]
        if kind == "octave_shift_start":
            return [at_quarters(s.start_quarters_from_start)
                    for s in data.direction_spans if s.kind == "octave_shift"]
        if kind == "octave_shift_end":
            return [at_quarters(s.end_quarters_from_start)
                    for s in data.direction_spans if s.kind == "octave_shift"]
        if kind == "rehearsal":
            return [first_of(m.measure)
                    for m in data.direction_marks if m.kind == "rehearsal"]
        if kind == "dashed_line_start":
            return [at_quarters(s.start_quarters_from_start)
                    for s in data.direction_spans if s.kind == "dashes"]
        if kind == "dashed_line_end":
            return [at_quarters(s.end_quarters_from_start)
                    for s in data.direction_spans if s.kind == "dashes"]
        if kind == "bracket_line_start":
            return [at_quarters(s.start_quarters_from_start)
                    for s in data.direction_spans if s.kind == "bracket"]
        if kind == "bracket_line_end":
            return [at_quarters(s.end_quarters_from_start)
                    for s in data.direction_spans if s.kind == "bracket"]
        if kind == "other_direction":
            return [first_of(m.measure)
                    for m in data.direction_marks if m.kind == "other_direction"]
        if kind == "key_signature_change":
            return list(self.key_signature_change_indices())
        if kind == "time_signature_change":
            return list(self.time_signature_change_indices())
        if kind == "tempo_change":
            return list(self.tempo_change_indices())
        return []

    def _distinct_values_by_key(
        self, voice_tuples: Set[Tuple[str, int, int]]
    ) -> Dict[str, List[str]]:
        """attribute key -> its distinct comma-split values across the whole
        score, restricted to VALUE_EXPANDED_KEYS (D1/D2). One pass over
        _real_timeline_slices (the stable, marker-free timeline - same scan
        shape as NoteRenderer.attribute_keys_for_voices), so
        available_targets() never scans once per key. Values come back
        sorted for a deterministic dialog order (available_targets then
        re-sorts by count)."""
        buckets: Dict[str, Set[str]] = {}
        for event_slice in self.data._real_timeline_slices:
            for note in event_slice.notes:
                if (note.part_id, note.staff, note.voice) not in voice_tuples:
                    continue
                pairs = self.data._note_attribute_pairs(note)
                for key in VALUE_EXPANDED_KEYS:
                    raw = pairs.get(key)
                    if raw is None:
                        continue
                    bucket = buckets.setdefault(key, set())
                    for value in raw.split(","):
                        value = value.strip()
                        if value:
                            bucket.add(value)
        return {key: sorted(values) for key, values in buckets.items()}

    def available_targets(self) -> List[FindTarget]:
        """The Find dialog's list (widgets/find_dialog.py) - see
        available_targets_with_counts, of which this is the count-less
        projection kept for callers that only need the targets."""
        return [target for target, _ in self.available_targets_with_counts()]

    def available_targets_with_counts(self) -> List[Tuple[FindTarget, int]]:
        """The Find dialog's list plus each row's occurrence count (D13),
        always computed fresh from the currently loaded score's own parsed
        data - never a fixed static menu.

        Attribute targets are the optional (non-CORE_ATTRIBUTE_KEYS) keys
        actually present on a note in one of the currently active voices
        (Ref 7); each such key gets an "any" target, and - for the keys in
        VALUE_EXPANDED_KEYS - one target per distinct value (D1/D2), ordered
        most-common-first. Marking targets are whichever of MARKING_KINDS
        actually occur anywhere in the score (structural, like Region 5 -
        not filtered by voice).

        Every target's occurrence list is computed exactly once here, via
        the cached sorted_candidate_indices path, and both its presence
        (offered only when non-empty - so no row ever reads "0 occurrences")
        and its count are read off that same list."""
        data = self.data
        voice_tuples = (
            data.active_voice_filter if data.active_voice_filter is not None
            else data._all_voice_tuples()
        )
        present_attribute_keys = [
            key for key in data.attribute_keys_for_voices(voice_tuples)
            if key not in data.CORE_ATTRIBUTE_KEYS
        ]
        distinct_values = self._distinct_values_by_key(voice_tuples)

        results: List[Tuple[FindTarget, int]] = []
        for key in present_attribute_keys:
            base_label = vocabulary.attribute_label(key, data.uk_terms)
            expanded = key in VALUE_EXPANDED_KEYS and distinct_values.get(key)
            any_label = f"{base_label} (any)" if expanded else base_label
            any_target = FindTarget("attribute", key, any_label)
            any_indices = self.sorted_candidate_indices(any_target)
            if not any_indices:
                continue
            results.append((any_target, len(any_indices)))
            if not expanded:
                continue
            value_rows: List[Tuple[FindTarget, int]] = []
            for value in distinct_values[key]:
                target = FindTarget("attribute", key, base_label, value)
                indices = self.sorted_candidate_indices(target)
                if indices:
                    value_rows.append((target, len(indices)))
            value_rows.sort(key=lambda row: (-row[1], row[0].value or ""))
            results.extend(value_rows)

        for kind_id, label in MARKING_KINDS:
            candidate = FindTarget("marking", kind_id, label)
            indices = self.sorted_candidate_indices(candidate)
            if indices:
                results.append((candidate, len(indices)))
        return results

    def sorted_candidate_indices(self, target: FindTarget) -> List[int]:
        """candidate_indices_for_target(), de-duplicated, None-filtered and
        sorted ascending - the form find_occurrence bisects over.
        Attribute-target lists are cached (see __init__); marking-target
        lists are rebuilt each call."""
        if target.category == "attribute":
            cache_key = (target.key, target.value)
            cached = self._attribute_candidate_cache.get(cache_key)
            if cached is None:
                cached = self._compute_sorted_candidates(target)
                self._attribute_candidate_cache[cache_key] = cached
            return cached
        return self._compute_sorted_candidates(target)

    def _compute_sorted_candidates(self, target: FindTarget) -> List[int]:
        return sorted(
            {i for i in self.candidate_indices_for_target(target) if i is not None}
        )

    def find_occurrence(self, target: FindTarget, from_index: int, direction: int) -> Optional[int]:
        """The next (direction=+1) or previous (direction=-1) timeline_
        slices index that is an occurrence of `target`, strictly after/
        before `from_index`, wrapping once around the ends - Alt+Right/
        Alt+Left once a target has been armed (NavigationController.
        find_next/find_previous). None if `target` has no occurrences at
        all (shouldn't happen for a target that came from
        available_targets(), but the catalog and the score can drift if the
        score reloads without a fresh Find)."""
        candidates = self.sorted_candidate_indices(target)
        if not candidates:
            return None
        if direction > 0:
            pos = bisect.bisect_right(candidates, from_index)
            return candidates[pos] if pos < len(candidates) else candidates[0]
        pos = bisect.bisect_left(candidates, from_index)
        return candidates[pos - 1] if pos > 0 else candidates[-1]
