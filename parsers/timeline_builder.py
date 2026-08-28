# parsers/timeline_builder.py
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from music21 import harmony as harmony21

from models.duration_units import (
    beat_unit_display_name,
    beat_unit_quarter_length,
    quarter_length_to_display_name,
    tuplet_word,
)
from models.coda_mark import CodaMark
from models.direction_mark import DirectionMark
from models.direction_span import DirectionSpan
from models.ending_span import EndingSpan
from models.event_slice import EventSlice
from models.fine_mark import FineMark
from models.hairpin_span import HairpinSpan
from models.navigation_jump import NavigationJump
from models.note_data import GraceNote, NoteData
from models.synthetic_parts import (
    CHORDS_PART_ID,
    CHORDS_PART_NAME,
    LYRICS_PART_ID,
    LYRICS_PART_NAME,
    STAVE_TEXT_VOICE_ID,
)
from models.parts_structure import PartStructureInfo
from models.repeat_span import RepeatSpan
from models.segno_mark import SegnoMark
from models.tempo_change import TempoChange
from models.to_coda_mark import ToCodaMark
from models.vocabulary import articulation_name, dynamic_name, spell_out_minor_chord
from parsers.xml_source import read_musicxml_root

# Synthetic parts a real MusicXML file can carry alongside its notated
# instruments, mirroring parsers/ug_timeline_builder.py's Chords/Lyrics
# concept but sourced from the file's own <harmony>/<lyric> elements rather
# than fabricated bar boundaries - the notated part already gives real
# measure/beat positions, so these are just extra NoteData entries bucketed
# into the SAME slices as the real notes, not a separate timeline. Shared by
# MusicXMLReader (parts_info entries, so Region 2/mixer/channel assignment
# see them) and TimelineBuilder (the notes themselves) via one constant each,
# so the two can't disagree on a name the way R5's two independent reads did.
# S2: re-exported from models/synthetic_parts.py (one definition, see there).

# Generic "stave text" support: any free-text <direction><direction-type>
# <words> a real part carries (guitar left-hand position roman numerals,
# tempo/technique words an exporter wrote as plain text instead of semantic
# markup - "Allegro", "Staccato", "Pizz.", all confirmed in real fixtures)
# becomes its own event, distinct from the notes around it - deliberately
# NOT sticky/carried forward to later notes (the user's own call: inferring
# how long a marking "lasts" would invent information the score doesn't
# state). Unlike Chords/Lyrics above, this is NOT a new top-level part -
# each occurrence attaches to whichever REAL part/staff its <direction>
# element is physically inside, via a fabricated voice id on that part -
# the same "fabricate a voice_id, reuse the existing tree" trick
# parsers/gp_timeline_builder.py's GP_CHORD_VOICE_ID already established for
# GP's synthetic Chords voice. This is what makes a guitar-duet's two
# independent fret-position tracks (or a flute+guitar duet's guitar-only
# fret text) fall out for free with zero cross-part guessing: each part's
# own <direction> elements can only ever produce a voice on that same part.
# S2: re-exported from models/synthetic_parts.py (one definition, see there).

# SMuFL Private Use Area (U+E000-U+F8FF): a <words> element can hold music-
# font glyph codepoints instead of readable text - confirmed in a real file
# (files/etude 1 tablature.mxl, font-family="Leland Text") where 12 such
# elements are MuseScore's own redundant *visual* rendering of right-hand
# pluck-fingering marks already captured properly via
# <notations><technical><pluck>/NoteData.pluck. Left in, these would read as
# garbage to a screen reader, so any <words> text that is ENTIRELY such
# glyphs (after stripping whitespace) is not qualifying stave text.
_SMUFL_PUA_RE = re.compile("[-]")


def _is_pure_smufl_glyph_text(text: str) -> bool:
    return _SMUFL_PUA_RE.sub("", text).strip() == ""


def _is_qualifying_stave_text(text: Optional[str]) -> bool:
    """Whether a <words> element's text should become a Stave Text event.

    Excludes only two things, both grounded in real fixture content: bare
    SMuFL glyph "text" (see _is_pure_smufl_glyph_text) and text that already
    matches the existing D.C./D.S./Fine/Coda/To-Coda jump-mark vocabulary
    (TimelineBuilder._is_jump_mark_words) - that text already drives real
    playback-jump behaviour and a Performance Report line elsewhere, so
    surfacing the identical printed mark a second time as an inert Stave
    Text event would just be confusing duplicate information. Everything
    else - tempo words, technique words, position marks, anything a sighted
    reader would see printed on the score - qualifies, deliberately generic
    rather than guitar/position-specific.
    """
    if not text:
        return False
    stripped = text.strip()
    if not stripped:
        return False
    if _is_pure_smufl_glyph_text(text):
        return False
    if TimelineBuilder._is_jump_mark_words(stripped):
        return False
    return True


def _stave_text_staves_for_part(part_elem: ET.Element) -> Set[int]:
    """Which staff numbers within this one real <part> carry at least one
    qualifying stave-text <words> mark. Used by MusicXMLReader to decide
    which (part, staff) pairs need a fabricated Stave Text voice added to
    PartStructureInfo; TimelineBuilder.build() independently re-applies the
    identical _is_qualifying_stave_text filter while walking notes, so the
    two can't disagree on which text counts (the same shared-detector
    convention has_harmony_elements/has_lyric_elements already use).
    """
    staves: Set[int] = set()
    for direction_elem in part_elem.findall(".//direction"):
        for words_el in direction_elem.findall("direction-type/words"):
            if not _is_qualifying_stave_text(words_el.text):
                continue
            staff_el = direction_elem.find("staff")
            staff = int(staff_el.text.strip()) if (staff_el is not None and staff_el.text) else 1
            staves.add(staff)
    return staves


def has_harmony_elements(root: Optional[ET.Element]) -> bool:
    """Whether this MusicXML document carries any <harmony> (chord symbol)
    markup at all - the single check both MusicXMLReader (whether to add a
    Chords entry to parts_info) and TimelineBuilder (whether to build any
    Chords notes) must agree on."""
    return root is not None and root.find(".//harmony") is not None


def has_lyric_elements(root: Optional[ET.Element]) -> bool:
    """Whether this MusicXML document carries any <lyric> markup at all -
    the Lyrics-part counterpart of has_harmony_elements above."""
    return root is not None and root.find(".//note/lyric") is not None


def _percussion_instrument_map(root: Optional[ET.Element]) -> Dict[str, Tuple[str, Optional[int]]]:
    """Wishlist #8: <score-instrument id> -> (spoken name, GM percussion
    note number), read once from <part-list> for every score-part. An
    <unpitched> note's own <instrument id> ref resolves through this map
    rather than its <display-step>/<display-octave> (staff position only,
    not a real pitch/sound - see Hit It.mxl). The note number comes from
    the SAME id's <midi-instrument><midi-unpitched> sibling, never guessed
    from the id string itself (nothing in the MusicXML spec ties them
    together, even though a real MuseScore export usually does).
    """
    instrument_map: Dict[str, Tuple[str, Optional[int]]] = {}
    if root is None:
        return instrument_map
    for score_part in root.findall(".//part-list/score-part"):
        midi_keys: Dict[str, int] = {}
        for midi_instr in score_part.findall("midi-instrument"):
            instr_id = midi_instr.attrib.get("id")
            unpitched_elem = midi_instr.find("midi-unpitched")
            if instr_id and unpitched_elem is not None and unpitched_elem.text:
                midi_keys[instr_id] = int(unpitched_elem.text.strip())
        for score_instr in score_part.findall("score-instrument"):
            instr_id = score_instr.attrib.get("id")
            if not instr_id:
                continue
            name_elem = score_instr.find("instrument-name")
            name = name_elem.text.strip() if name_elem is not None and name_elem.text else instr_id
            instrument_map[instr_id] = (name, midi_keys.get(instr_id))
    return instrument_map


def _pitch_name(step: str, alter_elem: Optional[ET.Element]) -> str:
    """MusicXML <root-step>/<root-alter> (or <bass-step>/<bass-alter>) as a
    music21 pitch name string ("F#", "B--") - music21's harmony.ChordSymbol
    accepts both `root=`/`bass=` and `kind=` using MusicXML's own vocabulary
    directly, so no separate kind->suffix mapping is needed here."""
    alter = int(float(alter_elem.text.strip())) if (alter_elem is not None and alter_elem.text) else 0
    accidental = {1: "#", -1: "-", 2: "##", -2: "--"}.get(alter, "")
    return f"{step}{accidental}"


def _resolve_harmony(harmony_elem) -> Tuple[List[int], str]:
    """A <harmony> element's MIDI pitches and display label ("Am", "G7",
    "F/C"), via music21.harmony.ChordSymbol - already a project dependency,
    first used this way by parsers/ug_timeline_builder.py's UG chord-symbol
    parsing. Falls back to a bare root triad, then to the root name alone
    with no real pitches, mirroring ug_timeline_builder's
    _chord_symbol_to_pitches "absence isn't an error, degrade gracefully"
    pattern - a malformed <kind> shouldn't make the whole bar's chord vanish.
    """
    root_elem = harmony_elem.find("root")
    if root_elem is None:
        return [], ""
    step_elem = root_elem.find("root-step")
    if step_elem is None or not step_elem.text:
        return [], ""
    root_name = _pitch_name(step_elem.text.strip(), root_elem.find("root-alter"))

    kind_elem = harmony_elem.find("kind")
    kind = kind_elem.text.strip() if (kind_elem is not None and kind_elem.text) else "major"

    bass_name = None
    bass_elem = harmony_elem.find("bass")
    if bass_elem is not None:
        bass_step_elem = bass_elem.find("bass-step")
        if bass_step_elem is not None and bass_step_elem.text:
            bass_name = _pitch_name(bass_step_elem.text.strip(), bass_elem.find("bass-alter"))

    try:
        kwargs = {"root": root_name, "kind": kind}
        if bass_name:
            kwargs["bass"] = bass_name
        cs = harmony21.ChordSymbol(**kwargs)
        pitches = [p.midi for p in cs.pitches]
        if pitches:
            return pitches, spell_out_minor_chord(cs.figure)
    except Exception:
        pass

    try:
        cs = harmony21.ChordSymbol(root=root_name)
        pitches = [p.midi for p in cs.pitches]
        if pitches:
            return pitches, spell_out_minor_chord(cs.figure)
    except Exception:
        pass

    return [], root_name


