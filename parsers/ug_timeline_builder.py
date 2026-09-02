# parsers/ug_timeline_builder.py
"""Builds the flat, sorted EventSlice timeline for an Ultimate Guitar
import - the UG counterpart of TimelineBuilder (MusicXML) / MidiTimelineBuilder
/ GpTimelineBuilder. UG gives neither real bar boundaries nor a time
signature - the only structure in wiki_tab.content is chord placement
relative to lyric text, [Section] labels and [tab]...[/tab] blocks - so:

- Bar numbers are fabricated. A chord/lyric block: one bar per chord change,
  always (the user's own steer during planning - "songs very often have just
  one chord per bar"). An ASCII-tablature block: one bar per '|' barline
  column in the source (an explicit marker), or the whole block as one bar
  when it has no interior barline.
- Rhythm is flat: a chord bar is one whole-bar event; a tab bar plays its
  struck columns in sequence as eighth notes. No inferred rhythm - matching
  the "intentionally simple, not notation-accurate" philosophy of the rest
  of this import.
- time_sig stays the EventSlice default (4, 4) on every slice.
- Tempo is a single, whole-piece value (strum_patterns[0].bpm when present,
  else the same 120 default MIDI/GP use). UgReader passes this bpm straight
  to MusicData's constructor.

Deviation from every other timeline builder, worth calling out: `source` is
effectively REQUIRED here, not an optional-with-fallback. A real MIDI/GP
file's own bytes live at file_path and can be re-parsed from there alone;
a UG import's file_path is a synthetic slug (see UgReader) with nothing
fetchable at that path - build() raises if source is None rather than
attempting a bogus re-fetch.
"""
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Union

from music21 import harmony

from models import guitar_tuning
from models.event_slice import EventSlice
from models.note_data import NoteData
from models.parts_structure import PartStructureInfo
from models.pitch_spelling import spell_pitch
from models.section_span import SectionSpan
from models.synthetic_parts import (
    CHORDS_PART_ID,
    LYRICS_PART_ID,
    TAB_PART_ID,
    TAB_PART_NAME,
)
from models.vocabulary import looks_like_chord_token, spell_out_minor_chord
from parsers.ug_source import UgSource

# S2: CHORDS_PART_ID / LYRICS_PART_ID / TAB_PART_ID are re-exported from
# models/synthetic_parts.py (one definition, see there) - these were an
# independent second copy of the same literals.

_CH_TAG_RE = re.compile(r"\[ch\](.*?)\[/ch\]")
_SECTION_LINE_RE = re.compile(r"^\[([^\[\]/][^\[\]]*)\]$")
# A line that is a fragment of ASCII guitar tablature: a leading string-name
# letter followed by a bar, or a line made up almost entirely of the
# characters tab diagrams use.
_TAB_STRING_PREFIX_RE = re.compile(r"^[A-Ga-g][#b]?\s*\|")
_TAB_LINE_CHARS = set("-|0123456789 .()/\\hpbrxX~*")

# A string row of an ASCII tab block: a note-letter label, optional
# accidental, whitespace, then '|', then the fret grid.
_TAB_ROW_RE = re.compile(r"^\s*([A-Ga-g][#b]?)\s*\|(.*)$")

# Single-character technique markers adjacent to a fret number.
_GLISSANDO_CHARS = {"/": "slide", "\\": "slide"}
_TECHNIQUE_CHARS = {"h": "hammer-on", "p": "pull-off", "b": "bend", "~": "vibrato"}


@dataclass
class _ChordEvent:
    section: str
    symbol: str
    lyric_fragment: Optional[str]


@dataclass
class _TabNote:
    string_index: int          # 0 = top row (highest string) -> NoteData.string = index + 1
    fret: int
    midi_pitch: Optional[int]   # None for a muted 'x' hit
    column: int                 # char column of the attack (grouping / ordering)
    glissando: Optional[str] = None
    technique: Optional[str] = None
    muted: bool = False


