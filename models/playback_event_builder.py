# models/playback_event_builder.py
"""S1 extraction: turning timeline positions into the note groups, timings
and step order that actually get played.

Three related jobs, kept together because they all answer "what sounds, and
for how long":

- grouping visible notes by part into (channel, program, pitches,
  duration_ms[, bank]) events (Ref 8/A8), plus the grace-note side channel;
- converting quarters to real milliseconds at the tempo in force, including
  the jump-aware Preview span walk;
- deciding the next index a run steps to, both the plain filtered step and
  the repeat/ending/Segno/Coda/D.C./D.S./Fine-aware one.

Stateless with respect to a playback RUN: PlaybackJumpState is owned by the
caller (Sequencer.play_from creates a fresh one per run), so this stays the
shared, re-entrant source of truth MusicData is everywhere else. MusicData
keeps a delegator for every method here.
"""
from typing import Dict, List, Optional, Tuple

from models.gm_percussion_map import GM_PERCUSSION_BANK, GM_PERCUSSION_PROGRAM
from models.playback_jump_state import PlaybackJumpState
from models.to_coda_mark import ToCodaMark

# Sentinel for _jump_from_measure_end: "nothing here redirects the run",
# as distinct from a real None ("the run ends here", a Fine). A module-level
# object rather than a falsy value, since None and 0 are both meaningful
# returns.
JUMP_NONE = object()


