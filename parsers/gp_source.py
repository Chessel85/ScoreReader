# parsers/gp_source.py
"""Raw Guitar Pro (.gp) parsing: unzip the container, parse
Content/score.gpif, and resolve its id-indirection graph (MasterBars -> a
Bar id per track -> a Voice id list per bar -> a Beat id list per voice ->
Rhythm ref + Note id list per beat) into a typed intermediate structure -
the GP counterpart of xml_source.py/midi_source.py. GpReader and
GpTimelineBuilder both read this SAME parse so they can't independently
re-walk the XML and drift (the bug class CLAUDE.md documents
MusicXMLReader's two-pass read once fell into).

Covers the GP7/GP8 zip+XML container - both share one schema (confirmed
against alphaTab's own format docs: GP8 only adds optional elements on top
of GP7's, never renaming/removing anything - see CLAUDE.md). Reads
defensively throughout: an absent element is "not present", never an error,
so an older GP7 file (untested against a real sample; none was available)
is expected to parse the same way, just with fewer optional fields
populated.
"""
import zipfile
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple
from xml.etree import ElementTree as ET

from models.duration_units import beat_unit_quarter_length

SCORE_GPIF_PATH = "Content/score.gpif"

# GP's <NoteValue> text is already almost identical to
# models.duration_units's type-name vocabulary; only the four common ones
# differ by capitalisation. Anything else (rare - 128th/256th) is
# lower-cased through unchanged rather than special-cased.
_NOTE_VALUE_TO_TYPE = {
    "Whole": "whole", "Half": "half", "Quarter": "quarter", "Eighth": "eighth",
}


@dataclass
class GpNote:
    string: Optional[int] = None
    fret: Optional[int] = None
    midi_pitch: Optional[int] = None
    # GP's own notated spelling (ConcertPitch/Pitch) - preferred over
    # deriving one from midi_pitch, since GP already did that work.
    step: Optional[str] = None
    accidental: str = ""  # "", "#", "b", "##", "bb" - GP's own vocabulary
    octave: Optional[int] = None
    tie_origin: bool = False
    slide: bool = False
    muted: bool = False


@dataclass
class GpBeat:
    quarter_length: float = 1.0
    duration_type: str = "quarter"
    duration_dots: int = 0
    tuplet_actual: Optional[int] = None
    note_ids: List[int] = field(default_factory=list)
    # Index into the owning track's chord_names dict - None if this beat
    # has no chord-name annotation.
    chord_index: Optional[int] = None
    # "Down"/"Up", only ever set on the rare beat where GP records one -
    # never inferred (see CLAUDE.md / the GP import plan).
    brush_direction: Optional[str] = None
    dynamic: Optional[str] = None  # raw GP text, e.g. "MF", "FFF"


@dataclass
class GpVoice:
    beat_ids: List[int] = field(default_factory=list)


@dataclass
class GpBar:
    voice_ids: List[int] = field(default_factory=list)  # -1 = unused slot


@dataclass
class GpTrack:
    index: int
    name: str
    gmidi_program: int  # 0-indexed, as GP stores it (see GpReader)
    tuning_pitches: List[int] = field(default_factory=list)
    capo_fret: int = 0
    chord_names: Dict[int, str] = field(default_factory=dict)  # diagram id -> name


@dataclass
class GpMasterBar:
    time_sig: Tuple[int, int] = (4, 4)
    key_fifths: int = 0
    # One bar id per track, in Tracks document order - the direct,
    # authoritative way to find a given track's Bar for this measure
    # (rather than inferring contiguous id ranges per track, which nothing
    # in the schema actually guarantees).
    track_bar_ids: List[int] = field(default_factory=list)


@dataclass
class GpSource:
    title: str = ""
    artist: str = ""
    tempo_bpm: int = 120
    tracks: List[GpTrack] = field(default_factory=list)
    master_bars: List[GpMasterBar] = field(default_factory=list)
    bars: Dict[int, GpBar] = field(default_factory=dict)
    voices: Dict[int, GpVoice] = field(default_factory=dict)
    beats: Dict[int, GpBeat] = field(default_factory=dict)
    notes: Dict[int, GpNote] = field(default_factory=dict)


