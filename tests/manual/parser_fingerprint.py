# tests/manual/parser_fingerprint.py
"""The R4-style parser diff harness: a byte-for-byte fingerprint of what
every timeline builder produces, across the whole score corpus.

This is the acceptance gate for any change to parsers/ that is supposed to
be behaviour-preserving. "The tests pass" is not evidence for a parser
refactor - the suite exercises a handful of fixtures against specific
assertions, while this dumps EVERY field of EVERY EventSlice and NoteData
in the whole corpus, plus every side channel a builder publishes.

Used successfully for R4 (consolidating four measure walks into
_scan_first_part) and again for S3 (splitting the ~560-line build() into
per-element handlers) - zero differences both times.

    python tests/manual/parser_fingerprint.py before.txt      # on the old tree
    python tests/manual/parser_fingerprint.py after.txt --check before.txt

See README.md in this folder for the git-worktree baseline workflow.

Reads through MusicData rather than constructing a builder directly. That
is deliberate on two counts: MusicData stores every single thing a builder
publishes (timeline_slices, _beat_markers, tempo_changes, all the spans and
marks, total_measures) so nothing is lost, and going through the one public
entry point means this harness runs unmodified against older revisions -
which is exactly when a baseline needs capturing.
"""
import sys

from _corpus import prepare_environment, render, run

prepare_environment()

# Side channels, in a fixed order. beat_markers is stored privately because
# MusicData only splices it into the timeline while the metronome is on -
# no model-level check would ever see it, so it has to be read here.
SIDE_CHANNELS = [
    ("tempo_changes", "tempo_changes"),
    ("beat_markers", "_beat_markers"),
    ("repeat_spans", "repeat_spans"),
    ("ending_spans", "ending_spans"),
    ("hairpin_spans", "hairpin_spans"),
    ("segno_marks", "segno_marks"),
    ("coda_marks", "coda_marks"),
    ("to_coda_marks", "to_coda_marks"),
    ("fine_marks", "fine_marks"),
    ("navigation_jumps", "navigation_jumps"),
]


def dump_slice(label, index, event_slice, out):
    """One line for the slice's own fields, then one line per note.

    Deliberately not one line per slice: a chord-heavy bar renders as a
    2,000-character line, and a unified diff of those is unreadable in a
    terminal (and worse through a screen reader). Per-note lines make a
    difference point at the exact note that changed.
    """
    fields = ", ".join(
        f"{name}={render(getattr(event_slice, name))}"
        for name in ("measure", "beat_position", "quarter_length", "time_sig",
                     "key_fifths", "quarters_from_start")
    )
    out.append(f"{label}[{index}] {fields} notes={len(event_slice.notes)}")
    for n_index, note in enumerate(event_slice.notes):
        out.append(f"{label}[{index}].note[{n_index}] {render(note)}")


def dump_one(path, out):
    from models.music_data import MusicData

    md = MusicData(file_path=path)

    out.append(f"total_measures={md.total_measures}")
    out.append(f"slice_count={len(md.timeline_slices)}")
    for i, s in enumerate(md.timeline_slices):
        dump_slice("slice", i, s, out)

    for label, attribute in SIDE_CHANNELS:
        values = getattr(md, attribute, None)
        if values is None:
            out.append(f"{label}: MISSING")
            continue
        out.append(f"{label} (n={len(values)}):")
        if label == "beat_markers":
            # Markers are EventSlices too, so give them the same per-note
            # treatment rather than one long line each.
            for i, marker in enumerate(values):
                dump_slice("  beat_marker", i, marker, out)
        else:
            for v in values:
                out.append(f"  {render(v)}")


if __name__ == "__main__":
    sys.exit(run("Parser-level fingerprint of every timeline builder output", dump_one))
