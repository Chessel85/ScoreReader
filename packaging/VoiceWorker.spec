# packaging/VoiceWorker.spec
# PyInstaller spec for the hands-free voice-control worker (Ref 19,
# audio/voice_recognition_worker.py) as its OWN separate executable, bundled
# alongside the main RecallScore.exe by RecallScore.spec (see that spec's
# own comment on why it pulls this build's output in as a subfolder). Three
# things force this apart from the main app build, found by live-testing the
# installed .exe (voice control silently reported "vosk/sounddevice not
# available" - see audio/voice_recognition.py's own module docstring/
# VOSK_AVAILABLE for the fuller story):
#
# 1. audio/voice_recognition.py never imports vosk/sounddevice itself - only
#    audio/voice_recognition_worker.py does, in a separate CHILD PROCESS,
#    specifically to avoid a DLL-name collision between vosk's and
#    FluidSynth's bundled MinGW runtime DLLs (libstdc++-6.dll,
#    libwinpthread-1.dll - see that module's own docstring). Since nothing
#    in main.py's own import graph ever reaches vosk/sounddevice, a single
#    combined PyInstaller build would never discover or bundle them at all.
#    Building the worker as its own PyInstaller output also keeps those
#    DLLs in a completely separate folder from bin/ (the FluidSynth DLLs
#    RecallScore.spec bundles), preserving the collision-avoidance at the
#    FILE level too, not just the process level.
# 2. In the dev tree, audio/voice_recognition.py launches the worker via
#    `sys.executable <path to voice_recognition_worker.py>` - a real
#    python.exe interpreting a real .py file. Neither exists once frozen:
#    sys.executable IS RecallScore.exe (no separate interpreter ships), and
#    plain .py source isn't shipped as a loose file (it's compiled into the
#    main app's own PYZ archive). The worker needs to be its own runnable
#    executable so it can be launched directly.
# 3. A `console=False` (windowed) PyInstaller build has sys.stdout/stdin/
#    stderr forced to None at bootstrap REGARDLESS of whether the process
#    was launched with piped handles (the same PyInstaller quirk main.py's
#    _redirect_stdio_if_headless works around for print()) - which would
#    break the worker's newline-delimited-JSON stdin/stdout protocol
#    entirely. This spec builds it `console=True` instead so real pipes
#    work; audio/voice_recognition.py launches it with the Windows
#    CREATE_NO_WINDOW process-creation flag so no console window is ever
#    actually shown on screen.
#
# Runnable directly, BEFORE RecallScore.spec (which bundles this build's
# output - see that spec's own comment), from the repo root:
#     .venv\Scripts\python.exe -m PyInstaller packaging\VoiceWorker.spec --noconfirm
# packaging/build_installer.ps1 runs this step automatically, in order.
# Missing this step entirely is not a build failure for RecallScore.spec -
# voice control is a supplementary feature (the app is fully usable
# without it) - it just means the installed app won't have it, the same
# "warn and no-op" degradation VOSK_AVAILABLE already gives a dev machine
# with no vosk/sounddevice installed at all.

import os

from PyInstaller.utils.hooks import collect_dynamic_libs

REPO_ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

# libvosk.dll (+ its own bundled libstdc++-6.dll/libwinpthread-1.dll/
# libgcc_s_seh-1.dll copies) live as loose files inside the installed vosk
# package folder and are dlopen'd by vosk/__init__.py's open_dll() relative
# to its own dirname(__file__) - not discoverable via PyInstaller's normal
# import-graph binary scan (that only follows Python import statements), so
# they're collected explicitly here. sounddevice's own bundled PortAudio DLL
# needs no equivalent handling - pyinstaller-hooks-contrib ships a
# hook-sounddevice.py that PyInstaller picks up automatically.
vosk_binaries = collect_dynamic_libs("vosk")

a = Analysis(
    [os.path.join(REPO_ROOT, "audio", "voice_recognition_worker.py")],
    pathex=[REPO_ROOT],
    binaries=vosk_binaries,
    datas=[],
    # vosk/sounddevice are only ever imported lazily, inside run()/
    # list_devices() (deliberately - see voice_recognition_worker.py's own
    # docstring on why this file stays import-minimal at module level).
    # PyInstaller's bytecode scan finds function-body imports fine without
    # this, but it's listed explicitly rather than relying on that.
    hiddenimports=["vosk", "sounddevice"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # vosk's own __init__.py unconditionally imports tqdm (for its optional
    # model-download progress bar - a code path this worker never calls,
    # only vosk.Model()/vosk.KaldiRecognizer()/vosk.SetLogLevel() are ever
    # used here), and tqdm/gui.py imports matplotlib, which in turn pulls in
    # PySide6/PIL/numpy/mpl_toolkits - PyInstaller's static analysis follows
    # that whole chain even though nothing here ever reaches tqdm.gui at
    # runtime. Found by inspecting a real build: it bloated this supposedly
    # minimal worker to 234MB and pulled a full Qt install into a process
    # that must stay Qt-free (see this worker's own docstring on why).
    # Excluding matplotlib (mirroring RecallScore.spec's identical exclusion
    # for music21's equally unused matplotlib dependency) cuts the whole
    # branch, including the PySide6/PIL/numpy it drags in.
    excludes=["matplotlib", "mpl_toolkits", "PIL"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RecallScoreVoiceWorker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # see point 3 above - required for real stdin/stdout pipes
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="RecallScoreVoiceWorker",
)
