# version.py
# Year.Release.Build (D-13, revised 2026-08-11 from the old Major.Minor.Patch
# scheme - see the About dialog, C8, and tasks.txt D-13).
#   Year:    calendar year, bumped by the user roughly annually.
#   Release: a release counter the user owns and bumps when they say so
#            (carries over "minor"'s old semantics).
#   Build:   bumped by whoever commits+pushes, on every push - never reset
#            when Year or Release changes (carries over "patch"'s old
#            semantics). Nothing in the codebase automates this; it's a
#            manual step to remember when asked to commit and push.
__version__ = "2026.1.12"
