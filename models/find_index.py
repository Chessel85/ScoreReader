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
from typing import List, Optional

from models import vocabulary
from models.find_target import MARKING_KINDS, FindTarget


class FindIndex:
    def __init__(self, data):
        self.data = data

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
            return [
                i for i in range(len(data.timeline_slices))
                if any(
                    target.key in data._note_attribute_pairs(n)
                    for n in data._visible_notes(index=i)
                )
            ]

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
        if kind == "key_signature_change":
            return list(self.key_signature_change_indices())
        if kind == "time_signature_change":
            return list(self.time_signature_change_indices())
        if kind == "tempo_change":
            return list(self.tempo_change_indices())
        return []

    def available_targets(self) -> List[FindTarget]:
        """The Find dialog's list (widgets/find_dialog.py), always computed
        fresh from the currently loaded score's own parsed data - never a
        fixed static menu. Attribute targets are the optional (non-
        CORE_ATTRIBUTE_KEYS) keys actually present on a note in one of the
        currently active voices (Ref 7); marking targets are whichever of
        MARKING_KINDS actually occur anywhere in the score (structural,
        like Region 5 - not filtered by voice)."""
        data = self.data
        voice_tuples = (
            data.active_voice_filter if data.active_voice_filter is not None
            else data._all_voice_tuples()
        )
        present_attribute_keys = data.attribute_keys_for_voices(voice_tuples)
        targets = [
            FindTarget("attribute", key, vocabulary.attribute_label(key, data.uk_terms))
            for key in present_attribute_keys
            if key not in data.CORE_ATTRIBUTE_KEYS
        ]
        for kind_id, label in MARKING_KINDS:
            candidate = FindTarget("marking", kind_id, label)
            if any(i is not None for i in self.candidate_indices_for_target(candidate)):
                targets.append(candidate)
        return targets

    def find_occurrence(self, target: FindTarget, from_index: int, direction: int) -> Optional[int]:
        """The next (direction=+1) or previous (direction=-1) timeline_
        slices index that is an occurrence of `target`, strictly after/
        before `from_index`, wrapping once around the ends - Alt+Right/
        Alt+Left once a target has been armed (NavigationController.
        find_next/find_previous). None if `target` has no occurrences at
        all (shouldn't happen for a target that came from
        available_targets(), but the catalog and the score can drift if the
        score reloads without a fresh Find)."""
        candidates = sorted({i for i in self.candidate_indices_for_target(target) if i is not None})
        if not candidates:
            return None
        if direction > 0:
            for i in candidates:
                if i > from_index:
                    return i
            return candidates[0]
        for i in reversed(candidates):
            if i < from_index:
                return i
        return candidates[-1]