def _cdata_text(el: Optional[ET.Element]) -> str:
    return (el.text or "").strip() if el is not None else ""


def _int_or(el: Optional[ET.Element], default: Optional[int] = None) -> Optional[int]:
    if el is not None and el.text and el.text.strip():
        return int(el.text.strip())
    return default


def _parse_rhythms(root: ET.Element) -> Dict[int, Tuple[str, int, Optional[int]]]:
    """rhythm id -> (type_name, dots, tuplet_actual_notes)."""
    rhythms: Dict[int, Tuple[str, int, Optional[int]]] = {}
    for rhythm_el in root.findall("Rhythms/Rhythm"):
        rhythm_id = int(rhythm_el.get("id"))
        nv_el = rhythm_el.find("NoteValue")
        nv_text = nv_el.text.strip() if (nv_el is not None and nv_el.text) else "Quarter"
        type_name = _NOTE_VALUE_TO_TYPE.get(nv_text, nv_text.lower())
        dot_el = rhythm_el.find("AugmentationDot")
        dots = int(dot_el.get("count", "0")) if dot_el is not None else 0
        tuplet_el = rhythm_el.find("PrimaryTuplet")
        tuplet_actual = int(tuplet_el.get("num")) if tuplet_el is not None else None
        rhythms[rhythm_id] = (type_name, dots, tuplet_actual)
    return rhythms


def _parse_tracks(root: ET.Element) -> List[GpTrack]:
    tracks: List[GpTrack] = []
    for track_index, track_el in enumerate(root.findall("Tracks/Track")):
        name = _cdata_text(track_el.find("Name")) or f"Track {track_index + 1}"

        program = 0
        program_el = track_el.find("Sounds/Sound/MIDI/Program")
        if program_el is not None and program_el.text:
            program = int(program_el.text.strip())

        tuning_pitches: List[int] = []
        capo_fret = 0
        chord_names: Dict[int, str] = {}
        for prop_el in track_el.findall("Staves/Staff/Properties/Property"):
            pname = prop_el.get("name")
            if pname == "Tuning":
                pitches_el = prop_el.find("Pitches")
                if pitches_el is not None and pitches_el.text:
                    tuning_pitches = [int(p) for p in pitches_el.text.split()]
            elif pname == "CapoFret":
                capo_fret = _int_or(prop_el.find("Fret"), 0)
            elif pname == "DiagramCollection":
                for item_el in prop_el.findall("Items/Item"):
                    item_id = item_el.get("id")
                    item_name = item_el.get("name")
                    if item_id is not None and item_name is not None:
                        chord_names[int(item_id)] = item_name

        tracks.append(GpTrack(
            index=track_index,
            name=name,
            gmidi_program=program,
            tuning_pitches=tuning_pitches,
            capo_fret=capo_fret,
            chord_names=chord_names,
        ))
    return tracks


def _parse_master_bars(root: ET.Element) -> List[GpMasterBar]:
    master_bars: List[GpMasterBar] = []
    for mb_el in root.findall("MasterBars/MasterBar"):
        time_el = mb_el.find("Time")
        if time_el is not None and time_el.text and "/" in time_el.text:
            num_str, den_str = time_el.text.strip().split("/")
            time_sig = (int(num_str), int(den_str))
        else:
            time_sig = (4, 4)

        # AccidentalCount is unsigned; TransposeAs says which side of the
        # circle of fifths it's on - the same (sharps positive, flats
        # negative) convention MusicXML's <fifths> and this codebase's
        # FIFTHS_MAP already use.
        key_fifths = 0
        acc_count_el = mb_el.find("Key/AccidentalCount")
        if acc_count_el is not None and acc_count_el.text:
            key_fifths = int(acc_count_el.text.strip())
            transpose_el = mb_el.find("Key/TransposeAs")
            if transpose_el is not None and transpose_el.text == "Flats":
                key_fifths = -key_fifths

        bars_el = mb_el.find("Bars")
        track_bar_ids = (
            [int(b) for b in bars_el.text.split()] if (bars_el is not None and bars_el.text) else []
        )
        master_bars.append(GpMasterBar(time_sig=time_sig, key_fifths=key_fifths, track_bar_ids=track_bar_ids))
    return master_bars


