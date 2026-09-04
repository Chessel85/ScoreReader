# ToMac.md — Producing a macOS build of Recall Score

**Audience:** the author of this repo, who has never used a Mac and does not own one.
**Goal:** a downloadable `.dmg` that at least one macOS user can install, run, and give feedback on — without breaking the existing Windows build.

Everything below is written so that Windows remains the primary, fully-supported platform. Every code change is a `sys.platform` branch that leaves the Windows path byte-identical. Nothing here is a rewrite.

---

## 0. The honest summary first

| Area | Difficulty | Notes |
|---|---|---|
| Python/Qt/music21 code | **Easy** | Already portable. Runs unmodified. |
| Paths, config, persistence | **Easy** | `QStandardPaths` already does the right thing on macOS. |
| FluidSynth audio | **Medium** | Driver name and library loading are Windows-specific; both are one-branch fixes. Bundling the `.dylib`s into the app is the fiddly part. |
| Voice control (Vosk) | **Medium** | One import-time crash to fix, plus microphone permission plumbing. Can be shipped disabled for v1. |
| Packaging (`.app` + `.dmg`) | **Medium** | PyInstaller does the `.app`; `hdiutil`/`create-dmg` does the `.dmg`. NSIS is not involved at all. |
| Code signing / Gatekeeper | **Medium** | Unsigned apps *can* be opened, but the tester needs a specific right-click gesture. Ad-hoc signing avoids the worse "app is damaged" error. |
| **Screen reader accessibility (VoiceOver)** | **Unknown — the real risk** | This is the product. Qt's macOS accessibility bridge is not the same as its Windows/NVDA one. This is what the tester exists to tell you. |

**Recommendation:** treat v1 macOS as an *experiment shipped to one tester*, not a supported platform. Build it, get it running, get feedback on VoiceOver, then decide whether to invest further.

---

## 1. How to build without owning a Mac

You cannot cross-compile a macOS app from Windows. PyInstaller must run on macOS. You have three options:

### Option A — GitHub Actions macOS runner (recommended)
GitHub gives you free macOS runners (`macos-14` and `macos-15` are Apple Silicon / arm64; `macos-13` is Intel / x86_64). You push a workflow file, it builds the `.app` and `.dmg`, and uploads them as a release asset or artifact.

- **Pros:** free (for public repos), reproducible, you never touch a Mac, and the tester downloads from a GitHub Release like any normal user.
- **Cons:** no interactive debugging — you iterate through commit → wait 5 minutes → read logs. You cannot see the UI or hear the audio.
- **The blocker to solve:** the runner has no `soundfonts/Airfont_380_final.sf2` (263 MB, gitignored) and no `vosk_model_large/` (205 MB, gitignored). See §8 for how to feed those in.

### Option B — a rented cloud Mac
MacStadium, MacinCloud, AWS EC2 Mac instances, Scaleway Mac minis. You get a real desktop over screen sharing, roughly $1–2/hour or $30+/month.

- **Pros:** interactive. You can actually run the app, hear whether audio works, and turn VoiceOver on yourself (`Cmd+F5`).
- **Cons:** costs money; and as a first-time Mac user you'll spend the first hour just learning the desktop.
- **Worth it for one session** if the Actions build fails in a way the logs don't explain.

### Option C — the tester builds it
If your Mac tester is technical, they clone the repo, `brew install fluid-synth`, `pip install -r requirements.txt`, `python main.py`. This is by far the fastest route to "does it work at all, and does VoiceOver read it" — and it skips packaging entirely.

**Suggested plan: do C first, then A.** Ask the tester to run from source. If the app works and VoiceOver is usable, *then* invest in the `.dmg` pipeline. If VoiceOver is unusable, you have saved yourself the whole packaging effort.

---

## 2. Which Mac architecture to target

Macs since late 2020 are **Apple Silicon (arm64)**. Older ones are **Intel (x86_64)**. An arm64 build will not run on an Intel Mac. An x86_64 build *will* run on Apple Silicon via Rosetta 2 translation, but with a startup penalty and, more importantly, an extra "install Rosetta" prompt for the user.

- **Build arm64 only for v1.** Ask your tester what Mac they have (Apple menu → About This Mac — the "Chip" line says either "Apple M…" or "Intel"). If they're on Intel, build x86_64 instead by using the `macos-13` runner.
- Universal2 (both architectures in one binary) is possible but requires every wheel — PySide6, numpy, vosk, python-rtmidi — to ship universal builds. They mostly don't. **Do not attempt this.**

---

## 3. Code changes

Six files. All changes are additive branches; the Windows behaviour is unchanged.

### 3.1 `audio/synth_engine.py` — audio driver and library loading

**Three separate problems.**

**(a) The `bin/` DLL preload block (lines ~15–37).**
This is already safe on macOS by accident: it's guarded by `if os.path.exists(BIN_DIR)` and `hasattr(os, "add_dll_directory")`, and the `.dll` filenames simply won't exist. It no-ops. **But** for the bundled `.app` you *do* need to help `pyfluidsynth` find the bundled `.dylib`, so this block gains a macOS sibling:

