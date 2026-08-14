# Code Review - 2026-08-14

Senior Python / PySide6 review of the whole codebase as of commit `ab860ae`
(main, plus an uncommitted `wishlist.txt` edit). Tracked in git deliberately,
same reasoning as `tasks.txt`: the findings outlive the conversation that
produced them. Remediation is tracked as **PHASE R** in `tasks.txt` - one line
per finding, cross-referenced back to the R-numbers below.

**Remediation status (2026-08-14): 15 of 18 fixed.** R1-R5, R7, R8, R10-R12,
R14-R18 are done - see the per-finding "Resolved" notes and the `> DONE` notes
in `tasks.txt`. Three remain open, each deliberately:

| Open | Why it was left |
|---|---|
| R6 (MainWindow God object) | A real refactor with its own design decisions - deserves its own change, not a tail-end of a cleanup batch. |
| R9 (prose-to-code ratio) | Judgement-heavy and touches nearly every file; wants an explicit call on how much history stays in the code. |
| R13 (silent no-op while loading) | Needs a product decision: what a screen-reader user should hear when a load is already in flight. |

Suite after remediation: **358 passing**, pyflakes clean across the project,
and clean under `-W error::RuntimeWarning`.

## Method

- Read all app code (~3,900 non-comment lines) across `models/`, `parsers/`,
  `audio/`, `widgets/`, `persistence/`, `workers/`, `main.py`, `main_window.py`.
- `pytest`: 350 passed in 6.14s.
- `pyflakes` over project directories (excluding `.venv`): 2 hits total.
- Benchmarked hot paths against `examples/etude-opus-25-no-12-ocean-frederic-chopin.mxl`
  (1,317 slices / 2,699 notes).
- Empirically probed Qt Tab/focus dispatch per region widget with an offscreen
  `QApplication` and a `NullSynth` (see R1 below - the measurement is the finding).

## Scores

| Criterion | Score | Verdict |
|---|---|---|
| Performance & efficiency | 8.5/10 | Measurably fine. Loading is off-thread; the caches that matter exist. |
| Simplification opportunities | 6/10 | Real duplication in `TimelineBuilder` and `MainWindow`. |
| Readability & maintainability | 6.5/10 | Code is clean and idiomatic; prose volume and two 1,300+ line files are the drag. |
| Architecture (Qt vs logic separation) | 7.5/10 | Good split, undermined by one layering violation and a God-class `MainWindow`. |
| Technical debt | 8/10 | Almost no dead code, pyflakes-clean, no unused imports. |
| Test engineering | 9/10 | Offscreen + audio-blocking fixtures, injected synth/timer/locale. |
| Error handling | 4/10 | `print("[ERROR]")` throughout - already tracked as Ref 25 / NFR-06 (Phase I). |
| **Overall** | **7.5/10** | |

### Measured performance (Chopin etude, 2,699 notes)

| Operation | Time |
|---|---|
| Full load (`MusicXMLReader.load()`, runs off the UI thread) | 266 ms |
| 200 x `move_timeline_right()` | 0.7 ms |
| `attribute_keys_for_voices()` over the whole score | 4.8 ms |
| `get_performance_report_lines()` | 0.4 ms |

No O(N^2) path, nothing blocking the event loop. The `_invalidate_visibility_cache`
work paid off: the two lookups that were O(N*M) are the two that got cached, and
the remaining linear scans are small enough not to matter at real score sizes.

---

## Findings

### HIGH

#### R1. Two region widgets' Tab handlers are dead code; the focus cycle works by coincidence

`widgets/region2_list_widget.py:85-90`, `widgets/timeline_list_widget.py:97-100`

`widgets/region5_list_widget.py:73-95` documents (live-tested, Ref 29) that
`QAbstractItemView` consumes Tab/Backtab at the `event()` level, before
`keyPressEvent()` is ever called, for a single-column view - and fixes it *only
for Region 5*. Region 2 and Region 3 still use the `keyPressEvent` pattern, so
their Tab branches never execute. Verified by instrumenting
`MainWindow.focus_next_region`:

