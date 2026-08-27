# tests/manual — refactor verification harnesses

Two scripts that fingerprint what this app produces across the **whole score
corpus**, so a refactor that is supposed to change nothing can be *proved* to
change nothing.

These are **not pytest tests**. `pytest.ini` sets `testpaths = tests`, but
pytest only collects files matching `test_*.py`, so nothing here is ever
collected or run by `pytest`. Run them by hand, as below.

## Why these exist

The test suite asserts specific things about a handful of fixtures. That is
the wrong shape of evidence for a behaviour-preserving refactor: a change can
keep every assertion true while quietly altering a beat position, a note's
enharmonic spelling, or which slice a hairpin starts on. These harnesses dump
*everything*, over every real file, and diff it.

`CLAUDE.md` records this approach being used for **R4** (consolidating four
measure walks into `_scan_first_part`), **S1** (splitting `MusicData` into
five collaborators), **S2** (removing `models/ → parsers/` imports) and **S3**
(splitting `TimelineBuilder.build()`). Zero differences every time.

## The two harnesses

| Script | Level | Use it when you change… |
|---|---|---|
| `parser_fingerprint.py` | Parser | anything in `parsers/` — every field of every `EventSlice` and `NoteData`, plus `beat_markers`, `tempo_changes`, the repeat/ending/hairpin spans, the Segno/Coda/To Coda/Fine/navigation marks, and `total_measures` |
| `model_fingerprint.py` | Model | anything in `models/` — navigation walks, Region 3/4 text, playback and grace events, durations and ring-out, bar bounds, jump-aware playback stepping, Find's occurrence lists, percussion items, the performance report, key-override round trips |

Both walk `files/`, `examples/` and `tests/fixtures/` (~56 files at time of
writing; the corpus grows on its own as fixtures are added — no list to
maintain).

## The workflow

Capture a baseline from the tree *before* your change, then check against it
after. The scripts resolve the repo root from their own location, so they run
correctly from inside a throwaway worktree.

```powershell
# 1. Baseline from the last good commit (or any ref), in a scratch worktree
git worktree add C:\Temp\baseline HEAD
Copy-Item tests\manual\*.py C:\Temp\baseline\tests\manual\ -Force
cd C:\Temp\baseline
..\..\Users\chess\github\SReader\.venv\Scripts\python.exe tests\manual\parser_fingerprint.py C:\Temp\before.txt

# 2. Back on your working tree, after the change
cd C:\Users\chess\github\SReader
.venv\Scripts\python.exe tests\manual\parser_fingerprint.py C:\Temp\after.txt --check C:\Temp\before.txt

# 3. Clean up
git worktree remove C:\Temp\baseline --force
```

`--check` prints `MATCH` and exits **0** when the two are identical, or prints
a unified diff (first 80 lines) and exits **1** when they are not. Without
`--check` it just writes the fingerprint.

Copying the scripts into the baseline worktree is what lets you capture a
baseline from a revision that predates them. Both are written to run against
older revisions: they go through public entry points only (`MusicData`), and
`model_fingerprint.py` probes for `find_index` so it works either side of S1.

## Reading a difference

Output is one line per note (`slice[12].note[0] NoteData(...)`), not one line
per slice, so a diff points at the exact note rather than dumping a
2,000-character bar. Dataclass fields are sorted by name, so merely reordering
a dataclass's fields is not reported as a behaviour change; floats are rounded
to 9dp so formatting alone cannot masquerade as a value change.

**Any difference at all is a regression** unless you can explain it and
intended it. If a change is meant to alter output, say so explicitly in the
commit — don't quietly re-baseline.

## Adding to a harness

Add anything a refactor could plausibly break and nothing that is
nondeterministic (no timestamps, no dict iteration order that isn't sorted, no
absolute paths). A parse failure is recorded in the output as a `FAILED:` line
rather than raised, so one broken fixture can't mask differences in the other
55 — and a file that fails identically before and after still compares equal.