@dataclass
class _TabBar:
    section: str
    notes: List[_TabNote] = field(default_factory=list)


def is_ascii_tablature_line(line: str) -> bool:
    """True when `line` looks like a row of ASCII guitar tablature rather
    than a chord line or a lyric line."""
    s = line.replace("[tab]", "").replace("[/tab]", "").strip()
    if not s or "[ch]" in s:
        return False
    if _TAB_STRING_PREFIX_RE.match(s):
        return True
    if len(s) < 6 or "-" not in s:
        return False
    return sum(c in _TAB_LINE_CHARS for c in s) / len(s) >= 0.8


def _tab_row_label_and_body(row: str) -> Optional[Tuple[str, str]]:
    """('e', '--0--2--|...') for a string row like 'e|--0--2--|...', else
    None. The label is the note letter(+accidental) before the first '|';
    the body is everything after it."""
    m = _TAB_ROW_RE.match(row)
    if not m:
        return None
    return m.group(1), m.group(2)


def _strip_chord_tags(chord_line: str) -> Tuple[str, List[Tuple[int, str]]]:
    """Removes [ch]/[/ch] markup from a chord line, returning the stripped
    text and (column, chord_symbol) for each chord found - the column is
    measured in the STRIPPED text, which is exactly what lines up with the
    plain-text lyric line beneath it in a real UG [tab] block."""
    out: List[str] = []
    chords: List[Tuple[int, str]] = []
    last_end = 0
    for m in _CH_TAG_RE.finditer(chord_line):
        out.append(chord_line[last_end:m.start()])
        col = sum(len(s) for s in out)
        symbol = m.group(1)
        chords.append((col, symbol))
        out.append(symbol)
        last_end = m.end()
    out.append(chord_line[last_end:])
    return "".join(out), chords


def _snap_to_word_boundary(text: str, col: int) -> int:
    """Never split a lyric word across two chords' fragments. When a raw
    chord-column boundary lands inside a word, give the WHOLE word to
    whichever side already holds the majority of its characters (a tie goes
    to the later fragment)."""
    if col <= 0 or col >= len(text):
        return col
    if text[col - 1].isspace() or text[col].isspace():
        return col
    start = col
    while start > 0 and not text[start - 1].isspace():
        start -= 1
    end = col
    while end < len(text) and not text[end].isspace():
        end += 1
    before = col - start
    after = end - col
    return start if after >= before else end


def _collect_tab_block(raw_lines: List[str], start: int) -> Tuple[List[str], int]:
    """raw_lines[start] begins with '[tab]'. Returns (rows, next_index) where
    `rows` are the block's lines with the [tab]/[/tab] markers stripped and
    `next_index` is the first line after the block. A block with no closing
    [/tab] (malformed - not seen in real data) runs to end of input."""
    rows: List[str] = []
    i = start
    n = len(raw_lines)
    while i < n:
        line = raw_lines[i]
        if i == start and line.startswith("[tab]"):
            line = line[len("[tab]"):]
        closed = line.endswith("[/tab]")
        if closed:
            line = line[: -len("[/tab]")]
        rows.append(line)
        i += 1
        if closed:
            break
    return rows, i


def _emit_chord_lyric(chord_cols: List[Tuple[int, str]], lyric_line: str, section: str,
                      out: List[Union[_ChordEvent, _TabBar]]) -> None:
    """The chord/lyric column-alignment path: `(column, symbol)` pairs and
    the plain lyric line beneath them, sliced by literal character column.
    Fed by both the [ch]-marked path (via _strip_chord_tags) and the bare
    plain-text chord line (via _scan_bare_chord_columns)."""
    if not chord_cols:
        return
    # Boundary 0 is always the very start of the lyric line (the first chord
    # owns any lead-in text before its own column); internal boundaries are
    # snapped to a whole-word edge; the final boundary is the true line end.
    boundaries = [0]
    for col, _symbol in chord_cols[1:]:
        boundaries.append(max(boundaries[-1], _snap_to_word_boundary(lyric_line, col)))
    boundaries.append(max(boundaries[-1], len(lyric_line)))
    for idx, (_col, symbol) in enumerate(chord_cols):
        fragment = lyric_line[boundaries[idx]:boundaries[idx + 1]].strip()
        out.append(_ChordEvent(section=section, symbol=symbol, lyric_fragment=fragment or None))


