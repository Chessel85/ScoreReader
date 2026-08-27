# Code Review — 27 August 2026

Senior Python / PySide6 review of Recall Score (`SReader`), covering all code
implemented to date.

**State at review time:** 1,013 tests pass in ~26 s. `pyflakes` is clean across
`models/ parsers/ widgets/ controllers/ audio/ persistence/ workers/ tools/
main.py main_window.py version.py` apart from four unused test locals (T6
below). Every numbered issue in `code_review_26th.md` (S1–S10) is closed; S11
was raised as a judgement call and left open. **Nothing in this review repeats
those.** All findings below are new.

The architecture established by S1–S5 (five `MusicData` collaborators, seven
controllers, `MainWindow` as a shell, `models/` free of `parsers/` and of Qt)
is holding well and is visibly paying off — the newest features (Tuner, voice
control, live MIDI input) all landed in the right layers without distorting
them. The problems found this pass concentrate in three places: **the main
thread doing blocking device I/O**, **prose volume overwhelming code**, and
**`CLAUDE.md` having drifted out of sync with the tree**.

---

## Scores

| Criterion | Score | One-line justification |
|---|---|---|
| Performance & Efficiency | **7/10** | No O(N²) in the hot paths, but three device-enumeration calls block the GUI thread, one by up to 10 s. |
| Simplification opportunities / bloat | **6/10** | Design-history prose is now the dominant content of several modules; four copies of the announcement idiom; 41 pure delegators on `MusicData`. |
| Code reuse & separation of responsibility | **8/10** | Collaborator/controller split is genuinely good; a handful of copy-paste idioms and one late-bound injection spoil it. |
| Readability & Maintainability | **6/10** | Individually excellent comments, collectively a signal-to-noise problem (`tuner_controller.py` is 64% prose). Stale docs compound it. |
| Architecture (Qt / logic separation) | **9/10** | Widgets are pure views, controllers touch no widgets except `RegionPresenter`, `models/` is Qt-free and enforced by test. Best aspect of the codebase. |
| Technical debt | **6/10** | Dead `_edit_snapshot` state, stale SAPI-era docstrings, `CLAUDE.md` describing renamed/deleted classes and fields. |
| Testing | **9/10** | 1,013 tests, no window, no audio device, isolated persistence, plus two corpus fingerprint harnesses. Exemplary. |
| Accessibility engineering | **8/10** | Announcement mechanism is right and hard-won; undermined by silent no-ops on failure paths (P2, M4). |

**Overall: 7.4 / 10** — a mature, well-tested codebase with a sound
architecture, carrying a growing documentation-drift and prose-volume debt.

---

## Issues, ranked by severity

### P1 — `available_devices()` spawns a subprocess on the GUI thread (up to 10 s freeze)

**Severity: High.** `controllers/voice_control_controller.py:168` →
`audio/voice_recognition.py:178` (`list_input_devices`). Enumerating voice
input devices runs `subprocess.run(... --list-devices, timeout=10)` — a full
Python process spawn — **synchronously on the Qt main thread**, called from
`main_window.py:1025` while building the Voice Control Settings dialog, and
again on every `refresh_requested` (`main_window.py:1029`). The docstring
explicitly says "Fresh enumeration every call - never cached."

Worst case the UI is frozen for the full 10 s timeout with no repaint and, more
importantly for this app, **no screen-reader output at all** — indistinguishable
from a hang. Typical case is still a process spawn (tens to hundreds of ms).

Same class, lower cost, two more sites:

- `controllers/tuner_controller.py:232` → `audio/tuner_capture.py:53`
  (`sd.query_devices()`, PortAudio host-API enumeration) — plus
  `TunerCapture.open()`, which does `query_devices()` **and**
  `InputStream.start()` on the main thread from `TunerDialog.showEvent`.
- `controllers/live_midi_input_controller.py:88` (RtMidi port enumeration).

**Fix:** move enumeration off the main thread. The repo already has the right
pattern twice (`workers/score_load_worker.py`, `workers/ug_import_worker.py`):
add a small `QThread` worker that emits a device list, populate the combo with a
"Scanning…" placeholder, and fill it in when the signal arrives. At minimum,
cache the result for the lifetime of one dialog so `refresh_requested` is the
*only* thing that pays the cost, and drop the voice timeout from 10 s to ~3 s.

