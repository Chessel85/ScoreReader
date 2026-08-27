# tests/manual/_corpus.py
"""Shared plumbing for the refactor-verification harnesses in this folder.

Not a pytest module (no `test_` prefix, so `testpaths = tests` never
collects it) and deliberately not imported by anything in the app.
"""
import argparse
import difflib
import os
import sys
from dataclasses import fields, is_dataclass

# Every directory holding real score files: developer/test fixtures,
# the bundled end-user examples, and the hand-authored parser fixtures.
SCORE_DIRS = ["files", "examples", "tests/fixtures"]
EXTS = (".xml", ".musicxml", ".mxl", ".mid", ".midi", ".gp")


def repo_root() -> str:
    """This file is tests/manual/_corpus.py, so the root is two levels up.
    Resolved from __file__ rather than the cwd so the harness can be run
    from anywhere - including from inside a throwaway git worktree, which
    is how a baseline gets captured (see README.md)."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def prepare_environment() -> None:
    """Import the app the same way the app does, without opening a window.

    Mirrors tests/conftest.py's own QT_QPA_PLATFORM guard: it must be set
    BEFORE PySide6 is first imported, and these harnesses import widgets
    indirectly via MusicData's controllers.
    """
    root = repo_root()
    os.chdir(root)
    sys.path.insert(0, root)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def score_files():
    """Every score file in the corpus, in a stable order."""
    found = []
    for root_dir in SCORE_DIRS:
        for dirpath, _dirnames, filenames in os.walk(root_dir):
            for name in sorted(filenames):
                if name.lower().endswith(EXTS):
                    found.append(os.path.join(dirpath, name).replace("\\", "/"))
    return sorted(found)


def render(value) -> str:
    """Stable, exhaustive text for any parser/model output.

    Dataclasses are expanded field by field and sorted BY NAME, so merely
    reordering a dataclass's fields during a refactor doesn't show up as a
    behaviour change. Floats are rounded to 9dp so a difference in
    formatting alone can't masquerade as one in value.
    """
    if is_dataclass(value) and not isinstance(value, type):
        inner = ", ".join(
            f"{f.name}={render(getattr(value, f.name))}"
            for f in sorted(fields(value), key=lambda f: f.name)
        )
        return f"{type(value).__name__}({inner})"
    if isinstance(value, list):
        return "[" + ", ".join(render(v) for v in value) + "]"
    if isinstance(value, tuple):
        return "(" + ", ".join(render(v) for v in value) + ")"
    if isinstance(value, dict):
        items = sorted(value.items(), key=lambda kv: repr(kv[0]))
        return "{" + ", ".join(f"{render(k)}: {render(v)}" for k, v in items) + "}"
    if isinstance(value, float):
        return repr(round(value, 9))
    return repr(value)


def run(description: str, dump_one):
    """Argument handling, the corpus walk, and capture-or-compare.

    `dump_one(path, out)` appends this file's fingerprint lines to `out`.
    Exceptions are recorded in the output rather than raised, so one broken
    fixture can't hide differences in the other 55 files - and so a file
    that fails identically before and after still compares equal.
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("output", help="file to write the fingerprint to")
    parser.add_argument(
        "--check",
        metavar="BASELINE",
        help="also diff the fresh fingerprint against BASELINE and exit "
             "non-zero on any difference",
    )
    args = parser.parse_args()

    out = []
    files = score_files()
    for path in files:
        out.append(f"===== {path}")
        try:
            dump_one(path, out)
        except Exception as e:
            out.append(f"FAILED: {type(e).__name__}: {e}")

    text = "\n".join(out) + "\n"
    with open(args.output, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

    failures = sum(1 for line in out if line.startswith("FAILED:"))
    print(f"{len(files)} files, {len(out)} lines, {failures} failed -> {args.output}")

    if not args.check:
        return 0

    with open(args.check, encoding="utf-8", newline="") as f:
        baseline = f.read()
    if baseline == text:
        print(f"MATCH: identical to {args.check}")
        return 0
    diff = list(difflib.unified_diff(
        baseline.splitlines(), text.splitlines(),
        fromfile=args.check, tofile=args.output, lineterm="", n=1,
    ))
    safe_print(f"DIFFERENCES: {len(diff)} diff lines against {args.check}")
    for line in diff[:80]:
        safe_print(line)
    if len(diff) > 80:
        safe_print(f"... {len(diff) - 80} more diff lines")
    return 1


def safe_print(line: str) -> None:
    """Print a line that may contain any character a score file does.

    Real fixtures carry non-ASCII part names (files/bach-bourree-tab.mxl's
    Korean instrument name - the very file R5's "0 notes" bug was found
    with), and a Windows console defaulting to cp1252 raises
    UnicodeEncodeError on them. A diff report that crashes halfway through
    is worse than one with a few substituted characters, and the written
    output file is UTF-8 and complete regardless.
    """
    encoding = getattr(sys.stdout, "encoding", None) or "ascii"
    print(line.encode(encoding, errors="replace").decode(encoding, errors="replace"))