```python
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN_DIR = os.path.join(PROJECT_ROOT, "bin")

if sys.platform == "win32" and os.path.exists(BIN_DIR):
    ...existing Windows block, unchanged...
elif sys.platform == "darwin":
    # pyfluidsynth's find_libfluidsynth() searches the system via
    # ctypes.util.find_library, which never looks inside an .app bundle.
    # It has one documented escape hatch: if HOMEBREW_PREFIX is set it
    # tries $HOMEBREW_PREFIX/lib/libfluidsynth.dylib. We reuse that to
    # point it at our own bundled copy. Only set it if we actually have
    # one - otherwise leave a developer's real Homebrew install alone.
    _bundled = os.path.join(PROJECT_ROOT, "lib", "libfluidsynth.dylib")
    if os.path.exists(_bundled) and not os.environ.get("HOMEBREW_PREFIX"):
        os.environ["HOMEBREW_PREFIX"] = PROJECT_ROOT
```

Read `.venv/Lib/site-packages/fluidsynth.py`'s `find_libfluidsynth()` to confirm this hook still exists in whatever version you build against — it is checked *after* `find_library` fails, which is exactly the frozen-app case. In dev on a Mac with Homebrew, `find_library` succeeds and this code never fires.

Note the bundled path is `lib/`, not `bin/` — that is a macOS convention *and* it is what the `HOMEBREW_PREFIX` trick requires (`$PREFIX/lib/libfluidsynth.dylib`).

**(b) The audio driver name (`_init_engine`, ~line 172).**
`driver = "wasapi"` is hardcoded. WASAPI does not exist on macOS; FluidSynth's macOS driver is `coreaudio`.

```python
driver = "coreaudio" if sys.platform == "darwin" else "wasapi"
device = self._fs.get_setting(f"audio.{driver}.device")
self._fs.setting("audio.driver", driver)
self._fs.setting(f"audio.{driver}.device", device)
self._fs.audio_driver = fluidsynth.new_fluid_audio_driver(self._fs.settings, self._fs.synth)
```

The surrounding comment block (why `Synth.start()` is deliberately not called — the MIDI-router collision and the teardown deadlock) applies equally on macOS; leave it, and add a line noting the driver is now platform-selected.

**(c) Latency settings.**
`audio.period-size = 128`, `audio.periods = 2` are your Ref 9 (25 ms) budget. CoreAudio generally handles small periods *better* than WASAPI, so these should be fine. If the tester reports crackling or dropouts, the fix is to raise `periods` to 3 and re-test — this is a tuning question, not a porting one. **Ask the tester specifically about audio glitching.**

**(d) Sample rate.** The `samplerate=48000.0` constructor argument and its load-bearing comment stay exactly as they are. CoreAudio, like WASAPI shared mode, resamples to the device rate. No change.

### 3.2 `audio/voice_recognition.py` — an import-time crash

**This one will hard-crash the app on macOS at startup, before anything else.**

Line ~151:
```python
_POPEN_CREATIONFLAGS = subprocess.CREATE_NO_WINDOW
```

`subprocess.CREATE_NO_WINDOW` **does not exist on macOS** — it is a Windows-only constant. This is an `AttributeError` at module import, and `audio/synth_engine.py` imports this chain, so the app dies before the window opens.

Fix:
```python
# Windows-only flag (suppresses the worker's console window). On macOS and
# Linux there is no console window to suppress and the constant does not
# exist, so the flag set is empty.
_POPEN_CREATIONFLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)
```