**Fixed (2026-08-27).**
- New `workers/device_enumeration_worker.py` — `DeviceEnumerationThread`, a
  `QThread` mirroring `ScoreLoadThread`/`UgImportThread`: runs any
  `available_devices` callable in `run()`, emits `devices_found(list)`, emits
  `[]` on failure.
- `main_window._scan_devices_async(dialog, enumerate_fn, selected=…)` shows a
  "Scanning for devices…" placeholder (`set_devices_scanning()` on
  `VoiceControlDialog`/`LiveMidiInputDialog`), spawns the worker, and calls
  `dialog.set_devices(...)` when it signals back — re-selecting the saved
  device on the first scan, the current pick on a Refresh. `_show_voice_
  control_dialog` and `_show_live_midi_input_dialog` route both the initial
  population and `refresh_requested` through it; `closeEvent` `wait()`s any
  in-flight scan so window teardown can't orphan one.
- `audio/voice_recognition.list_input_devices` timeout 10 s → 5 s (cold
  PortAudio init headroom, kept off the main thread now regardless).
- **Tuner left synchronous.** `sd.query_devices()` is the "lower cost" site,
  and `TunerDialog.showEvent` auto-starts listening via `TunerCapture.open()`
  (which does its own `query_devices()` + `InputStream.start()`) — async
  enumeration there is entangled with that separate item, not the P1
  subprocess. Deferred to it.
- Tests: `tests/test_device_enumeration_worker.py` (off-thread + failure) and
  a `test_main_window_misc_dialogs.py` case (placeholder shown first, list
  fills from the worker, saved device re-selected). Suite 1013 → 1016, green;
  `pyflakes` clean. Live NVDA test on real hardware still owed per the
  Verification section.

---

### P2 — A second `File > Open` while a load is in flight is a silent no-op

**Severity: High (accessibility).** `controllers/score_session.py:47` and
`:63`: both `load()` and `import_from_url()` `return` immediately when
`self._load_thread is not None`. For a screen-reader-first app this is the
worst possible failure mode — the user picks a file, presses Enter, and nothing
is spoken or shown. `_on_score_load_failed` (`main_window.py:574`) is the same
shape: `print("[ERROR] ...")` only.

This is adjacent to the known gap tracked as Ref 25 / NFR-06 (I1), but is worse
than "no error dialog": it is a *success-path* silence.

