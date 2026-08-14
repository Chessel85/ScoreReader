# Code Review - 2026-08-14

Senior Python / PySide6 review of the whole codebase as of commit `ab860ae`
(main, plus an uncommitted `wishlist.txt` edit). Tracked in git deliberately,
same reasoning as `tasks.txt`: the findings outlive the conversation that
produced them. Remediation is tracked as **PHASE R** in `tasks.txt` - one line
per finding, cross-referenced back to the R-numbers below.

**Remediation status (2026-08-14): all 18 addressed.** 17 fixed; R13's
"silent no-op" half was closed as won't-fix on measured evidence (see its
entry). Details in the per-finding "Resolved" notes below and the `> DONE`
notes in `tasks.txt`.

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

**Resolved 2026-08-14.** Split into a `controllers/` package: `ScoreSession`,
`PlaybackController`, `NavigationController`, `RegionPresenter`,
`AttributeController`, `FocusController`, `ScorePersistenceController`, plus
`widgets/menu_builder.py`. `main_window.py` went 1,320 -> 682 lines and is now
a facade of one-line delegators and read-only properties over the controllers -
kept deliberately, since that is the API the region widgets call through
`window()` and the tests drive.

Two design points carry the weight: controllers read `session.music_data` per
call and never cache it (MusicData is replaced wholesale on each load), and
only `RegionPresenter` touches widgets - everything else receives
widget-derived values as arguments, which is what makes the transport and
navigation logic testable without a window.

Verified three ways rather than asserted: the 358 pre-existing tests pass
**unchanged** (`git diff` on `tests/` is empty; the 12 new tests are in new
files); a 44-score behaviour baseline - playback events, Region 3/4 text,
status fields, performance rows, report lines and Region 2 voice filtering at
every slice - is byte-identical before and after; and an offscreen end-to-end
smoke run exercised load, navigation, all three transport states, the toggles,
the Tab cycle wrap-around, F6, Region 5 jumps and the dialect switch.

Landed alongside it, at the user's request: inert groundwork for the wishlist's
top audio items - `models/mixer_settings.py` (#4 mixer, #7 mute) persisted
through `ScoreConfig`, `SynthEngine.set_channel_volume/pan`, and Region 2 solo
(#8). No UI for any of it yet, and all default-inert: an empty mixer sends zero
CC messages, and with nothing soloed the voice filter takes the untouched
original code path.

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

**Resolved 2026-08-14.** 608 prose lines removed across 22 files; ratio 0.60 ->
0.44 (0.56 in the original finding counted `tools/`). Largest reductions:
`main_window.py` -176, `models/music_data.py` -143, `audio/synth_engine.py`
-85, `parsers/timeline_builder.py` -48, `audio/sequencer.py` -35.

The rule applied: **keep what the constraint is and why the code must be this
way; cut how it was discovered.** So non-obvious Qt/FluidSynth/music21
behaviour and invariants that would be re-broken if unstated all stayed;
"reported bug, live-tested", repro anecdotes, descriptions of what the old code
did, and references to which test caught it all went - `git log` and `tasks.txt`
already hold those. The R-number annotations added earlier the same day got the
same treatment, being the same kind of commentary.

Verified prose-only mechanically: an AST guard compares every touched file's
tree, with docstrings blanked, against its committed version - comments never
reach the AST, so an identical tree proves no code moved. All 22 files passed.
Eleven specific load-bearing gotchas were spot-checked as surviving.

### LOW

All but R13 resolved 2026-08-14 (see `tasks.txt` for the per-item notes).

| # | Location | Finding | Status |
|---|---|---|---|
| R10 | `models/music_data.py:260` | `_slice_is_navigable` indexes `timeline_slices[index]` after `_slice_has_visible_notes` already returned False for out-of-range. No live caller reaches it; latent `IndexError`. | fixed |
| R11 | `widgets/region2_list_widget.py:75` | `setData(Qt.UserRole, node.node_id)` is never read back. Also the only unscoped `Qt.UserRole` in the codebase. | fixed |
| R12 | `parsers/musicXML_reader.py:22` | Unconditional `[DEBUG]` prints on the production load path. | fixed |
| R13 | `main_window.py:660-670` | `load_score_from_file` silently no-ops if a load is in flight - a keystroke that does nothing and says nothing is the worst failure mode for this app's users. `ScoreLoadThread` instances are also parented and never `deleteLater`'d, so one accumulates per file opened. | thread leak fixed; silent no-op **won't-fix**, see below |
| R14 | `models/music_data.py:125-148` | `__post_init__` sets `attribute_order`, `_beat_markers` and four caches as undeclared attributes on a `@dataclass`; `attribute_order` is public API absent from the field list/`repr`/`eq`. | fixed |
| R15 | `main_window.py:1326` | `set_field(4, ...)` hardcodes the playback field index; `StatusBarWidget` should expose a named constant. | fixed |
| R16 | `audio/synth_engine.py:394-401` | `_stop_group` uses `list.remove((ch, note))`, removing the *first* match - two groups sounding the same pitch on the same channel (a unison across voices in one part) let one group's expiry release the other's still-ringing note. | fixed |
| R17 | `parsers/timeline_builder.py:482-484` | `_measure_start_quarters` reads only the first direct-child `<attributes>` per measure, while `build()`'s walker applies attributes wherever they appear - a mid-measure time-signature change makes the two disagree. | fixed |
| R18 | `latency_harness.py:128` | Unused local `app` (the only pyflakes hit in app code). `workers/score_load_worker.py:10` cites `improvements.txt`, which is not in the repo. | fixed |

### R13, in full (the one finding partly declined)

**The silent no-op: won't-fix, on measurement.** My original framing - "a
keystroke that does nothing and says nothing is the worst failure mode for
this app's users" - is true in general but wrong here, because the guard turns
out to be unreachable. It sits at the top of `load_score_from_file`, whose only
production caller is `_open_score_file_dialog`, i.e. it runs *after* a modal
`QFileDialog` returns. Triggering it would mean completing an entire second
file-picker interaction inside the previous load's window.

Measured load times across every score in the repo:

| Score | Notes | Load |
|---|---|---|
| Pachelbel's Canon (string quartet) | 3,856 | 390 ms |
| I See Angels... | 3,345 | 350 ms |
| Chopin Etude Op. 25/12 | 2,699 | 217 ms |
| Typical smaller scores | 24-492 | 12-80 ms |

390 ms worst case, against a human file-dialog interaction. An audible cue for
that path would be dead code. **Revisit only if a non-dialog load path appears**
- a recent-files list, drag-and-drop, or a command-line argument - where two
loads genuinely could fire back to back.

**The thread accumulation: fixed.** `ScoreSession._on_thread_finished` now
calls `deleteLater()`. The thread is parented to the session, so the C++ object
outlived the Python reference and one accumulated per file opened for the
process's lifetime. Modest in size (the parsed score is a local inside `run()`,
so nothing large was retained) but free to fix. Verified: eight consecutive
loads leave zero `QThread` children alive.

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