Passing `creationflags=0` is valid on POSIX (it's the default), so the two call sites (`subprocess.run` at ~line 195, `subprocess.Popen` at ~line 326) need no changes.

**Also:** `WORKER_EXE` hardcodes `"RecallScoreVoiceWorker.exe"`. On macOS the executable has no extension:
```python
_WORKER_EXE_NAME = (
    "RecallScoreVoiceWorker.exe" if sys.platform == "win32" else "RecallScoreVoiceWorker"
)
WORKER_EXE = os.path.join(
    getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "voice_worker", _WORKER_EXE_NAME,
)
```

**Design note for macOS:** the entire reason the voice worker is a *separate process* is a Windows-specific DLL-name collision between Vosk's bundled MinGW runtime and FluidSynth's (documented in that module's docstring). That collision does not exist on macOS. **Keep the separate-process design anyway** — one architecture for both platforms is far cheaper to maintain than two, and the separate process costs nothing on macOS.

### 3.3 `main.py` — log path and app icon

**Log redirection.** `_redirect_stdio_if_headless()` uses `%LOCALAPPDATA%`, falling back to `~`. On macOS that works but drops a folder in the user's home directory, which is untidy. Macs put logs in `~/Library/Logs`:

```python
if sys.platform == "darwin":
    log_dir = os.path.expanduser("~/Library/Logs/Recall Score")
else:
    log_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Recall Score")
```

Note: a PyInstaller windowed macOS app *also* gets `sys.stdout = None`, so this function is load-bearing on macOS for exactly the same reason it is on Windows. Don't skip it — and remember this log file is where you will read every `[WARN]`/`[ERROR]` when debugging remotely.

**App icon.** `_app_icon_path()` looks for `RecallScore.ico`. macOS needs `.icns`, and `QIcon` will not read a `.ico` reliably for the Dock. Widen the search:

```python
def _app_icon_path():
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    for name in ("RecallScore.icns", "RecallScore.ico"):
        candidate = os.path.join(base_dir, name)
        if os.path.exists(candidate):
            return candidate
    return None
```

On macOS the *real* icon comes from the `.app` bundle's `Info.plist`, not from `setWindowIcon` — see §5.2. This change just stops it looking wrong in edge cases.

Creating the `.icns` needs a Mac (or the `icnsutil` Python package on Windows). The simplest path is to commit a 1024×1024 PNG of the existing icon and generate the `.icns` on the build runner with `iconutil` (macOS built-in). See §5.2.

### 3.4 `packaging/` — a new macOS spec

Do **not** modify `RecallScore.spec` / `VoiceWorker.spec` into cross-platform monsters. Create two new files alongside them:

- `packaging/RecallScore-mac.spec`
- `packaging/VoiceWorker-mac.spec`

They can be near-copies. Full contents and reasoning are in §5.

### 3.5 Menus and keyboard shortcuts

**Mostly free, with four things to check.**

- **`Ctrl` maps to `Command` automatically.** Qt's `QKeySequence("Ctrl+F")` produces ⌘F on macOS. All 49 `Ctrl+` shortcuts in `widgets/menu_builder.py` translate for free. If you ever wanted a *literal* Control key on macOS you'd write `Meta+`, but you don't.
- **Ampersand mnemonics (`&File`) are ignored on macOS.** The `&` characters are stripped from menu titles automatically — the menus read correctly, they just have no underlined access letters. But **Alt-key mnemonics on dialog buttons will not work**: `Alt+U`/`Alt+D` in `AttributeOrderDialog` and `PartOrderDialog`, `Alt+P` in the strumming dialog, `Alt+W` in the mixer. This is a real functional loss for a keyboard-first app. Flag it for the tester; the fix, if it matters, is an explicit `QShortcut` on macOS.
- **Qt auto-moves some menu items into the macOS application menu.** Qt guesses from the action's *text*: anything matching "About…", "Preferences…"/"Settings…", "Quit"/"Exit" is relocated to the "Recall Score" menu at the far left. This is correct macOS behaviour and you should let it happen — but Qt's matching is loose and can *steal* an item you didn't intend. If a menu item goes missing on macOS, this is why; the fix is `action.setMenuRole(QAction.MenuRole.NoRole)`.
- **Bare-letter shortcuts work unchanged** — the Z/X/C/V/B region jumps, F/S/D tempo, O toggle, Space play/stop, and the 0–9 typed-bar buffer. These are unmodified keys, so there's no mapping question. macOS does reserve some system shortcuts (⌘Space for Spotlight, ⌃↑ for Mission Control), but none of yours collide on paper. **Ask the tester to report any shortcut that behaves unexpectedly.**

### 3.6 Nothing to change (verified against the code)

- **`persistence/app_settings.py` / `score_config.py`** — `QStandardPaths.AppLocalDataLocation` resolves to `~/Library/Application Support/Recall Score` on macOS automatically. Because `QApplication.setApplicationName("Recall Score")` is already set in `main.py`, this just works, and per-user config stays per-user exactly as on Windows.
- **`controllers/score_persistence.py`'s "Open Local Folder"** — `QDesktopServices.openUrl(QUrl.fromLocalFile(...))` opens Finder on macOS. Works.
- **`main_window.py`'s Help > User Guide** — same mechanism, opens the default browser. Works.
- **`_app_base_dir()` / `version.py` / `sys._MEIPASS`** — PyInstaller sets `_MEIPASS` on macOS too. See §5.1 for a bundle-layout caveat to verify on the first build.
- **`models/`, `parsers/`, `widgets/`, `controllers/`, `workers/`** — pure Python and Qt. Nothing platform-specific anywhere in them.
- **`audio/midi_input.py`** — `python-rtmidi` supports CoreMIDI natively and ships macOS wheels. The module already degrades to `RTMIDI_AVAILABLE = False` if the import fails.
- **`audio/metronome.py`, `position_announcer.py`, `performance_cue.py`, `strum_schedule.py`, `pitch_detector.py`** — pure stdlib/numpy maths. Nothing to do.

---

## 4. Dependencies on macOS

### 4.1 Python
Use **python.org's official installer** or Homebrew's `python@3.13`. Do **not** use the `/usr/bin/python3` that ships with macOS — it's a stub and can't install packages cleanly.

### 4.2 The pip requirements
| Package | macOS arm64 status |
|---|---|
| `PySide6==6.11.1` | Official wheels. Fine. |
| `music21==10.5.0` | Pure Python. Fine. |
| `pyfluidsynth==1.4.0` | Pure Python binding — needs the native library (below). |
| `python-rtmidi==1.5.8` | Wheels published for macOS. May build from source; needs Xcode Command Line Tools. |
| `numpy==2.5.1` | Wheels. Fine. |
| `vosk==0.3.45` | Publishes macOS arm64 wheels. **Verify** — this is the one most likely to need a version bump or to be dropped for v1. |
| `sounddevice==0.5.6` | Bundles PortAudio. Fine. |
| `pyinstaller==6.22.0` | Fine. |

If `vosk` won't install, **ship v1 without voice control**. The app already degrades gracefully (`VOSK_AVAILABLE = False`) and voice control is a supplementary feature. That is a much better use of your time than fighting a wheel.

### 4.3 FluidSynth native library
There is no `bin/` equivalent to copy — you install it:

```bash
xcode-select --install     # Xcode Command Line Tools, a Homebrew prerequisite
brew install fluid-synth
```

This installs `libfluidsynth.dylib` plus its own dependencies (glib, libsndfile, libinstpatch and more) into `/opt/homebrew/` on Apple Silicon or `/usr/local/` on Intel. `pyfluidsynth`'s `find_library` locates it automatically in dev. `README.md`'s **Native dependencies** section documents this step for builders alongside the Windows `bin/` DLL steps.

### 4.4 The two big local binaries
- **`soundfonts/Airfont_380_final.sf2`** (263 MB) — gitignored, exactly as on Windows. Must be present at the same relative path. The app runs without it, silently and with no audio. Original source: <https://musical-artifacts.com/artifacts/635> ("Airfont 380 Final", Milton Paredes / mpj factory studios) — `README.md`'s **Native dependencies** section now points builders there.
- **`soundfonts/recall_score_sounds.sf2`** — checked into git. Comes with the clone.
- **`vosk_model_large/`** (205 MB) — gitignored. Only needed for voice control.

The same rule from CLAUDE.md applies unchanged: **never `git add` these.** Getting them onto a build runner is §8's problem.

---

## 5. Packaging: `.app` and `.dmg`

macOS has no NSIS, no `Program Files`, and no registry. The conventions are:

- An application is a **bundle**: a directory named `RecallScore.app` that Finder displays as a single file. Inside: `Contents/MacOS/` (the executable), `Contents/Resources/` (data), `Contents/Frameworks/` (libraries), `Contents/Info.plist` (metadata).
- An **installer** is usually just a **`.dmg`** — a disk image the user double-clicks, which mounts and shows a window containing the `.app` and a shortcut to `/Applications`. The user drags one onto the other. That is the whole installation.
- There is no uninstaller. The user drags the `.app` to the Trash. Your `~/Library/Application Support` config survives — which is exactly what your Windows uninstaller deliberately does with `AppData`. Same behaviour, no work needed.

### 5.1 `packaging/RecallScore-mac.spec`

Start from `RecallScore.spec` and make these changes:

```python
# Instead of bin/*.dll: the FluidSynth dylibs, collected from Homebrew and
# relocated (see 5.3). Destination is "lib" (not "bin") to match the
# HOMEBREW_PREFIX hook in audio/synth_engine.py.
datas = [
    (os.path.join(REPO_ROOT, "macbin", "*.dylib"), "lib"),
    (os.path.join(REPO_ROOT, "soundfonts", "Airfont_380_final.sf2"), "soundfonts"),
    (os.path.join(REPO_ROOT, "soundfonts", "recall_score_sounds.sf2"), "soundfonts"),
    (os.path.join(REPO_ROOT, "docs", "user_guide.html"), "docs"),
    (os.path.join(REPO_ROOT, "version.txt"), "."),
]
```

Everything else — the `music21` corpus exclusion, the `matplotlib`/`PIL` excludes, the `examples/` glob, and the guarded voice-worker/vosk-model `Tree()` additions — **carries over verbatim**.

Drop the `version_info.txt` generation entirely: that's a Windows PE resource and PyInstaller ignores `version=` on macOS. Version metadata goes in `Info.plist` instead.

Then `EXE` and `COLLECT` as before (`console=False`, `icon=` pointing at the `.icns`), plus a **`BUNDLE`** step that has no Windows equivalent:

```python
app = BUNDLE(
    coll,
    name="Recall Score.app",
    icon=os.path.join(PACKAGING_DIR, "RecallScore.icns"),
    bundle_identifier="com.recallscore.app",
    version=APP_VERSION,
    info_plist={
        "CFBundleName": "Recall Score",
        "CFBundleDisplayName": "Recall Score",
        "CFBundleShortVersionString": APP_VERSION,
        "CFBundleVersion": APP_VERSION,
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
        # REQUIRED. Without this key, macOS KILLS the process the instant it
        # opens the microphone - it does not merely deny permission. Affects
        # both Tools > Tuner (audio/tuner_capture.py) and voice control
        # (audio/voice_recognition_worker.py).
        "NSMicrophoneUsageDescription":
            "Recall Score uses the microphone for the instrument tuner and "
            "for hands-free voice commands. Audio is processed on your Mac "
            "and never leaves it.",
        # Lets Finder's Open With / double-click route score files here.
        "CFBundleDocumentTypes": [{
            "CFBundleTypeName": "Music score",
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeExtensions": [
                "xml", "musicxml", "mxl", "mid", "midi", "gp", "ug"
            ],
        }],
    },
)
```

`LSMinimumSystemVersion: "12.0"` (Monterey) is a safe floor for PySide6 6.11. Ask your tester their macOS version and lower it only if needed.

**Bundle-layout caveat — verify this on the first build.** PyInstaller 6 splits a macOS `.app`'s contents between `Contents/Frameworks` (binaries) and `Contents/Resources` (data files), creating cross-symlinks so both resolve. `sys._MEIPASS` points at `Contents/Frameworks`. Your `_app_base_dir()` / `PROJECT_ROOT` / `MODEL_DIR` idiom *should* still find `docs/`, `soundfonts/`, `lib/` and `version.txt` through those symlinks — but **this is the single most likely thing to be wrong on the first build.** If the app launches with "SoundFont not found" in the log, this is the cause. Diagnose by temporarily adding `print(sys._MEIPASS, os.listdir(sys._MEIPASS))` and reading `~/Library/Logs/Recall Score/recall_score.log`.

### 5.2 The `.icns` icon

`iconutil` (built into macOS) converts an `.iconset` folder of PNGs. Save this as `packaging/make_icns.sh`:

```bash
#!/bin/bash
set -e
SRC=packaging/RecallScore-1024.png     # commit this: a 1024x1024 PNG of the icon
OUT=packaging/RecallScore.iconset
rm -rf "$OUT"; mkdir -p "$OUT"
sips -z 16 16    "$SRC" --out "$OUT/icon_16x16.png"
sips -z 32 32    "$SRC" --out "$OUT/icon_16x16@2x.png"
sips -z 32 32    "$SRC" --out "$OUT/icon_32x32.png"
sips -z 64 64    "$SRC" --out "$OUT/icon_32x32@2x.png"
sips -z 128 128  "$SRC" --out "$OUT/icon_128x128.png"
sips -z 256 256  "$SRC" --out "$OUT/icon_128x128@2x.png"
sips -z 256 256  "$SRC" --out "$OUT/icon_256x256.png"
sips -z 512 512  "$SRC" --out "$OUT/icon_256x256@2x.png"
sips -z 512 512  "$SRC" --out "$OUT/icon_512x512.png"
cp "$SRC"                "$OUT/icon_512x512@2x.png"
iconutil -c icns "$OUT" -o packaging/RecallScore.icns
```

Commit the 1024×1024 PNG (the source art the `.ico` was made from — a small real asset, like `RecallScore.ico` itself). The `.icns` is then generated on the build machine and never needs committing. Like `has_icon` in the Windows spec, guard for its absence so a missing icon degrades the build rather than failing it.

### 5.3 Bundling the FluidSynth dylibs

This is the fiddliest step. A macOS `.dylib` records the *paths of its own dependencies* inside itself (its "install names"). Homebrew's `libfluidsynth.dylib` says "I need `/opt/homebrew/opt/glib/lib/libglib-2.0.0.dylib`" — an absolute path that will not exist on the tester's machine.

**Easy option — `dylibbundler`:**
```bash
brew install dylibbundler
mkdir -p macbin
cp "$(brew --prefix fluid-synth)/lib/libfluidsynth.dylib" macbin/
dylibbundler -od -b -x macbin/libfluidsynth.dylib -d macbin/ -p @loader_path/
```
This copies every transitive dependency into `macbin/` and rewrites all the install names to `@loader_path/…` ("next to me"), which is exactly what a bundle needs. The `datas` entry `("macbin/*.dylib", "lib")` then puts them all in one directory inside the app, where they find each other.

**Always verify afterwards:**
```bash
otool -L macbin/libfluidsynth.dylib
```
Every line should start with `@loader_path/`, `/usr/lib/` or `/System/Library/` (the last two are OS-provided and fine). **Any remaining `/opt/homebrew/` path is a bug that will work on the build machine and crash on the tester's.**

`macbin/` should be gitignored, like `bin/` — it's a build byproduct.

### 5.4 The `.dmg`

```bash
brew install create-dmg

create-dmg \
  --volname "Recall Score $APP_VERSION" \
  --window-size 600 400 \
  --icon "Recall Score.app" 150 200 \
  --app-drop-link 450 200 \
  --hide-extension "Recall Score.app" \
  "dist_installer/RecallScore-$APP_VERSION.dmg" \
  "dist/Recall Score.app"
```

`--app-drop-link` is what creates the `/Applications` shortcut users drag onto. That is the entire installer.

If `create-dmg` is unavailable, `hdiutil create -volname "Recall Score" -srcfolder "dist/Recall Score.app" -ov -format UDZO out.dmg` produces a plain, uglier but functional disk image.

---

## 6. Code signing and Gatekeeper — what your tester will actually see

This matters more than it sounds, because **without handling it the tester will download the app and be told it is damaged.** They will assume your app is broken. It isn't.

### The three tiers

**Tier 0 — completely unsigned.** On Apple Silicon, macOS *requires* every executable to carry at least an ad-hoc signature. A downloaded, wholly unsigned app produces: *"Recall Score is damaged and can't be opened. You should move it to the Trash."* This is misleading, but it's what the user sees. **Avoid this tier.**

**Tier 1 — ad-hoc signed (free, recommended for v1).**
```bash
codesign --force --deep --sign - "dist/Recall Score.app"
```
The `-` means "ad-hoc": a valid signature with no identity behind it. The "damaged" error goes away, and the user instead gets *"Recall Score can't be opened because Apple cannot check it for malicious software"* — which is honest and, crucially, **bypassable**.

**Send these instructions to your tester, in the release notes:**

> The app is not signed with an Apple developer certificate, so macOS will warn you the first time. To open it:
>
> 1. Drag **Recall Score** to your **Applications** folder.
> 2. In Applications, **right-click** (or Control-click) Recall Score and choose **Open**.
> 3. Click **Open** in the dialog that appears.
>
> You only have to do this once — double-clicking works normally from then on.
>
> If macOS still refuses, open **System Settings → Privacy & Security**, scroll down, and click **Open Anyway** next to the message about Recall Score.
>
> If you see "damaged and can't be opened", open the **Terminal** app and run:
> `xattr -cr "/Applications/Recall Score.app"`
> then try again.

**Tier 2 — Developer ID signed and notarized ($99/year).** Requires an Apple Developer Program membership, a Developer ID certificate, and submitting the `.dmg` to Apple's notary service (`xcrun notarytool submit`). The user then sees **no warning at all**. This is the right answer if macOS becomes a supported platform. **It is not worth $99 to get one tester's feedback.** Revisit later.

### Microphone permission

The first time the Tuner or voice control opens the mic, macOS shows a permission prompt using your `NSMicrophoneUsageDescription` text. If the user declines, they re-enable it in System Settings → Privacy & Security → Microphone.

**Known risk:** the voice worker is a *separate process*. A child process inside a signed bundle normally inherits the parent app's permission identity, but with only an ad-hoc signature this is less reliable. If the tester reports "the tuner works but voice control never hears anything", this is the likely cause — and it is a reason to defer voice control on macOS rather than debug it deeply.

---

## 7. Testing

The pytest suite should pass on macOS unchanged:
- `tests/conftest.py` sets `QT_QPA_PLATFORM=offscreen` before PySide6 loads — platform-independent.
- The autouse fixture blocking `SynthEngine._init_engine` means no audio device is ever opened.
- The `_isolate_persistence` fixture redirects `QStandardPaths` to `tmp_path`.

```bash
python -m pytest
python -m pytest -m "not slow"
```

**Add one test** to `tests/test_harness.py` guarding the crash from §3.2 — import `audio.voice_recognition` and assert `_POPEN_CREATIONFLAGS` is an `int`. It would have caught the macOS import failure *while running on Windows*, which is the class of guard worth having for every platform branch you add.

`tests/manual/parser_fingerprint.py` and `model_fingerprint.py` are pure parsing/model code and should produce **byte-identical** output on macOS. Running them on the Mac and diffing against a Windows baseline is an excellent, cheap end-to-end check that the port changed no behaviour. Watch for line-ending differences in the comparison (`.gitattributes` already normalises text).

---

## 8. A GitHub Actions build workflow

The obstacle: `soundfonts/Airfont_380_final.sf2` (263 MB) and `vosk_model_large/` (205 MB) are gitignored, so a fresh checkout doesn't have them.

**Three ways to solve it, best first:**

1. **Upload them once as assets on a GitHub Release** (e.g. a release tagged `build-assets`) and have the workflow `gh release download` them. GitHub release assets can be up to 2 GB each. Cleanest option, costs nothing, and — importantly — does not put them in git history, so the 100 MB file-limit disaster documented in CLAUDE.md cannot recur.
2. **Fetch the soundfont from its original source** — <https://musical-artifacts.com/artifacts/635> ("Airfont 380 Final"), the URL `README.md` now points builders at — with `curl`, if the page exposes a stable direct download link. Downsides: an external dependency that can vanish, and the download may be an archive needing extraction rather than a bare `.sf2`.
3. **Build without them.** Both are guarded — the spec prints `[WARN]` and continues, and the app runs silently. Useless for a real tester, but a valid way to prove the *pipeline* works before solving the asset problem. **Do this first.**

Sketch of `.github/workflows/build-macos.yml`:

```yaml
name: Build macOS
on:
  workflow_dispatch:        # run it by hand from the Actions tab
  push:
    tags: ["v*"]

jobs:
  build:
    runs-on: macos-14       # Apple Silicon (arm64). Use macos-13 for Intel.
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Install FluidSynth and packaging tools
        run: brew install fluid-synth dylibbundler create-dmg

      - name: Install Python dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt -r requirements-dev.txt -r requirements-build.txt

      - name: Run tests
        run: python -m pytest -m "not slow"

      - name: Fetch large binaries
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          mkdir -p soundfonts
          gh release download build-assets --pattern 'Airfont_380_final.sf2' \
            --dir soundfonts || echo "::warning::SoundFont unavailable - building without audio"

      - name: Collect and relocate FluidSynth dylibs
        run: |
          mkdir -p macbin
          cp "$(brew --prefix fluid-synth)/lib/libfluidsynth.dylib" macbin/
          dylibbundler -od -b -x macbin/libfluidsynth.dylib -d macbin/ -p @loader_path/
          otool -L macbin/libfluidsynth.dylib

      - name: Build the icon
        run: bash packaging/make_icns.sh

      - name: Build the app
        run: python -m PyInstaller packaging/RecallScore-mac.spec --noconfirm

      - name: Ad-hoc sign
        run: codesign --force --deep --sign - "dist/Recall Score.app"

      - name: Build the DMG
        run: |
          VERSION=$(cat version.txt)
          mkdir -p dist_installer
          create-dmg \
            --volname "Recall Score $VERSION" \
            --window-size 600 400 \
            --icon "Recall Score.app" 150 200 \
            --app-drop-link 450 200 \
            "dist_installer/RecallScore-$VERSION.dmg" \
            "dist/Recall Score.app"

      - uses: actions/upload-artifact@v4
        with:
          name: RecallScore-macOS
          path: dist_installer/*.dmg
```

The voice-worker build (`packaging/VoiceWorker-mac.spec`) would be an extra PyInstaller step **before** the main one, mirroring the Windows ordering documented in CLAUDE.md exactly. Omit it for v1.

---

## 9. Updating `README.md`

**Status (2026-09-04): partially done.** `README.md` on `main` now carries the cross-platform native-dependency instructions this section called for:

- The **Requirements** OS line notes macOS support is in progress and points at this file.
- A new **## Native dependencies (not in git)** section gives per-platform FluidSynth acquisition steps — Windows: download `fluidsynth-<version>-win10-x64.zip` (or `-winarm64.zip`) from the [FluidSynth GitHub releases page](https://github.com/FluidSynth/fluidsynth/releases) and copy its `bin/` DLLs into the repo's `bin/`; macOS: `xcode-select --install` then `brew install fluid-synth`, with a note that nothing goes in `bin/` on macOS and that `.app` bundling stages `.dylib`s into `macbin/` per §5.3.
- The **GM SoundFont** subsection points builders at the original source, <https://musical-artifacts.com/artifacts/635> ("Airfont 380 Final", Milton Paredes / mpj factory studios), rather than hosting the 263 MB file — download, extract if compressed, place at exactly `soundfonts/Airfont_380_final.sf2`.
- **Getting Started (development)** now has both a Windows PowerShell block and a macOS bash block (`python3 -m venv`, `source .venv/bin/activate`).
- The **License** section credits the Airfont 380 SoundFont and links its terms.

**Still to do** (deferred until the macOS build actually exists): a **Platform support** table, a macOS **Building an installer** subsection (collect dylibs → `.icns` → `RecallScore-mac.spec` → `codesign` → `create-dmg`), an **Installing on macOS (for testers)** section carrying §6's right-click → Open instructions verbatim, and a `ToMac.md` line in the Documentation list. The fuller skeleton below is the target for that pass:

```
# Recall Score
  One paragraph. Note the rename from ScoreReader (GitHub repo now `RecallScore`).

## Features
  - Five regions (add Region 5, the Performance region)
  - Import: MusicXML (.xml/.musicxml/.mxl), MIDI, Guitar Pro (.gp),
    Ultimate Guitar chord tabs, saved .ug imports
  - Screen reader first: NVDA on Windows; VoiceOver on macOS is experimental
  - Low-latency in-process FluidSynth audio
  - Live MIDI input, metronome, talking metronome, tuner, voice control

## Platform support
  | Platform | Status |
  |---|---|
  | Windows 10/11 | Supported and tested. Installer provided. |
  | macOS 12+ (Apple Silicon) | Experimental. Feedback wanted. |
  | Linux | Not tested. Should mostly work from source. |

## Prerequisites
### Windows
  Python 3.13; Microsoft Visual C++ Redistributable;
  bin/ FluidSynth DLLs and soundfonts/Airfont_380_final.sf2 (both gitignored)
### macOS
  xcode-select --install
  brew install fluid-synth
  soundfonts/Airfont_380_final.sf2
  Optional, for voice control: vosk_model_large/

## Running from source
### Windows
  python -m venv .venv
  .venv\Scripts\Activate.ps1
  pip install -r requirements.txt
  python main.py
### macOS
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  python main.py

## Running the tests      (identical on both platforms)
  pip install -r requirements-dev.txt
  python -m pytest
  python -m pytest -m "not slow"

## Building an installer
### Windows   -> dist_installer/RecallScore-Setup-<version>.exe
  Three steps, in this order: VoiceWorker.spec, RecallScore.spec, makensis
  (copy the exact commands from CLAUDE.md's Packaging section, including
   the note about running makensis from inside packaging/)
### macOS     -> dist_installer/RecallScore-<version>.dmg
  brew install fluid-synth dylibbundler create-dmg
  collect dylibs -> build .icns -> RecallScore-mac.spec -> codesign -> create-dmg
  See ToMac.md for the full explanation of each step.

## Installing on macOS (for testers)
  The right-click -> Open instructions from ToMac.md section 6, verbatim.
  This is the part testers most need.

## Keyboard controls
  Expand the existing four lines: Space play/stop, Ctrl+F find,
  Z/X/C/V/B region jumps, F/S/D tempo, 0-9 then Enter for a bar number.
  Point at Help > User Guide / docs/user_guide.md for the full map.
  Note: on macOS, Ctrl becomes Command.

## Documentation
  docs/user_guide.md               end-user guide
  Product Definition Document.md   the authoritative spec
  CLAUDE.md                        architecture and development notes
  ToMac.md                         the macOS porting plan

## Version
  Single source of truth: version.txt

## License
  MIT. Bundled FluidSynth/GLib/libsndfile/libinstpatch are LGPL -
  see packaging/THIRD_PARTY_NOTICES.txt.
```

When writing the macOS command blocks, remember to convert `\` path separators to `/`, `.venv\Scripts\python.exe` to `.venv/bin/python`, and `Activate.ps1` to `source .venv/bin/activate`.

---

## 10. Suggested order of work

Each phase ends in something you can verify. **Do not skip ahead** — phase 3 alone might tell you whether the rest is worth doing.

**Phase 1 — make the code importable on macOS (½ day, done entirely on Windows).**
1. Fix `audio/voice_recognition.py`'s `CREATE_NO_WINDOW` crash (§3.2).
2. Add the `sys.platform` branches to `audio/synth_engine.py` (§3.1) and `main.py` (§3.3).
3. Add the guard test (§7).
4. Run the full pytest suite on Windows. **Nothing may change.**
5. Run `tests/manual/parser_fingerprint.py --check` and `model_fingerprint.py --check` against the current baseline. **Zero differences.**
6. Commit.

**Phase 2 — does it run at all? (one evening, needs a Mac.)**
Have your tester (or a rented cloud Mac) clone, `brew install fluid-synth`, `pip install -r requirements.txt`, `python main.py`. No packaging. Report back: does the window open, do the five regions appear, does a score load, is there sound?

**Phase 3 — the question that actually matters (the same session).**
Have them turn on VoiceOver (**⌘F5**) and try to navigate. This is the go/no-go — see §12 for the exact questions. If this goes badly, stop and think: packaging an app nobody can navigate is wasted work.

**Phase 4 — the build pipeline, with no assets (½ day).**
Write `packaging/RecallScore-mac.spec` and the Actions workflow. Run it *without* the soundfont. Success criterion: a `.dmg` artifact is produced, and the tester can install it and see the window (silently). This proves the packaging with the 263 MB problem out of the way.

**Phase 5 — the assets (½ day).**
Upload the soundfont as a release asset, add the `gh release download` step, add the dylib bundling and ad-hoc signing. Success criterion: the installed `.app` produces sound.

**Phase 6 — polish.**
Voice control (or a documented decision to defer it), the `.icns` icon, `Info.plist` document types, the README rewrite, and release notes carrying the Gatekeeper instructions.

---

## 11. Things most likely to go wrong

| Symptom | Likely cause | Where to look |
|---|---|---|
| App won't launch — no window, no error | The `CREATE_NO_WINDOW` import crash | §3.2. Check `~/Library/Logs/Recall Score/recall_score.log` |
| "Recall Score is damaged" | Unsigned bundle on Apple Silicon | §6 — ad-hoc sign, and send the `xattr -cr` instruction |
| Launches but silent; log says "SoundFont not found" | Bundle layout / `_MEIPASS` resolution | §5.1 caveat — read the exact path the warning prints |
| Launches but silent; log says FluidSynth init failed | `wasapi` driver name still hardcoded, or the dylib wasn't found | §3.1 |
| Audio crackles or drops out | CoreAudio period settings | Try `audio.periods = 3` |
| Crashes the instant the Tuner opens | Missing `NSMicrophoneUsageDescription` | §5.1 — macOS kills the process, it doesn't just deny |
| Works on the build machine, "damaged" on the tester's | A `/opt/homebrew/…` path left in a dylib | `otool -L` on every `.dylib` (§5.3) |
| A menu item is missing on macOS | Qt relocated it into the application menu by name | §3.5 — `setMenuRole(NoRole)` |
| The `.app` runs on one Mac, not another | Architecture mismatch (arm64 vs Intel) | §2 — ask which chip they have |
| Dialog Alt+U / Alt+D buttons do nothing | macOS ignores Alt mnemonics | §3.5 — needs explicit `QShortcut`s |
| VoiceOver reads nothing useful | Qt's macOS accessibility bridge | Not a quick fix. This is the finding, not a bug to squash |

---

## 12. What to ask the tester for

Send a short, specific list — an open-ended "how was it?" produces nothing usable.

1. Which Mac and which macOS version? (Apple menu → About This Mac — the "Chip" line and the version number.)
2. Did the install work, and how many warnings did you have to click through?
3. Does the app open, and can you load one of the bundled example scores?
4. **With VoiceOver on:** can you Tab between the five regions and tell where you are?
5. **With VoiceOver on:** in the note region, do the arrow keys move, and does it read the note out ("F sharp, quarter, beat 1")?
6. **With VoiceOver on:** does Region 2's on/off toggle announce its new state when you press O?
7. Do you hear audio when you move between notes? Is it clean, or does it crackle?
8. Does anything read as a wall of text, or get skipped over entirely?
9. Does any keyboard shortcut do something unexpected? (macOS may be intercepting it.)
10. If you use a screen reader every day: is this usable, nearly usable, or not usable?

Question 10 is the one that decides whether macOS becomes a supported platform.
