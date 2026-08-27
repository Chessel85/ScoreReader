# Code Review — 26 August 2026

Senior Python / PySide6 review of Recall Score (`SReader`) as implemented to date.
State at review time: all 806 tests pass; `pyflakes` clean apart from S8 below.

---

## Current state (updated 2026-08-27) — read this first

**Done:** S1, S2, S3, S4, S5, S6, S7, S8, S9, S10. **S11 raised, not
actioned** (it is a design question — see its entry for the recommendation).
Every numbered issue is now closed; nothing outstanding.

Tree state now: **1,013 tests pass** (the +3 over the earlier 1,010 are S4's
new `stop()` tests), `pyflakes` clean across `models/ parsers/ widgets/
controllers/ audio/ persistence/ workers/ tests/manual/ main.py
main_window.py`. All fixes are **committed and pushed to `main`**.

**Line numbers in the open entries were re-verified on 2026-08-27** and are
current as of that point. They will drift again as you edit — confirm with
`grep` before trusting any of them. S7 in particular had moved: the code it
describes is no longer in the file the original entry named.

### How to verify a fix here

1. `.venv\Scripts\python.exe -m pytest` — must stay at 1,010 passing.
2. **If you touch `models/` or `parsers/`, that is not sufficient.** Use the
   corpus harnesses in `tests/manual/` (see that folder's `README.md`):
   capture a baseline from the pre-change tree in a `git worktree`, then
   `--check` against it. They fingerprint every builder output and everything
   `MusicData` answers across all 56 score files; **any** difference is a
   regression. S1/S2/S3 each passed this at zero differences.
3. `.venv\Scripts\python.exe -m pyflakes <dirs>` — keep it at zero findings.

### Traps that already caught someone

- **Don't edit a delegator and think you're done.** After S1, `MusicData` is
  a facade: ~100 of its methods forward to five collaborators in `models/`
  (`timeline_navigator`, `note_renderer`, `playback_event_builder`,
  `override_manager`, `find_index`). The real code is in those.
- **Don't move `MusicData.__post_init__`'s function-local import of
  `parsers.timeline_builder_factory` to module scope.** It is load-bearing:
  it keeps `models/` free of `parsers/` imports and keeps music21 out of the
  import path (461ms → 45ms). See S2.
- **Don't assume "the tests pass" proves a behaviour-preserving change.**
  S8 found a clamp whose removal broke pickup preview timing by 1.5 seconds
  while the entire suite stayed green.
- **Dialog construction stays in `MainWindow`** — tests monkeypatch
  `main_window.<DialogClass>` with lambdas matching each constructor
  signature. Controllers own the logic behind a dialog, never its lifecycle.
- **Comments here encode real live-tested bugs.** Preserve them through a
  refactor; they are the most valuable thing in the file.

---

## Scores

| Criterion | Score |
|---|---|
| Performance & Efficiency | 8/10 |
| Simplification opportunities / bloat | 6/10 |
| Code reuse & separation of responsibility | 7/10 |
| Readability & Maintainability | 7/10 |
| Architecture (Qt/logic separation) | 8/10 |
| Technical debt | 8/10 |
| Test coverage & harness design | 9/10 |
| Accessibility engineering (pertinent here) | 10/10 |
| **Overall** | **7.5/10** |

Genuine strengths, worth preserving through any refactor:

- Score loading is on a `QThread`; no `sleep`/`processEvents` anywhere in the UI path.
- Filter-dependent lookups are cached and invalidated in exactly one place
  (`MusicData._invalidate_visibility_cache`).
- `widgets/` imports almost nothing outside `models/`; only one widget reaches
  through `window()` for behaviour.
- Comments encode real live-tested bugs and their causes rather than restating
  the code — unusually high value, do not strip them during refactoring.

## Issues, ranked by severity

### S1 — `models/music_data.py` is a 2,481-line god object — **DONE (2026-08-27)**

~110 methods spanning at least seven unrelated jobs. Extracted into five
collaborators, each built in `__post_init__` and holding a back-reference to
`MusicData`, with a one-line delegator left on `MusicData` for every method
they took over:

- `models/timeline_navigator.py` (`TimelineNavigator`) — cursor movement and
  the filter-dependent visibility caches
- `models/note_renderer.py` (`NoteRenderer`) — Ref 15 AC4's attribute
  display system, Region 3/4 text
- `models/playback_event_builder.py` (`PlaybackEventBuilder`) — note groups,
  timings, and both stepping functions
- `models/override_manager.py` (`OverrideManager`) — part/percussion/key
  overrides
- `models/find_index.py` (`FindIndex`) — the Find catalog and scanner

`models/music_data.py` is now 1,446 lines. Verified behaviour-preserving by
fingerprinting all 56 score files before and after (86,496 lines, zero
differences) plus the full test suite. As a side effect this also removed
`music_data.py`'s import of the private `parsers.midi_timeline_builder.
_spell_pitch`, which is part of S2 below.

**Follow-on still open:** S2's remaining half (the four timeline-builder
imports and the parsing side effect in `__post_init__`), and S10 — splitting
`tests/test_music_data.py` (2,226 lines) along the same five boundaries, which
is now mechanical.

### S2 — `models/` depends on `parsers/` — **DONE (2026-08-27)**

Five `models/ -> parsers/` imports (one of them a private name) and a
parsing side effect in `MusicData.__post_init__`. All removed:

- `models/synthetic_parts.py` — the fabricated part/voice identifiers, which
  had been **defined independently in three parser modules**. That
  duplication was a latent R5-class bug (the copies must agree verbatim),
  not just a layering problem; one definition now.
- `models/pitch_spelling.py` — `spell_pitch`, was the private
  `parsers.midi_timeline_builder._spell_pitch`.
- `models/strum_codes.py` — UG's strum-code table and both decodes, a pure
  lookup like `models/gm_instruments.py`.
- `parsers/timeline_builder_factory.py` + `models/timeline_build.py` — the
  format dispatch moved to `parsers/`; `models/` keeps the contract.
  `MusicData.__post_init__` reaches the factory via a **deliberate
  function-local import**, which preserves the documented
  `MusicData(file_path=...)` shortcut (the ~1ms path timeline tests need)
  while deferring the parser/music21 cost.

`grep "^from parsers" models/*.py` is now empty. Measured effect: importing
`models.music_data` went from **461 ms / 706 modules / music21 loaded** to
**45 ms / 111 modules / music21 not loaded**.

Verified by the same 56-file fingerprint used for S1 (86,496 lines, zero
differences against the pre-S1 baseline), the full test suite, and an
end-to-end load through all four readers (MusicXML with repeats/endings,
percussion routing to bank 128, MIDI, Guitar Pro).

**Note for future work:** do not "tidy" that function-local import up to
module scope — it would reinstate both the layering inversion and the
import cost.

### S3 — `TimelineBuilder.build()` is a single ~560-line method — **DONE (2026-08-27)**

`build()` is now **84 lines** showing only the shape of the walk
(part → measure → element), dispatching each measure child to a handler:
`_handle_direction`, `_handle_harmony`, `_handle_note` (which calls
`_read_pitch` and `_read_notations`), `_flush_pending_grace`,
`_assemble_slices`. Three state objects carry what survives between
elements — `_PartState` (across a part's measures), `_MeasureState` (reset
per measure), `_NoteSink` (buckets + per-slice time signature/key).

Duplication the split removed: five copies of the bucket/slice-state write
pair (now `_NoteSink.add`), three copies of the pickup beat-position
calculation (now `_PartState.beat_position`), two copies each of the
`<offset>` and `<staff>` reads (`_displaced_offset_divs`, `_staff_number`).

Nesting: 8 levels → 5. Code lines in `build()`: 374 → 72.

**Acceptance gate — the R4-style parser diff harness.** Run over every score
file in `files/`, `examples/` and `tests/fixtures/` (56 files, 9,354 slices,
27,946 notes), dumping every field of every `EventSlice` and every
`NoteData` in it (grace notes included), plus `beat_markers` (450 across the
corpus), `tempo_changes` (22), `repeat_spans` (7), `ending_spans` (12),
`hairpin_spans` (18), `segno`/`coda`/`to_coda`/`fine`/`navigation_jumps`
(33) and `total_measures`. Captured immediately before the refactor and
again after: **zero differences**, no load failures. The end-to-end
MusicData fingerprint against the pre-S1 baseline is also still zero-diff,
and the full suite passes.

Two deliberate, harness-confirmed tolerance changes (both strictly more
forgiving, neither reachable in any corpus file): a `<staff>` or
`<time-modification>` element present but with empty/malformed text no
longer raises.

### S4 — `VoiceRecognitionManager.stop()` blocked the GUI thread up to 6 s — **DONE (2026-08-27)**

Was `process.wait(timeout=3.0)` then `reader_thread.join(timeout=3.0)` inline
on the Qt main thread (reached from `VoiceControlController._disconnect` /
`.close` and `start()`'s restart path) — up to 6 s of frozen UI, NVDA with
it, if the worker hung.

`stop()` now detaches `self._process` / `self._reader_thread` synchronously
(so `is_running` goes `False` at once and a following `start()` builds a
fresh worker rather than adopting this one), gives the worker a ~200 ms grace
period to exit on the calling thread — it almost always does, having only a
PortAudio input stream to close — and hands anything slower to `_reap_worker`
(wait → kill → join) on a daemon thread. `_on_worker_exit` gained a
`process is self._process` guard so a late EOF from a stopped worker can't
fire the ready callback and report a newly started one as failed.

Three new tests (`tests/test_voice_recognition.py`) with a `_FakeProcess`
stand-in that honours `wait()` timeouts like `Popen`: prompt detach, no
block on a wedged worker + background reap, and the no-worker no-op. Suite is
now 1,013 (was 1,010).

### S5 — Business logic in the shell — **DONE (2026-08-27)**

New `controllers/score_edit_controller.py` (`ScoreEditController`) owns
score-data edits driven by a dialog: the Instruments dialog's part
name/instrument and per-percussion-item overrides, the Key Signature
dialog's whole-piece override, and Reorder Parts. `PlaybackController`
gained `end_mixer_edit(accepted)` for the Mixer dialog's own commit/revert
plus the "silence anything Preview left running" step.

`MainWindow`'s four `_show_*_dialog` methods are now pure wiring — read the
dialog's inputs from a controller, construct, `exec()`, hand the result
back, restore focus:

| method | before | after |
|---|---|---|
| `_show_instrument_dialog` | 70 lines | 22 |
| `_show_key_signature_dialog` | 29 | 16 |
| `_show_part_order_dialog` | 23 | 19 |
| `_show_mixer_dialog` | 25 | 15 |

`main_window.py`: 1,252 → 1,183 lines (97 deletions, 28 insertions).

Dialog CONSTRUCTION deliberately stays in `MainWindow` — tests monkeypatch
`main_window.<DialogClass>` with lambdas matching each constructor's
signature, and every one of those still works untouched. The controller
touches no widgets either: Region 2's labels and row order go through three
new thin `RegionPresenter` methods (`rename_part`, `rename_voice`,
`reorder_parts`), so the presenter remains the only controller that talks to
widgets.

Verified by the full suite (1,010 tests, including the 17 that drive these
four dialogs — among them "rename does not reset Region 2 toggle state",
which pins the in-place-not-rebuild invariant the moved code depends on),
`pyflakes` clean, and the model corpus gate still byte-identical to the
pre-S1 `HEAD` baseline.

The other `_show_*_dialog` methods were audited at the same time
(tempo offset, preview settings, performance report, goto measure, find,
live MIDI input, voice control, tuner) and are already clean wiring — signal
connections plus a controller call — so they were left alone.

### S6 — 10x duplicated focus save/restore boilerplate — **DONE (2026-08-27)**

The verbatim `previous_focus = self.focusWidget()` … `if previous_focus is
not None: previous_focus.setFocus()` in ten `_show_*_dialog` methods is now
one `@contextmanager _preserving_focus(self)` — `self.focusWidget()` (not
`QApplication.focusWidget()`, same reason `FocusController` uses it) with a
`finally` so an exception mid-dialog still restores focus. Every call site is
`with self._preserving_focus():` around its existing body; behaviour
unchanged, covered by the existing dialog tests.

### S7 — Uncached linear scans beside their cached siblings — **DONE (2026-08-27)**

Both O(N) scans in `models/timeline_navigator.py` now cache. Neither depends
on `active_voice_filter` and `timeline_slices` is never reassigned after
construction, so both caches are built lazily once and live **outside**
`invalidate_cache()`:

- `first_event_index_of_measure` → a `measure -> first index` dict.
- `slice_index_at_or_after_quarters` → `bisect.bisect_left` over a once-built
  list of `quarters_from_start` (monotonically non-decreasing across the
  timeline, so `bisect` is sound).

Verified behaviour-preserving with `tests/manual/model_fingerprint.py` over
the 56-file corpus: **86,496 lines, zero differences**. Full suite green.

### S8 — Dead code and stale artifacts — **DONE (2026-08-27)**

- **`parsers/midi_source.py:197` — `pending` removed.** Traced to the
  original MIDI-import commit (`c04baca`): it was declared alongside
  `offs_by_key` and never read. The FIFO note-on/note-off pairing its
  neighbouring comment describes is implemented by `offs_by_key` +
  `off_cursor`, so the comment stays accurate. Dead from birth.

- **`controllers/playback_controller.py:507` — `bar_start_quarters`
  removed, and it was NOT lost behaviour — but investigating it found a
  real coverage gap.** `git log -L` pins it to commit `5eb1101`, which moved
  the `lead_quarters`/`offset_ms` calculation out of `_build_preview_run`
  into `_refresh_preview_span` (so it re-runs per loop iteration and picks
  up live tempo changes) and left this local behind. The pickup clamp itself
  survives in `_refresh_preview_span`, computed identically, and
  `_build_preview_run` calls that method before returning — so deleting the
  local is provably behaviour-neutral.

  **The gap:** the surviving clamp was completely untested. Removing it made
  the *entire* suite still pass, while `offset_ms` for a pickup preview went
  from 0 to **1500 ms** — a second and a half of silence at the top of every
  loop iteration on `bach-bourree-tab.mxl` (bar bounds `(-3.0, 1.0)` at
  120bpm). The two sibling lead-in tests assert count-in timing *relative*
  to the play offset, so they stay green either way. Added
  `test_preview_from_a_pickup_bar_does_not_wait_out_the_beats_it_replaces`,
  verified to fail (`assert 1500 == 0`) with the clamp removed and pass with
  it present.

- ~~`parsers/ug_timeline_builder.py:29` — unused `typing.Dict` import.~~
  **Fixed incidentally during S2** (that file was edited anyway).

- **`code_review_2026-08-14.md`** — already deleted in the working tree
  (an uncommitted deletion that predates this work, alongside
  `Menus and shortcuts.txt`). Nothing further to do in the source; it just
  needs committing, which is the repo owner's call.

- **The branch item was stale.** `feature/ug-import` and
  `feature/voice-control` no longer exist, locally or on `origin` — both
  have already been cleaned up. The only feature branch left is
  `feature/tuner` (local + `origin`), and `git branch --merged main` confirms
  it is fully merged. Deleting it is a judgement call for the repo owner,
  not a code-review fix, and `CLAUDE.md`'s stated convention is that
  branches are not auto-deleted post-merge — so it has been left alone.

`pyflakes` across `models/ parsers/ widgets/ controllers/ audio/ persistence/
workers/ tests/manual/ main.py main_window.py` is now **completely clean**.

### S9 — `_refresh_all_item_texts` emitted a signal as a side effect — **DONE (2026-08-27)**

Renamed to `_refresh_all_item_texts_and_notify`, with a docstring spelling
out that the `filter_changed` emit is load-bearing. All four call sites
(`apply_muted_node_keys`, `apply_soloed_node_keys`, `unmute_all`,
`unsolo_all`) genuinely need it — the two restore-from-`ScoreConfig` paths
change the effective voice filter just as the two clear-all paths do — so
splitting the emit out was not an option. Behaviour unchanged.

### S10 — `tests/test_main_window.py` was 4,457 lines — **DONE (2026-08-27)**

Split into **12 feature modules** along the controller / feature boundaries,
each 130–880 lines:

| module | area |
|---|---|
| `test_main_window_navigation.py` | load, timeline nav, boundary cues, status bar, typed-measure jumps, file loading |
| `test_main_window_focus.py` | F6 panes, Tab/Shift+Tab region cycle, app-focus tracking, focus-gated action enablement |
| `test_main_window_menus.py` | menu shortcuts/mnemonics, Ctrl+T/G/F wiring, About dialog |
| `test_main_window_find.py` | Find dialog + Alt+Right/Left occurrence cycling |
| `test_main_window_playback.py` | play/pause/stop, phrase audition, Preview + lead-in, Shift+Space, tempo offset, metronome, announcer, F/S/D |
| `test_main_window_attributes.py` | Reorder Attributes dialog + Region 4 attribute menu |
| `test_main_window_region2.py` | mute/solo, Region 2 collapse/expand |
| `test_main_window_score_edit.py` | `ScoreEditController`: Mixer / Instruments / Key Signature / Reorder Parts |
| `test_main_window_persistence.py` | UK/US terminology, Ref 27 per-file `.rsc`, window title, Recent Files |
| `test_main_window_performance.py` | Region 5, Performance Report, Guitar Pro load |
| `test_main_window_ug_import.py` | File > Import from Ultimate Guitar + `.ug` round trip |
| `test_main_window_misc_dialogs.py` | voice-control + Tuner dialog wiring |

Shared infrastructure moved so there is exactly one copy:

- **`window` fixture → `tests/conftest.py`** (needs `MainWindow`, so
  conftest now imports it at module scope).
- **`no_lead_in` / `load_and_wait` / `_show` / `_focus` → new
  `tests/support/main_window_helpers.py`**, imported by every split module
  that uses them. The old inline `def _show` / `def _focus` are gone.
- **`_fake_ug_import_dialog` / `_fake_ug_source` / `_load_ug_import` → the
  same helper module**, because the Recent Files and Reorder Parts tests
  (now in `_persistence` / `_score_edit`) each need a loaded UG score too.

Per-section helpers that only one module uses (`_select_find_target`,
`_mnemonic`, `_fake_mixer_dialog`, `_fake_instrument_dialog`,
`_fake_key_signature_dialog`, `_fake_part_order_dialog`, `_fake_tuner_dialog`,
`_region_3_labels`, `_region_5_labels`) stayed with their tests.

**Verification:** `1,010 passed` — identical count to the pre-split baseline,
no test lost or renamed. `pyflakes` on the 12 new modules + the helper module
+ `conftest.py` is clean apart from four pre-existing `local variable
'dialog' is assigned to but never used` warnings in the Mixer tests, carried
over verbatim from the original file (they were there before this split and
`tests/` is outside the documented `pyflakes` gate). One straddling
`@pytest.mark.parametrize("focus_target", …)` decorator had to be kept with
its test when picking the cut line — worth knowing if the modules are
re-partitioned again.

### S11 — `main_window.py` is still mostly delegators (Low, judgement call)

**Numbers updated:** 1,183 lines (was 1,252 before S5), 104 `def`s, most of
them one-line pass-throughs. This is deliberate and documented as the facade
the region widgets and tests drive, so it should not be undone as-is.

**The S5 precondition in the original entry is now met.** S5 has landed, so
the open question is live: could region widgets hold a controller reference
directly instead of routing through `window()`? That would let a large block
of these disappear. Note the constraint that makes it non-trivial — the
widgets reach the window via `self.window()` at call time precisely because
they are constructed before the controllers exist, and `FocusController`
depends on `window.focusWidget()` rather than `QApplication.focusWidget()`
(see `CLAUDE.md`). Treat this as a design question to raise, not a
mechanical edit.

**Investigated 2026-08-27 — recommendation: leave it as-is (or do only the
tiny variant below). Do NOT undo the facade.**

What the numbers actually are:

- `main_window.py` is **1,180 lines / 105 methods**, 73 of them
  single-statement (delegators + 7 `@property`).
- The widget → `window()` coupling is already **small and localised**: only
  **three** region widgets touch it — `timeline_list_widget.py` (~11 methods
  via a `_main_window()` helper), `region5_list_widget.py` (2), and
  `region4_list_widget.py` (1) — plus `region_focus_cycle.py`'s mixin
  (`focus_next_region` / `focus_previous_region`, all four item-view
  regions). `region1` / `region2` / `region_property` / `status_bar` widgets
  reach into the window **zero** times.
- So the "large block that would disappear" is really **~16 delegators**,
  and most are genuine one-liners (`self.navigation.timeline_left()`).

Why removing them is not worth it:

1. **The tests drive `window.<method>()` directly**, not just the widgets —
   e.g. `window.navigate_timeline_right()`, `window.audition_phrase()`,
   `window.increase_preview_bars()` are called straight from the split test
   modules. Deleting the delegator means every such call site moves to
   `window.navigation.timeline_right()` etc., spreading controller-internal
   structure across ~200 test call sites. That is a bigger, riskier diff
   than the one it removes, and it erodes the "stable API the tests drive"
   property the facade exists for.
2. **The construction-order constraint is real.** Widgets are built in
   `setup_ui` before `setup_controllers`. Handing each widget a controller
   ref means either a two-phase `widget.set_controllers(...)` wiring step
   (new surface, new "did you forget to wire it" failure mode) or
   reordering construction (controllers need widgets too — `RegionPresenter`
   owns them). `self.window()` at call time sidesteps both.
3. **A few of these aren't pure delegators** and would have to move
   wholesale into a controller anyway (`increase_preview_bars` persists +
   announces; `jump_to_performance_span_start` reads
   `region_5.current_row_data()` then calls `navigation`) — i.e. real
   cross-cutting wiring, exactly what the shell is documented to keep.

If some reduction is still wanted, the **only** low-risk slice: give
`RegionFocusCycleMixin` and `TimelineListWidget` / `Region5ListWidget` /
`Region4ListWidget` a `_controllers` attribute set once at the end of
`setup_controllers` (a single explicit wiring line, not per-widget), and let
those four call `self._controllers.navigation` / `.playback` / `.focus`
directly. That removes ~16 window methods **without touching any test** as
long as the identically-named `window.*` delegators are kept for the tests —
which defeats most of the point. Net: the churn/risk clearly exceeds the
benefit. **Recommend closing S11 as "considered, declined"** unless the
window crosses ~1,500 lines again.

## Notes for whoever picks this up

- Nothing here was a correctness bug in shipped behaviour. The items that
  compounded most (S1–S3) are done.
- Status and suggested order live in **"Current state"** at the top of this
  file — that is the authoritative summary; this section is just the
  verification reminders.
- Every refactor above is covered by existing tests; run
  `.venv\Scripts\python.exe -m pytest` after each step.
- **Use the corpus harnesses in `tests/manual/` as the acceptance gate** for
  anything touching `parsers/` or `models/` — `parser_fingerprint.py` and
  `model_fingerprint.py`, with the git-worktree baseline workflow in that
  folder's README. They were built for S1/S2/S3 and are now permanent. "The
  tests pass" is not sufficient evidence for a behaviour-preserving
  refactor; a byte-identical corpus fingerprint is.