def _consume_tab_block(rows: List[str], section: str, tuning_text: str, capo: int,
                       out: List[Union[_ChordEvent, _TabBar]]) -> None:
    """Route one [tab]...[/tab] block: a [ch]-marked chord/lyric pair goes to
    the alignment path; ASCII string rows go to _parse_tab_block."""
    nonempty = [r for r in rows if r.strip()]
    if not nonempty:
        return

    if "[ch]" in nonempty[0]:
        lyric_line = nonempty[1] if len(nonempty) > 1 else ""
        if is_ascii_tablature_line(lyric_line):
            lyric_line = ""
        _emit_chord_lyric(_strip_chord_tags(nonempty[0])[1], lyric_line, section, out)
        return

    string_rows = [r for r in rows if _tab_row_label_and_body(r) is not None]
    if len(string_rows) >= 2 or any(is_ascii_tablature_line(r) for r in nonempty):
        out.extend(_parse_tab_block(string_rows or nonempty, section, tuning_text, capo))


def _open_string_midis_for(rows: List[str], tuning_text: str) -> Tuple[List[str], List[int]]:
    """(bodies, open_string_midis) for a set of tab rows. Resolution order:
    each row's own leading label -> the page's tuning text -> standard
    tuning. `bodies` is each row's fret grid (label prefix stripped when it
    had one)."""
    labels_bodies = [_tab_row_label_and_body(r) for r in rows]
    if labels_bodies and all(lb is not None for lb in labels_bodies):
        labels = [lb[0] for lb in labels_bodies]
        bodies = [lb[1] for lb in labels_bodies]
        open_midis = guitar_tuning.open_string_midis_from_rows(labels)
    else:
        bodies = list(rows)
        open_midis = None
    if open_midis is None:
        open_midis = guitar_tuning.parse_tuning_text(tuning_text)
    if open_midis is None:
        open_midis = list(guitar_tuning.STANDARD_TUNING_HIGH_TO_LOW)

    num_rows = len(bodies)
    open_midis = list(open_midis)
    while len(open_midis) < num_rows:
        open_midis.append(open_midis[-1] - 5)  # extend downward by a fourth; defensive
    return bodies, open_midis[:num_rows]