def _resolve_chord_diagram(harmony_elem) -> Optional[str]:
    """A spoken summary of a <harmony>'s <frame> chord diagram (P2,
    find_feature_plan.md A12), or None when there is no <frame>. Reads the
    <frame-note> fret per string from the highest string number down to 1
    (string 6 -> 1 on a guitar): "frets 3 2 0 0 0 1", with "x" for a muted
    string (fret -1, or a string with no <frame-note> at all). Appends
    "barre at fret N" when any <frame-note> carries a <barre>, and
    "from fret N" when <first-fret> is greater than 1."""
    frame_elem = harmony_elem.find("frame")
    if frame_elem is None:
        return None

    strings_elem = frame_elem.find("frame-strings")
    try:
        num_strings = int(strings_elem.text.strip()) if (strings_elem is not None and strings_elem.text) else 6
    except ValueError:
        num_strings = 6

    fret_by_string: Dict[int, str] = {}
    barre_fret: Optional[int] = None
    for fn in frame_elem.findall("frame-note"):
        s_el = fn.find("string")
        f_el = fn.find("fret")
        if s_el is None or not s_el.text or f_el is None or not f_el.text:
            continue
        try:
            s_num = int(s_el.text.strip())
            f_num = int(f_el.text.strip())
        except ValueError:
            continue
        fret_by_string[s_num] = "x" if f_num < 0 else str(f_num)
        if fn.find("barre") is not None:
            barre_fret = f_num

    frets = [fret_by_string.get(s, "x") for s in range(num_strings, 0, -1)]
    parts = [f"frets {' '.join(frets)}"]
    if barre_fret is not None and barre_fret > 0:
        parts.append(f"barre at fret {barre_fret}")

    first_fret_elem = frame_elem.find("first-fret")
    if first_fret_elem is not None:
        ff_text = first_fret_elem.find("fret")
        raw = ff_text.text if (ff_text is not None and ff_text.text) else first_fret_elem.text
        try:
            first_fret = int(raw.strip()) if raw else 1
        except (ValueError, AttributeError):
            first_fret = 1
        if first_fret > 1:
            parts.append(f"from fret {first_fret}")

    return ", ".join(parts)


def _duration_divs(elem) -> int:
    dur_el = elem.find("duration")
    return int(dur_el.text.strip()) if (dur_el is not None and dur_el.text) else 0


def _raw_measure_number(measure_elem) -> int:
    """The <measure number="..."> attribute as an int, defaulting to 1 for a
    missing or non-numeric one (MusicXML permits things like "X1" for an
    editorially-added bar)."""
    try:
        return int(measure_elem.attrib.get("number", "1"))
    except ValueError:
        return 1


def _measure_number(measure_elem, needs_reindex: bool) -> int:
    """The measure number this app uses: the raw one, shifted down by one
    when a pickup bar has to become measure 0 (Ref 17). Every pass over the
    document must go through here, so the pickup convention is defined
    once."""
    return _raw_measure_number(measure_elem) - 1 if needs_reindex else _raw_measure_number(measure_elem)


def _apply_attributes(
    attrs_elem, divisions: int, ts_num: int, ts_den: int, fifths: int
) -> Tuple[int, int, int, int]:
    """Ref 18: divisions/time signature can change mid-score, so this is
    called every time an <attributes> element is encountered walking in
    document order, not just once for the whole file. Key signature
    (fifths) is tracked the same way (C6/D-11) for the status bar."""
    div_elem = attrs_elem.find("divisions")
    if div_elem is not None and div_elem.text:
        divisions = int(div_elem.text.strip())

    time_elem = attrs_elem.find("time")
    if time_elem is not None:
        b = time_elem.find("beats")
        bt = time_elem.find("beat-type")
        if b is not None and b.text:
            ts_num = int(b.text.strip())
        if bt is not None and bt.text:
            ts_den = int(bt.text.strip())

    fifths_elem = attrs_elem.find("key/fifths")
    if fifths_elem is not None and fifths_elem.text:
        fifths = int(fifths_elem.text.strip())

    return divisions, ts_num, ts_den, fifths


class _MeasureOffsetWalker:
    """Tracks the <backup>/<forward>-adjusted offset (in divisions) through
    one <measure>, updating divisions and time/key signature on every
    <attributes> element along the way.

    Every pass over the document shares this, so a fix to the offset or
    signature handling applies to all of them at once.
    """

    def __init__(self, divisions: int, ts_num: int, ts_den: int, fifths: int = 0):
        self.divisions = divisions
        self.ts_num = ts_num
        self.ts_den = ts_den
        self.fifths = fifths
        self.offset_divs = 0

    def step(self, elem) -> Optional[Tuple[int, bool]]:
        """Advances state for one child of a <measure>.

        Returns (note_offset_divs, is_chord) for a <note> element - the
        offset the note itself starts at, which for a chord note is behind
        the running offset by the chord's own duration since chord notes
        share their predecessor's start time. Returns None for every other
        element (attributes/backup/forward already applied as a side
        effect).
        """
        if elem.tag == "attributes":
            self.divisions, self.ts_num, self.ts_den, self.fifths = _apply_attributes(
                elem, self.divisions, self.ts_num, self.ts_den, self.fifths
            )
            return None
        if elem.tag == "backup":
            self.offset_divs -= _duration_divs(elem)
            return None
        if elem.tag == "forward":
            self.offset_divs += _duration_divs(elem)
            return None
        if elem.tag == "note":
            dur_divs = _duration_divs(elem)
            is_chord = elem.find("chord") is not None
            if is_chord:
                note_offset_divs = self.offset_divs - dur_divs
            else:
                note_offset_divs = self.offset_divs
                self.offset_divs += dur_divs
            return note_offset_divs, is_chord
        return None


@dataclass
class _FirstPartScan:
    """Everything one walk of the first <part> produces - so _scan_first_part
    returns six related results without a six-element tuple, and the
    per-element helpers have somewhere to append as they go."""

    measure_start_quarters: Dict[int, float] = field(default_factory=dict)
    measure_ts_fifths: Dict[int, Tuple[int, int, int]] = field(default_factory=dict)
    tempo_changes: List[TempoChange] = field(default_factory=list)
    repeat_spans: List[RepeatSpan] = field(default_factory=list)
    ending_spans: List[EndingSpan] = field(default_factory=list)
    hairpin_spans: List[HairpinSpan] = field(default_factory=list)
    segno_marks: List[SegnoMark] = field(default_factory=list)
    coda_marks: List[CodaMark] = field(default_factory=list)
    to_coda_marks: List[ToCodaMark] = field(default_factory=list)
    fine_marks: List[FineMark] = field(default_factory=list)
    navigation_jumps: List[NavigationJump] = field(default_factory=list)


def _staff_number(elem, default):
    """A <staff> child's number, or `default` when absent. Read three
    different ways in the original walk (defaulting to None for a dynamics
    direction, 1 for stave text and for a note); the default is the only
    difference, so it's the parameter."""
    staff_el = elem.find("staff")
    if staff_el is not None and staff_el.text:
        return int(staff_el.text.strip())
    return default


def _displaced_offset_divs(elem, walker) -> int:
    """The walker's current offset, displaced by an <offset> child if the
    element has one. <direction> and <harmony> are both <measure> children
    that never advance the cursor themselves and both use this same
    convention; a malformed offset is ignored rather than raising."""
    offset_divs = walker.offset_divs
    offset_el = elem.find("offset")
    if offset_el is not None and offset_el.text:
        try:
            offset_divs += int(offset_el.text.strip())
        except ValueError:
            pass
    return offset_divs


def _duration_display_name(elem, quarter_len: float) -> Optional[str]:
    """The note's spoken duration word.

    Taken from the note's own notated shape (<type>/<dot>), not a
    reverse-lookup from quarter_length - a tuplet member's <type> still
    reads "eighth" even though its actual sounding duration isn't a clean
    fraction, which is exactly what a musician reading the note list wants
    ("quaver", not some approximated tuplet fraction). Falls back to the
    reverse-lookup only when there is no <type> at all - chiefly a
    whole-measure rest, which MusicXML allows to omit it - rather than
    leaving the note with no word.
    """
    type_el = elem.find("type")
    duration_type = type_el.text.strip() if (type_el is not None and type_el.text) else None
    if duration_type is not None:
        name = beat_unit_display_name(duration_type, len(elem.findall("dot")))
    else:
        name = quarter_length_to_display_name(quarter_len)

    time_mod_el = elem.find("time-modification")
    if name is not None and time_mod_el is not None:
        actual_notes_el = time_mod_el.find("actual-notes")
        if actual_notes_el is not None and actual_notes_el.text:
            word = tuplet_word(int(actual_notes_el.text.strip()))
            if word is not None:
                name = f"{name} {word}"
    return name


@dataclass
class _NoteReading:
    """What <pitch>/<unpitched> (or a rest) says a note sounds as."""
    step_name: str
    octave: Optional[int] = None
    midi_pitch: Optional[int] = None
    percussion_source_key: Optional[int] = None
    # A percussion item replaces the note's real notated <voice> with its
    # own declared key - see TimelineBuilder._read_pitch.
    voice_override: Optional[int] = None


# P1 (find_feature_plan.md, D6): the <notations> child tags this parser
# recognises and handles explicitly. Anything under <notations> NOT in here
# becomes the `other_notation` catch-all attribute (value = tag, hyphens as
# spaces), so a rare or future exporter element is still findable rather
# than vanishing silently. Adding a real handler for a tag means adding it
# here in the same commit, which automatically removes it from the catch-all.
# `footnote`/`level` are editorial metadata with no performance meaning -
# deliberately recognised (i.e. ignored) rather than surfaced as noise.
_RECOGNISED_NOTATION_TAGS = frozenset({
    "tied", "slur", "tuplet", "glissando", "slide", "ornaments",
    "technical", "articulations", "dynamics", "fermata",
    "arpeggiate", "non-arpeggiate", "accidental-mark", "footnote", "level",
})


# P3 (find_feature_plan.md, D6): the <direction-type> child tags this parser
# handles explicitly. Anything else becomes the `other_direction` catch-all
# point mark (DirectionMark, value = tag with hyphens as spaces), so a rare
# or future exporter element stays findable rather than vanishing. Adding a
# real handler for a tag means adding it here in the same commit, which
# automatically removes it from the catch-all. `words`/`dynamics`/`wedge`/
# `metronome`/`segno`/`coda` are consumed elsewhere (_handle_direction's own
# dynamics+words handling, _scan_first_part's wedge/tempo/jump-mark scan).
_RECOGNISED_DIRECTION_TYPE_TAGS = frozenset({
    "words", "dynamics", "wedge", "metronome", "segno", "coda",
    "pedal", "octave-shift", "rehearsal", "dashes", "bracket",
})


