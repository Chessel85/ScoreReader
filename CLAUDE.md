# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

"Recall Score" (repo `SReader`, remote `ScoreReader`) — a screen-reader-first music score and guitar-tab viewer/editor for visually impaired musicians. `Product Definition Document.md` is the authoritative spec: roles, numbered functional requirements with acceptance criteria, the 2x2 region layout, and the intended keystroke map. Read the relevant requirement rows before implementing a feature; most current code maps directly onto them (e.g. pickup-bar measure numbering is Ref 17, TS-relative beat/duration units is Ref 18, part/staff/voice filtering is Ref 7).

Accessibility is the product, not a polish item: notes are rendered as spoken-friendly text ("F sharp", "B double flat", octave omitted in the note list), navigation is keyboard-driven with a cyclic region focus loop, and every timeline move triggers MIDI audition. Ref 9 sets a 25 ms audition latency budget — that constraint is why the audio path is in-process FluidSynth rather than an external MIDI port. Preserve these properties when changing UI or data formatting.

## Commands

Windows, Python 3.13, dependencies in the checked-out `.venv` (not tracked):

```powershell
.venv\Scripts\python.exe main.py          # run the app
.venv\Scripts\Activate.ps1                # then plain `python main.py`
```

Dependencies are split: `requirements.txt` (runtime — PySide6 6.11, music21 10.5, pyfluidsynth 1.4) and `requirements-dev.txt` (pytest, pytest-qt, pytest-cov). `mido` is no longer used or installed. No linter is configured.

```powershell
.venv\Scripts\python.exe -m pytest                    # whole suite (~0.6s)
.venv\Scripts\python.exe -m pytest -m "not slow"      # skip music21 tests
.venv\Scripts\python.exe -m pytest tests/models/test_music_data.py::test_name
.venv\Scripts\python.exe -m pytest --cov=models --cov=parsers --cov=widgets
```

Two invariants the harness enforces, both guarded by tests in `tests/test_harness.py`:

- **No window opens.** `tests/conftest.py` sets `QT_QPA_PLATFORM=offscreen` before PySide6 is imported.
- **No audio device opens.** An autouse fixture blocks `SynthEngine._init_engine`, so constructing a real engine in a test fails with a pointer to the fix. `MainWindow(synth=...)` accepts any object with the `SynthEngine` interface; `tests/support/null_synth.py` records calls so tests can assert what *would* have sounded.

Timeline tests must build `MusicData(file_path=...)` directly — that walks the XML with ElementTree in ~1 ms. Going through `MusicXMLReader.load()` also runs music21 at ~460 ms; those tests carry the `slow` marker.

VS Code launch config is "Python: Current File" (debugpy) — debug by opening `main.py` and pressing F5.

## Local binaries (never commit these)

`audio/synth_engine.py` needs native FluidSynth DLLs in `bin/` and a SoundFont at `soundfonts/FluidR3_GM.sf2` (~148 MB). Both directories are gitignored and exist only in the working tree.

**This is load-bearing.** The 148 MB soundfont exceeds GitHub's 100 MB file limit; committing it in August blocked all pushes and the recovery attempt cost two days of work. Never `git add` these paths, never remove those `.gitignore` entries, and if you need to restore them use `git cat-file blob <sha> > <path>` — `git checkout <commit> -- bin/` stages the files and reintroduces the problem.

If the binaries are missing the app still runs: `SynthEngine` sets `FLUIDSYNTH_AVAILABLE = False`, prints a warning, and every playback call becomes a no-op.

## Architecture

Package-per-domain layout; each module holds one class. Data flows one way:

`main.py` → `MainWindow` → `MusicXMLReader.load()` → `MusicData` → four region views + `SynthEngine`

- **`models/`** — `note_data.py` (`NoteData`), `event_slice.py` (`EventSlice`), `parts_structure.py` (`PartStructureInfo`), and `music_data.py` (`MusicData`, the aggregate + timeline builder).
- **`parsers/musicXML_reader.py`** — `MusicXMLReader` builds header/metadata: credits, key, time signature, tempo, per-part structure (staff→clef, staff→voices, GM program). It parses the file **twice**: raw `ElementTree` for credits/part-list/clefs, and `music21.converter.parse` for tempo/key/time, with the ElementTree values as fallback when music21 returns nothing.
- **`audio/synth_engine.py`** — in-process FluidSynth. At import it prepends `<root>/bin` via `os.add_dll_directory` + `PATH` and pre-loads the glib/gobject/gthread/fluidsynth DLLs with `ctypes.CDLL` before `import fluidsynth`; that ordering is required on Windows and is why the module has side effects at import time. The synth runs on the WASAPI driver at 48 kHz with a 128-frame period and 2 periods — low-latency settings chosen for Ref 9; don't raise them without cause. Note-off is scheduled by a single-shot `QTimer`, so playback timing rides the Qt event loop.
- **`widgets/`** — `region_table_widget.py` (`RegionTableWidget`, used by regions 1, 2 and 4), `timeline_list_widget.py` (`TimelineListWidget`, region 3), and `region2_manager.py` (`Region2HierarchyModel` / `Region2Node`, pure state — no Qt).
- **`main_window.py`** — 2x2 `QGridLayout`. Region 1 = score info, 2 = parts/staves/voices, 3 = note list at the cursor, 4 = note attributes for the *selected* notes.