```
region_1  handler_called=True    (QTableWidget - Tab does reach keyPressEvent)
region_2  handler_called=False   -> moved via Qt's native focus chain
region_3  handler_called=False   -> moved via Qt's native focus chain
region_4  handler_called=True
region_5  handler_called=True
```

Focus currently lands correctly in both directions, wrap included - purely
because Qt's implicit chain (built from widget creation order in `setup_ui`)
happens to match the intended cycle. Inserting or reordering a region breaks it
silently, which is exactly the failure Ref 29 already hit once at the
wrap-around.

**Fix:** move Tab/Backtab interception into `event()` for `Region2ListWidget`
and `TimelineListWidget`, sharing one implementation with `Region5ListWidget`.
Both Shift+Tab conventions (`Key_Backtab`, and `Key_Tab` + `ShiftModifier`) must
be checked, per Region 5's own finding.

**Resolved 2026-08-14.** Region 5's `event()` interception was extracted to
`widgets/region_focus_cycle.py` (`RegionFocusCycleMixin`) and applied to all
four `QAbstractItemView`-based region widgets - `RegionTableWidget` (Regions 1
and 4), `Region2ListWidget`, `TimelineListWidget`, `Region5ListWidget`. The four
now-dead `keyPressEvent` Tab branches were deleted. All ten transitions
(5 regions x Tab/Shift+Tab) were re-measured and now route through the real
handler.

Two notes for whoever touches this next:

- The new test asserts the *handler runs*, not just where focus lands. The two
  pre-existing cycle tests only asserted the landing widget, so they passed
  throughout the broken period - a coincidence is indistinguishable from
  correct wiring by that measure.
- `tests/widgets/test_region4_table_widget.py::test_tab_still_forwards_to_the_region_cycle`
  had to change: it called `keyPressEvent` directly, explicitly to route around
  Qt intercepting Tab first. That interception *was the bug*, so the test now
  dispatches through `event()` - the path Qt itself uses.

#### R2. Layering violation: `models/` transitively imports PySide6

`models/music_data.py:16` -> `persistence/score_config.py:8`

`main_window.py:52` states the invariant "models/ stays Qt-free" as the reason
`detect_default_uk_terms()` lives in the UI layer rather than in
`models/vocabulary.py`. That invariant is already broken: importing
`models.music_data` loads `PySide6.QtCore` (confirmed via `sys.modules`),
because `MusicData` imports `ScoreConfig`, and `ScoreConfig` sits in the same
module as the `QStandardPaths` path resolution.

**Fix:** move the `ScoreConfig` dataclass into `models/`, leaving
`persistence/score_config.py` as Qt-aware I/O only
(`config_dir`/`path_for`/`load_for`/`save`/`delete_for`). Re-export from
`persistence.score_config` so existing imports keep working.

**Resolved 2026-08-14.** `ScoreConfig` plus the `VoiceKey`/`StaffKey` aliases
now live in `models/score_config_data.py` (stdlib only). The JSON key codecs
deliberately stayed in `persistence/` - how a tuple key is spelled in a file is
a serialisation concern, not part of the data shape. `persistence.score_config`
re-exports `ScoreConfig`, so no import site changed.

Guarded by `test_models_package_does_not_import_qt` in `tests/test_harness.py`,
which imports every `models/` module in a **subprocess** - the test session
itself loads PySide6 via conftest before anything else, so in-process
`sys.modules` cannot attribute the import to anyone. Confirmed non-vacuous:
importing all of `models/*` leaves 0 PySide6 modules loaded; adding
`import persistence.score_config` leaves 15.

### MEDIUM

#### R3. `QApplication.focusChanged` is connected and never disconnected

`main_window.py:227`. Application-scoped connection with no teardown in
`closeEvent`. Every `MainWindow` ever constructed stays subscribed; after one is
destroyed the slot fires into a deleted C++ object. The adjacent comment
(231-233) records that cross-test window survival has already caused
ambiguous-shortcut conflicts.

**Resolved 2026-08-14.** `_disconnect_focus_tracking()`, called from
`closeEvent`. Guarded by a `_focus_tracking_connected` flag rather than
try/except - `closeEvent` legitimately runs twice (an explicit `close()` then
fixture teardown, which two tests do), and PySide6 does **not** raise on a stale
disconnect: it emits a `RuntimeWarning` and continues, so an `except` clause
would never have caught it and the noise would have accumulated silently. The
suite now runs clean under `-W error::RuntimeWarning`.