@dataclass
class _NoteMarks:
    """Everything hanging off a <note> that isn't its pitch. All optional by
    design: absence is how Region 3/4 know not to render a row (see
    NoteRenderer.note_attribute_pairs)."""
    fret: Optional[int] = None
    string_num: Optional[int] = None
    fingering: Optional[str] = None
    pluck: Optional[str] = None
    articulation: Optional[str] = None
    dynamic: Optional[str] = None
    strum: Optional[str] = None
    lyric_text: Optional[str] = None
    # P1: note-attached notations made findable - see NoteData's own field
    # comments for each one's value vocabulary.
    tie: Optional[str] = None
    slur: Optional[str] = None
    tuplet: Optional[str] = None
    fermata: Optional[str] = None
    arpeggio: Optional[str] = None
    accidental: Optional[str] = None
    technique: Optional[str] = None
    glissando: Optional[str] = None
    other_notation: Optional[str] = None


@dataclass
class _PartState:
    """State that survives across one part's measures.

    divisions/time signature/key carry forward from each measure's walker to
    seed the next (MusicXML states them once and they persist); the sticky
    current chord is what lets an arpeggiate mark several bars later still
    know which chord it strums. Scoped per PART, not per document - every
    real file seen carries <harmony>/<notations/arpeggiate> on a single
    part, and interleaving correctly across parts would need the measures
    walked in time order across parts rather than one part fully at a time.
    """
    part_id: str
    part_name: str
    percussion_instruments: Dict[str, Tuple[str, Optional[int]]]
    pickup_filled_quarters: float

    divisions: int = 1
    time_sig_num: int = 4
    time_sig_den: int = 4
    fifths: int = 0

    current_chord_pitches: Optional[List[int]] = None
    current_chord_label: str = "Strum"
    # Reported: when a bar's own <harmony> lands at the same beat as an
    # arpeggiate-marked note (a bar with no other stroke, so the harmony IS
    # the first note - files/Three Blind Mice.mxl's bar 4), the once-per-bar
    # harmony entry and the stroke entry ended up as two near-identical
    # Chords rows at the same slice ("G, beat position 1.0" right next to
    # "G, beat position 1.0, strum down stroke") - real information, but
    # redundant enough to read as noise ("obfuscated by the presence of the
    # chord", the user's own description). Tracks the harmony NoteData
    # already emitted at each (measure, offset) this part has seen, so a
    # stroke landing on that same slice sets .strum on that SAME NoteData in
    # place instead of adding a second one.
    harmony_notes_by_key: Dict[Tuple[int, float], NoteData] = field(default_factory=dict)

    # P3/D5: <direction> spans (pedal, octave shift, dashed/bracket lines)
    # still open, keyed by kind. Most-recent-wins on an unclosed second
    # start, mirroring _step_barline's single forward-repeat slot - nested
    # same-kind direction spans on one staff aren't a real notation concept.
    # Each value is (start_measure, start_beat_position,
    # start_quarters_from_start, staff, label).
    open_direction_spans: Dict[str, Tuple[int, float, float, int, str]] = field(
        default_factory=dict
    )

    def __post_init__(self):
        self.refresh_bar_shape()

    def refresh_bar_shape(self, walker=None) -> None:
        """Recompute the beat unit and bar length. Called once per part from
        the seeded time signature, and again at every <attributes> from the
        walker's live one (a time signature change takes effect there).

        Deliberately does NOT write back to time_sig_num/time_sig_den:
        those exist only to seed the NEXT measure's walker, and carry_forward
        is the one place that sets them - keeping the two roles separate is
        what makes a mid-measure <attributes> affect this bar's beat maths
        without touching the seed.
        """
        ts_num = walker.ts_num if walker is not None else self.time_sig_num
        ts_den = walker.ts_den if walker is not None else self.time_sig_den
        self.beat_unit_quarter_len = 4.0 / ts_den
        self.full_bar_quarters = ts_num * self.beat_unit_quarter_len

    def carry_forward(self, walker) -> None:
        """Seed the next measure's walker from where this one ended."""
        self.divisions = walker.divisions
        self.time_sig_num = walker.ts_num
        self.time_sig_den = walker.ts_den
        self.fifths = walker.fifths

    def beat_position(self, m_num: int, offset_q: float) -> float:
        """Ts-relative beat position (Ref 18) for an offset within a
        measure. A pickup bar's notes sit at the END of a notional full bar
        (Ref 17), which is what _start_beat computes. Shared by notes,
        stave text and harmony entries - all three had their own copy of
        this two-branch calculation before S3."""
        if m_num == 0:
            start_beat = TimelineBuilder._start_beat(
                self.full_bar_quarters, self.pickup_filled_quarters, self.beat_unit_quarter_len
            )
        else:
            start_beat = 1.0
        return round(start_beat + (offset_q / self.beat_unit_quarter_len), 2)


@dataclass
class _MeasureState:
    """State scoped to one measure and reset with it: the offset walker, any
    dynamics mark waiting for a note at the same offset to claim it, and
    grace notes buffered until the note they decorate arrives."""
    m_num: int
    walker: "_MeasureOffsetWalker"
    pending_dynamics: Dict[Tuple[Optional[int], int], str] = field(default_factory=dict)
    pending_grace: Dict[Tuple[int, int], List[Tuple[NoteData, bool, Tuple[int, float]]]] = field(
        default_factory=dict
    )
    # P1/D7: id() of every <note> element in this measure that belongs to a
    # chord (carries <chord/>, or is the first note of a group whose next
    # sibling does). An <arpeggiate>/<non-arpeggiate> mark on one of these
    # is the real "roll this chord" notation and becomes the `arpeggio`
    # attribute; the same mark on a lone note stays re-read as a strum
    # stroke, the existing behaviour.
    chord_member_ids: Set[int] = field(default_factory=set)

    def key_for(self, offset_q: float) -> Tuple[int, float]:
        """The (measure, offset) bucket key. Rounded to 4dp so two notes
        meant to be simultaneous can't miss each other by a float hair."""
        return (self.m_num, round(offset_q, 4))


class _NoteSink:
    """Collects notes into (measure, offset) buckets, with the time
    signature and key in force at each.

    One place that writes both, because they must stay in step: a bucket
    with no slice_state entry renders as 4/4 with no accidentals. The
    original walk repeated this two-line pair at five separate call sites.

    overwrite_state distinguishes the two conventions the original used and
    is preserved exactly: a real note stamps its slice's state
    unconditionally (the last writer at a position wins), while stave text
    and harmony entries only fill it in if nothing has yet (setdefault) -
    they are <measure> children that can precede the notes they sit with.
    """

    def __init__(self):
        self.buckets: Dict[Tuple[int, float], List[NoteData]] = {}
        self.slice_state: Dict[Tuple[int, float], Tuple[Tuple[int, int], int]] = {}

    def add(self, key, note: NoteData, walker, overwrite_state: bool = True) -> None:
        self.buckets.setdefault(key, []).append(note)
        state = ((walker.ts_num, walker.ts_den), walker.fifths)
        if overwrite_state:
            self.slice_state[key] = state
        else:
            self.slice_state.setdefault(key, state)

    def append_only(self, key, note: NoteData) -> None:
        """Add a note that rides along with one already bucketed here (a
        lyric, a Chords-part stroke), which therefore never sets the slice
        state itself - the note it accompanies already did."""
        self.buckets[key].append(note)