def _parse_tab_block(rows: List[str], section: str, tuning_text: str, capo: int) -> List[_TabBar]:
    """One ASCII-tablature [tab] block -> one or more fabricated bars, split
    on '|' barline columns."""
    bodies, open_midis = _open_string_midis_for(rows, tuning_text)
    num_rows = len(bodies)
    if num_rows == 0:
        return []

    width = max((len(b) for b in bodies), default=0)
    bodies = [b.ljust(width) for b in bodies]
    barline_threshold = max(1, (num_rows + 1) // 2)

    bars: List[_TabBar] = [_TabBar(section=section)]
    col = 0
    while col < width:
        column_chars = [b[col] for b in bodies]

        if sum(1 for c in column_chars if c == "|") >= barline_threshold:
            if bars[-1].notes:
                bars.append(_TabBar(section=section))
            col += 1
            continue

        attack_rows = [r for r, c in enumerate(column_chars) if c.isdigit() or c in ("x", "X")]
        if not attack_rows:
            col += 1
            continue

        run_end = col + 1
        for r in attack_rows:
            c0 = bodies[r][col]
            if c0 in ("x", "X"):
                bars[-1].notes.append(_TabNote(
                    string_index=r, fret=0, midi_pitch=None, column=col, muted=True,
                ))
                continue
            j = col
            digits = ""
            while j < width and bodies[r][j].isdigit():
                digits += bodies[r][j]
                j += 1
            run_end = max(run_end, j)
            fret = int(digits)
            before = bodies[r][col - 1] if col > 0 else " "
            after = bodies[r][j] if j < width else " "
            gliss = tech = None
            for ch in (before, after):
                if ch in _GLISSANDO_CHARS:
                    gliss = _GLISSANDO_CHARS[ch]
                elif ch in _TECHNIQUE_CHARS:
                    tech = _TECHNIQUE_CHARS[ch]
            bars[-1].notes.append(_TabNote(
                string_index=r,
                fret=fret,
                midi_pitch=guitar_tuning.midi_for(open_midis[r], fret, capo),
                column=col,
                glissando=gliss,
                technique=tech,
            ))
        col = run_end

    for bar in bars:
        bar.notes.sort(key=lambda nt: (nt.column, nt.string_index))
    return [b for b in bars if b.notes]


def _strip_tab_markers(line: str) -> str:
    return line.replace("[tab]", "").replace("[/tab]", "")


def _is_tab_row_line(line: str) -> bool:
    """True when `line` (with any [tab]/[/tab] markers removed) is one row of
    an ASCII-tablature system - a labelled string row ('e|--0--') or a bare
    fret-grid line."""
    s = _strip_tab_markers(line)
    return _tab_row_label_and_body(s.strip()) is not None or is_ascii_tablature_line(s)


def _scan_bare_chord_columns(line: str) -> List[Tuple[int, str]]:
    """(start_column, token) for each whitespace-separated run of a bare
    plain-text chord line. The column is measured in the raw line, which is
    exactly what lines up with the lyric line beneath it. Returns [] when
    there are no runs, or when ANY run fails looks_like_chord_token (one
    ordinary word is enough to disqualify the whole line)."""
    cols: List[Tuple[int, str]] = []
    for m in re.finditer(r"\S+", line):
        if not looks_like_chord_token(m.group(0)):
            return []
        cols.append((m.start(), m.group(0)))
    return cols


def _looks_like_chord_line(line: str) -> bool:
    """A bare chord line: every run is a chord token, at most 8 of them, and
    either a single token or a >=2-space gap somewhere (the wide spacing a
    chord-over-lyric layout always has - guards against a short all-caps
    lyric line being read as chords). Never a [Section] label."""
    if _SECTION_LINE_RE.match(line.strip()):
        return False
    cols = _scan_bare_chord_columns(line)
    if not cols or len(cols) > 8:
        return False
    if len(cols) == 1:
        return True
    return bool(re.search(r"\S {2,}\S", line))


def _looks_like_lyric_line(line: str) -> bool:
    """Any non-blank text that isn't a chord line, a section label or a
    tab-ish line, and doesn't start with a tab/diagram lead character."""
    s = line.strip()
    if not s or s[0] in "|*[":
        return False
    if _SECTION_LINE_RE.match(s):
        return False
    if _looks_like_chord_line(line):
        return False
    return not _is_tab_row_line(line)


def _tab_block_label(header_line: str, ordinal: int) -> str:
    """A navigable label for a section-less [tab] fingerpicking block: the
    chord names in its own header line joined with an arrow
    ("Picking: D -> F#m") when it has them, else "Intro" for the first such
    block and "Picking pattern N" after."""
    cols = _scan_bare_chord_columns(header_line)
    if cols:
        return "Picking: " + " → ".join(sym for _c, sym in cols)
    return "Intro" if ordinal == 1 else f"Picking pattern {ordinal}"


def _parse_content(content: str, tuning_text: str = "", capo: int = 0
                   ) -> List[Union[_ChordEvent, _TabBar]]:
    """Walks source.content top-to-bottom, tracking the current [Section]
    label, and returns an ordered, interleaved list of chord events and
    fabricated tablature bars in performance order."""
    out: List[Union[_ChordEvent, _TabBar]] = []
    section = ""
    tab_ordinal = 0
    raw_lines = content.replace("\r\n", "\n").split("\n")
    i = 0
    n = len(raw_lines)

    def _emit_tab_bars(rows: List[str], header_line: str) -> None:
        """Parse `rows` into fabricated bars and append them. Inside a
        [Section] the bars carry it; outside one (the fingerpicking
        library, P2) they carry a generated label - numbered only across
        blocks that actually produce bars, so the first real one is
        "Intro"."""
        nonlocal tab_ordinal
        bars = _parse_tab_block(rows, section, tuning_text, capo)
        if bars and not section:
            tab_ordinal += 1
            label = _tab_block_label(header_line, tab_ordinal)
            for bar in bars:
                bar.section = label
        out.extend(bars)

    while i < n:
        line = raw_lines[i]
        stripped = line.strip()

        section_match = _SECTION_LINE_RE.match(stripped)
        if section_match and "[ch]" not in stripped:
            section = section_match.group(1).strip()
            i += 1
            continue

        # Classic chords-page shape: a [ch]-marked chord line (+ optional
        # lyric line) wrapped in one [tab]...[/tab].
        if line.startswith("[tab]") and "[ch]" in _strip_tab_markers(line):
            rows, i = _collect_tab_block(raw_lines, i)
            _consume_tab_block(rows, section, tuning_text, capo, out)
            continue

        # An ASCII-tablature system: a maximal run of consecutive string /
        # fret-grid rows. UG wraps these inconsistently - the whole system
        # in one [tab]...[/tab], each string row in its own, or no markers
        # at all - so the run is collected across all of those and the
        # markers simply stripped. A blank line ends the system.
        if _is_tab_row_line(line):
            rows: List[str] = []
            while i < n and raw_lines[i].strip() and _is_tab_row_line(raw_lines[i]):
                rows.append(_strip_tab_markers(raw_lines[i]))
                i += 1
            labelled = [r for r in rows if _tab_row_label_and_body(r.strip()) is not None]
            _emit_tab_bars(labelled or rows, "")
            continue

        # Any other [tab] block. UG very often opens a tablature system with
        # a non-tab header line naming the chords played over it
        # ("        D              F#m"), so the block's real string rows sit
        # under a line that is neither [ch] markup nor a fret grid - collect
        # the whole block and parse whatever string rows it holds. Ignore it
        # only when there are none.
        if line.startswith("[tab]"):
            rows, i = _collect_tab_block(raw_lines, i)
            labelled = [r for r in rows if _tab_row_label_and_body(r.strip()) is not None]
            tab_rows: Optional[List[str]] = None
            if len(labelled) >= 2:
                tab_rows = labelled
            elif any(is_ascii_tablature_line(r) for r in rows):
                tab_rows = rows
            if tab_rows is not None:
                header = next(
                    (r for r in rows if r.strip()
                     and _tab_row_label_and_body(r.strip()) is None
                     and not is_ascii_tablature_line(r)),
                    "",
                )
                _emit_tab_bars(tab_rows, header)
            continue

        # P2: a bare plain-text chord line (no [ch] markup) over its lyric
        # line - the body of a UG "Tab" song sheet. Gated on being inside a
        # [Section]: the pre-verse prose paragraph and the trailing
        # chord-shape legend both sit outside one, and neither should
        # produce events.
        if section != "":
            if _looks_like_chord_line(line):
                j = i + 1
                while j < n and not raw_lines[j].strip():
                    j += 1
                lyric_line = ""
                if (j < n and _looks_like_lyric_line(raw_lines[j])
                        and not _looks_like_chord_line(raw_lines[j])):
                    lyric_line = raw_lines[j]
                    i = j
                _emit_chord_lyric(_scan_bare_chord_columns(line), lyric_line, section, out)
                i += 1
                continue
            if _looks_like_lyric_line(line):
                out.append(_ChordEvent(section=section, symbol="", lyric_fragment=stripped))
                i += 1
                continue

        # A bare chord-only line (intro/instrumental/outro) - no lyric row.
        for _col, symbol in _strip_chord_tags(line)[1]:
            out.append(_ChordEvent(section=section, symbol=symbol, lyric_fragment=None))
        i += 1

    return out


def count_tablature_blocks(content: str) -> int:
    """How many fabricated bars the ASCII-tablature [tab] blocks in `content`
    produce - for the Region 1 "Tablature: N bars imported" credit. (Was
    "N blocks not imported"; ASCII tab is now imported as a Tablature part.)"""
    return sum(1 for seg in _parse_content(content) if isinstance(seg, _TabBar))


def content_part_summary(content: str) -> Tuple[bool, bool]:
    """(has_chord_or_lyric_content, has_tablature_content) for `content` -
    lets UgReader build parts_info for only the parts the import produces."""
    segs = _parse_content(content)
    return (
        any(isinstance(s, _ChordEvent) for s in segs),
        any(isinstance(s, _TabBar) for s in segs),
    )


def _chord_symbol_to_pitches(symbol: str) -> List[int]:
    """Resolves a UG chord-symbol string ("Fmaj7", "C/B", "G7"...) to a list
    of MIDI pitches via music21.harmony.ChordSymbol. On a parse failure
    (UG is user-submitted text and can contain a typo), falls back to the
    chord's root letter alone, so the event stays audible/navigable."""
    try:
        pitches = [p.midi for p in harmony.ChordSymbol(symbol).pitches]
        if pitches:
            return pitches
    except Exception:
        pass
    root_match = re.match(r"[A-Ga-g][#b]?", symbol)
    if root_match:
        try:
            return [p.midi for p in harmony.ChordSymbol(root_match.group(0)).pitches]
        except Exception:
            pass
    return [60]  # middle C - last-resort fallback so the event still sounds


class UgTimelineBuilder:
    def __init__(
        self,
        file_path: str,
        parts_info: List[PartStructureInfo],
        source: Optional[UgSource] = None,
    ):
        self.file_path = file_path
        self.parts_info = parts_info
        self._source = source

        self.tempo_changes: List = []
        self.beat_markers: List[EventSlice] = []
        self.repeat_spans: List = []
        self.ending_spans: List = []
        self.hairpin_spans: List = []
        # P3: MusicXML-only, like the span lists above.
        self.direction_spans: List = []
        self.direction_marks: List = []
        # P4: MusicXML-only (bar-style / mid-part clef / measure-style).
        self.barline_marks: List = []
        self.clef_change_marks: List = []
        self.measure_style_marks: List = []
        self.segno_marks: List = []
        self.coda_marks: List = []
        self.to_coda_marks: List = []
        self.fine_marks: List = []
        self.navigation_jumps: List = []
        # P2: [Intro]/[Verse 1]/[Chorus]/... labels, as spans of the
        # fabricated bars.
        self.section_spans: List[SectionSpan] = []
        self.total_measures: int = 0

    def build(self) -> List[EventSlice]:
        source = self._source
        if source is None:
            raise ValueError(
                "UgTimelineBuilder requires an already-parsed UgSource - "
                "unlike a real MIDI/GP file, a UG import's file_path has "
                "nothing fetchable at it to re-parse."
            )

        segments = _parse_content(source.content, source.tuning, source.capo or 0)
        if not segments:
            return []

        slices: List[EventSlice] = []
        measure = 0
        quarters = 0.0
        measure_sections: List[str] = []

        for seg in segments:
            measure += 1
            measure_sections.append(seg.section)
            if isinstance(seg, _ChordEvent):
                slices.append(self._chord_slice(seg, measure, quarters))
            else:
                slices.extend(self._tab_slices(seg, measure, quarters))
            quarters += 4.0  # uniform bar advance, chord bar or tab bar alike

        self.total_measures = measure
        self.section_spans = _section_spans(measure_sections, self.total_measures)
        return slices

    def _chord_slice(self, event: _ChordEvent, measure: int, quarters: float) -> EventSlice:
        notes: List[NoteData] = []
        # P2: a lyrics-only bar (plain-text lyric line with no chord above
        # it) carries symbol == "" - emit only the Lyrics note, no Chords
        # note. A real song always has at least one real chord, so the
        # Chords part is never empty overall.
        if event.symbol:
            pitches = _chord_symbol_to_pitches(event.symbol)
            label = spell_out_minor_chord(event.symbol)
            notes.append(NoteData(
                step_name=label,
                octave=None,
                midi_pitch=max(pitches),
                measure=measure,
                beat_position=1.0,
                ts_duration=4.0,
                quarter_length=4.0,
                part_id=CHORDS_PART_ID,
                part_name="Chords",
                staff=1,
                voice=1,
                chord_pitches=pitches,
                # P2: same text as step_name, but a findable key.
                chord_symbol=label,
            ))
        notes.append(NoteData(
            step_name=event.lyric_fragment or "No lyrics",
            octave=None,
            midi_pitch=None,  # deliberately silent, like a rest
            measure=measure,
            beat_position=1.0,
            ts_duration=4.0,
            quarter_length=4.0,
            part_id=LYRICS_PART_ID,
            part_name="Lyrics",
            staff=1,
            voice=1,
        ))
        return EventSlice(
            measure=measure,
            beat_position=1.0,
            quarter_length=4.0,
            notes=notes,
            time_sig=(4, 4),
            key_fifths=0,
            quarters_from_start=quarters,
        )

    def _tab_slices(self, bar: _TabBar, measure: int, quarters: float) -> List[EventSlice]:
        columns = sorted({nt.column for nt in bar.notes})
        slices: List[EventSlice] = []
        for k, colv in enumerate(columns):
            beat_pos = 1.0 + k * 0.5  # flat eighth-note grid
            notes: List[NoteData] = []
            for nt in sorted((n for n in bar.notes if n.column == colv),
                             key=lambda n: n.string_index):
                if nt.midi_pitch is None:
                    step, octave = "muted", None
                else:
                    step, octave = spell_pitch(nt.midi_pitch, 0)
                notes.append(NoteData(
                    step_name=step,
                    octave=octave,
                    midi_pitch=nt.midi_pitch,
                    measure=measure,
                    beat_position=beat_pos,
                    ts_duration=0.5,
                    quarter_length=0.5,
                    part_id=TAB_PART_ID,
                    part_name=TAB_PART_NAME,
                    staff=1,
                    voice=1,
                    string=nt.string_index + 1,
                    fret=nt.fret if nt.midi_pitch is not None else None,
                    glissando=nt.glissando,
                    technique=nt.technique,
                    articulation="muted" if nt.muted else None,
                    duration_name_us="eighth",
                ))
            slices.append(EventSlice(
                measure=measure,
                beat_position=beat_pos,
                quarter_length=0.5,
                notes=notes,
                time_sig=(4, 4),
                key_fifths=0,
                quarters_from_start=quarters + k * 0.5,
            ))
        return slices


def _section_spans(measure_sections: List[str], total_measures: int) -> List[SectionSpan]:
    """One SectionSpan per run of consecutive bars sharing a [Section] label.
    end_measure is the bar before the next section starts (or total_measures
    for the last). Bars before the first [Section] label carry "" and are
    not given a span."""
    spans: List[SectionSpan] = []
    current: Optional[str] = None
    for idx, label in enumerate(measure_sections):
        measure = idx + 1
        if not label:
            continue
        if current is not None and label == current:
            continue
        if spans:
            spans[-1].end_measure = measure - 1
        spans.append(SectionSpan(label=label, start_measure=measure, end_measure=measure))
        current = label
    if spans:
        spans[-1].end_measure = max(spans[-1].start_measure, total_measures)
    return spans
