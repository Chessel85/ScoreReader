# parsers/timeline_builder.py
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from music21 import harmony as harmony21

from models.duration_units import (
    beat_unit_display_name,
    beat_unit_quarter_length,
    quarter_length_to_display_name,
    tuplet_word,
)
from models.ending_span import EndingSpan
from models.event_slice import EventSlice
from models.hairpin_span import HairpinSpan
from models.note_data import NoteData
from models.parts_structure import PartStructureInfo
from models.repeat_span import RepeatSpan
from models.tempo_change import TempoChange
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
CHORDS_PART_ID = "chords"
CHORDS_PART_NAME = "Chords"
LYRICS_PART_ID = "lyrics"
LYRICS_PART_NAME = "Lyrics"


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
        root = self._root
        if root is None:
            try:
                root = read_musicxml_root(self.file_path)
            except Exception as e:
                print(f"[ERROR] Failed to parse XML for timeline: {e}")
                return []

        default_part_name = self.parts_info[0].name if self.parts_info else "Classical Guitar"
        part_names = self._part_names(root, default_part_name)

        first_measure_number, needs_reindex, pickup_filled_quarters = self._detect_pickup(root)
        scan = self._scan_first_part(root, needs_reindex, pickup_filled_quarters)
        measure_start_quarters = scan.measure_start_quarters
        measure_ts_fifths = scan.measure_ts_fifths
        self.tempo_changes = scan.tempo_changes
        self.repeat_spans = scan.repeat_spans
        self.ending_spans = scan.ending_spans
        self.hairpin_spans = scan.hairpin_spans
        self.total_measures = max(measure_start_quarters.keys()) if measure_start_quarters else 0

        buckets: Dict[Tuple[int, float], List[NoteData]] = {}
        # Time signature + key fifths at each (measure, offset), stamped
        # onto the EventSlice. Tracked alongside the buckets because a
        # slice's state isn't known until every part's notes are visited.
        slice_state: Dict[Tuple[int, float], Tuple[Tuple[int, int], int]] = {}

        for part in root.findall("part"):
            part_id = part.attrib.get("id", "")
            part_name = part_names.get(part_id, default_part_name)

            divisions, time_sig_num, time_sig_den, fifths = 1, 4, 4, 0
            beat_unit_quarter_len = 4.0 / time_sig_den
            full_bar_quarters = time_sig_num * beat_unit_quarter_len

            # Reported: a strum/pick-direction mark reads as belonging to
            # the melody instrument that carries it in the XML (a Piano part
            # here), but conceptually it's a guitar-accompaniment idea, not
            # something a piano does - the user's own steer. So a strum mark
            # produces an extra Chords-part NoteData at that same beat
            # (the sticky current chord, same "last named chord carries
            # forward" convention GP/UG already use for their own Chords
            # voice/part) rather than an attribute on the melody note
            # itself. Sticky state is scoped per part - the real files this
            # was built against carry <harmony> and <notations/arpeggiate>
            # on the same single part, and interleaving it correctly across
            # multiple parts would need the measures walked in time order
            # across parts rather than one part fully at a time.
            current_chord_pitches: Optional[List[int]] = None
            current_chord_label: str = "Strum"
            # Reported: when a bar's own <harmony> lands at the same beat as
            # an arpeggiate-marked note (a bar with no other stroke, so the
            # harmony IS the first note - files/Three Blind Mice.mxl's bar
            # 4), the once-per-bar harmony entry and the stroke entry ended
            # up as two near-identical Chords rows at the same slice ("G,
            # beat position 1.0" right next to "G, beat position 1.0, strum
            # down stroke") - real information, but redundant enough to read
            # as noise ("obfuscated by the presence of the chord", the
            # user's own description). Tracks the harmony NoteData already
            # emitted at each (measure, offset) this part has seen, so a
            # stroke landing on that same slice sets .strum on that SAME
            # NoteData in place instead of adding a second one.
            harmony_notes_by_key: Dict[Tuple[int, float], NoteData] = {}

            for m in part.findall("measure"):
                m_num = _measure_number(m, needs_reindex)

                walker = _MeasureOffsetWalker(divisions, time_sig_num, time_sig_den, fifths)
                # A MuseScore-style dynamics mark is a <direction> SIBLING
                # of <note>, not a child. Keyed by (staff_or_None,
                # offset_divs) so the note at that same offset picks it up -
                # including every note of a chord, which share an offset.
                # Reset per measure; a direction's target is always local.
                pending_dynamics: Dict[Tuple[Optional[int], int], str] = {}

                for elem in m:
                    result = walker.step(elem)

                    if elem.tag == "attributes":
                        beat_unit_quarter_len = 4.0 / walker.ts_den
                        full_bar_quarters = walker.ts_num * beat_unit_quarter_len

                    if elem.tag == "direction":
                        dyn_el = elem.find("direction-type/dynamics")
                        if dyn_el is not None and len(dyn_el) > 0:
                            mark_el = dyn_el[0]
                            mark = mark_el.text.strip() if (mark_el.tag == "other-dynamics" and mark_el.text) else mark_el.tag
                            dir_staff_el = elem.find("staff")
                            dir_staff = int(dir_staff_el.text.strip()) if (dir_staff_el is not None and dir_staff_el.text) else None
                            pending_dynamics[(dir_staff, walker.offset_divs)] = dynamic_name(mark)

                    if elem.tag == "harmony":
                        # <harmony> is a <measure> child like <direction>,
                        # not a <note> child - walker.step() already
                        # returned None for it, so it never advances
                        # offset_divs itself. An <offset> child (rare;
                        # absent in every file seen so far) displaces it
                        # from the current cursor position, same convention
                        # MusicXML uses for <direction>.
                        offset_el = elem.find("offset")
                        harmony_offset_divs = walker.offset_divs
                        if offset_el is not None and offset_el.text:
                            try:
                                harmony_offset_divs += int(offset_el.text.strip())
                            except ValueError:
                                pass
                        chord_pitches, chord_label = _resolve_harmony(elem)
                        if chord_pitches:
                            current_chord_pitches = chord_pitches
                            current_chord_label = chord_label
                            h_offset_q = harmony_offset_divs / walker.divisions
                            if m_num == 0:
                                h_start_beat = self._start_beat(
                                    full_bar_quarters, pickup_filled_quarters, beat_unit_quarter_len
                                )
                                h_beat_pos = h_start_beat + (h_offset_q / beat_unit_quarter_len)
                            else:
                                h_beat_pos = 1.0 + (h_offset_q / beat_unit_quarter_len)
                            chord_note = NoteData(
                                step_name=chord_label,
                                octave=None,
                                midi_pitch=max(chord_pitches),
                                measure=m_num,
                                beat_position=round(h_beat_pos, 2),
                                ts_duration=float(walker.ts_num),
                                quarter_length=full_bar_quarters,
                                part_id=CHORDS_PART_ID,
                                part_name=CHORDS_PART_NAME,
                                staff=1,
                                voice=1,
                                chord_pitches=chord_pitches,
                            )
                            h_key = (m_num, round(h_offset_q, 4))
                            buckets.setdefault(h_key, []).append(chord_note)
                            slice_state.setdefault(h_key, ((walker.ts_num, walker.ts_den), walker.fifths))
                            harmony_notes_by_key[h_key] = chord_note

                    if result is None:
                        continue
                    note_offset_divs, is_chord = result

                    is_rest = elem.find("rest") is not None
                    dur_divs = _duration_divs(elem)

                    # The note's own notated shape (<type>/<dot>), not a
                    # reverse-lookup from quarter_length - a tuplet member's
                    # <type> still reads "eighth" even though its actual
                    # sounding duration isn't a clean fraction, which is
                    # exactly what a musician reading the note list wants
                    # ("quaver", not some approximated tuplet fraction).
                    # duration_name_us itself isn't finished until quarter_len
                    # is known below (the <type>-less whole-measure-rest
                    # fallback needs it), so only the raw ingredients are
                    # collected here.
                    type_el = elem.find("type")
                    duration_type = type_el.text.strip() if (type_el is not None and type_el.text) else None
                    duration_dots = len(elem.findall("dot"))
                    time_mod_el = elem.find("time-modification")
                    tuplet_actual_notes = None
                    if time_mod_el is not None:
                        actual_notes_el = time_mod_el.find("actual-notes")
                        if actual_notes_el is not None and actual_notes_el.text:
                            tuplet_actual_notes = int(actual_notes_el.text.strip())

                    staff = int(elem.find("staff").text.strip()) if elem.find("staff") is not None else 1
                    voice = int(elem.find("voice").text.strip()) if elem.find("voice") is not None else 1

                    if is_rest:
                        step_name = "rest"
                        octave = None
                        midi_pitch = None
                        fret = None
                        string_num = None
                        dynamic = None
                        articulation = None
                        fingering = None
                        pluck = None
                        strum = None
                        lyric_text = None
                    else:
                        pitch_el = elem.find("pitch")
                        if pitch_el is None:
                            continue

                        step = pitch_el.find("step").text.strip() if pitch_el.find("step") is not None else "C"
                        octave = int(pitch_el.find("octave").text.strip()) if pitch_el.find("octave") is not None else 4
                        alter_el = pitch_el.find("alter")
                        alter = int(alter_el.text.strip()) if (alter_el is not None and alter_el.text) else 0

                        acc_words = {1: " sharp", -1: " flat", 2: " double sharp", -2: " double flat", 0: ""}
                        step_name = f"{step}{acc_words.get(alter, '')}"

                        step_offsets = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
                        midi_pitch = (octave + 1) * 12 + step_offsets.get(step, 0) + alter

                        fret = None
                        string_num = None
                        fingering = None
                        pluck = None
                        tech_el = elem.find("notations/technical")
                        if tech_el is not None:
                            f_el = tech_el.find("fret")
                            s_el = tech_el.find("string")
                            if f_el is not None and f_el.text:
                                fret = int(f_el.text.strip())
                            if s_el is not None and s_el.text:
                                string_num = int(s_el.text.strip())
                            # MusicXML allows several <fingering>/<pluck>
                            # per note (a rasgueado marks one note p/i/m/a),
                            # so use findall - .find() silently drops
                            # everything after the first.
                            fing_texts = [e.text.strip() for e in tech_el.findall("fingering") if e.text]
                            pluck_texts = [e.text.strip() for e in tech_el.findall("pluck") if e.text]
                            fingering = ", ".join(fing_texts) or None
                            pluck = ", ".join(pluck_texts) or None

                        # Articulations and ornaments get the same
                        # spoken-word treatment, so both are merged into one
                        # comma-joined field.
                        artic_tags = [
                            child.tag
                            for parent_tag in ("articulations", "ornaments")
                            for child in elem.findall(f"notations/{parent_tag}/*")
                        ]
                        articulation = ", ".join(articulation_name(t) for t in artic_tags) or None

                        # A direct notations/dynamics is the rarer exporter
                        # form; being note-specific, it beats an
                        # offset-matched <direction>.
                        note_dyn_el = elem.find("notations/dynamics")
                        if note_dyn_el is not None and len(note_dyn_el) > 0:
                            note_mark_el = note_dyn_el[0]
                            note_mark = (
                                note_mark_el.text.strip()
                                if (note_mark_el.tag == "other-dynamics" and note_mark_el.text)
                                else note_mark_el.tag
                            )
                            dynamic = dynamic_name(note_mark)
                        else:
                            dynamic = pending_dynamics.get((staff, note_offset_divs))
                            if dynamic is None:
                                dynamic = pending_dynamics.get((None, note_offset_divs))

                        # <notations/arpeggiate direction="up"/"down"> on a
                        # single (non-chord) note has no conventional
                        # notation meaning - real arpeggios apply to chords -
                        # so this is read as a per-note pick/strum-direction
                        # indicator instead, the same "down stroke"/
                        # "up stroke" vocabulary Guitar Pro's synthetic
                        # Chords voice already established for NoteData.strum
                        # (see CLAUDE.md). Reported: strumming isn't
                        # something a piano/melody note does - it belongs to
                        # the (guitar) chord accompaniment, so this never
                        # ends up on the melody note's own NoteData; it only
                        # ever triggers an extra Chords-part "stroke" entry
                        # below. Left None (not inferred) when absent, same
                        # "leave unstated" convention.
                        strum = None
                        arpeggiate_el = elem.find("notations/arpeggiate")
                        if arpeggiate_el is not None:
                            arp_direction = arpeggiate_el.attrib.get("direction")
                            if arp_direction == "up":
                                strum = "up stroke"
                            elif arp_direction == "down":
                                strum = "down stroke"

                        # Only the first verse - real files with more than
                        # one <lyric> per note are untested by any fixture
                        # seen so far.
                        lyric_text = None
                        lyric_el = elem.find("lyric")
                        if lyric_el is not None:
                            lyric_text_el = lyric_el.find("text")
                            if lyric_text_el is not None and lyric_text_el.text:
                                lyric_text = lyric_text_el.text.strip()

                    offset_q = note_offset_divs / walker.divisions
                    quarter_len = dur_divs / walker.divisions
                    ts_duration = round(quarter_len / beat_unit_quarter_len, 2)

                    if duration_type is not None:
                        duration_name_us = beat_unit_display_name(duration_type, duration_dots)
                    else:
                        # No <type> in the source XML - chiefly a
                        # whole-measure rest, which MusicXML allows to omit
                        # <type> entirely. Reverse-lookup from the real
                        # quarter-length rather than leaving this note/rest
                        # with no word at all.
                        duration_name_us = quarter_length_to_display_name(quarter_len)
                    if duration_name_us is not None and tuplet_actual_notes is not None:
                        word = tuplet_word(tuplet_actual_notes)
                        if word is not None:
                            duration_name_us = f"{duration_name_us} {word}"

                    if m_num == 0:
                        start_beat = self._start_beat(
                            full_bar_quarters, pickup_filled_quarters, beat_unit_quarter_len
                        )
                        beat_pos = start_beat + (offset_q / beat_unit_quarter_len)
                    else:
                        beat_pos = 1.0 + (offset_q / beat_unit_quarter_len)

                    note_obj = NoteData(
                        step_name=step_name,
                        octave=octave,
                        midi_pitch=midi_pitch,
                        measure=m_num,
                        beat_position=round(beat_pos, 2),
                        ts_duration=ts_duration,
                        quarter_length=quarter_len,
                        part_id=part_id,
                        part_name=part_name,
                        staff=staff,
                        voice=voice,
                        fret=fret,
                        string=string_num,
                        dynamic=dynamic,
                        articulation=articulation,
                        fingering=fingering,
                        pluck=pluck,
                        duration_name_us=duration_name_us,
                    )

                    key = (m_num, round(offset_q, 4))
                    if key not in buckets:
                        buckets[key] = []
                    buckets[key].append(note_obj)
                    slice_state[key] = ((walker.ts_num, walker.ts_den), walker.fifths)

                    if lyric_text is not None:
                        # Bucketed into the SAME slice as the melody note it
                        # came from, unlike parsers/ug_timeline_builder.py's
                        # Lyrics part - MusicXML already gives real per-note
                        # timing, so there is no need to fabricate one bar
                        # per lyric the way UG (plain chord-tab text, no real
                        # positions) has to.
                        lyric_note = NoteData(
                            step_name=lyric_text,
                            octave=None,
                            midi_pitch=None,
                            measure=m_num,
                            beat_position=round(beat_pos, 2),
                            ts_duration=ts_duration,
                            quarter_length=quarter_len,
                            part_id=LYRICS_PART_ID,
                            part_name=LYRICS_PART_NAME,
                            staff=1,
                            voice=1,
                        )
                        buckets[key].append(lyric_note)

                    if strum is not None and current_chord_pitches is not None:
                        # A stroke mark with no chord known yet (arpeggiate
                        # before the piece's first <harmony>) is skipped
                        # rather than fabricating a chord - an untested
                        # edge case in every real file seen so far.
                        #
                        # A stroke landing on the exact same slice as the
                        # bar's own harmony entry (no other note between
                        # them - the harmony IS the stroke's note) sets
                        # .strum on that existing entry rather than adding a
                        # second, near-identical Chords row.
                        existing_harmony_note = harmony_notes_by_key.get(key)
                        if existing_harmony_note is not None:
                            existing_harmony_note.strum = strum
                            continue
                        stroke_note = NoteData(
                            step_name=current_chord_label,
                            octave=None,
                            midi_pitch=max(current_chord_pitches),
                            measure=m_num,
                            beat_position=round(beat_pos, 2),
                            ts_duration=ts_duration,
                            quarter_length=quarter_len,
                            part_id=CHORDS_PART_ID,
                            part_name=CHORDS_PART_NAME,
                            staff=1,
                            voice=1,
                            chord_pitches=current_chord_pitches,
                            strum=strum,
                        )
                        buckets[key].append(stroke_note)

                divisions, time_sig_num, time_sig_den, fifths = (
                    walker.divisions, walker.ts_num, walker.ts_den, walker.fifths
                )

        sorted_keys = sorted(buckets.keys(), key=lambda k: (k[0], k[1]))

        # Region 3/4 must read highest-to-lowest pitch within each
        # instrument, regardless of how the source XML orders a chord's
        # notes (a real MuseScore guitar-tab export was found writing
        # chords lowest-string/lowest-pitch first, reported bug: measures
        # 8-9 of files/bach-bourree-tab/score.xml). Notes are already
        # grouped by part by construction - the loop above finishes one
        # part's measures entirely before starting the next, so entries
        # sharing a bucket never interleave across parts - but a plain
        # pitch-only sort would still break that grouping whenever one
        # part's pitch range overlaps another's. part_order pins each
        # note to its part's position first and sorts by pitch only within
        # that group; ties (e.g. the same chord duplicated across a
        # notation stave and a tab stave) keep their original relative
        # order via Python's stable sort. Rests (midi_pitch None) sort
        # last within their part - they don't sound, so their position
        # among sounding notes doesn't matter. The synthetic Chords/Lyrics
        # parts are appended after every real part's index (not left to the
        # dict.get() fallback of 0 below, which would collide with whichever
        # real part happens to be first) so they always sort after the
        # notated instruments, Chords before Lyrics - the same order
        # MusicXMLReader appends them to parts_info in.
        part_order = {p.attrib.get("id", ""): i for i, p in enumerate(root.findall("part"))}
        part_order[CHORDS_PART_ID] = len(part_order)
        part_order[LYRICS_PART_ID] = len(part_order)

        def _pitch_sort_key(note: NoteData) -> Tuple[int, float]:
            pitch_component = -note.midi_pitch if note.midi_pitch is not None else float("inf")
            return (part_order.get(note.part_id, 0), pitch_component)

        for bucket_notes in buckets.values():
            bucket_notes.sort(key=_pitch_sort_key)

        slices = []
        for m_num, offset_q in sorted_keys:
            notes = buckets[(m_num, offset_q)]
            q_len = min(n.quarter_length for n in notes) if notes else 1.0
            beat_pos = notes[0].beat_position if notes else 1.0
            time_sig, key_fifths = slice_state.get((m_num, offset_q), ((4, 4), 0))

            slices.append(
                EventSlice(
                    measure=m_num,
                    beat_position=beat_pos,
                    quarter_length=q_len,
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
            self._beat_marker_slices(buckets, measure_start_quarters, measure_ts_fifths, pickup_filled_quarters),
            key=lambda s: (s.measure, s.quarters_from_start),
        )

        return slices

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