#### R4. `TimelineBuilder`: the same measure-number parse five times, and four separate walks of part 1

`parsers/timeline_builder.py:191-197, 473-478, 520-525, 606-611, 673-678` -
identical `int(m.attrib.get("number", "1"))` + reindex block, verbatim, five
times. Extract `_measure_number(m, needs_reindex)`.

Separately, `_measure_start_quarters`, `_tempo_changes`,
`_repeat_and_ending_spans` and `_hairpin_spans` each independently walk
`root.find("part")`'s measures with their own `_MeasureOffsetWalker`. Runtime
cost is negligible (~1 ms), but it is 4x the maintenance surface and 4x the
places a reindex or offset bug can diverge.

**Resolved 2026-08-14.** `_measure_number()`/`_raw_measure_number()` module
helpers replace all five copies. The four passes collapse into one
`_scan_first_part()` returning a `_FirstPartScan`, with `_step_barline` and
`_step_wedge` as per-element helpers (-148 lines). Verified behaviour-preserving
by diffing slices, `tempo_changes`, repeat/ending/hairpin spans, `beat_markers`
and `total_measures` between the pre- and post-refactor parsers across all 44
scores in `files/`, `examples/` and `tests/fixtures/`: **zero differences**.

#### R5. The `<part-name>` duplication CLAUDE.md flags as fragile is structurally avoidable

`parsers/timeline_builder.py:156-162` vs `parsers/musicXML_reader.py` (part
structure extraction). CLAUDE.md documents that these two independent reads
"must match verbatim" or the Performance Report silently reports 0 notes - a bug
already shipped and fixed once (the Korean `<part-name>` case). But
`TimelineBuilder.__init__` already *receives* `parts_info` and uses it only for
`parts_info[0].name` as a default. Deriving `part_names` from `parts_info` when
it is non-empty removes the invariant instead of documenting it.

**Resolved 2026-08-14.** `TimelineBuilder._part_names()` derives from
`parts_info` when present, keeping the ElementTree read only for the no-reader
path (`MusicData(file_path=...)` built directly, which has no `parts_info` at
all). Agreement is now structural rather than a convention to remember. Two
regression tests: one hands `TimelineBuilder` a `parts_info` the file itself
contradicts, proving the XML is no longer consulted; one covers the fallback.
Re-checked end to end on the Korean-`<part-name>` bourree - the report shows 492
notes, not 0.

#### R6. `MainWindow` is a 1,469-line God object

Menu construction (`setup_menu`, ~190 lines), focus/pane management, six dialog
launchers, timeline navigation, playback transport, persistence orchestration
and per-region refresh in one class. Business logic is *not* leaking into the
widgets (`MusicData` owns it - that part is right), but the controller has no
seams. Suggested split: `MenuBuilder`, a `PlaybackController` wrapping
Sequencer/status-field logic, a `RegionRefresher`. Concrete duplication inside:

- `selected_indices = [item.row() for item in self.region_3.selectedIndexes()]`
  three times (`main_window.py:1000, 1014, 1125`).
- Five one-line `_navigation_menu_move_to_*` methods (509-519) and four
  near-identical `navigate_*` methods (724-754).
- The click + announcer blocks in `_play_selected_region_3_notes` (1138-1153)
  duplicate `Sequencer._sound_current_step` (`audio/sequencer.py:155-171`).

#### R7. Stale documentation contradicting the code

`audio/metronome.py:44-48` and `audio/position_announcer.py:33, 95` still state
that `play_click`/`play_word` read each sample's natural duration from a sidecar
`soundfonts/recall_score_sounds.sf2.json`. That sidecar was removed;
`audio/synth_engine.py:264` documents the removal at length. Also
`models/music_data.py:1150` says "16 channels minus the two reservations" -
there are three (`RESERVED_CHANNELS`).

**Resolved 2026-08-14.** Both docstrings now state the real mechanism (a
one-shot sample retires itself; no note-off scheduling anywhere) and say
explicitly that the description outlived the mechanism. The remaining
`.sf2.json` mentions in `synth_engine.py` and `tools/wav_to_sf2.py` are correct
- they document the removal.