**Fix:** at minimum, fire a `QAccessibleAnnouncementEvent` ("Still loading
<name>.") from the guard, and one on load failure. Ideally, disable the Open and
Import actions while `is_loading()` is true so the state is discoverable.

---

### M1 — `find_occurrence` rescans the whole score on every Alt+Right / Alt+Left

**Severity: Medium (performance).** `models/find_index.py:160`. Each keypress
calls `candidate_indices_for_target`, which for an attribute target
(`:73`–`:80`) is:

```
for every slice           (9,354 on the review corpus)
  for every visible note  (~3 avg)
    _note_attribute_pairs(note)   # builds a full dict per note
```

— then `sorted({...})` over the result, then a linear scan for the next
candidate. It is discarded and rebuilt on the next keypress.
`_note_attribute_pairs` does real string formatting per note, so this is not a
cheap scan.

`available_targets()` (`:135`) makes it worse at dialog-open time: it calls
`candidate_indices_for_target` once per entry in `MARKING_KINDS`, three of which
(`key_signature_change`, `time_signature_change`, `tempo_change`) are themselves
full-timeline scans, and `tempo_change_indices` (`:47`) calls `_tempo_change_at`
twice per slice, each a linear walk of `tempo_changes` — O(N·T).

**Fix:** cache the sorted candidate list per `(target, active_voice_filter
generation)` on `FindIndex`, invalidated from the same
`MusicData._invalidate_visibility_cache` hook `TimelineNavigator` already uses
(S7 established exactly this pattern). `find_occurrence` then becomes a `bisect`
over the cached list. Separately, give `_tempo_change_at`
(`models/music_data.py:1138`) a `bisect` over a prebuilt `quarters_from_start`
list — it is also on the Sequencer's per-step path via `effective_tempo_bpm`.

---

### M2 — The `QAccessibleAnnouncementEvent` idiom is copy-pasted four times

**Severity: Medium (reuse).** An identical four-line block — construct,
`setPoliteness(Assertive)`, `updateAccessibility` — appears at:

- `controllers/region_presenter.py:174` (`_announce_measure_change`)
- `controllers/region_presenter.py:217` (`announce_attribute_by_number`)
- `controllers/region_presenter.py:235` (`announce_preview_length`)
- `widgets/tuner_dialog.py:329` (`announce`)

This is the app's single most load-bearing accessibility mechanism, and the
hard-won invariant behind it (**the event target must be a real widget**,
documented at length in `controllers/tuner_controller.py`'s module docstring) is
currently enforced only by four separate developers remembering it.

**Fix:** add `widgets/accessible_announcer.py` with
`announce(widget: QWidget, message: str) -> None` that asserts/annotates the
widget requirement in one place, and route all four call sites through it.
Cheap, and it makes the invariant structural rather than remembered.

**Fixed (2026-08-27).**
- New `widgets/accessible_announcer.py` — `announce(widget, message)`:
  builds the `QAccessibleAnnouncementEvent`, sets `Assertive` politeness,
  posts it via `QAccessible.updateAccessibility`. `assert isinstance(widget,
  QWidget)` makes "the target must be a real widget, never a bare QObject"
  structural; the docstring carries the reasoning that used to live only in
  `tuner_controller.py`.
- All four sites routed through it: `region_presenter._announce_measure_
  change` / `announce_attribute_by_number` / `announce_preview_length`, and
  `tuner_dialog.announce`. Both files dropped their now-unused `from
  PySide6.QtGui import QAccessible, QAccessibleAnnouncementEvent`.
- Tests: the two suites that monkeypatch `QAccessible.updateAccessibility`
  (`test_main_window_navigation.py` ×5, `test_tuner_dialog.py` ×1) now
  target `accessible_announcer.QAccessible`. `test_tuner_dialog`'s
  `object() is dialog` assertion still holds — the helper builds the event
  with the passed widget as target. Suite 1016 → 1016, green; `pyflakes`
  clean. No `models/`/`parsers/` code touched.
- **Lesson for any future announcement:** call
  `accessible_announcer.announce(<a real widget you own>, msg)` — do not
  hand-roll the three-line event dance again, and do not target a
  controller/`QObject`. A `QObject` has no accessibility interface for the
  platform bridge to resolve, so the event is silently dropped (the
  original live-tested tuner bug). A `QObject` controller must therefore
  route its message to a widget it already owns (RegionPresenter →
  `region_3`; TunerController → the dialog, via a signal). Keep the
  message a pure side channel: never fold it into a widget's persisted
  text (it then gets re-read on every revisit — see
  `feedback_accessible_announcements`), and prefer a short TEXT-FREE
  message posted *before* the natural per-row announcement rather than
  trying to suppress that announcement (`blockSignals` does not gate it).

---

### M3 — `CLAUDE.md` describes classes, files and fields that no longer exist

**Severity: Medium (maintainability).** `CLAUDE.md` is the primary onboarding
document for both humans and AI contributors, and several load-bearing sections
are now wrong. Verified against the tree:

| `CLAUDE.md` says | Reality |
|---|---|
| `widgets/region_table_widget.py` (`RegionTableWidget`), "a plain property-list table used by regions 1 and 4" | File does not exist. It is `widgets/region_property_list_widget.py` (`RegionPropertyListWidget`), plus `region1_list_widget.py` / `region4_list_widget.py`. |
| `Region4TableWidget`, "a `QTableWidget` — Tab *does* reach `keyPressEvent` there" (the Ref 29 / R1 GOTCHA) | Class is gone; the reasoning it anchors is stale. Only survives as a comment at `widgets/region_property_list_widget.py:11`. |
| `Region2Node.enabled`, "the untouched ancestor-gated `enabled` walk", "Region 2 solo … no UI yet" | The field is `muted`; there is no `enabled` anywhere in `widgets/region2_manager.py`. Solo has full UI (`Actions.solo`, `Actions.unsolo_all`). |
| `ScoreConfig.parts_off` / `staves_off` / `voices_off`; `get_off_node_keys()` / `apply_off_node_keys()` described as "the real save/restore path" | Fields are `parts_muted` / `staves_muted` / `voices_muted` (+ `*_soloed`); neither method exists anywhere in the tree. |
| `_refresh_all_item_texts` | Renamed to `_refresh_all_item_texts_and_notify` by S9 (commit `590813e`). |

**Fix:** re-verify each named symbol in the `models/`, `widgets/` and
`persistence/` sections with `grep` and correct them. Documentation edit only —
no code should change.

---

### M4 — `TunerController.MIN_CONFIDENCE = 0.85` can silently reject a badly mistuned string

**Severity: Medium (correctness of the feature's core purpose).**
`controllers/tuner_controller.py:198`. Measured empirically during this review
against `audio/pitch_detector.detect_pitch` (0.25 s buffer, 44.1 kHz,
fundamental + 2nd harmonic + 5% Gaussian noise, target 82.41 Hz, ±4 semitone
band):

| detune | reported error | confidence |
|---|---|---|
| −350 c | +0.08 c | 0.995 |
| 0 c | +0.45 c | 0.989 |
| +200 c | +0.37 c | 0.969 |
| **+350 c** | +2.03 c | **0.714 — rejected** |

Accuracy is excellent throughout (worst case ~2 cents), but confidence decays
toward the **sharp** edge of the search band under noise and falls below the
0.85 gate. The rejected case — a string ~3 semitones sharp, still detected
correctly to within 2 cents — is precisely the case a tuner exists to fix, and
the user gets "no result", indistinguishable from the microphone not working.

Root cause is structural, not just a badly chosen constant: `detect_pitch`'s
CMND normalisation (`audio/pitch_detector.py:69`–`73`) accumulates `running_sum`
from `min_lag` rather than from lag 1, so lags near the *bottom* of the band are
normalised against a very short running mean. That asymmetry is what makes
confidence position-dependent within the band. (Clean tones score 0.99+ at every
detune tested, which is why the existing tests do not catch it.)

**Fix (pick one):** (a) compute `diff`/`cmnd` over a slightly wider lag range
than the reported band and only *search* the band, so normalisation is
symmetric; (b) make `MIN_CONFIDENCE` scale with distance from `expected_hz`; or
(c) widen `DEFAULT_SEARCH_SEMITONES` past 4 so a 3-semitone error is no longer
near the edge. Add a regression test in `tests/audio/test_pitch_detector.py`
covering the noisy band-edge case.

---

### M5 — Prose has overtaken code in several modules

**Severity: Medium (readability).** Measured docstring + comment share of total
lines:

| File | Total lines | Prose |
|---|---|---|
| `controllers/tuner_controller.py` | 471 | **64%** |
| `controllers/playback_controller.py` | 916 | 37% |
| `models/music_data.py` | 1,436 | 37% |
| `parsers/timeline_builder.py` | 1,590 | 30% |
| `main_window.py` | 1,181 | 27% |

The comments are individually excellent — they encode real live-tested bugs, and
`code_review_26th.md` rightly calls them "the most valuable thing in the file".
The problem is *shape*, not value: `tuner_controller.py`'s module docstring is a
numbered chronological changelog ("SECOND live-testing report… THIRD… FOURTH…
FIFTH… SIXTH"), and `_advance_state`'s own docstring is 60 lines of design
history in front of 25 lines of code. A reader who needs to know what the state
machine *currently does* has to reconstruct it from a narrative of what it used
to do.

**Fix (documentation only, zero behaviour change):** move the numbered
live-testing chronologies into `docs/design-notes/tuner.md` (or a section of
`tasks.txt`, which already serves this role), leaving in the source only the
**current** invariants plus a one-line pointer. Keep every inline comment that
sits next to the line it protects — those are working correctly. Apply the same
treatment to `main_window.py:1040`'s `_show_tuner_dialog`, where ~30 comment
lines wrap 20 lines of signal wiring.

---

### M6 — Preview computes its span twice on every start

**Severity: Medium-Low (performance / clarity).**
`controllers/playback_controller.py:497` `_build_preview_run` ends by calling
`_refresh_preview_span(run)` (`:538`); `_start_preview_iteration` (`:572`) then
calls it again as its first action (`:581`). `_refresh_preview_span` calls
`playback_span_ms` (`models/playback_event_builder.py:444`), which runs a full
jump-aware simulated walk of the preview window with a guard of
`len(slices)*2+4` iterations, each calling `next_playback_index` and
`effective_tempo_bpm`. Every Preview start therefore does this walk twice.

**Fix:** drop the call at the end of `_build_preview_run` —
`_start_preview_iteration` always runs immediately afterwards and always
refreshes. Verify with `tests/test_main_window_playback.py` and the preview
timing tests.

---

### L1 — `TunerController._edit_snapshot` is dead state

**Severity: Low (dead code).** `controllers/tuner_controller.py:228`, `:300`,
`:306`, `:309`. The snapshot is assigned in `begin_settings_edit` and cleared in
both `commit_settings_edit` and `cancel_settings_edit`, but **never read**. It
exists because the method group was modelled on `LiveMidiInputController`
(`:145`–`:146`) and `VoiceControlController` (`:206`–`:207`), which *do* read
theirs to revert live-previewed synth state. The tuner dialog has no live
preview to revert, so the field is pure noise — and misleading, since it implies
a revert that does not happen.

**Fix:** delete the field and its three assignments; keep `cancel_settings_edit`
as an explicit no-op with a one-line docstring saying why nothing needs
reverting.

---

### L2 — `ScoreSession.load()` and `import_from_url()` are the same method twice

**Severity: Low (reuse).** `controllers/score_session.py:43`–`:68`. The two
bodies differ only in which thread class is constructed; the in-flight guard,
the three `connect` calls and `start()` are identical, and the docstrings say so.

**Fix:**

```python
def _start(self, thread) -> None:
    self._load_thread = thread
    thread.loaded.connect(self._on_loaded)
    thread.failed.connect(self.load_failed.emit)
    thread.finished.connect(self._on_thread_finished)
    thread.start()
```

with both public methods reduced to the guard plus one `_start(...)` call. Fold
P2's announcement into that single guard while you are there.

---

### L3 — Stale SAPI-era docstrings after the Vosk rewrite

**Severity: Low (technical debt).** SAPI 5.4 was abandoned in favour of Vosk
(documented in `CLAUDE.md`'s "Known gaps"), but the module that defines the
vocabulary still describes itself in SAPI terms:

- `audio/voice_commands.py:3` — "the fixed command vocabulary for the SAPI
  command-and-control grammar"
- `:6` — "no Qt/COM anywhere in this file"
- `:14` — "so SAPI's own CFG rejection model does most of the work" (Vosk has no
  CFG rejection model; the accuracy argument is a different one)
- `:112` — "a SAPI grammar phrase must match what is actually said"
- `:176` — "Resolves SAPI's recognized text to…"
- `controllers/voice_control_controller.py:108` — "pywin32/SAPI not being
  available"; `pywin32` is no longer a dependency
- `main_window.py:280` — "auto-starts listening if enabled and pywin32/SAPI are
  available"

`audio/voice_recognition.py` itself is correctly Vosk-documented; only the
downstream files were missed.

**Fix:** replace the SAPI references with Vosk, restating the accuracy reasoning
for Vosk's phrase list, and drop the `pywin32` mentions. Also update the merged
branch references (`audio/voice_commands.py:2` `feature/voice-control`,
`widgets/menu_builder.py:126` `feature/ug-import`) — both branches are merged
into `main`.

---

### L4 — Four copies of the `sys._MEIPASS` base-directory idiom

**Severity: Low (reuse).** `main.py:41`, `main_window.py:76`, `version.py:13`,
`audio/voice_recognition.py:122`. Three of the four docstrings say "same idiom
as…", which is the tell.

**Fix:** a two-function `app_paths.py` at the repo root (`app_base_dir()`,
`resource_path(*parts)`), imported by all four. It must stay import-cheap and
Qt-free — `main.py` calls it before any other import.

---

### L5 — Three parallel linear scans of `parts_info` on the playback path

**Severity: Low (performance).** `models/music_data.py:1227`
(`get_channel_for_part`), `:1246` (`get_gmidi_program_for_part`) and `:1252`
(`is_percussion_part`) each walk `parts_info` looking for one `part_id`, and
`PlaybackEventBuilder.events_for_indices` calls all three once per part group
per audition — O(P²) per keypress. `get_channel_for_part` additionally rebuilds
its 16-element `usable_channels` list on every call.

P is small (≤ ~20 in every real score), so this is not currently a bottleneck —
but it is three scans where one dict lookup would do, and the `usable_channels`
docstring spends five lines justifying the rebuild.

**Fix:** build a `Dict[str, PartStructureInfo]` and a `Dict[str, int]` channel
map once in `__post_init__` (both derive purely from `parts_info`, stable for a
`MusicData`'s lifetime apart from `reorder_parts` / `apply_part_overrides` —
rebuild there). This deletes the class-scope-comprehension explanation entirely.

---

### L6 — `VoiceControlController.presenter` is injected after construction

**Severity: Low (architecture).** `main_window.py:311`:
`self.voice_control.presenter = self.presenter`, wired late because
`RegionPresenter` does not exist yet when `VoiceControlController` is built.
`_dispatch` then has to guard `self.presenter is None` on the `ATTRIBUTE`
branch. Every other controller dependency is a constructor argument.

**Fix:** construct `RegionPresenter` before `VoiceControlController` (nothing in
the presenter needs the voice controller) and pass it in normally. The `is None`
guard and the seven-line explanatory comment both disappear.

---

### T1 — `_advance_preview`'s "schedule was rebuilt" sentinel is fragile

**Severity: Low (maintainability; no known bug).**
`controllers/playback_controller.py:668`:

```python
if self._preview is not run or run.event_index == 0:
    return
```

`run.event_index == 0` means "a `loop` event re-entered
`_start_preview_iteration`, which reset the index". This is an implicit signal
read from a mutated field, correct only because `_start_preview_iteration`
happens to set `event_index = 0` last. A future change that leaves the index
non-zero silently reintroduces double-walking of the schedule.

**Fix:** give `_PreviewRun` an explicit monotonic `generation: int`, bumped by
`_start_preview_iteration`; compare the generation captured at the top of
`_advance_preview`. Self-documenting and immune to statement ordering.

---

### T2 — `TunerCapture` fires one `threading.Timer` (= one OS thread) every 200 ms

**Severity: Low (efficiency / lifecycle).** `audio/tuner_capture.py:180`
(`_schedule_detection`) creates a fresh `threading.Timer` — and therefore a
fresh OS thread — per detection cycle, five per second for as long as the Tuner
dialog is open. It works and is correctly cancelled, but a single long-lived
worker thread with `while not stop_event.wait(DETECT_INTERVAL_SECONDS)` is
cheaper and simpler.

There is also a benign race: `close()` cancels `_detect_timer` before setting
`_stream = None`, so a `_run_detection` already in flight can invoke the callback
**once after `close()` returned**. `TunerController` currently tolerates this
(the queued-connection handler is harmless post-close), but it is undocumented
and would break if that handler ever touched dialog state.

**Fix:** switch to one worker thread plus a `threading.Event`, and have
`close()` join it. Document the post-close callback guarantee either way.

---

### T3 — `Actions` is 45 `Optional[QAction] = None` fields, none of which are optional

**Severity: Low (boilerplate).** `widgets/menu_builder.py:12`–`:66`. Every field
is unconditionally assigned by `build()`; the `Optional`/`None` defaults exist
only so `Actions()` can be constructed empty and populated field-by-field. The
result is 55 lines of declaration a reader must diff against `build()` to trust,
and a forgotten assignment surfaces as an `AttributeError` far from its cause.

**Fix (judgement call):** have each `_*_menu` method return its own small
dataclass, or build a plain `dict[str, QAction]` and construct `Actions(**d)`
once at the end, so the fields become non-optional and a missing assignment is a
`TypeError` at construction. Low value; skip if the churn is not worth it.

---

### T4 — `MenuBuilder` calls private methods on `MainWindow`

**Severity: Low (encapsulation).** `widgets/menu_builder.py` reaches for
`self.slots._show_instrument_dialog`, `._open_score_config_folder`,
`._clear_preferences_action_text`, `._clear_current_score_preferences`,
`._show_key_signature_dialog` and others — leading-underscore names consumed from
a different module. The class docstring says `slots` exposes "the callbacks
below", implying a public contract the names contradict.

**Fix:** drop the underscore from the methods `MenuBuilder` actually calls — they
are, by construction, `MainWindow`'s public slot surface. Note that the tests
reference several of these names, so this is a mechanical rename across
`main_window.py`, `widgets/menu_builder.py` and `tests/`.

---

### T5 — `latency_harness.py` sits at the repo root, apart from its siblings

**Severity: Low (organisation).** It is a manual, human-run benchmark, correctly
excluded from pytest discovery — exactly like `tests/manual/parser_fingerprint.py`
and `tests/manual/model_fingerprint.py`, which live together under
`tests/manual/` with a shared `README.md`.

**Fix:** move it to `tests/manual/latency_harness.py`, add it to that folder's
`README.md`, and update the invocation line in its own module docstring. Confirm
nothing in `packaging/` references the old path first.

---

### T6 — Four unused locals in the test suite

**Severity: Low (hygiene).** The only `pyflakes` findings in the tree:
`tests/test_main_window_score_edit.py:59`, `:88`, `:122`, `:144` — `local
variable 'dialog' is assigned to but never used`.

**Fix:** replace `dialog = ...` with a bare call, or assert on it. Restores
`pyflakes` to zero findings across the whole repo including `tests/`.

---

### N1 — Accepted, not a defect: `MusicData`'s 41 delegators

41 of `MusicData`'s 93 methods are one-line forwards to the five S1
collaborators. `CLAUDE.md` documents this as deliberate and load-bearing
(`MusicData` is replaced wholesale on load, so no caller may hold a
collaborator), and `code_review_26th.md`'s S11 raised the same shape for
`main_window.py`. Recorded here for completeness only — **do not "fix" it**; the
delegators are the contract that keeps callers and tests off the collaborators.

---

## Suggested order of work

1. **P1** and **P2** — both are user-visible freezes/silences in a
   screen-reader-first app. Do these first.
2. **M3** and **L3** — pure documentation corrections, no test risk, and they
   stop the next contributor being misled.
3. **M2**, **L1**, **L2**, **T6** — small, mechanical, low-risk cleanups.
4. **M4** — needs a new pitch-detector test and a live re-tune of the thresholds
   with the user; schedule it as its own piece of work.
5. **M1**, **M6**, **L5** — performance; none currently painful, so batch them.
6. **M5** — the largest edit by line count but zero behaviour change. Do it one
   file per pass so the diff stays reviewable.
7. **L4**, **L6**, **T1**–**T5** — opportunistic.

## Verification requirements

- `.venv\Scripts\python.exe -m pytest` must stay at **1,013 passing**.
- `.venv\Scripts\python.exe -m pyflakes models parsers widgets controllers audio
  persistence workers tools tests main.py main_window.py version.py` must reach
  **zero** findings once T6 is done.
- **M1, L5 and anything else touching `models/` or `parsers/` must clear the
  corpus harnesses** (`tests/manual/parser_fingerprint.py`,
  `tests/manual/model_fingerprint.py`) at **zero differences** against a baseline
  captured from the pre-change tree in a `git worktree`. See
  `tests/manual/README.md`. "The tests pass" is not evidence for a
  behaviour-preserving change — S8 in the previous review broke pickup preview
  timing by 1.5 s with the entire suite green.
- **P1, M4 and T2 need live testing on real hardware with NVDA**; none of them
  can be validated by the offscreen/null-audio harness.

## Traps carried forward from `code_review_26th.md`

Still true, still worth re-reading before starting:

- Don't edit a `MusicData` delegator and think you're done — the real code is in
  `models/{timeline_navigator,note_renderer,playback_event_builder,override_manager,find_index}.py`.
- Don't move `MusicData.__post_init__`'s function-local import of
  `parsers.timeline_builder_factory` to module scope (461 ms → 45 ms).
- Dialog **construction** stays in `MainWindow` — tests monkeypatch
  `main_window.<DialogClass>` with lambdas matching each constructor signature.
  This directly constrains L6 and T4.
- Region 3's `setCurrentRow(0, QItemSelectionModel.SelectionFlag.NoUpdate)` needs
  the explicit flag; the one-arg overload collapses the selection.
- Comments encode real live-tested bugs. M5 asks you to **relocate** the
  chronological narrative, never to delete the invariants.
