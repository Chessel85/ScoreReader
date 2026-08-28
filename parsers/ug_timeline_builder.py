# parsers/ug_timeline_builder.py
"""Builds the flat, sorted EventSlice timeline for an Ultimate Guitar chord
import - the UG counterpart of TimelineBuilder (MusicXML) / MidiTimelineBuilder
/ GpTimelineBuilder. UG gives neither real bar boundaries nor a time
signature - the only structure in wiki_tab.content is chord placement
relative to lyric text and [Section] labels - so:

- Bar numbers are fabricated: one bar per chord change, always (the user's
  own steer during planning - "songs very often have just one chord per
  bar"). No per-line or strumming-grid heuristics.
- time_sig stays the EventSlice default (4, 4) on every slice - not
  inferred from the strumming grid size, to avoid unverified meter-guessing.
- Tempo is a single, whole-piece value (source.bpm when present, else the
  same 120 default MIDI/GP use) - UG's strummings block has no per-position
  tempo-change data, only one pattern for the whole tab, so there is nothing
  here that plays the role of MIDI/GP's tempo_changes list. UgReader passes
  this bpm straight to MusicData's constructor (mirroring GpReader, which
  does the same rather than building a tempo_changes entry).

Deviation from every other timeline builder, worth calling out: `source` is
effectively REQUIRED here, not an optional-with-fallback. A real MIDI/GP
file's own bytes live at file_path and can be re-parsed from there alone;
a UG import's file_path is a synthetic slug (see UgReader) with nothing
fetchable at that path - build() raises if source is None rather than
attempting a bogus re-fetch.
"""
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from music21 import harmony

from models.event_slice import EventSlice
from models.note_data import NoteData
from models.parts_structure import PartStructureInfo
from models.synthetic_parts import CHORDS_PART_ID, LYRICS_PART_ID
from models.vocabulary import spell_out_minor_chord
from parsers.ug_source import UgSource

# S2: re-exported from models/synthetic_parts.py (one definition, see
# there) - these were an independent second copy of the same literals.

_CH_TAG_RE = re.compile(r"\[ch\](.*?)\[/ch\]")
_SECTION_LINE_RE = re.compile(r"^\[([^\[\]/][^\[\]]*)\]$")


@dataclass
class _ChordEvent:
    section: str
    symbol: str
    lyric_fragment: Optional[str]


def _strip_chord_tags(chord_line: str) -> Tuple[str, List[Tuple[int, str]]]:
    """Removes [ch]/[/ch] markup from a chord line, returning the stripped
    text and (column, chord_symbol) for each chord found - the column is
    measured in the STRIPPED text, which is exactly what lines up with the
    plain-text lyric line beneath it in a real UG [tab] block (validated
    against a real page during discovery: chord/lyric column-slicing landed
    on the correct word every time)."""
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
    """Never split a lyric word across two chords' fragments. A raw
    chord-column boundary can land inside a word - confirmed against a real
    UG page during discovery, where a contributor's own column spacing
    split "warning" into "w"/"arning" across a C/B -> Am chord change. When
    that happens, give the WHOLE word to whichever side already holds the
    majority of its characters (a tie goes to the later fragment, since
    that is where the contributor's own chord marker sits closer to)."""
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


def _parse_content(content: str) -> List[_ChordEvent]:
    """Walks source.content top-to-bottom, tracking the current [Section]
    label, and emits one _ChordEvent per chord occurrence in performance
    order - inside a [tab]...[/tab] block (chord line + lyric line pair,
    lyric fragment = the slice of the lyric line from this chord's column up
    to the next chord's column) or bare (intro/instrumental/outro chord-only
    lines, which produce a chord event with no lyric fragment at all)."""
    events: List[_ChordEvent] = []
    section = ""
    raw_lines = content.replace("\r\n", "\n").split("\n")
    i = 0
    n = len(raw_lines)
    while i < n:
        line = raw_lines[i]
        stripped = line.strip()

        section_match = _SECTION_LINE_RE.match(stripped)
        if section_match and "[ch]" not in stripped:
            section = section_match.group(1).strip()
            i += 1
            continue

        if line.startswith("[tab]"):
            chord_line = line[len("[tab]"):]
            lyric_line = ""
            if chord_line.endswith("[/tab]"):
                # A single-line [tab]...[/tab] with no lyric row underneath -
                # defensive; not seen in real data, but handled rather than
                # producing a bogus fragment.
                chord_line = chord_line[: -len("[/tab]")]
            elif i + 1 < n and raw_lines[i + 1].endswith("[/tab]"):
                lyric_line = raw_lines[i + 1][: -len("[/tab]")]
                i += 1

            _stripped_chords, chord_cols = _strip_chord_tags(chord_line)
            # Boundary 0 is always the very start of the lyric line (the
            # first chord owns any lead-in text before its own column too -
            # e.g. "And" before a chord that isn't itself at column 0 -
            # rather than that text being silently dropped), and internal
            # boundaries are each snapped to a whole-word edge; only the
            # final boundary is a raw column (the true end of the line).
            boundaries = [0]
            for col, _symbol in chord_cols[1:]:
                boundaries.append(max(boundaries[-1], _snap_to_word_boundary(lyric_line, col)))
            boundaries.append(max(boundaries[-1], len(lyric_line)))

            for idx, (_col, symbol) in enumerate(chord_cols):
                fragment = lyric_line[boundaries[idx]:boundaries[idx + 1]].strip()
                events.append(_ChordEvent(section=section, symbol=symbol, lyric_fragment=fragment or None))
            i += 1
            continue

        # A bare chord-only line (intro/instrumental/outro) - no lyric row
        # exists for these chords at all.
        for _col, symbol in _strip_chord_tags(line)[1]:
            events.append(_ChordEvent(section=section, symbol=symbol, lyric_fragment=None))
        i += 1

    return events