def _parse_bars(root: ET.Element) -> Dict[int, GpBar]:
    bars: Dict[int, GpBar] = {}
    for bar_el in root.findall("Bars/Bar"):
        bar_id = int(bar_el.get("id"))
        voices_el = bar_el.find("Voices")
        voice_ids = (
            [int(v) for v in voices_el.text.split()] if (voices_el is not None and voices_el.text) else []
        )
        bars[bar_id] = GpBar(voice_ids=voice_ids)
    return bars


def _parse_voices(root: ET.Element) -> Dict[int, GpVoice]:
    voices: Dict[int, GpVoice] = {}
    for voice_el in root.findall("Voices/Voice"):
        voice_id = int(voice_el.get("id"))
        beats_el = voice_el.find("Beats")
        beat_ids = (
            [int(b) for b in beats_el.text.split()] if (beats_el is not None and beats_el.text) else []
        )
        voices[voice_id] = GpVoice(beat_ids=beat_ids)
    return voices


def _parse_beats(root: ET.Element, rhythms: Dict[int, Tuple[str, int, Optional[int]]]) -> Dict[int, GpBeat]:
    beats: Dict[int, GpBeat] = {}
    for beat_el in root.findall("Beats/Beat"):
        beat_id = int(beat_el.get("id"))

        rhythm_ref_el = beat_el.find("Rhythm")
        rhythm_id = int(rhythm_ref_el.get("ref")) if rhythm_ref_el is not None else None
        type_name, dots, tuplet_actual = rhythms.get(rhythm_id, ("quarter", 0, None))
        quarter_length = beat_unit_quarter_length(type_name, dots)
        if tuplet_actual:
            # GP tuplets only ever record the "actual" side (e.g. 3 for a
            # triplet); the implied "normal" side is always one less power
            # relationship - 3:2, 5:4, 6:4, 7:4 - matched by
            # duration_units.tuplet_word's own keys. Using num-1 here would
            # be wrong for non-simple ratios, so multiply by the same 2/3
            # MusicXML's <time-modification> would encode for the common
            # cases actually seen in GP output (triplets).
            tuplet_normal = {3: 2, 5: 4, 6: 4, 7: 4}.get(tuplet_actual, tuplet_actual - 1)
            quarter_length *= tuplet_normal / tuplet_actual

        notes_el = beat_el.find("Notes")
        note_ids = (
            [int(n) for n in notes_el.text.split()] if (notes_el is not None and notes_el.text) else []
        )

        chord_index = None
        chord_el = beat_el.find("Chord")
        if chord_el is not None and chord_el.text and chord_el.text.strip().lstrip("-").isdigit():
            chord_index = int(chord_el.text.strip())

        brush_direction = None
        for prop_el in beat_el.findall("Properties/Property"):
            if prop_el.get("name") == "Brush":
                direction_el = prop_el.find("Direction")
                if direction_el is not None and direction_el.text:
                    brush_direction = direction_el.text.strip()

        dynamic_el = beat_el.find("Dynamic")
        dynamic = dynamic_el.text.strip() if (dynamic_el is not None and dynamic_el.text) else None

        beats[beat_id] = GpBeat(
            quarter_length=quarter_length,
            duration_type=type_name,
            duration_dots=dots,
            tuplet_actual=tuplet_actual,
            note_ids=note_ids,
            chord_index=chord_index,
            brush_direction=brush_direction,
            dynamic=dynamic,
        )
    return beats


