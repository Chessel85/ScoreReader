# Recall Score

Recall Score is a **screen-reader-first music score and guitar-tab viewer and editor
for visually impaired musicians**, for Windows. It turns a score into structured,
spoken-friendly text laid out across five keyboard-navigable regions, and plays every
move you make through the music as low-latency MIDI, so you always know where you are
and what's sounding.

The app is built around memorising: visually impaired musicians usually can't read
notation and play at the same time, so learning a piece well enough to play it from
memory matters more than it does for a sighted player. Recall Score is designed to
make that process efficient.

*(Local folder `SReader`; GitHub repo `RecallScore` — <https://github.com/Chessel85/RecallScore>.
Current version: see `version.txt`.)*

---

## Features

* **Five-region structured layout**, cycled with `Tab` / `Shift+Tab`, plus a
  six-field status bar (`F6`):
  * Region 1 — Score information (title, composer, key, time signature, tempo).
  * Region 2 — Parts / staves / voices tree, with per-row mute (`F8`) and solo (`F9`).
  * Region 3 — Note timeline at the cursor; the region where you navigate the music.
  * Region 4 — Full note attributes for the current Region 3 selection.
  * Region 5 — Performance markings (repeats, 1st/2nd-time endings, dynamics
    hairpins, Segno/Coda/D.C./D.S./Fine, key/time/tempo changes) at the cursor.
* **Accessibility is the product.** Notes render as speech-friendly text
  ("F sharp", "B double flat"), navigation is entirely keyboard-driven with a
  cyclic region focus loop, and every timeline move triggers a MIDI audition.
* **Low-latency audio.** In-process FluidSynth on the WASAPI driver, chosen to meet
  a 25 ms audition-latency budget. Each part plays on its own MIDI channel with its
  own instrument sound.
* **Multiple input formats:**
  * MusicXML — `.xml`, `.musicxml`, and compressed `.mxl`.
  * Standard MIDI Files — `.mid`, `.midi` (bar boundaries reconstructed from timing).
  * Guitar Pro 7 / 8 — `.gp` (tab staves, string/fret attributes).
  * Ultimate Guitar import — chords-and-lyrics pages and ASCII-tablature "Tab" pages,
    via File > Import from Ultimate Guitar...; saved and reopened as `.ug` files.
  * Embedded chord symbols / lyrics in a MusicXML lead sheet are surfaced
    automatically as synthetic Chords / Lyrics parts.
* **Playback that follows the score** — repeats, endings and Da Capo / Dal Segno /
  Coda / Fine are performed during Play; looping with a configurable count-in and
  repeat-handling; absolute (flat) playback tempo saved per score.
* **Study tools** — a comprehensive Find (any note attribute or structural marking),
  a whole-score Performance Report, a click metronome and a spoken "talking
  metronome" position announcer, a per-instrument volume/pan Mixer, per-part
  instrument and key-signature overrides.
* **Instrument tools** — live playthrough of a connected MIDI keyboard, a
  microphone-based chromatic Tuner, and hands-free voice control (offline, Vosk).
* **UK / US terminology** toggle (bar/measure, crotchet/quarter note, …).
* **Remembers your work** — per-score: last position, mute/solo state, shown
  attributes and their order, mixer settings, overrides; globally: terminology and
  device settings.

---

## Requirements

* **Windows** (Python 3.13). macOS support is in progress — see `ToMac.md`.
* Windows only: Microsoft Visual C++ Redistributable (for the native FluidSynth DLLs).
* Runtime Python packages (`requirements.txt`): PySide6 6.11, music21 10.5,
  pyfluidsynth 1.4, python-rtmidi 1.5, vosk 0.3, sounddevice 0.5, numpy 2.5.