The widget subclasses exist mainly to intercept keys: both forward `Tab`/`Shift+Tab` to `focusNextChild()`/`focusPreviousChild()` so the region cycle stays intact, `TimelineListWidget` maps Left/Right to `MainWindow.navigate_timeline_*` and Up/Down to `on_region_3_vertical_move`, and `RegionTableWidget` maps Spacebar to toggling a hierarchy row. `RegionTableWidget.refresh_table(preferred_node_id=...)` deliberately re-anchors the current cell after a rebuild so NVDA keeps announcing the row the user is on.

GM programs are **1-indexed in the model** (25 = nylon guitar, from MusicXML `<midi-program>`) and **0-indexed on the wire** — `MainWindow._play_selected_region_3_notes` does the `-1` conversion, so don't convert twice.

### Timeline model

The timeline is a flat, sorted list of `EventSlice` — one entry per distinct `(measure, offset_in_quarters)` with at least one sounding note. Rests are skipped, so navigation lands only on attacks. `active_event_index` is the cursor; `move_timeline_left/right` return `bool` (False at the boundaries, where the spec wants an audible boundary cue that isn't implemented yet).

`MusicData._build_timeline_from_xml` is a third hand-rolled `ElementTree` pass. music21's stream is stored on `MusicData.score` but is **not** the source of truth for notes — the DOM walk is, because it handles `<backup>`/`<forward>` offsets, `<chord>` grouping, and `notations/technical` string/fret data explicitly.

Two conventions the parser enforces, both spec requirements:

- **Pickup bars** are detected by `implicit="yes"` or by measure 1's staff-1 content summing to less than a full bar. When present every measure number shifts down by one, so the pickup is measure **0** and the first full bar is **1**. Pickup notes get beat positions placing them at the *end* of the notional bar.
- **Beat positions and durations are relative to the time-signature denominator**, not to quarter notes. `beat_unit_quarter_len = 4.0 / denominator`; a quarter note is `ts_duration` 1.0 in 4/4 but 2.0 in 7/8. `NoteData.quarter_length` is kept separately for playback timing.

### Selection-driven regions

Region 3 is `ExtendedSelection` and defaults to selecting every note in the current slice (`Ctrl+A` reselects all). Regions 4 and audio follow the **selection**, not the slice: `get_region_4_data_for_indices(indices)` and `get_midi_notes_for_indices(indices)` take Region 3's selected rows. `_update_timeline_views(play_all=...)` blocks Region 3's signals during a rebuild to avoid audition storms, then fires playback once. Keep view code reading through these accessors rather than reaching into `timeline_slices`.

## Known gaps

- **Region 2 filtering is half-built** (Ref 7). `widgets/region2_manager.py` and the `filter_changed` signal are complete and tested, but `MainWindow` calls `_music_data.get_score_structure()` and `set_active_voice_filter()`, and **neither exists on `MusicData`**. Both call sites are `hasattr`-guarded, so the app runs: Region 2 falls back to the flat `get_region_2_data()` property table via `_populate_table`, which bypasses `model_manager` entirely — so `_current_visible_nodes` stays empty and **Spacebar toggling silently does nothing**. Finishing this means adding those two methods to `MusicData` (emitting the `parts_data` shape documented in `Region2HierarchyModel.build_from_score`) and filtering `get_region_3_data()` by the active `(part_id, staff, voice)` tuples.
- Scores with a TAB staff duplicating the notation staff currently show every note twice in Region 3 (the Bourrée sample yields `['E','G','E','G']` on the first slice). Region 2 filtering is the intended fix.
- Parsing errors are swallowed with `print("[ERROR] ...")` and partial state. Ref 25 / NFR-06 call for an accessible error dialog; prefer moving that way over adding more silent prints.
- Not yet built despite being specified: measure jump, play/pause/stop, metronome, voice control, edit mode, MIDI/Guitar Pro/BME I/O, capo handling, chord naming, and settings persistence.

## Git recovery notes

Local tags `recovered-2026-08-03` (= `b4b7c52`) and `pre-reset-tip` (= `b914f67`) pin the August commits that a hard reset orphaned, so `git gc` can't drop them. **Do not push these tags** — their ancestry contains the 148 MB soundfont and the push will be rejected. The recovered content itself is already on `main` as commit `8385e59`, applied as a fresh tree copy rather than a merge for exactly that reason.

`git show 520f743:test_midi_latency.py` recovers a latency benchmark that was deleted before the reset — the only test file this project has ever had.