class TimelineBuilder:
    """Builds the flat, sorted EventSlice timeline for a MusicXML file.

    A hand-rolled ElementTree pass, not music21, and the source of truth for
    notes: it handles <backup>/<forward> offsets, <chord> grouping and
    notations/technical string/fret data explicitly, and is ~460x faster
    than routing through music21.converter.parse.
    """

    def __init__(
        self,
        file_path: str,
        parts_info: List[PartStructureInfo],
        root: Optional[ET.Element] = None,
    ):
        """root: an already-parsed ElementTree root if the caller has one,
        so the file isn't parsed twice. Falls back to parsing file_path
        itself, the path MusicData(file_path=...) takes."""
        self.file_path = file_path
        self.parts_info = parts_info
        self._root = root
        # Every <sound tempo=.../> marking in the piece, not just the first,
        # so callers can look up the tempo in effect at a given position.
        # Populated by build() as a side effect.
        self.tempo_changes: List[TempoChange] = []

        # Ref 14 AC4: synthetic, empty-notes EventSlices at every whole beat
        # with no real note. Deliberately NOT part of the returned
        # timeline_slices - see build().
        self.beat_markers: List[EventSlice] = []

        # Ref 29: repeat-barline pairs, endings and hairpins, same
        # side-channel pattern as tempo_changes.
        self.repeat_spans: List[RepeatSpan] = []
        self.ending_spans: List[EndingSpan] = []
        self.hairpin_spans: List[HairpinSpan] = []
        # P3: <direction>/<direction-type> spans and points, collected in
        # the per-part walk (_handle_direction), not _scan_first_part -
        # pedal/octave-shift/rehearsal/dashes/bracket are per-part/per-staff
        # facts, not score-wide ones (D5).
        self.direction_spans: List[DirectionSpan] = []
        self.direction_marks: List[DirectionMark] = []
        # Segno/Coda/D.C./D.S./Fine navigation marks, same side-channel
        # pattern - see _step_direction_jump_marks.
        self.segno_marks: List[SegnoMark] = []
        self.coda_marks: List[CodaMark] = []
        self.to_coda_marks: List[ToCodaMark] = []
        self.fine_marks: List[FineMark] = []
        self.navigation_jumps: List[NavigationJump] = []
        # From measure_start_quarters, which exists regardless of note
        # content - deriving it from timeline_slices would undercount a
        # trailing all-rest measure, since rests are skipped from there.
        self.total_measures: int = 0

    def _part_names(self, root, default_part_name: str) -> Dict[str, str]:
        """part_id -> the name shown against every note of that part.

        Derived from parts_info whenever the caller has it, rather than
        re-reading <part-name> here. Two independent reads of the same
        element have to agree exactly or anything joining on the name (the
        Performance Report's per-instrument tally) silently finds nothing;
        deriving removes that invariant instead of restating it.

        The etree fallback covers the no-reader path - a directly-built
        MusicData has no parts_info at all.
        """
        if self.parts_info:
            return {p.part_id: p.name for p in self.parts_info}

        part_names: Dict[str, str] = {}
        for sp in root.findall(".//part-list/score-part"):
            sp_id = sp.attrib.get("id", "")
            name_elem = sp.find("part-name")
            part_names[sp_id] = (
                name_elem.text.strip()
                if name_elem is not None and name_elem.text
                else default_part_name
            )
        return part_names

    def build(self) -> List[EventSlice]:
        """S3: the top-level shape of the walk only - one part at a time,
        one measure at a time, dispatching each measure child to the handler
        that owns it. Everything that reads an element lives in a _handle_*
        method below, following the shape _scan_first_part/_step_barline/
        _step_wedge already established in this file for the structural
        scan.

        The two state objects carry exactly what has to survive between
        elements: _PartState what persists across a part's measures
        (divisions/time signature/key carried forward, the sticky current
        chord), _MeasureState what is scoped to one measure and reset with
        it (the offset walker, pending dynamics, buffered grace notes).
        _NoteSink collects what every handler produces.
        """
        root = self._root
        if root is None:
            try:
                root = read_musicxml_root(self.file_path)
            except Exception as e:
                print(f"[ERROR] Failed to parse XML for timeline: {e}")
                return []

        default_part_name = self.parts_info[0].name if self.parts_info else "Classical Guitar"
        part_names = self._part_names(root, default_part_name)
        percussion_instruments = _percussion_instrument_map(root)

        first_measure_number, needs_reindex, pickup_filled_quarters = self._detect_pickup(root)
        scan = self._scan_first_part(root, needs_reindex, pickup_filled_quarters)
        measure_start_quarters = scan.measure_start_quarters
        measure_ts_fifths = scan.measure_ts_fifths
        self.tempo_changes = scan.tempo_changes
        self.repeat_spans = scan.repeat_spans
        self.ending_spans = scan.ending_spans
        self.hairpin_spans = scan.hairpin_spans
        self.segno_marks = scan.segno_marks
        self.coda_marks = scan.coda_marks
        self.to_coda_marks = scan.to_coda_marks
        self.fine_marks = scan.fine_marks
        self.navigation_jumps = scan.navigation_jumps
        self.total_measures = max(measure_start_quarters.keys()) if measure_start_quarters else 0

        sink = _NoteSink()

        for part in root.findall("part"):
            part_id = part.attrib.get("id", "")
            part_state = _PartState(
                part_id=part_id,
                part_name=part_names.get(part_id, default_part_name),
                percussion_instruments=percussion_instruments,
                pickup_filled_quarters=pickup_filled_quarters,
            )

            for m in part.findall("measure"):
                measure_state = _MeasureState(
                    m_num=_measure_number(m, needs_reindex),
                    walker=_MeasureOffsetWalker(
                        part_state.divisions,
                        part_state.time_sig_num,
                        part_state.time_sig_den,
                        part_state.fifths,
                    ),
                )

                # <chord/> is only ever on consecutive <note> siblings
                # (MusicXML spec), so a plain adjacency scan finds every
                # chord member, first note included (D7).
                note_elems = [e for e in m if e.tag == "note"]
                for i, ne in enumerate(note_elems):
                    if ne.find("chord") is not None:
                        measure_state.chord_member_ids.add(id(ne))
                        if i > 0:
                            measure_state.chord_member_ids.add(id(note_elems[i - 1]))

                for elem in m:
                    result = measure_state.walker.step(elem)

                    if elem.tag == "attributes":
                        part_state.refresh_bar_shape(measure_state.walker)
                    elif elem.tag == "direction":
                        self._handle_direction(
                            elem, part_state, measure_state, sink, measure_start_quarters
                        )
                    elif elem.tag == "harmony":
                        self._handle_harmony(elem, part_state, measure_state, sink)

                    if result is not None:
                        self._handle_note(elem, result, part_state, measure_state, sink)

                self._flush_pending_grace(measure_state, sink)
                part_state.carry_forward(measure_state.walker)

            # P3/D5: a pedal/octave-shift/dashes/bracket span left open at
            # the part's end closes at that part's last measure rather than
            # being dropped (untested by any real file - same "defensive
            # default" category as _step_barline's unmatched backward repeat).
            self._flush_open_direction_spans(
                part_state, measure_state.m_num, measure_start_quarters
            )

        return self._assemble_slices(
            root, sink, measure_start_quarters, measure_ts_fifths, pickup_filled_quarters
        )

    # --- per-element handlers -------------------------------------------

    def _handle_direction(
        self, elem, part_state, measure_state, sink, measure_start_quarters
    ) -> None:
        """A <direction> carries several independent things this parser
        reads: a dynamics mark (deferred - a later note at the same offset
        picks it up), generic stave text (bucketed immediately), and (P3)
        the pedal / octave-shift / rehearsal / dashed / bracketed
        <direction-type> spans and points, plus the D6 catch-all for any
        other <direction-type> child."""
        walker = measure_state.walker

        # A MuseScore-style dynamics mark is a <direction> SIBLING of
        # <note>, not a child. Keyed by (staff_or_None, offset_divs) so the
        # note at that same offset picks it up - including every note of a
        # chord, which share an offset. Reset per measure; a direction's
        # target is always local.
        dyn_el = elem.find("direction-type/dynamics")
        if dyn_el is not None and len(dyn_el) > 0:
            mark_el = dyn_el[0]
            mark = mark_el.text.strip() if (mark_el.tag == "other-dynamics" and mark_el.text) else mark_el.tag
            dir_staff = _staff_number(elem, default=None)
            measure_state.pending_dynamics[(dir_staff, walker.offset_divs)] = dynamic_name(mark)

        for words_el in elem.findall("direction-type/words"):
            if not _is_qualifying_stave_text(words_el.text):
                continue
            offset_q = _displaced_offset_divs(elem, walker) / walker.divisions
            sink.add(
                measure_state.key_for(offset_q),
                NoteData(
                    step_name=words_el.text.strip(),
                    octave=None,
                    midi_pitch=None,
                    measure=measure_state.m_num,
                    beat_position=part_state.beat_position(measure_state.m_num, offset_q),
                    ts_duration=float(walker.ts_num),
                    quarter_length=part_state.full_bar_quarters,
                    part_id=part_state.part_id,
                    part_name=part_state.part_name,
                    staff=_staff_number(elem, default=1),
                    voice=STAVE_TEXT_VOICE_ID,
                ),
                walker,
                overwrite_state=False,
            )

        self._step_direction_marks(elem, part_state, measure_state, measure_start_quarters)

    # --- P3: <direction-type> spans and points ------------------------

    def _step_direction_marks(
        self, elem, part_state, measure_state, measure_start_quarters
    ) -> None:
        """P3/D5/D6: each <direction-type> child that isn't a dynamics mark
        or stave text (handled above) or a wedge/tempo/jump mark (handled by
        _scan_first_part). Spans open/close through part_state.open_direction_
        spans; unrecognised children become the `other_direction` catch-all
        point mark."""
        walker = measure_state.walker
        m_num = measure_state.m_num
        offset_q = _displaced_offset_divs(elem, walker) / walker.divisions
        beat_pos = part_state.beat_position(m_num, offset_q)
        quarters = measure_start_quarters.get(m_num, 0.0) + offset_q
        staff = _staff_number(elem, default=1)

        for dt_child in elem.findall("direction-type/*"):
            tag = dt_child.tag
            if tag in ("words", "dynamics", "wedge", "metronome", "segno", "coda"):
                continue  # handled elsewhere
            if tag == "pedal":
                self._step_pedal(
                    dt_child, part_state, m_num, beat_pos, quarters, staff
                )
            elif tag == "octave-shift":
                self._step_octave_shift(
                    dt_child, part_state, m_num, beat_pos, quarters, staff
                )
            elif tag in ("dashes", "bracket"):
                self._step_direction_line(
                    dt_child, tag, part_state, m_num, beat_pos, quarters, staff
                )
            elif tag == "rehearsal":
                self.direction_marks.append(
                    DirectionMark(
                        kind="rehearsal",
                        part_id=part_state.part_id,
                        staff=staff,
                        label=(dt_child.text or "").strip(),
                        measure=m_num,
                        beat_position=beat_pos,
                        quarters_from_start=quarters,
                    )
                )
            elif tag not in _RECOGNISED_DIRECTION_TYPE_TAGS:
                self.direction_marks.append(
                    DirectionMark(
                        kind="other_direction",
                        part_id=part_state.part_id,
                        staff=staff,
                        label=tag.replace("-", " "),
                        measure=m_num,
                        beat_position=beat_pos,
                        quarters_from_start=quarters,
                    )
                )

    def _open_direction_span(
        self, part_state, kind: str, m_num, beat_pos, quarters, staff, label: str
    ) -> None:
        part_state.open_direction_spans[kind] = (m_num, beat_pos, quarters, staff, label)

    def _close_direction_span(
        self, part_state, kind: str, m_num, beat_pos, quarters
    ) -> None:
        open_slot = part_state.open_direction_spans.pop(kind, None)
        if open_slot is None:
            return
        start_m, start_beat, start_quarters, start_staff, label = open_slot
        self.direction_spans.append(
            DirectionSpan(
                kind=kind,
                part_id=part_state.part_id,
                staff=start_staff,
                label=label,
                start_measure=start_m,
                start_beat_position=start_beat,
                start_quarters_from_start=start_quarters,
                end_measure=m_num,
                end_beat_position=beat_pos,
                end_quarters_from_start=quarters,
            )
        )

    def _step_pedal(
        self, pedal_el, part_state, m_num, beat_pos, quarters, staff
    ) -> None:
        """<pedal type="start"|"sostenuto"|"stop"|"change">. A `change`
        (pedal lift-and-retake) is a point, not a span; start/sostenuto open
        one span kind, stop closes it."""
        ptype = pedal_el.attrib.get("type", "")
        if ptype in ("start", "sostenuto", "resume"):
            self._open_direction_span(part_state, "pedal", m_num, beat_pos, quarters, staff, "")
        elif ptype == "stop":
            self._close_direction_span(part_state, "pedal", m_num, beat_pos, quarters)
        elif ptype == "change":
            self.direction_marks.append(
                DirectionMark(
                    kind="pedal_change",
                    part_id=part_state.part_id,
                    staff=staff,
                    label="",
                    measure=m_num,
                    beat_position=beat_pos,
                    quarters_from_start=quarters,
                )
            )

    def _step_octave_shift(
        self, shift_el, part_state, m_num, beat_pos, quarters, staff
    ) -> None:
        """<octave-shift type="up"|"down"|"stop" size="8"|"15">. The label
        ("8va" above / "8vb" below; "15ma"/"15mb" for two octaves) is set at
        the opening end and carried to the closed span."""
        stype = shift_el.attrib.get("type", "")
        if stype in ("up", "down"):
            two_octaves = shift_el.attrib.get("size", "8").strip() == "15"
            if two_octaves:
                label = "15ma" if stype == "up" else "15mb"
            else:
                label = "8va" if stype == "up" else "8vb"
            self._open_direction_span(
                part_state, "octave_shift", m_num, beat_pos, quarters, staff, label
            )
        elif stype == "stop":
            self._close_direction_span(part_state, "octave_shift", m_num, beat_pos, quarters)

    def _step_direction_line(
        self, line_el, kind: str, part_state, m_num, beat_pos, quarters, staff
    ) -> None:
        """<dashes>/<bracket> type="start"|"stop" - a plain span, the same
        open/close shape as pedal."""
        ltype = line_el.attrib.get("type", "")
        if ltype == "start":
            self._open_direction_span(part_state, kind, m_num, beat_pos, quarters, staff, "")
        elif ltype in ("stop", "end"):
            self._close_direction_span(part_state, kind, m_num, beat_pos, quarters)

    def _flush_open_direction_spans(
        self, part_state, last_m_num: int, measure_start_quarters
    ) -> None:
        """Close any span still open when a part ends (D5) - end position is
        the end of that part's last measure."""
        if not part_state.open_direction_spans:
            return
        end_quarters = measure_start_quarters.get(last_m_num, 0.0) + part_state.full_bar_quarters
        end_beat = part_state.beat_position(last_m_num, part_state.full_bar_quarters)
        for kind in list(part_state.open_direction_spans):
            self._close_direction_span(
                part_state, kind, last_m_num, end_beat, end_quarters
            )

    def _handle_harmony(self, elem, part_state, measure_state, sink) -> None:
        """<harmony> is a <measure> child like <direction>, not a <note>
        child - walker.step() already returned None for it, so it never
        advances offset_divs itself. An <offset> child (rare; absent in
        every file seen so far) displaces it from the current cursor
        position, the same convention MusicXML uses for <direction>."""
        walker = measure_state.walker
        chord_pitches, chord_label = _resolve_harmony(elem)
        if not chord_pitches:
            return

        part_state.current_chord_pitches = chord_pitches
        part_state.current_chord_label = chord_label

        offset_q = _displaced_offset_divs(elem, walker) / walker.divisions
        key = measure_state.key_for(offset_q)
        chord_note = NoteData(
            step_name=chord_label,
            octave=None,
            midi_pitch=max(chord_pitches),
            measure=measure_state.m_num,
            beat_position=part_state.beat_position(measure_state.m_num, offset_q),
            ts_duration=float(walker.ts_num),
            quarter_length=part_state.full_bar_quarters,
            duration_name_us=quarter_length_to_display_name(part_state.full_bar_quarters),
            part_id=CHORDS_PART_ID,
            part_name=CHORDS_PART_NAME,
            staff=1,
            voice=1,
            chord_pitches=chord_pitches,
            # P2: same text as step_name, but findable (step is a core key).
            chord_symbol=chord_label or None,
            chord_diagram=_resolve_chord_diagram(elem),
        )
        sink.add(key, chord_note, walker, overwrite_state=False)
        part_state.harmony_notes_by_key[key] = chord_note

    def _handle_note(self, elem, result, part_state, measure_state, sink) -> None:
        """One <note>: read it, bucket it, and emit whatever rides along
        with it (a lyric, a Chords-part stroke). Grace notes are buffered
        rather than bucketed - see _MeasureState.pending_grace."""
        walker = measure_state.walker
        m_num = measure_state.m_num
        note_offset_divs, _is_chord = result

        is_rest = elem.find("rest") is not None
        dur_divs = _duration_divs(elem)

        # <grace> is a <note> child with no <duration> sibling - dur_divs
        # above is already 0 for it, which is also why walker.step() never
        # advances offset_divs past a grace note (see
        # _MeasureOffsetWalker.step). slash="yes" is the conventional
        # "crushed" acciaccatura; slash="no" or absent is a longer
        # appoggiatura - both are captured here and realized identically
        # for now (see GraceNote).
        grace_el = elem.find("grace")
        is_grace = grace_el is not None
        grace_slash = grace_el.attrib.get("slash", "no") == "yes" if is_grace else False

        staff = _staff_number(elem, default=1)
        voice = int(elem.find("voice").text.strip()) if elem.find("voice") is not None else 1

        if is_rest:
            pitch = _NoteReading(step_name="rest")
            marks = _NoteMarks()
        else:
            pitch = self._read_pitch(elem, part_state)
            if pitch is None:
                # Neither <pitch> nor <unpitched> - nothing soundable to
                # place, so this element contributes no note at all.
                return
            if pitch.voice_override is not None:
                voice = pitch.voice_override
            marks = self._read_notations(
                elem, staff, note_offset_divs, measure_state,
                is_chord_member=id(elem) in measure_state.chord_member_ids,
            )

        offset_q = note_offset_divs / walker.divisions
        quarter_len = dur_divs / walker.divisions
        ts_duration = round(quarter_len / part_state.beat_unit_quarter_len, 2)
        duration_name_us = _duration_display_name(elem, quarter_len)
        beat_pos = part_state.beat_position(m_num, offset_q)

        note_obj = NoteData(
            step_name=pitch.step_name,
            octave=pitch.octave,
            midi_pitch=pitch.midi_pitch,
            measure=m_num,
            beat_position=beat_pos,
            ts_duration=ts_duration,
            quarter_length=quarter_len,
            part_id=part_state.part_id,
            part_name=part_state.part_name,
            staff=staff,
            voice=voice,
            fret=marks.fret,
            string=marks.string_num,
            dynamic=marks.dynamic,
            articulation=marks.articulation,
            fingering=marks.fingering,
            pluck=marks.pluck,
            duration_name_us=duration_name_us,
            percussion_source_key=pitch.percussion_source_key,
            tie=marks.tie,
            slur=marks.slur,
            tuplet=marks.tuplet,
            fermata=marks.fermata,
            arpeggio=marks.arpeggio,
            accidental=marks.accidental,
            technique=marks.technique,
            glissando=marks.glissando,
            other_notation=marks.other_notation,
        )

        key = measure_state.key_for(offset_q)
        voice_key = (staff, voice)

        if is_grace:
            # Not bucketed here at all - see GraceNote/pending_grace's own
            # comments. Held until the next non-grace note for this
            # (staff, voice) arrives.
            measure_state.pending_grace.setdefault(voice_key, []).append(
                (note_obj, grace_slash, key)
            )
            return

        grace_list = measure_state.pending_grace.pop(voice_key, None)
        if grace_list:
            note_obj.grace_notes = [
                GraceNote(step_name=g.step_name, midi_pitch=g.midi_pitch, slash=slash)
                for g, slash, _ in grace_list
            ]
            # P1: a spoken summary of the grace group, its own findable
            # attribute - the grace_notes list above still drives the
            # "A grace B" step rendering, untouched.
            note_obj.grace = ", ".join(
                "acciaccatura" if slash else "appoggiatura"
                for _, slash, _ in grace_list
            )

        sink.add(key, note_obj, walker)

        if marks.lyric_text is not None:
            # Bucketed into the SAME slice as the melody note it came from,
            # unlike parsers/ug_timeline_builder.py's Lyrics part - MusicXML
            # already gives real per-note timing, so there is no need to
            # fabricate one bar per lyric the way UG (plain chord-tab text,
            # no real positions) has to.
            sink.append_only(
                key,
                NoteData(
                    step_name=marks.lyric_text,
                    octave=None,
                    midi_pitch=None,
                    measure=m_num,
                    beat_position=beat_pos,
                    ts_duration=ts_duration,
                    quarter_length=quarter_len,
                    part_id=LYRICS_PART_ID,
                    part_name=LYRICS_PART_NAME,
                    staff=1,
                    voice=1,
                ),
            )

        if marks.strum is not None and part_state.current_chord_pitches is not None:
            # A stroke mark with no chord known yet (arpeggiate before the
            # piece's first <harmony>) is skipped rather than fabricating a
            # chord - an untested edge case in every real file seen so far.
            #
            # A stroke landing on the exact same slice as the bar's own
            # harmony entry (no other note between them - the harmony IS the
            # stroke's note) sets .strum on that existing entry rather than
            # adding a second, near-identical Chords row.
            existing_harmony_note = part_state.harmony_notes_by_key.get(key)
            if existing_harmony_note is not None:
                existing_harmony_note.strum = marks.strum
                return
            sink.append_only(
                key,
                NoteData(
                    step_name=part_state.current_chord_label,
                    octave=None,
                    midi_pitch=max(part_state.current_chord_pitches),
                    measure=m_num,
                    beat_position=beat_pos,
                    ts_duration=ts_duration,
                    quarter_length=quarter_len,
                    part_id=CHORDS_PART_ID,
                    part_name=CHORDS_PART_NAME,
                    staff=1,
                    voice=1,
                    chord_pitches=part_state.current_chord_pitches,
                    strum=marks.strum,
                    duration_name_us=duration_name_us,
                    # P2: the sticky chord label, so a strum stroke's Chords
                    # entry is findable under "chord symbol" like the
                    # <harmony>'s own entry.
                    chord_symbol=part_state.current_chord_label or None,
                ),
            )

    def _read_pitch(self, elem, part_state) -> Optional["_NoteReading"]:
        """Name/octave/sounding pitch for a non-rest note, or None when the
        element carries neither <pitch> nor <unpitched>."""
        pitch_el = elem.find("pitch")
        if pitch_el is None:
            unpitched_el = elem.find("unpitched")
            if unpitched_el is None:
                return None
            # Wishlist #8: a percussion note's real sound/name comes from
            # its <instrument id> ref into percussion_instruments (the
            # score-part's own <score-instrument>/<midi-instrument>
            # children) - never from <display-step>/<display-octave>, which
            # is only where the notehead is drawn on the percussion staff,
            # not a real pitch (confirmed against Hit It.mxl).
            instr_el = elem.find("instrument")
            instr_id = instr_el.attrib.get("id") if instr_el is not None else None
            instr_name, instr_key = part_state.percussion_instruments.get(instr_id, (None, None))
            # Region 2 follow-up (user: "the pitch defines the instrument -
            # that is the defining feature"): each distinct percussion item
            # gets its OWN voice number - its own declared key, not the real
            # notated <voice> several instruments may share (Hit It.mxl's
            # hi-hat and snare are both real MusicXML voice 1). This is what
            # splits them into independently mute/soloable Region 2 rows for
            # free, reusing the existing part/staff/voice machinery
            # untouched rather than adding a new tree level - the same
            # "fabricate a voice_id" trick GP's synthetic Chords voice
            # (GP_CHORD_VOICE_ID) already uses. Falls back to the real
            # notated voice only if the instrument id didn't resolve.
            return _NoteReading(
                step_name=instr_name if instr_name is not None else "Percussion",
                octave=None,
                midi_pitch=instr_key,
                percussion_source_key=instr_key,
                voice_override=instr_key,
            )

        step = pitch_el.find("step").text.strip() if pitch_el.find("step") is not None else "C"
        octave = int(pitch_el.find("octave").text.strip()) if pitch_el.find("octave") is not None else 4
        alter_el = pitch_el.find("alter")
        alter = int(alter_el.text.strip()) if (alter_el is not None and alter_el.text) else 0

        acc_words = {1: " sharp", -1: " flat", 2: " double sharp", -2: " double flat", 0: ""}
        step_offsets = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
        return _NoteReading(
            step_name=f"{step}{acc_words.get(alter, '')}",
            octave=octave,
            midi_pitch=(octave + 1) * 12 + step_offsets.get(step, 0) + alter,
        )

    def _read_notations(
        self, elem, staff, note_offset_divs, measure_state, is_chord_member: bool = False
    ) -> "_NoteMarks":
        """Everything hanging off a note that isn't its pitch: technical
        (fret/string/fingering/pluck), articulations and ornaments, its
        dynamic, a strum/pick direction, its first lyric, and (P1) the
        note-attached notations made findable - ties, slurs, tuplet,
        fermata, chord arpeggio, cautionary/editorial accidental, tier-2
        playing techniques, glissando/slide, and a catch-all for anything
        else under <notations> (D6)."""
        marks = _NoteMarks()

        tech_el = elem.find("notations/technical")
        if tech_el is not None:
            f_el = tech_el.find("fret")
            s_el = tech_el.find("string")
            if f_el is not None and f_el.text:
                marks.fret = int(f_el.text.strip())
            if s_el is not None and s_el.text:
                marks.string_num = int(s_el.text.strip())
            # MusicXML allows several <fingering>/<pluck> per note (a
            # rasgueado marks one note p/i/m/a), so use findall - .find()
            # silently drops everything after the first.
            fing_texts = [e.text.strip() for e in tech_el.findall("fingering") if e.text]
            pluck_texts = [e.text.strip() for e in tech_el.findall("pluck") if e.text]
            marks.fingering = ", ".join(fing_texts) or None
            marks.pluck = ", ".join(pluck_texts) or None

        # Articulations and ornaments get the same spoken-word treatment, so
        # both are merged into one comma-joined field.
        artic_tags = [
            child.tag
            for parent_tag in ("articulations", "ornaments")
            for child in elem.findall(f"notations/{parent_tag}/*")
        ]
        marks.articulation = ", ".join(articulation_name(t) for t in artic_tags) or None

        # A direct notations/dynamics is the rarer exporter form; being
        # note-specific, it beats an offset-matched <direction>.
        note_dyn_el = elem.find("notations/dynamics")
        if note_dyn_el is not None and len(note_dyn_el) > 0:
            note_mark_el = note_dyn_el[0]
            note_mark = (
                note_mark_el.text.strip()
                if (note_mark_el.tag == "other-dynamics" and note_mark_el.text)
                else note_mark_el.tag
            )
            marks.dynamic = dynamic_name(note_mark)
        else:
            pending = measure_state.pending_dynamics
            marks.dynamic = pending.get((staff, note_offset_divs))
            if marks.dynamic is None:
                marks.dynamic = pending.get((None, note_offset_divs))

        # <notations/arpeggiate direction="up"/"down"> on a single
        # (non-chord) note has no conventional notation meaning - real
        # arpeggios apply to chords - so this is read as a per-note
        # pick/strum-direction indicator instead, the same "down stroke"/
        # "up stroke" vocabulary Guitar Pro's synthetic Chords voice already
        # established for NoteData.strum (see CLAUDE.md). Reported:
        # strumming isn't something a piano/melody note does - it belongs to
        # the (guitar) chord accompaniment, so this never ends up on the
        # melody note's own NoteData; it only ever triggers an extra
        # Chords-part "stroke" entry. Left None (not inferred) when absent,
        # same "leave unstated" convention.
        arpeggiate_el = elem.find("notations/arpeggiate")
        non_arpeggiate_el = elem.find("notations/non-arpeggiate")
        if is_chord_member:
            # D7: on a real chord, <arpeggiate>/<non-arpeggiate> keeps its
            # conventional "roll this chord" meaning and becomes the
            # findable `arpeggio` attribute (never a strum stroke).
            if arpeggiate_el is not None:
                marks.arpeggio = {
                    "up": "arpeggio up", "down": "arpeggio down"
                }.get(arpeggiate_el.attrib.get("direction"), "arpeggio")
            elif non_arpeggiate_el is not None:
                marks.arpeggio = "non-arpeggio"
        elif arpeggiate_el is not None:
            # A lone note's <arpeggiate> has no real arpeggio meaning, so
            # it stays re-read as a per-note pick/strum direction feeding
            # an extra Chords-part stroke entry (see _handle_note).
            arp_direction = arpeggiate_el.attrib.get("direction")
            if arp_direction == "up":
                marks.strum = "up stroke"
            elif arp_direction == "down":
                marks.strum = "down stroke"

        # --- P1: note-attached notations made findable -----------------
        # <tied>/<slur> can each appear twice on one note (a note that ends
        # one slur and begins the next), so findall - never find (F3 bug).
        tie_types = [
            e.attrib.get("type") for e in elem.findall("notations/tied")
            if e.attrib.get("type")
        ]
        marks.tie = ", ".join(tie_types) or None
        slur_types = [
            e.attrib.get("type") for e in elem.findall("notations/slur")
            if e.attrib.get("type")
        ]
        marks.slur = ", ".join(slur_types) or None

        # Tuplet: folded into the duration NAME already (_duration_display_
        # name) - this is the separate findable fact. <time-modification> is
        # a direct <note> child, not a notations child.
        time_mod_el = elem.find("time-modification")
        if time_mod_el is not None:
            actual_el = time_mod_el.find("actual-notes")
            normal_el = time_mod_el.find("normal-notes")
            if actual_el is not None and actual_el.text:
                actual = int(actual_el.text.strip())
                word = tuplet_word(actual)
                if word is not None:
                    marks.tuplet = word
                elif normal_el is not None and normal_el.text:
                    marks.tuplet = f"{actual} in the time of {int(normal_el.text.strip())}"
                else:
                    marks.tuplet = str(actual)

        fermata_el = elem.find("notations/fermata")
        if fermata_el is not None:
            shape = (fermata_el.text or "").strip()
            marks.fermata = "fermata" if shape in ("", "normal") else f"{shape} fermata"

        # Accidental: D14 - only a cautionary or editorial one is findable
        # (a plain printed accidental is already spoken inside the step
        # name, and MuseScore writes one for every accidental on the page).
        # It is a <note> child, sibling of <pitch>, not a notations child.
        acc_el = elem.find("accidental")
        if acc_el is not None and acc_el.text:
            is_caut = acc_el.attrib.get("cautionary") == "yes"
            is_edit = acc_el.attrib.get("editorial") == "yes"
            if is_caut or is_edit:
                prefix = "cautionary" if is_caut else "editorial"
                marks.accidental = f"{prefix} {acc_el.text.strip().replace('-', ' ')}"

        # Tier-2 playing techniques: every notations/technical child beyond
        # the fret/string/fingering/pluck already read above, spoken via the
        # same hyphens-as-spaces fallback articulation_name uses.
        technique_tags = [
            child.tag for child in elem.findall("notations/technical/*")
            if child.tag not in ("fret", "string", "fingering", "pluck")
        ]
        marks.technique = ", ".join(
            articulation_name(t) for t in technique_tags
        ) or None

        gliss_parts = []
        for gliss_tag in ("glissando", "slide"):
            for e in elem.findall(f"notations/{gliss_tag}"):
                gtype = e.attrib.get("type")
                gliss_parts.append(f"{gliss_tag} {gtype}" if gtype else gliss_tag)
        marks.glissando = ", ".join(gliss_parts) or None

        # D6 catch-all: any <notations> child this parser does not handle
        # explicitly still becomes a findable attribute rather than being
        # dropped silently.
        notations_el = elem.find("notations")
        if notations_el is not None:
            extra = [
                child.tag.replace("-", " ")
                for child in notations_el
                if child.tag not in _RECOGNISED_NOTATION_TAGS
            ]
            marks.other_notation = ", ".join(dict.fromkeys(extra)) or None

        # Only the first verse - real files with more than one <lyric> per
        # note are untested by any fixture seen so far.
        lyric_el = elem.find("lyric")
        if lyric_el is not None:
            lyric_text_el = lyric_el.find("text")
            if lyric_text_el is not None and lyric_text_el.text:
                marks.lyric_text = lyric_text_el.text.strip()

        return marks

    def _flush_pending_grace(self, measure_state, sink) -> None:
        """A grace note with no following non-grace note for its
        (staff, voice) before the measure ends (the piece's very last note
        being itself a grace note, or a voice ending mid-measure on one -
        untested by any real file so far). Flushed as an ordinary standalone
        note at its own captured key rather than silently dropped - the same
        "degrade gracefully" convention every other absent-data case in this
        parser follows."""
        for grace_list in measure_state.pending_grace.values():
            for note_obj, _slash, key in grace_list:
                sink.add(key, note_obj, measure_state.walker)

    # --- assembling the result ------------------------------------------

    def _assemble_slices(
        self, root, sink, measure_start_quarters, measure_ts_fifths, pickup_filled_quarters
    ) -> List[EventSlice]:
        """Sort each bucket into reading order, turn every bucket into an
        EventSlice, and compute the metronome's beat markers."""
        buckets = sink.buckets
        sort_key = self._pitch_sort_key(root)
        for bucket_notes in buckets.values():
            bucket_notes.sort(key=sort_key)

        slices = []
        for key in sorted(buckets.keys(), key=lambda k: (k[0], k[1])):
            m_num, offset_q = key
            notes = buckets[key]
            time_sig, key_fifths = sink.slice_state.get(key, ((4, 4), 0))
            slices.append(
                EventSlice(
                    measure=m_num,
                    beat_position=notes[0].beat_position if notes else 1.0,
                    quarter_length=min(n.quarter_length for n in notes) if notes else 1.0,
                    notes=notes,
                    time_sig=time_sig,
                    key_fifths=key_fifths,
                    quarters_from_start=measure_start_quarters.get(m_num, 0.0) + offset_q,
                )
            )

        # Ref 14 AC4: markers are kept OUT of the returned timeline_slices,
        # which must stay exactly "one entry per (measure, offset) with at
        # least one sounding note" - an invariant the rest of the codebase
        # relies on. MusicData splices these in only while the metronome is
        # actually on.
        self.beat_markers = sorted(
            self._beat_marker_slices(
                buckets, measure_start_quarters, measure_ts_fifths, pickup_filled_quarters
            ),
            key=lambda s: (s.measure, s.quarters_from_start),
        )
        return slices

    @staticmethod
    def _pitch_sort_key(root):
        """Region 3/4 must read highest-to-lowest pitch within each
        instrument, regardless of how the source XML orders a chord's notes
        (a real MuseScore guitar-tab export was found writing chords
        lowest-string/lowest-pitch first, reported bug: measures 8-9 of
        files/bach-bourree-tab/score.xml). Notes are already grouped by part
        by construction - the walk finishes one part's measures entirely
        before starting the next, so entries sharing a bucket never
        interleave across parts - but a plain pitch-only sort would still
        break that grouping whenever one part's pitch range overlaps
        another's. part_order pins each note to its part's position first
        and sorts by pitch only within that group; ties (e.g. the same chord
        duplicated across a notation stave and a tab stave) keep their
        original relative order via Python's stable sort. Rests (midi_pitch
        None) sort last within their part - they don't sound, so their
        position among sounding notes doesn't matter. The synthetic
        Chords/Lyrics parts are appended after every real part's index (not
        left to the dict.get() fallback of 0 below, which would collide with
        whichever real part happens to be first) so they always sort after
        the notated instruments, Chords before Lyrics - the same order
        MusicXMLReader appends them to parts_info in.
        """
        part_order = {p.attrib.get("id", ""): i for i, p in enumerate(root.findall("part"))}
        part_order[CHORDS_PART_ID] = len(part_order)
        part_order[LYRICS_PART_ID] = len(part_order)

        def key(note: NoteData) -> Tuple[int, float]:
            # Stave text shares its real part's own part_id (not a separate
            # part - see STAVE_TEXT_VOICE_ID), so it would otherwise fall
            # into the ordinary midi_pitch-is-None tiebreak below and sort
            # AFTER every real note, same as a silent rest. User-requested:
            # it should read first instead, matching how it's already listed
            # above the real voices in Region 2 (mirroring a position mark's
            # own placement above the stave on the printed score) -
            # float("-inf") beats every real pitch_component.
            if note.voice == STAVE_TEXT_VOICE_ID:
                pitch_component = float("-inf")
            else:
                pitch_component = -note.midi_pitch if note.midi_pitch is not None else float("inf")
            return (part_order.get(note.part_id, 0), pitch_component)

        return key
    @staticmethod
    def _start_beat(full_bar_quarters: float, pickup_filled_quarters: float, beat_unit_quarter_len: float) -> float:
        """Ref 17: pickup notes sit at the END of a notional full bar - a
        6/8 pickup holding 3 beats starts at beat 4, not beat 1. Shared by
        real notes and synthetic beat markers so the two can't drift."""
        return 1.0 + ((full_bar_quarters - pickup_filled_quarters) / beat_unit_quarter_len)

    def _beat_marker_slices(
        self,
        buckets: Dict[Tuple[int, float], List[NoteData]],
        measure_start_quarters: Dict[int, float],
        measure_ts_fifths: Dict[int, Tuple[int, int, int]],
        pickup_filled_quarters: float,
    ) -> List[EventSlice]:
        """Ref 14 AC4: one empty-notes EventSlice per whole beat that has no
        real event. The pickup measure only gets markers from its own
        _start_beat onward - earlier beats correspond to no real time, so
        generating them would make positions reachable before the piece
        begins.
        """
        markers: List[EventSlice] = []
        for m_num, (ts_num, ts_den, fifths) in measure_ts_fifths.items():
            beat_unit_quarter_len = 4.0 / ts_den
            full_bar_quarters = ts_num * beat_unit_quarter_len
            start_beat = (
                self._start_beat(full_bar_quarters, pickup_filled_quarters, beat_unit_quarter_len)
                if m_num == 0
                else 1.0
            )

            beat = start_beat
            while beat <= ts_num + 1e-9:
                offset_q = (beat - start_beat) * beat_unit_quarter_len
                key = (m_num, round(offset_q, 4))
                if key not in buckets:
                    markers.append(
                        EventSlice(
                            measure=m_num,
                            beat_position=round(beat, 2),
                            quarter_length=beat_unit_quarter_len,
                            notes=[],
                            time_sig=(ts_num, ts_den),
                            key_fifths=fifths,
                            quarters_from_start=measure_start_quarters.get(m_num, 0.0) + offset_q,
                        )
                    )
                beat += 1.0
        return markers

    def _scan_first_part(
        self, root, needs_reindex: bool, pickup_filled_quarters: float
    ) -> "_FirstPartScan":
        """One walk of the first <part>, collecting everything score-wide:
        measure start positions, per-measure time/key signature, tempo
        changes, repeat and ending spans, hairpins.

        Read from the FIRST <part> only, the "structural, not per-voice"
        convention _detect_pickup also follows: time signatures, tempo
        markings, barlines and hairpins are score-wide properties, not
        things that vary between parts.

        Measure LENGTH uses the time signature at the START of the measure
        (snapshotted at its first <attributes>), since a time signature
        change takes effect at a barline. Every other consumer reads the
        walker's live value, so a mid-measure <attributes> still affects
        offsets after it. That difference is deliberate.
        """
        scan = _FirstPartScan()
        first_part = root.find("part")
        if first_part is None:
            return scan

        running_total = 0.0
        divisions, ts_num, ts_den, fifths = 1, 4, 4, 0
        open_repeat_measure: Optional[int] = None
        open_endings: Dict[int, int] = {}
        # Unlike pending_dynamics in build() (reset per measure), an open
        # wedge must persist ACROSS measures - a hairpin routinely spans
        # several bars.
        # (kind, start_measure, start_beat_position, start_quarters_from_start)
        open_wedge: Optional[Tuple[str, int, float, float]] = None

        for m in first_part.findall("measure"):
            m_num = _measure_number(m, needs_reindex)
            # Set before walking the contents, so the tempo and hairpin
            # handlers can resolve absolute positions as they go.
            scan.measure_start_quarters[m_num] = running_total

            walker = _MeasureOffsetWalker(divisions, ts_num, ts_den, fifths)
            measure_ts: Optional[Tuple[int, int, int]] = None

            for elem in m:
                walker.step(elem)

                if elem.tag == "attributes":
                    if measure_ts is None:
                        measure_ts = (walker.ts_num, walker.ts_den, walker.fifths)
                elif elem.tag == "direction":
                    change = self._tempo_change_from_direction(
                        elem, m_num, walker, scan.measure_start_quarters
                    )
                    if change is not None:
                        scan.tempo_changes.append(change)
                    open_wedge = self._step_wedge(
                        elem, m_num, walker, scan, open_wedge, pickup_filled_quarters
                    )
                    self._step_direction_jump_marks(elem, m_num, scan)
                elif elem.tag == "barline":
                    open_repeat_measure = self._step_barline(
                        elem, m_num, scan, open_repeat_measure, open_endings
                    )

            if measure_ts is None:
                # No <attributes> here, so nothing could have changed the
                # carried-in signature - the walker still holds it.
                measure_ts = (walker.ts_num, walker.ts_den, walker.fifths)
            scan.measure_ts_fifths[m_num] = measure_ts

            full_bar_quarters = measure_ts[0] * (4.0 / measure_ts[1])
            running_total += pickup_filled_quarters if m_num == 0 else full_bar_quarters

            divisions, ts_num, ts_den, fifths = (
                walker.divisions, walker.ts_num, walker.ts_den, walker.fifths
            )

        scan.tempo_changes.sort(key=lambda c: c.quarters_from_start)
        return scan

    def _step_barline(
        self,
        barline_parent,
        m_num: int,
        scan: "_FirstPartScan",
        open_repeat_measure: Optional[int],
        open_endings: Dict[int, int],
    ) -> Optional[int]:
        """Ref 29: <barline>/<repeat> and <barline>/<ending>, paired by
        open/close tracking in document order. Returns the currently open
        forward-repeat measure (None once closed).

        A second forward repeat before any close replaces the open one -
        nested repeat barlines aren't a real notation concept. A backward
        repeat with no open forward starts at measure 1, the standard
        reading of an unmarked opening repeat. Endings are tracked per
        number; start and close are often the same measure, a 1st/2nd-ending
        pair typically living on one bar's two barlines.
        """
        repeat_el = barline_parent.find("repeat")
        if repeat_el is not None:
            direction = repeat_el.attrib.get("direction")
            if direction == "forward":
                open_repeat_measure = m_num
            elif direction == "backward":
                start = open_repeat_measure if open_repeat_measure is not None else 1
                scan.repeat_spans.append(RepeatSpan(start_measure=start, end_measure=m_num))
                open_repeat_measure = None

        ending_el = barline_parent.find("ending")
        if ending_el is not None:
            number_attr = ending_el.attrib.get("number", "").strip()
            first_token = number_attr.replace(",", " ").split()[0] if number_attr else ""
            try:
                number = int(first_token)
            except ValueError:
                return open_repeat_measure
            ending_type = ending_el.attrib.get("type")
            if ending_type == "start":
                open_endings[number] = m_num
            elif ending_type in ("stop", "discontinue"):
                start = open_endings.pop(number, m_num)
                scan.ending_spans.append(
                    EndingSpan(number=number, start_measure=start, end_measure=m_num)
                )

        return open_repeat_measure

    def _step_wedge(
        self,
        direction_elem,
        m_num: int,
        walker: "_MeasureOffsetWalker",
        scan: "_FirstPartScan",
        open_wedge: Optional[Tuple[str, int, float, float]],
        pickup_filled_quarters: float,
    ) -> Optional[Tuple[str, int, float, float]]:
        """Ref 29: crescendo/diminuendo hairpins. Returns the new open-wedge
        state.

        MusicXML's wedge `number` attribute, which disambiguates overlapping
        wedges on one staff, is ignored - only a single open wedge is
        tracked. A deliberate simplification; no file tested so far has
        overlapping wedges.
        """
        wedge_el = direction_elem.find("direction-type/wedge")
        if wedge_el is None:
            return open_wedge

        wedge_type = wedge_el.attrib.get("type")
        beat_unit_quarter_len = 4.0 / walker.ts_den
        full_bar_quarters = walker.ts_num * beat_unit_quarter_len
        offset_q = walker.offset_divs / walker.divisions
        if m_num == 0:
            start_beat = self._start_beat(
                full_bar_quarters, pickup_filled_quarters, beat_unit_quarter_len
            )
            beat_pos = start_beat + (offset_q / beat_unit_quarter_len)
        else:
            beat_pos = 1.0 + (offset_q / beat_unit_quarter_len)
        quarters = scan.measure_start_quarters.get(m_num, 0.0) + offset_q

        if wedge_type in ("crescendo", "diminuendo"):
            return (wedge_type, m_num, round(beat_pos, 2), quarters)
        if wedge_type == "stop" and open_wedge is not None:
            kind, start_m, start_beat_pos, start_quarters = open_wedge
            scan.hairpin_spans.append(
                HairpinSpan(
                    kind=kind,
                    start_measure=start_m,
                    start_beat_position=start_beat_pos,
                    start_quarters_from_start=start_quarters,
                    end_measure=m_num,
                    end_beat_position=round(beat_pos, 2),
                    end_quarters_from_start=quarters,
                )
            )
            return None
        return open_wedge

    # D.C./D.S. "al Fine"/"al Coda" is matched but its qualifier is
    # discarded - the actual Fine/To-Coda marks live in their OWN separate
    # <words> elsewhere in the piece (MuseScore's own convention, see the
    # coda-variant fixtures), so the qualifier itself carries no extra
    # information this app needs. Order matters: "to coda"/"coda" must be
    # tried before the bare "D.C."/"D.S." patterns since a phrase like
    # "D.C. al Coda" would otherwise never reach the coda branch.
    _TO_CODA_WORDS_RE = re.compile(r"^\s*to\s+coda\s*([\w.]*)\s*$", re.IGNORECASE)
    _CODA_WORDS_RE = re.compile(r"^\s*coda\s*([\w.]*)\s*$", re.IGNORECASE)
    _DACAPO_WORDS_RE = re.compile(r"^\s*d\.?\s*c\.?(\s+al\s+.+)?\s*$", re.IGNORECASE)
    _DALSEGNO_WORDS_RE = re.compile(r"^\s*d\.?\s*s\.?(\s+al\s+.+)?\s*$", re.IGNORECASE)
    _FINE_WORDS_RE = re.compile(r"^\s*fine\s*\.?\s*$", re.IGNORECASE)

    def _step_direction_jump_marks(
        self, direction_elem, m_num: int, scan: "_FirstPartScan"
    ) -> None:
        """Segno/Coda signs and D.C./D.S./To-Coda/Fine directions.

        Prefers the sibling <sound> element's machine-readable attributes
        (dacapo/dalsegno/segno/coda/tocoda/fine) whenever present - read
        directly and unconditionally, NOT gated on a <segno/>/<coda/> sign
        glyph also being present in the same <direction-type>, since the
        spec ties the two together by convention rather than requirement.
        Falls back to case-insensitive <words> text matching only when no
        <sound> element exists at all - real files (including MuseScore's
        own test corpus) sometimes carry only the printed words with no
        playback-oriented <sound> attributes.
        """
        sound_el = direction_elem.find("sound")
        if sound_el is not None:
            attrib = sound_el.attrib
            if "segno" in attrib:
                scan.segno_marks.append(SegnoMark(measure=m_num, label=attrib.get("segno") or "1"))
            if "coda" in attrib:
                scan.coda_marks.append(CodaMark(measure=m_num, label=attrib.get("coda") or "1"))
            if "dacapo" in attrib:
                scan.navigation_jumps.append(
                    NavigationJump(measure=m_num, kind="dacapo", target_label=None)
                )
            if "dalsegno" in attrib:
                scan.navigation_jumps.append(
                    NavigationJump(measure=m_num, kind="dalsegno", target_label=attrib.get("dalsegno") or "1")
                )
            if "tocoda" in attrib:
                scan.to_coda_marks.append(ToCodaMark(measure=m_num, label=attrib.get("tocoda") or "1"))
            if "fine" in attrib:
                scan.fine_marks.append(FineMark(measure=m_num))
            return

        dtypes = direction_elem.findall("direction-type")
        if any(dt.find("segno") is not None for dt in dtypes):
            scan.segno_marks.append(SegnoMark(measure=m_num, label="1"))
        if any(dt.find("coda") is not None for dt in dtypes):
            scan.coda_marks.append(CodaMark(measure=m_num, label=""))

        for dt in dtypes:
            words_el = dt.find("words")
            if words_el is None or not words_el.text:
                continue
            self._match_words_jump_mark(words_el.text, m_num, scan)

    @classmethod
    def _is_jump_mark_words(cls, text: str) -> bool:
        """Pure predicate version of the five _match_words_jump_mark
        patterns below, for _is_qualifying_stave_text's dedup check - no
        scan mutation, safe to call from anywhere without touching
        _step_direction_jump_marks' own (first-part-only) control flow."""
        return any(
            p.match(text) is not None
            for p in (
                cls._TO_CODA_WORDS_RE,
                cls._CODA_WORDS_RE,
                cls._DACAPO_WORDS_RE,
                cls._DALSEGNO_WORDS_RE,
                cls._FINE_WORDS_RE,
            )
        )

    @classmethod
    def _match_words_jump_mark(cls, text: str, m_num: int, scan: "_FirstPartScan") -> None:
        """Text-only fallback for a <words> direction with no accompanying
        <sound> element - see _step_direction_jump_marks. Defensive: text
        that doesn't match any known pattern is silently ignored, the same
        "reads don't crash, absence isn't an error" convention every other
        format's parser in this codebase follows."""
        to_coda_match = cls._TO_CODA_WORDS_RE.match(text)
        if to_coda_match:
            scan.to_coda_marks.append(ToCodaMark(measure=m_num, label=to_coda_match.group(1) or ""))
            return

        dacapo_match = cls._DACAPO_WORDS_RE.match(text)
        if dacapo_match:
            scan.navigation_jumps.append(
                NavigationJump(measure=m_num, kind="dacapo", target_label=None)
            )
            return

        dalsegno_match = cls._DALSEGNO_WORDS_RE.match(text)
        if dalsegno_match:
            scan.navigation_jumps.append(
                NavigationJump(measure=m_num, kind="dalsegno", target_label="1")
            )
            return

        if cls._FINE_WORDS_RE.match(text):
            scan.fine_marks.append(FineMark(measure=m_num))
            return

        # Tried last: a bare "Coda"/"Coda II" label under a <coda/> sign
        # already recorded above (or, rarely, standing in for it in a
        # file with no sign glyph at all) would otherwise never be
        # captured with its printed label.
        coda_match = cls._CODA_WORDS_RE.match(text)
        if coda_match:
            scan.coda_marks.append(CodaMark(measure=m_num, label=coda_match.group(1) or ""))

    @staticmethod
    def _tempo_change_from_direction(
        elem, m_num: int, walker: "_MeasureOffsetWalker", measure_start_quarters: Dict[int, float]
    ) -> Optional[TempoChange]:
        sound_el = elem.find("sound")
        metronome_el = elem.find("direction-type/metronome")
        if sound_el is None or metronome_el is None:
            return None
        tempo_attr = sound_el.attrib.get("tempo")
        beat_unit_el = metronome_el.find("beat-unit")
        per_minute_el = metronome_el.find("per-minute")
        if not tempo_attr or beat_unit_el is None or not beat_unit_el.text or per_minute_el is None or not per_minute_el.text:
            return None

        try:
            tempo_bpm = float(tempo_attr)
            per_minute = float(per_minute_el.text.strip())
        except ValueError:
            return None

        dots = len(metronome_el.findall("beat-unit-dot"))
        beat_unit_ql = beat_unit_quarter_length(beat_unit_el.text.strip(), dots)
        offset_q = walker.offset_divs / walker.divisions

        return TempoChange(
            quarters_from_start=measure_start_quarters.get(m_num, 0.0) + offset_q,
            tempo_bpm=int(round(tempo_bpm)),
            beat_unit_quarter_length=beat_unit_ql,
            beat_unit_name=beat_unit_display_name(beat_unit_el.text.strip(), dots),
            display_number=str(int(per_minute)) if per_minute.is_integer() else str(per_minute),
        )

    def _detect_pickup(self, root) -> Tuple[int, bool, float]:
        """Ref 17: is the first measure a pickup, and if so how full is it
        (in quarters)? Walks only the first <measure>, using staff-1
        non-chord notes to measure how much of a bar it contains.

        Returns (first_measure_number, needs_reindex, pickup_filled_quarters),
        the last two being False/0.0 for a full first bar so callers can use
        them unconditionally.
        """
        first_measure = root.find(".//part/measure")
        is_pickup = False
        pickup_filled_quarters = 0.0
        first_measure_number = 1

        if first_measure is None:
            return first_measure_number, False, pickup_filled_quarters

        # Raw, not _measure_number: this pass DECIDES needs_reindex, so it
        # must read the number as the file spells it.
        first_measure_number = _raw_measure_number(first_measure)

        if first_measure.attrib.get("implicit") == "yes":
            is_pickup = True

        walker = _MeasureOffsetWalker(divisions=1, ts_num=4, ts_den=4)
        max_offset = 0

        for elem in first_measure:
            result = walker.step(elem)
            if result is None:
                continue
            note_offset_divs, is_chord = result
            if is_chord:
                continue

            staff = elem.find("staff")
            staff_id = int(staff.text.strip()) if staff is not None and staff.text else 1
            if staff_id == 1:
                max_offset = max(max_offset, walker.offset_divs)

        det_full_bar_quarters = walker.ts_num * (4.0 / walker.ts_den)
        pickup_filled_quarters = max_offset / walker.divisions

        if 0 < pickup_filled_quarters < det_full_bar_quarters:
            is_pickup = True

        # Two exporter conventions for the pickup: numbered 1 (re-index
        # every measure down by one so it lands on 0) or already numbered 0
        # (leave numbering alone - subtracting again would land it on -1).
        needs_reindex = is_pickup and first_measure_number != 0

        return first_measure_number, needs_reindex, pickup_filled_quarters