* **Native dependencies that are not in git** — the FluidSynth library, a General
  MIDI SoundFont, and (for voice control) a Vosk model. See
  [Native dependencies](#native-dependencies-not-in-git) below for how to get each
  one. If any are missing the app still runs, with the affected feature degrading
  to a silent no-op (`FLUIDSYNTH_AVAILABLE` / `VOSK_AVAILABLE` / `RTMIDI_AVAILABLE`
  become `False`).

---

## Native dependencies (not in git)

These are fetched once and placed in the working tree. The SoundFont alone is
~263 MB — well over GitHub's 100 MB file limit — so none of this lives in the repo.

### FluidSynth native library

**Windows.** Download the latest `fluidsynth-<version>-win10-x64.zip` (or the
`-winarm64.zip` variant on an ARM64 machine) from the
[FluidSynth releases page](https://github.com/FluidSynth/fluidsynth/releases), then
copy the DLLs out of the zip's `bin/` folder into a `bin/` folder at the root of
this repo (create it if it doesn't exist). You should end up with:

* `bin/libfluidsynth-3.dll`
* its bundled dependencies: `libglib-2.0-0.dll`, `libgobject-2.0-0.dll`,
  `libgthread-2.0-0.dll`, `libsndfile-1.dll`, `libinstpatch-2.dll`, plus the MinGW
  runtime DLLs (`libgcc_*`, `libwinpthread-1.dll`, `libstdc++-6.dll`,
  `libintl-8.dll`).

The zip bundles all of these — there is nothing else to install except the
Microsoft Visual C++ Redistributable (usually already present).
`audio/synth_engine.py` pre-loads these from `bin/` at import.

**macOS.**

```bash
xcode-select --install      # Command Line Tools (Homebrew prerequisite)
brew install fluid-synth
```

That is all that is needed to run from source — `pyfluidsynth` finds the Homebrew
library automatically, so there is **no `bin/` folder to populate on macOS**.
Building a distributable `.app` stages the `.dylib`s into a gitignored `macbin/`
folder instead; see `ToMac.md` §5.3.

### General MIDI SoundFont

Recall Score needs a GM SoundFont at `soundfonts/Airfont_380_final.sf2`. Any GM
SoundFont will work, but the app and the packaging specs default to **Airfont 380
Final** by Milton Paredes (mpj factory studios), ~263 MB:

1. Download it from <https://musical-artifacts.com/artifacts/635>.
2. If the download is compressed, extract the `.sf2`.
3. Place it at exactly `soundfonts/Airfont_380_final.sf2` — that is the path
   `audio/synth_engine.py` and the PyInstaller specs look for.

`soundfonts/recall_score_sounds.sf2` (the click-metronome and position-announcer
sounds, ~520 KB) **is** tracked in git and arrives with the clone — no action
needed.

### Vosk model (voice control only)

Download `vosk-model-small-en-us-0.15` (or similar) from
<https://alphacephei.com/vosk/models> and extract it to `vosk_model/`.

---

## Getting Started (development)

Windows (PowerShell):

```powershell
git clone git@github.com:Chessel85/RecallScore.git SReader
cd SReader

python -m venv .venv
.venv\Scripts\Activate.ps1

pip install --upgrade pip
pip install -r requirements.txt -r requirements-dev.txt
```

macOS (bash / zsh):

```bash
git clone git@github.com:Chessel85/RecallScore.git SReader
cd SReader

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt -r requirements-dev.txt
```

With the [native dependencies](#native-dependencies-not-in-git) above in place, run:

```powershell
.venv\Scripts\python.exe main.py     # Windows; or, with the venv activated:  python main.py
```

```bash
python main.py                       # macOS, with the venv activated
```

VS Code: the launch config is "Python: Current File" (debugpy) — open `main.py` and
press F5.

---

## Tests

```powershell
.venv\Scripts\python.exe -m pytest                 # whole suite (~0.6s)
.venv\Scripts\python.exe -m pytest -m "not slow"   # skip the music21-backed tests
.venv\Scripts\python.exe -m pytest --cov=models --cov=parsers --cov=widgets
```

The harness never opens a real window (`QT_QPA_PLATFORM=offscreen`) or a real audio
device (an autouse fixture blocks engine creation). `tests/manual/` holds two
non-pytest refactor-verification fingerprint harnesses — see `tests/manual/README.md`.

---

## Packaging (Windows installer)

`packaging/` builds `dist_installer/RecallScore-Setup-<version>.exe`, a standard NSIS
wizard. Three command-line steps, run in order (VoiceWorker first, then the app, then
the installer); `packaging/build_installer.ps1` is an optional wrapper. Requires
`pip install -r requirements-build.txt` (PyInstaller) and NSIS 3.11+. Full details,
including the gotchas, are in `CLAUDE.md` under "Packaging".

---

## Documentation

* **`docs/user_guide.md`** — the complete end-user guide (also reachable in-app via
  Help > User Guide). Section 15 is a full keyboard-shortcut reference.
* **`Product Definition Document.md`** — the authoritative spec: roles, numbered
  functional requirements, the region layout, the intended keystroke map.
* **`CLAUDE.md`** — architecture and contributor notes.
* **`docs/release_notes.md`** — per-version changes.

---

## Keyboard controls (quick reference)

| Action | Keys |
| :--- | :--- |
| Move between regions / to the status bar | `Tab` / `Shift+Tab`, `F6` |
| Jump straight to region 1–5 | `Z` `X` `C` `V` `B` |
| Step through notes *(Note region)* | `Left` / `Right Arrow` |
| Jump by bar / to start / to end *(Note region)* | `Ctrl+Left` / `Ctrl+Right`, `Home` / `End` |
| Move within a chord *(Note region)* | `Up` / `Down Arrow` |
| Jump to a bar number | type digits, then `Enter` |
| Play / pause / audition current chord | `Space` / `Ctrl+Space` / `Shift+Space` |
| Playback tempo up / down / reset | `F` / `S` / `D` |
| Mute / solo focused row *(Parts region)* | `F8` / `F9` |
| Find, find next / previous | `Ctrl+F`, `Alt+Right` / `Alt+Left` |
| Metronome / position announcer | `Ctrl+M` / `Ctrl+P` |

See `docs/user_guide.md` §15 for the exhaustive list.

---

## License

MIT — see `LICENSE`. Bundled LGPL FluidSynth / GLib / libsndfile / libinstpatch DLLs
are attributed separately in `packaging/THIRD_PARTY_NOTICES.txt`. The Airfont 380
SoundFont is the work of Milton Paredes (mpj factory studios) — see its
[Musical Artifacts page](https://musical-artifacts.com/artifacts/635) for its terms.