def _chord_symbol_to_pitches(symbol: str) -> List[int]:
    """Resolves a UG chord-symbol string ("Fmaj7", "C/B", "G7"...) to a list
    of MIDI pitches via music21.harmony.ChordSymbol - already a project
    dependency (requirements.txt), confirmed during discovery to correctly
    parse every chord found in a real UG page including slash-bass chords.
    Lives here, in parsers/, not in models/ - the only other music21 use in
    this codebase (musicXML_reader.py) is likewise confined to the parser
    layer; models/gm_instruments.py states models/ is stdlib-only.

    On a parse failure (none occurred against real test data, but UG is
    user-submitted text and can contain a typo/non-standard symbol), falls
    back to the chord's root letter alone as a single pitch, so the event
    stays audible/navigable rather than silently vanishing - the same
    "absence isn't an error, degrade gracefully" pattern gp_source.py uses
    throughout."""
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
        self.total_measures: int = 0

    def build(self) -> List[EventSlice]:
        source = self._source
        if source is None:
            raise ValueError(
                "UgTimelineBuilder requires an already-parsed UgSource - "
                "unlike a real MIDI/GP file, a UG import's file_path has "
                "nothing fetchable at it to re-parse."
            )

        chord_events = _parse_content(source.content)
        if not chord_events:
            return []

        slices: List[EventSlice] = []
        for i, event in enumerate(chord_events):
            measure = i + 1  # one bar per chord change, always
            pitches = _chord_symbol_to_pitches(event.symbol)

            chord_note = NoteData(
                # event.symbol is UG's own raw [ch] markup text ("Am"),
                # unlike TimelineBuilder's MusicXML path which gets a label
                # from music21's ChordSymbol.figure - both need the same
                # bare-"m" expansion (see models/vocabulary.py).
                step_name=spell_out_minor_chord(event.symbol),
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
                # P2 (find_feature_plan.md): same label as step_name, but a
                # findable key - "Find chord symbol" works the same across
                # MusicXML <harmony>, GP diagrams and UG [ch] markup.
                chord_symbol=spell_out_minor_chord(event.symbol),
            )
            # Always present, even with no real lyric at this chord (the
            # wordless bars of an intro/instrumental/outro) - an explicit
            # "No lyrics" row rather than silently omitting the part
            # entirely, so its absence reads as "this bar has none" and not
            # as a missing/broken feature (reported: without this, a user
            # who lands on the wordless intro first has no way to tell the
            # two apart).
            lyric_note = NoteData(
                step_name=event.lyric_fragment or "No lyrics",
                octave=None,
                # Deliberately None, like a rest - keeps this part
                # genuinely silent (no midi relates to it). The slice
                # stays navigable regardless, since chord_note above
                # always carries a real midi_pitch.
                midi_pitch=None,
                measure=measure,
                beat_position=1.0,
                ts_duration=4.0,
                quarter_length=4.0,
                part_id=LYRICS_PART_ID,
                part_name="Lyrics",
                staff=1,
                voice=1,
            )
            notes = [chord_note, lyric_note]

            slices.append(
                EventSlice(
                    measure=measure,
                    beat_position=1.0,
                    quarter_length=4.0,
                    notes=notes,
                    time_sig=(4, 4),
                    key_fifths=0,
                    quarters_from_start=float(i) * 4.0,
                )
            )

        self.total_measures = len(chord_events)
        return slices
