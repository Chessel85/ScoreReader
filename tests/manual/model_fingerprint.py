# tests/manual/model_fingerprint.py
"""End-to-end fingerprint of what MusicData answers, across the whole score
corpus - the model-level counterpart of parser_fingerprint.py.

Where that one proves a parser change didn't alter what comes out of the
builders, this proves a MODEL change didn't alter what the app asks of the
data: navigation walks, Region 3/4 text, playback and grace events,
durations and ring-out, bar bounds, jump-aware playback stepping, Find's
occurrence lists, percussion items, the performance report, and key-override
round trips.

Used for S1 (splitting MusicData into five collaborators) and S2 (removing
models -> parsers imports) - zero differences both times.

    python tests/manual/model_fingerprint.py before.txt      # on the old tree
    python tests/manual/model_fingerprint.py after.txt --check before.txt

See README.md in this folder for the git-worktree baseline workflow.
"""
import sys

from _corpus import prepare_environment, run

prepare_environment()


def dump_one(path, out):
    from models.music_data import MusicData
    from models.playback_jump_state import PlaybackJumpState

    md = MusicData(file_path=path)
    n = len(md.timeline_slices)
    out.append(f"slices={n} measures={md.total_measures} tempo={md.tempo_bpm}")
    out.append(f"measure_numbers={md.measure_numbers()}")
    out.append(f"sounding_bounds={md._sounding_bounds()}")

    # --- navigation: walk to each end and back, recording every landing
    md.active_event_index = 0
    walk = [md.active_event_index]
    while md.move_timeline_right():
        walk.append(md.active_event_index)
    out.append(f"right_walk={walk}")
    back = [md.active_event_index]
    while md.move_timeline_left():
        back.append(md.active_event_index)
    out.append(f"left_walk={back}")

    md.active_event_index = 0
    bars = [md.active_event_index]
    while md.move_timeline_right_by_measure():
        bars.append(md.active_event_index)
    out.append(f"bar_right_walk={bars}")
    bars_back = [md.active_event_index]
    while md.move_timeline_left_by_measure():
        bars_back.append(md.active_event_index)
    out.append(f"bar_left_walk={bars_back}")

    out.append(f"home={md.move_timeline_home()},{md.active_event_index}")
    out.append(f"end={md.move_timeline_end()},{md.active_event_index}")
    out.append(f"last_sounding={md.last_sounding_event_index()}")
    for m in md.measure_numbers():
        out.append(
            f"measure {m}: first={md.first_event_index_of_measure(m)} "
            f"firstvis={md.first_visible_event_index_of_measure(m)} "
            f"lastvis={md.last_visible_event_index_of_measure(m)} "
            f"jump={md.jump_to_measure(m)}"
        )

    # --- rendering, events and timings at every slice
    for i in range(n):
        md.active_event_index = i
        s = md.timeline_slices[i]
        visible = list(range(len(md._visible_notes())))
        out.append(f"[{i}] m={s.measure} beat={s.beat_position} ts={s.time_sig} key={s.key_fifths}")
        out.append(f"  r3={md.get_region_3_data()}")
        out.append(f"  r4={md.get_region_4_rows_for_indices(visible)}")
        out.append(f"  ev={md.get_playback_events_at_index(i)}")
        out.append(f"  grace={md.get_grace_note_events_at_index(i)}")
        out.append(f"  dur={md.get_duration_ms_for_index(i)} ring={md.get_ring_out_ms_for_index(i)}")
        out.append(f"  bar={md.bar_bounds_quarters(i)} nextvis={md.next_visible_event_index(i)}")
        out.append(
            "  r5="
            + str([
                (r.label, r.jump_target_measure, r.jump_target_quarters)
                for r in md.get_performance_region_rows(i)
            ])
        )
        out.append(f"  span={md.span_ms_to_quarters(i, s.quarters_from_start + 4.0)}")

    # --- repeat/ending/D.C./D.S./Coda-aware playback stepping
    state = PlaybackJumpState()
    idx = 0
    seq = [0]
    guard = n * 3 + 10
    while guard > 0:
        guard -= 1
        nxt = md.next_playback_index(idx, state)
        if nxt is None:
            break
        seq.append(nxt)
        idx = nxt
    out.append(f"playback_walk={seq}")
    if n:
        last = min(n - 1, 20)
        end_q = md.timeline_slices[last].quarters_from_start + 4.0
        out.append(f"playback_span_ms={md.playback_span_ms(0, last, end_q)}")

    # --- Find: every offered target and everywhere it occurs
    for t in md.available_find_targets():
        # Version-agnostic: pre-S1 the scanner was
        # MusicData._candidate_indices_for_target; post-S1 it is
        # FindIndex.candidate_indices_for_target. Keeping both readable
        # means this harness can still capture a baseline from an older
        # tree.
        scan = (
            md.find_index.candidate_indices_for_target
            if hasattr(md, "find_index") else md._candidate_indices_for_target
        )
        occurrences = sorted({i for i in scan(t) if i is not None})
        out.append(f"find {t.category}/{t.key} '{t.label}' -> {occurrences}")
        out.append(
            f"  next_from_0={md.find_occurrence(t, 0, 1)} "
            f"prev_from_end={md.find_occurrence(t, n, -1)}"
        )

    # --- parts, percussion items, and the whole-score summaries
    for p in md.parts_info:
        out.append(
            f"part {p.part_id} '{p.name}' prog={p.gmidi_program} perc={p.is_percussion} "
            f"chan={md.get_channel_for_part(p.part_id)} "
            f"voices={sorted(p.staves_voices.items())} "
            f"names={sorted((str(k), v) for k, v in p.voice_names.items())}"
        )
        out.append(f"  perc_items={md.get_percussion_items_for_part(p.part_id)}")
    out.append(f"report={md.get_performance_report_lines()}")
    out.append(f"region1={md.get_region_1_data()}")
    out.append(f"status={md.get_status_bar_fields()}")

    # --- overrides must be lossless: set one, clear it, expect the original
    before = [note.step_name for s in md._real_timeline_slices for note in s.notes]
    md.apply_key_signature_override(3, "major")
    overridden = [note.step_name for s in md._real_timeline_slices for note in s.notes]
    out.append(f"key_override_steps={overridden[:60]}")
    md.apply_key_signature_override(None, None)
    after = [note.step_name for s in md._real_timeline_slices for note in s.notes]
    out.append(f"key_override_lossless={before == after}")

    md.percussion_auto_correct_enabled = True
    md.apply_percussion_overrides()
    corrected = [
        note.midi_pitch
        for s in md._real_timeline_slices
        for note in s.notes
        if note.percussion_source_key is not None
    ]
    out.append(f"perc_autocorrect_pitches={corrected[:60]}")
    md.percussion_auto_correct_enabled = False
    md.apply_percussion_overrides()


if __name__ == "__main__":
    sys.exit(run(__doc__.strip().splitlines()[0], dump_one))