def _parse_notes(root: ET.Element) -> Dict[int, GpNote]:
    notes: Dict[int, GpNote] = {}
    for note_el in root.findall("Notes/Note"):
        note_id = int(note_el.get("id"))
        string_num = fret = midi_pitch = octave = None
        step = None
        accidental = ""
        slide = muted = False

        for prop_el in note_el.findall("Properties/Property"):
            pname = prop_el.get("name")
            if pname == "String":
                string_num = _int_or(prop_el.find("String"))
            elif pname == "Fret":
                fret = _int_or(prop_el.find("Fret"))
            elif pname == "Midi":
                midi_pitch = _int_or(prop_el.find("Number"))
            elif pname == "ConcertPitch":
                pitch_el = prop_el.find("Pitch")
                if pitch_el is not None:
                    step_el = pitch_el.find("Step")
                    step = step_el.text.strip() if (step_el is not None and step_el.text) else None
                    acc_el = pitch_el.find("Accidental")
                    accidental = (acc_el.text or "").strip() if acc_el is not None else ""
                    octave = _int_or(pitch_el.find("Octave"))
            elif pname == "Slide":
                slide = True
            elif pname == "Muted":
                muted = True

        tie_el = note_el.find("Tie")
        tie_origin = tie_el is not None and tie_el.get("origin") == "true"

        notes[note_id] = GpNote(
            string=string_num, fret=fret, midi_pitch=midi_pitch,
            step=step, accidental=accidental, octave=octave,
            tie_origin=tie_origin, slide=slide, muted=muted,
        )
    return notes


def read_gp_source(file_path: str) -> GpSource:
    with zipfile.ZipFile(file_path) as zf:
        with zf.open(SCORE_GPIF_PATH) as f:
            root = ET.parse(f).getroot()

    score_el = root.find("Score")
    title = _cdata_text(score_el.find("Title")) if score_el is not None else ""
    artist = _cdata_text(score_el.find("Artist")) if score_el is not None else ""

    tempo_bpm = 120
    for automation_el in root.findall("MasterTrack/Automations/Automation"):
        type_el = automation_el.find("Type")
        if type_el is not None and type_el.text == "Tempo":
            value_el = automation_el.find("Value")
            if value_el is not None and value_el.text:
                # "126 2" - bpm, then a linear-automation flag not needed here.
                tempo_bpm = round(float(value_el.text.split()[0]))
            break

    rhythms = _parse_rhythms(root)

    return GpSource(
        title=title,
        artist=artist,
        tempo_bpm=tempo_bpm,
        tracks=_parse_tracks(root),
        master_bars=_parse_master_bars(root),
        bars=_parse_bars(root),
        voices=_parse_voices(root),
        beats=_parse_beats(root, rhythms),
        notes=_parse_notes(root),
    )


def iter_track_positions(source: GpSource, track_index: int) -> Iterator[Tuple[int, int, int]]:
    """Yields (measure_index, voice_slot, beat_id) for every beat position
    of the given track, across all master bars, in performance order.
    voice_slot is 0-indexed (GP's own <Voices> slot position within a bar).

    beat_id can repeat across positions: GP dedupes identical beat content
    (same rhythm/notes/properties) into one shared <Beat id> reused from
    multiple voice positions - confirmed against the real sample file, where
    a held chord re-struck with identical content shares one beat id across
    several onsets in the same bar. Callers must treat each YIELDED position
    as its own event, never collapse by beat_id.

    Shared by GpReader (a lightweight pass to find used voice slots and
    chord/brush-qualifying tracks) and GpTimelineBuilder (the full note
    walk), so the two can't independently re-walk this graph and drift."""
    for measure_index, master_bar in enumerate(source.master_bars):
        if track_index >= len(master_bar.track_bar_ids):
            continue
        bar = source.bars.get(master_bar.track_bar_ids[track_index])
        if bar is None:
            continue
        for voice_slot, voice_id in enumerate(bar.voice_ids):
            if voice_id == -1:
                continue
            voice = source.voices.get(voice_id)
            if voice is None:
                continue
            for beat_id in voice.beat_ids:
                yield measure_index, voice_slot, beat_id