class PlaybackEventBuilder:
    def __init__(self, data):
        self.data = data

    # --- note groups ---------------------------------------------------

    def events_for_indices(
        self, selected_indices: List[int], index: Optional[int] = None
    ) -> List[Tuple[int, Optional[int], List[int], int]]:
        """Group selected notes by part for simultaneous multi-part playback.

        Each group is (channel, zero-indexed GM program, midi pitches,
        duration_ms[, bank]), so a chord spanning two parts sounds both
        instruments rather than collapsing onto parts_info[0]'s (Ref 8).
        duration_ms is PER PART - the max quarter_length among that part's
        own notes here, not the slice-wide minimum - so no part is clamped
        to whichever other part happens to have the shortest note at this
        instant (Ref 9 AC2, Ref 13 AC2). The max, not the min, so a chord
        with slightly inconsistent source data rings for its longest member.

        Wishlist #8: a percussion part's group carries a trailing bank=128
        instead of its (meaningless, for percussion) gmidi_program - the
        same "trailing optional field" shape duration_ms already uses, so
        every existing 4-tuple caller (SynthEngine.play_chord's
        `event[3] if len(event) > 3 else duration_ms`) needs no change; only
        play_chord's bank read is new.

        index: read an explicit slice instead of the cursor (Sequencer).
        """
        data = self.data
        pitches_by_part, part_order, quarter_length_by_part = self._group_by_part(
            selected_indices, index, self._sounding_pitches, track_quarter_length=True
        )

        events = []
        for part_id in part_order:
            channel = data.get_channel_for_part(part_id)
            duration_ms = self.quarters_to_ms(quarter_length_by_part[part_id], index)
            if data.is_percussion_part(part_id):
                events.append(
                    (channel, GM_PERCUSSION_PROGRAM, pitches_by_part[part_id],
                     duration_ms, GM_PERCUSSION_BANK)
                )
            else:
                program = max(0, data.get_gmidi_program_for_part(part_id) - 1)
                events.append((channel, program, pitches_by_part[part_id], duration_ms))
        return events

    def grace_events_for_indices(
        self, selected_indices: List[int], index: Optional[int] = None
    ) -> List[Tuple[int, Optional[int], List[int]]]:
        """Grace note(s) attached to the selected notes (NoteData.grace_notes,
        see models/note_data.py), grouped by part - same (channel, program,
        pitches) shape as events_for_indices but with no duration_ms, since
        these are meant to sound BRIEFLY before the main chord, not for their
        own notated length (there isn't one - a grace note carries no
        <duration>). audio/strum_schedule.py's sound_events is what actually
        schedules them ahead of the main chord via
        SynthEngine.play_chord_with_grace; empty when nothing selected
        carries a grace note, the common case, which callers use to fall
        straight through to the plain play_chord path unchanged.
        """
        data = self.data
        pitches_by_part, part_order, _ = self._group_by_part(
            selected_indices, index, self._grace_pitches
        )
        return [
            (
                data.get_channel_for_part(part_id),
                max(0, data.get_gmidi_program_for_part(part_id) - 1),
                pitches_by_part[part_id],
            )
            for part_id in part_order
        ]

    @staticmethod
    def _sounding_pitches(note) -> List[int]:
        """Guitar Pro's synthetic Chords voice: one NoteData per strum event
        carries the whole chord in chord_pitches rather than a single
        midi_pitch, so the group sounds every string, not just a
        representative one (see NoteData.chord_pitches)."""
        if note.chord_pitches is not None:
            return note.chord_pitches
        return [note.midi_pitch] if note.midi_pitch is not None else []

    @staticmethod
    def _grace_pitches(note) -> List[int]:
        if not note.grace_notes:
            return []
        return [g.midi_pitch for g in note.grace_notes if g.midi_pitch is not None]

    def _group_by_part(
        self, selected_indices, index, pitches_of, track_quarter_length: bool = False
    ) -> Tuple[Dict[str, List[int]], List[str], Dict[str, float]]:
        """The walk both event builders above share: visible notes at this
        slice, restricted to the selected rows, bucketed by part in
        first-seen order (which is what keeps a chord's parts sounding in
        score order). Returns empty structures when nothing is selected or
        nothing there has a pitch to sound."""
        notes = self.data._visible_notes(index)
        pitches_by_part: Dict[str, List[int]] = {}
        quarter_length_by_part: Dict[str, float] = {}
        part_order: List[str] = []
        if not notes:
            return pitches_by_part, part_order, quarter_length_by_part
        for i in selected_indices:
            if not (0 <= i < len(notes)):
                continue
            note = notes[i]
            pitches = pitches_of(note)
            if not pitches:
                continue
            if note.part_id not in pitches_by_part:
                pitches_by_part[note.part_id] = []
                quarter_length_by_part[note.part_id] = 0.0
                part_order.append(note.part_id)
            pitches_by_part[note.part_id].extend(pitches)
            if track_quarter_length:
                quarter_length_by_part[note.part_id] = max(
                    quarter_length_by_part[note.part_id], note.quarter_length
                )
        return pitches_by_part, part_order, quarter_length_by_part

    def events_at_index(self, index: int) -> List[Tuple[int, Optional[int], List[int], int]]:
        """All visible notes at timeline index `index`, grouped by part
        (Ref 8) - the Sequencer (E4) equivalent of events_for_indices for
        Region 3's selection, playing a slice by absolute index independent
        of active_event_index."""
        return self._all_visible(index, self.events_for_indices)

    def grace_events_at_index(self, index: int) -> List[Tuple[int, Optional[int], List[int]]]:
        """The Sequencer's (index-based) equivalent of
        grace_events_for_indices, mirroring events_at_index."""
        return self._all_visible(index, self.grace_events_for_indices)

    def _all_visible(self, index: int, builder):
        """"Everything visible at this slice" - the index-based callers'
        shared "select every row" step."""
        notes = self.data._visible_notes(index)
        if not notes:
            return []
        return builder(list(range(len(notes))), index=index)

    # --- durations and elapsed time -------------------------------------

    def duration_ms_for_index(self, index: int) -> int:
        """Slice-wide duration at an arbitrary index - used only by the
        Sequencer to know how long to stay playing after the final step.
        Real per-note note-off timing is per group; see events_for_indices."""
        slices = self.data.timeline_slices
        if not (0 <= index < len(slices)):
            return 500
        return self.quarters_to_ms(slices[index].quarter_length, index)

    def ring_out_ms_for_index(self, index: int, events=None) -> int:
        """How long the notes sounding at this index actually take to
        finish ringing - the real per-part max (events_for_indices'
        duration_ms, A8/D-5), falling back to the slice-wide
        duration_ms_for_index only when nothing sounds there (a rest
        reached via the metronome's beat-marker stepping).

        Shared by Sequencer._sound_current_step (the wait before a run
        that reaches its own end naturally is considered finished) and
        playback_span_ms (so a Preview loop-restart's stop_all_notes()
        doesn't fire, and cut off, before the last previewed note has
        actually finished ringing - see playback_span_ms's own comment).
        Callers that already fetched events (Sequencer) pass them in to
        avoid recomputing."""
        if events is None:
            events = self.events_at_index(index)
        if events:
            return max(group[3] for group in events)
        return self.duration_ms_for_index(index)

    def quarters_to_ms(self, quarter_length: float, index: Optional[int]) -> int:
        ms = (quarter_length * 60000.0) / float(self.data.effective_tempo_bpm(index))
        return max(100, int(ms))

    def bar_bounds_quarters(self, index: int) -> Optional[Tuple[float, float]]:
        """(start, end) of the bar containing this slice, in elapsed
        quarters from the start of the piece - what Preview's loop needs to
        restart exactly on the bar line rather than when the last note stops
        ringing (a bar ending in rests would otherwise repeat early and out
        of time).

        Derived from the slice itself rather than from a per-measure table
        the four timeline builders would each have to publish: beat_position
        is ts-relative (Ref 18), so the distance back to the bar line is
        (beat_position - 1) beats of 4/ts_den quarters each. A pickup bar
        (Ref 17) gives its NOTIONAL bar, whose end is the real bar line -
        which is the endpoint that matters here.
        """
        slices = self.data.timeline_slices
        if not (0 <= index < len(slices)):
            return None
        current = slices[index]
        ts_num, ts_den = current.time_sig
        beat_quarters = 4.0 / float(ts_den or 4)
        start = current.quarters_from_start - (current.beat_position - 1.0) * beat_quarters
        end = start + float(ts_num or 4) * beat_quarters
        # beat_position is itself quantised to 2dp at parse time (see
        # TimelineBuilder's _MeasureOffsetWalker), so subtracting
        # (beat_position - 1) * beat_quarters leaks that rounding error into
        # start/end - e.g. a bar of triplets came out as (11.9967, 15.9967)
        # instead of (12.0, 16.0), which drifted a looping Preview's
        # bar-line restart. Real bar lines fall on 2dp-clean quarter
        # positions for every realistic metre, so snapping to that same
        # precision removes the artefact without disturbing a genuine
        # fractional bar start (a pickup's negative notional start included).
        return round(start, 2), round(end, 2)

    def span_ms_to_quarters(self, start_index: int, end_quarters: float) -> int:
        """Real milliseconds from the slice at start_index to an elapsed-
        quarters point later in the piece.

        Walks the slices in between rather than dividing once, so a tempo
        change inside the span is honoured - the same "the tempo in force
        beforehand governs the time taken to get there" rule as
        Sequencer._delay_ms_to, which this mirrors.
        """
        data = self.data
        slices = data.timeline_slices
        if not (0 <= start_index < len(slices)):
            return 0
        total_ms = 0.0
        index = start_index
        position = slices[start_index].quarters_from_start
        while index + 1 < len(slices):
            next_quarters = slices[index + 1].quarters_from_start
            if next_quarters >= end_quarters:
                break
            if next_quarters > position:
                total_ms += (next_quarters - position) * 60000.0 / float(
                    data.effective_tempo_bpm(index)
                )
                position = next_quarters
            index += 1
        if end_quarters > position:
            total_ms += (end_quarters - position) * 60000.0 / float(
                data.effective_tempo_bpm(index)
            )
        return max(0, int(round(total_ms)))

    # --- stepping ------------------------------------------------------

    def next_visible_event_index(
        self, index: int, end_index: Optional[int] = None
    ) -> Optional[int]:
        """Next index after `index` passing the Region 2 filter - rests
        INCLUDED, unlike _sounding_bounds()'s navigation range, because
        playback must advance through a rest and take up its time rather
        than skip it. Visits metronome beat markers too when the metronome
        is on, which is what makes the Sequencer click on a silent beat with
        no extra scheduling. None means the end of playback."""
        data = self.data
        limit = end_index if end_index is not None else len(data.timeline_slices) - 1
        idx = index
        while idx < limit:
            idx += 1
            if data._slice_is_navigable(idx):
                return idx
        return None

    def _dacapo_target_measure(self) -> int:
        """Da Capo means the true beginning of the piece - measure 0 when a
        pickup bar exists (Ref 17's pickup numbering), not a hardcoded 1."""
        measures = self.data.measure_numbers()
        return measures[0] if measures else 1

    def _resolve_coda_target(self, to_coda: ToCodaMark) -> Optional[int]:
        """The CodaMark a ToCodaMark jumps to: an exact label match first
        (the normal <sound tocoda="X">/<sound coda="X"> case), else the
        nearest CodaMark after this ToCodaMark's own measure (the text-only
        fallback, where neither mark carries a real label to match)."""
        coda_marks = self.data.coda_marks
        for coda in coda_marks:
            if to_coda.label and coda.label == to_coda.label:
                return coda.measure
        candidates = [c.measure for c in coda_marks if c.measure > to_coda.measure]
        return min(candidates) if candidates else None

    def next_playback_index(
        self,
        index: int,
        jump_state: PlaybackJumpState,
        end_index: Optional[int] = None,
        jump_lower_bound: int = 0,
    ) -> Optional[int]:
        """Repeat/ending/Segno/Coda/D.C./D.S./Fine-aware sibling of
        next_visible_event_index, for PLAYBACK AND PREVIEW ONLY - arrow-key
        navigation keeps calling the plain, stateless next_visible_event_index
        and is entirely untouched by this method's existence.

        jump_state is per-RUN, owned by the caller (Sequencer.play_from
        creates a fresh PlaybackJumpState alongside its other per-run resets)
        - MusicData itself stays the stateless, shared source of truth it is
        everywhere else.

        A jump is only followed when its target index falls within
        [jump_lower_bound, effective end] - this single rule is what makes
        one algorithm correct for both callers: full playback passes
        jump_lower_bound=0 (every jump in the piece is reachable, including
        one that lands before wherever this particular run happened to
        start), while Preview passes jump_lower_bound=start_index (its own
        window start) with its own short end_index, so a repeat/ending fully
        inside the previewed bars is followed while a D.C./D.S./Coda whose
        target lies outside that short window is silently skipped - it just
        falls through to plain linear stepping, exactly as it does today.

        When the score has none of these marks (every list below is empty),
        this degrades to a single next_visible_event_index call.

        Also sets jump_state.last_step_was_jump - see its own docstring.
        Default False here; each jump branch below sets it True right
        before returning.
        """
        data = self.data
        jump_state.last_step_was_jump = False
        effective_end = end_index if end_index is not None else len(data.timeline_slices) - 1

        def in_bounds(target: Optional[int]) -> bool:
            return target is not None and jump_lower_bound <= target <= effective_end

        if 0 <= index < len(data.timeline_slices):
            m = data.timeline_slices[index].measure
            if data.last_visible_event_index_of_measure(m) == index:
                target = self._jump_from_measure_end(m, jump_state, in_bounds)
                if target is not JUMP_NONE:
                    return target

        candidate = self.next_visible_event_index(index, effective_end)
        if candidate is None or not jump_state.endings_to_skip:
            return candidate
        return self._skip_taken_endings(candidate, jump_state, in_bounds)

    def _jump_from_measure_end(self, m: int, jump_state, in_bounds):
        """Whether a repeat/D.C./D.S./To Coda/Fine at the END of measure `m`
        redirects the run, and where to.

        Returns the JUMP_NONE sentinel for "no jump applies, carry on with
        plain linear stepping", which is distinct from a real None return
        (Fine: the run ends here). That distinction is why this can't just
        return Optional[int] - both outcomes are reachable from the same
        branch set."""
        data = self.data

        if not jump_state.jump_taken:
            for i, rs in enumerate(data.repeat_spans):
                if rs.end_measure == m and i not in jump_state.repeats_taken:
                    target = data.first_visible_event_index_of_measure(rs.start_measure)
                    if in_bounds(target):
                        jump_state.repeats_taken.add(i)
                        for j, es in enumerate(data.ending_spans):
                            if es.start_measure <= m <= es.end_measure:
                                jump_state.endings_to_skip.add(j)
                        jump_state.last_step_was_jump = True
                        return target
                    break

            for nj in data.navigation_jumps:
                if nj.measure != m:
                    continue
                if nj.kind == "dacapo":
                    target_measure = self._dacapo_target_measure()
                else:
                    label = nj.target_label or "1"
                    segno = next(
                        (s for s in data.segno_marks if (s.label or "1") == label), None
                    )
                    if segno is None:
                        continue
                    target_measure = segno.measure
                target = data.first_visible_event_index_of_measure(target_measure)
                if in_bounds(target):
                    jump_state.jump_taken = True
                    jump_state.last_step_was_jump = True
                    return target
                break

        if jump_state.jump_taken:
            for tc in data.to_coda_marks:
                if tc.measure == m:
                    coda_measure = self._resolve_coda_target(tc)
                    if coda_measure is not None:
                        target = data.first_visible_event_index_of_measure(coda_measure)
                        if in_bounds(target):
                            jump_state.last_step_was_jump = True
                            return target
                    break

            if any(fm.measure == m for fm in data.fine_marks):
                return None

        return JUMP_NONE

    def _skip_taken_endings(self, candidate: int, jump_state, in_bounds) -> Optional[int]:
        """Redirect past any 1st/2nd ending this run has already played -
        looped, since skipping one ending can land straight on another."""
        data = self.data
        seen = 0
        while candidate is not None and seen <= len(data.ending_spans):
            candidate_measure = data.timeline_slices[candidate].measure
            hit = next(
                (
                    j for j in jump_state.endings_to_skip
                    if data.ending_spans[j].start_measure == candidate_measure
                ),
                None,
            )
            if hit is None:
                break
            redirected = data.first_visible_event_index_of_measure(
                data.ending_spans[hit].end_measure + 1
            )
            if not in_bounds(redirected):
                break
            candidate = redirected
            jump_state.last_step_was_jump = True
            seen += 1
        return candidate

    def _step_ms(self, index: int, next_index: int, position: float, jumped: bool) -> int:
        """One walk step's contribution to elapsed ms, matching
        Sequencer._delay_ms_to exactly: a step reached by a jump waits out
        the departing note's own real ring-out (ring_out_ms_for_index, the
        per-group max - not the slice-wide minimum); a plain forward step is
        the quarters delta at the tempo in force, int()-truncated with a 1 ms
        floor (see playback_span_ms's own comment on why accumulating the
        un-rounded float instead drifts audibly late)."""
        if jumped:
            return self.ring_out_ms_for_index(index)
        slices = self.data.timeline_slices
        delta_quarters = slices[next_index].quarters_from_start - position
        return max(1, int(
            delta_quarters * 60000.0 / float(self.data.effective_tempo_bpm(index))
        ))

    def _tail_ms(self, index: int, position: float, end_quarters: float) -> int:
        """The distance from the last walked note's onset to end_quarters
        (the bar line), OR that note's own real ring-out - whichever is
        longer. int()-truncated to match ring_out_ms_for_index's own
        precision (see playback_span_ms's own comment)."""
        bar_line_ms = int(max(0.0, end_quarters - position) * 60000.0 / float(
            self.data.effective_tempo_bpm(index)
        ))
        return max(bar_line_ms, self.ring_out_ms_for_index(index))

    def simulate_loop_iteration(
        self, start_index: int, measure_budget: int, seed_jump_state=None
    ) -> Tuple[List[int], int, float]:
        """One looped iteration's repeat-aware walk, as
        (indices, span_ms, end_quarters).

        A budgeted, seedable generalisation of playback_span_ms: steps
        next_playback_index from start_index with jump_lower_bound=0 (so a
        backward repeat whose target precedes the loop window is still
        followed) and no end_index, seeded from a COPY of seed_jump_state
        (fresh when None), until it has entered measure_budget distinct bars
        or next_playback_index genuinely returns None (end of score). A
        backward jump into an earlier bar counts as a new bar entry. span_ms
        accumulates real elapsed milliseconds with the same jump/ring-out
        handling the real Sequencer applies; end_quarters is the bar line
        after the last walked note, which is where the ("loop",) restart
        timer fires.
        """
        data = self.data
        slices = data.timeline_slices
        if not (0 <= start_index < len(slices)):
            return [], 0, 0.0
        jump_state = (
            seed_jump_state.copy() if seed_jump_state is not None else PlaybackJumpState()
        )
        budget = max(1, int(measure_budget))
        indices = [start_index]
        total_ms = 0.0
        index = start_index
        position = slices[start_index].quarters_from_start
        measures_entered = 1
        budget_measure = slices[start_index].measure
        guard = len(slices) * 4 + 8
        while guard > 0:
            guard -= 1
            next_index = self.next_playback_index(index, jump_state, None, 0)
            if next_index is None:
                break
            next_measure = slices[next_index].measure
            if next_measure != budget_measure:
                if measures_entered + 1 > budget:
                    break
                measures_entered += 1
                budget_measure = next_measure
            total_ms += self._step_ms(
                index, next_index, position, jump_state.last_step_was_jump
            )
            position = slices[next_index].quarters_from_start
            index = next_index
            indices.append(next_index)
        bounds = self.bar_bounds_quarters(indices[-1])
        end_quarters = bounds[1] if bounds else slices[indices[-1]].quarters_from_start
        total_ms += self._tail_ms(index, position, end_quarters)
        return indices, max(0, int(round(total_ms))), end_quarters

    def playback_span_ms(self, start_index: int, end_index: int, end_quarters: float) -> int:
        """Jump-aware sibling of span_ms_to_quarters (left untouched, still
        used elsewhere) - needed because Preview's own loop-restart timing
        (_build_preview_run's iteration_ms) must know the REAL elapsed time a
        repeat/jump-aware run through [start_index, end_index] takes, not the
        flat, jump-unaware walk span_ms_to_quarters does. Without this, a
        repeat fully inside the preview window would make the real Sequencer
        run take longer than the separately-scheduled loop-restart timer
        expects, truncating the repeat mid-replay.

        Simulates the walk with a throwaway PlaybackJumpState (this is not a
        real playback run - nothing actually sounds), using the same
        jump_lower_bound=start_index Preview itself passes to Sequencer.
        play_from, then adds the same tail-to-end_quarters segment
        span_ms_to_quarters computes, so the loop still restarts on the true
        bar line rather than when the last simulated note's ring-out ends.
        When nothing inside the window jumps, this is numerically identical
        to span_ms_to_quarters.
        """
        data = self.data
        slices = data.timeline_slices
        if not (0 <= start_index < len(slices)):
            return 0
        jump_state = PlaybackJumpState()
        total_ms = 0.0
        index = start_index
        position = slices[start_index].quarters_from_start
        guard = len(slices) * 2 + 4
        while guard > 0:
            guard -= 1
            next_index = self.next_playback_index(index, jump_state, end_index, start_index)
            # Deliberately NOT "if index == end_index: break" here - reaching
            # end_index must still get its own next_playback_index call
            # before stopping, or a repeat/jump whose TRIGGER point is
            # end_index itself (e.g. a repeat spanning exactly the previewed
            # window, a common case since a repeat is often exactly the
            # requested bar count) would never be detected: next_index is
            # None only once next_playback_index has genuinely found nothing
            # further to do at end_index (bounded by the SAME end_index it
            # was passed), which is what actually ends this walk.
            if next_index is None:
                break
            next_quarters = slices[next_index].quarters_from_start
            # _step_ms encapsulates both cases (a jump waits out the
            # departing note's real ring-out; a plain step is the
            # int()-truncated, 1ms-floored quarters delta) - the same
            # computation simulate_loop_iteration walks with, so the two
            # predictions can't drift apart. See _step_ms's own docstring
            # for why the truncation is load-bearing (reported live: a
            # repeated passage's loop-restart drifted audibly late when the
            # un-rounded float was accumulated instead).
            total_ms += self._step_ms(
                index, next_index, position, jump_state.last_step_was_jump
            )
            position = next_quarters
            index = next_index
        # The bar-line-anchored distance from the last simulated note's
        # onset to end_quarters, OR that note's own real ring-out - whichever
        # is longer. Ordinarily the bar line wins (a short final note
        # followed by rests must not restart the loop early - see this
        # method's own docstring); but a note written to ring PAST the bar
        # line (e.g. tied into the next, unpreviewed bar) must still finish
        # before Preview's loop-restart calls stop_all_notes(), or it gets
        # cut short - reported live, the same "don't cut the last note
        # short" bug class next_index-is-None handling already fixed for a
        # repeat landing exactly on the window's last bar (see this
        # method's own docstring).
        # int()-truncated to match ring_out_ms_for_index's own precision
        # (duration_ms_for_index -> quarters_to_ms) - when the final note
        # fills exactly to the bar line, both express the identical
        # quarters-to-ms conversion, and comparing an untruncated float
        # against a truncated int would let the float win by its own
        # sub-1ms fraction even though they agree on the real duration,
        # adding a spurious extra ms (reported live, same drift as the walk
        # truncation above - this is the tail's own instance of it).
        total_ms += self._tail_ms(index, position, end_quarters)
        return max(0, int(round(total_ms)))

