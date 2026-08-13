# version.py
# Reads the app version from version.txt (repo root), which the user
# maintains by hand - see the "Packaging" section of CLAUDE.md. This is the
# single source of truth for both the About dialog (widgets/about_dialog.py)
# and the installer build (packaging/RecallScore.spec, packaging/installer.nsi).
#
# version.txt is bundled into the frozen app by RecallScore.spec, so this
# resolves next to version.py in dev and at the frozen bundle root
# (sys._MEIPASS) once packaged - same idiom as main.py's _app_icon_path().
import os
import sys

_base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(_base_dir, "version.txt"), "r", encoding="utf-8") as _f:
    __version__ = _f.read().strip()
