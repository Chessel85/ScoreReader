# Code Review — 26 August 2026

Senior Python / PySide6 review of Recall Score (`SReader`) as implemented to date.
State at review time: all 806 tests pass; `pyflakes` clean apart from S8 below.

---

## Current state (updated 2026-08-27) — read this first

**Done:** S1, S2, S3, S5, S8. **Open:** S4, S6, S7, S9, S10, S11.
Suggested next order: **S6 → S4 → S9 → S7 → S10 → S11**
(S6/S9 are contained; S4 needs care around process shutdown; S7 touches
`models/`; S10 is mechanical but large; S11 is a design question, not an edit).

Tree state now: **1,010 tests pass**, `pyflakes` is **completely clean**
across `models/ parsers/ widgets/ controllers/ audio/ persistence/ workers/
tests/manual/ main.py main_window.py`. All five completed fixes are
**committed and pushed to `main`** (version `2026.1.32`), so `HEAD` is a
clean, green starting point — capture your corpus baseline from it BEFORE
you start editing.

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

### S4 — `VoiceRecognitionManager.stop()` blocks the GUI thread up to 6 s (Medium)

`audio/voice_recognition.py:354` — `process.wait(timeout=3.0)` followed by
`reader_thread.join(timeout=3.0)` on the main thread, reachable from
`toggle_voice_control` and `closeEvent`. A wedged worker freezes the UI, and
NVDA with it.

**Fix:** send `stop`, then drive the wait from a `QTimer` polling
`process.poll()`, or perform the join on a daemon thread. Cap the synchronous
path at roughly 200 ms.

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

### S6 — 10x duplicated focus save/restore boilerplate (Medium)

`previous_focus = self.focusWidget()` … `if previous_focus is not None:
previous_focus.setFocus()` appears verbatim in 10 dialog methods in
`main_window.py`. Given the project's dialog-focus invariant, this is exactly
the thing that should not be hand-copied.

**Fix:** one `@contextmanager def _preserving_focus(self)`, or a
`_run_dialog(dialog) -> bool` helper that also performs `exec()`, used by all ten.

### S7 — Uncached linear scans beside their cached siblings (Low, performance)

**Locations updated after S1 — this code MOVED.** The two scans now live in
`models/timeline_navigator.py`:
`TimelineNavigator.first_event_index_of_measure` (line 159) and
`TimelineNavigator.slice_index_at_or_after_quarters` (line 194). What is
still in `models/music_data.py` at lines 407/426 are one-line **delegators** —
editing those achieves nothing. Fix it in the navigator.

Both are O(N) full scans, while `first_visible_event_index_of_measure` /
`last_visible_event_index_of_measure` in the same class are cached dicts
(invalidated by `TimelineNavigator.invalidate_cache`, which
`MusicData._invalidate_visibility_cache` delegates to).

**Fix:** `first_event_index_of_measure` is unfiltered, so it can use a
plain cached `measure -> first index` dict built once (the timeline never
changes after construction — no filter invalidation needed, unlike its
visible-only siblings). `slice_index_at_or_after_quarters` should be
`bisect.bisect_left` over a cached list of `quarters_from_start`.
**Precondition verified:** `quarters_from_start` is monotonically
non-decreasing across the timeline — checked over 9 real MusicXML and MIDI
files, zero violations — so `bisect` is sound.

Not currently hot (spans are few), but it will matter on a long score during
Region 5 jumps.

**Verification:** this touches `models/`, so run BOTH corpus gates in
`tests/manual/`, not just the suite.

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

### S9 — `_refresh_all_item_texts` emits a signal as a side effect (Low)

`widgets/region2_list_widget.py:295` — a method named "refresh texts" also
fires `filter_changed`, which is the only reason `unmute_all` / `unsolo_all`
work at all.

**Correction to the original entry:** it has **four** call sites
(`apply_muted_node_keys`, `apply_soloed_node_keys`, `unmute_all`,
`unsolo_all` — lines 253, 258, 283, 288), and all four genuinely need the
emit: the two restore-from-`ScoreConfig` paths change the effective voice
filter just as the two clear-all paths do. So the "split the emit out to the
call sites that need it" option is NOT available — there is no call site
that doesn't.

**Fix:** rename to `_refresh_all_item_texts_and_notify` (or similar) so the
signal is visible in the name. Behaviour must not change.

### S10 — `tests/test_main_window.py` is 4,457 lines (Low)

Largest file in the repo. Split by feature area
(`test_main_window_dialogs.py`, `_navigation.py`, `_focus.py`) along the
controller boundaries. S1 and S5 are now done, so the boundaries to split
along already exist — including the newest, `ScoreEditController` (the
Instruments / Key Signature / Reorder Parts dialog tests).

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
