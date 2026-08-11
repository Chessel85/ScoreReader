# packaging/RecallScore.spec
# PyInstaller spec for the Windows onedir build of Recall Score (M2,
# NFR-02 AC-02.1/AC-02.3). Bundles the FluidSynth DLLs (bin/) and SoundFont
# (soundfonts/) that are gitignored in the working tree (see CLAUDE.md -
# "Local binaries (never commit these)") so the installed app needs no
# separate download - `audio/synth_engine.py`'s PROJECT_ROOT/BIN_DIR
# resolution already works unmodified here: PyInstaller fakes __file__ for
# frozen modules to a path under sys._MEIPASS matching the source tree, so
# dirname(dirname(audio/synth_engine.py)) still lands on the bundle root
# where these datas are placed below.
#
# Not meant to be invoked directly - run packaging/build_installer.ps1,
# which regenerates version_info.txt from version.py first and points
# PyInstaller at this file with --distpath/--workpath at the repo root.

import os

from PyInstaller.utils.hooks import collect_data_files

REPO_ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
PACKAGING_DIR = SPECPATH

datas = [
    (os.path.join(REPO_ROOT, "bin", "*.dll"), "bin"),
    (os.path.join(REPO_ROOT, "soundfonts", "FluidR3_GM.sf2"), "soundfonts"),
]

# music21 ships its example-score corpus as package data (~58 MB) - the app
# only ever calls converter.parse() on the user's own file, never
# music21.corpus, so it's excluded to keep the installer size down.
datas += collect_data_files(
    "music21",
    excludes=["corpus/**", "test/**", "languageExcerpts/**"],
)

# Dropped in by the user (see main.py's _app_icon_path()) - optional, the
# build works without it.
icon_path = os.path.join(PACKAGING_DIR, "icon.ico")
has_icon = os.path.exists(icon_path)
if has_icon:
    datas.append((icon_path, "."))

# Regenerated fresh by build_installer.ps1 on every run from version.py -
# not tracked in git, so it may not exist yet if this spec is run by hand.
version_file = os.path.join(PACKAGING_DIR, "version_info.txt")
has_version_file = os.path.exists(version_file)

a = Analysis(
    [os.path.join(REPO_ROOT, "main.py")],
    pathex=[REPO_ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # music21 declares matplotlib as a hard dependency for its graph/
    # audioSearch plotting modules (music21/graph/primitives.py,
    # music21/audioSearch/*.py) - this app never imports either, only
    # converter.parse()/tempo/key/meter, so excluding them (and PIL, which
    # matplotlib itself pulls in) keeps ~100+ MB of unused plotting code out
    # of the installer.
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
    name="RecallScore",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path if has_icon else None,
    version=version_file if has_version_file else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="RecallScore",
)