#### R8. `create_property_list` carries a dead loop

`main_window.py:628-641`. Both call sites pass `[]`; the `items` parameter, the
`len(items)` row count and the population loop are vestigial.

**Resolved 2026-08-14.** Parameter and loop removed, both call sites updated.
Population is `_populate_table`'s job and always was.

#### R9. Prose-to-code ratio is 0.56 (2,165 prose lines vs 3,897 code lines)

`audio/synth_engine.py` 0.97, `audio/sequencer.py` 0.92, `audio/metronome.py`
5.86. Much of it is bug archaeology duplicating `tasks.txt`. The rationale is
genuinely valuable and should not be stripped wholesale - but the recommendation
is to keep the *invariant* ("samplerate must be a constructor kwarg - a later
`.setting()` call doesn't reinitialise the engine") in the code and move the
*investigation narrative* to `tasks.txt` / commit messages.

### LOW

All but R13 resolved 2026-08-14 (see `tasks.txt` for the per-item notes).

| # | Location | Finding | Status |
|---|---|---|---|
| R10 | `models/music_data.py:260` | `_slice_is_navigable` indexes `timeline_slices[index]` after `_slice_has_visible_notes` already returned False for out-of-range. No live caller reaches it; latent `IndexError`. | fixed |
| R11 | `widgets/region2_list_widget.py:75` | `setData(Qt.UserRole, node.node_id)` is never read back. Also the only unscoped `Qt.UserRole` in the codebase. | fixed |
| R12 | `parsers/musicXML_reader.py:22` | Unconditional `[DEBUG]` prints on the production load path. | fixed |
| R13 | `main_window.py:660-670` | `load_score_from_file` silently no-ops if a load is in flight - a keystroke that does nothing and says nothing is the worst failure mode for this app's users. `ScoreLoadThread` instances are also parented and never `deleteLater`'d, so one accumulates per file opened. | **open** - product decision |
| R14 | `models/music_data.py:125-148` | `__post_init__` sets `attribute_order`, `_beat_markers` and four caches as undeclared attributes on a `@dataclass`; `attribute_order` is public API absent from the field list/`repr`/`eq`. | fixed |
| R15 | `main_window.py:1326` | `set_field(4, ...)` hardcodes the playback field index; `StatusBarWidget` should expose a named constant. | fixed |
| R16 | `audio/synth_engine.py:394-401` | `_stop_group` uses `list.remove((ch, note))`, removing the *first* match - two groups sounding the same pitch on the same channel (a unison across voices in one part) let one group's expiry release the other's still-ringing note. | fixed |
| R17 | `parsers/timeline_builder.py:482-484` | `_measure_start_quarters` reads only the first direct-child `<attributes>` per measure, while `build()`'s walker applies attributes wherever they appear - a mid-measure time-signature change makes the two disagree. | fixed |
| R18 | `latency_harness.py:128` | Unused local `app` (the only pyflakes hit in app code). `workers/score_load_worker.py:10` cites `improvements.txt`, which is not in the repo. | fixed |

---

## What is working well

Worth recording, because it is unusual:

- **Test harness.** Offscreen platform forced before PySide6 import, autouse
  audio blocking, `tmp_path`-isolated persistence, injected
  `NullSynth`/timer/locale. Better than most production Qt codebases.
- **Accessor discipline.** Regions 3/4 and playback all read through
  `MusicData._visible_notes()`, so a row index means the same note everywhere
  even under filtering. This is holding up under feature growth.
- **Performance instincts.** Exactly the two O(N*M) lookups got cached and the
  rest was left alone; the measurements confirm that was sufficient.
- **Parser ownership.** The hand-rolled ElementTree walk being the source of
  truth (rather than music21) is the right call and is why `<backup>`/`<chord>`/
  `technical` handling is correct.

## Theme

The dominant thread across the medium findings: the codebase carries its history
*in-line* rather than *in its structure* - five copies of a parse block, two
copies of a part-name read guarded by a comment, a Tab fix applied to one widget
instead of to the pattern. Consolidating those removes roughly 200 lines and
three documented "must stay in sync" invariants.
