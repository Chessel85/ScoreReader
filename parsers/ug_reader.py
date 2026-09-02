# parsers/ug_reader.py
from models.music_data import MusicData
from models.parts_structure import PartStructureInfo
from models.synthetic_parts import (
    CHORDS_PART_ID,
    CHORDS_PART_NAME,
    LYRICS_PART_ID,
    LYRICS_PART_NAME,
    TAB_PART_ID,
    TAB_PART_NAME,
)
from models.strum_codes import strumming_pattern_text
from parsers.ug_source import UgSource, read_ug_source, read_ug_source_file
from parsers.ug_timeline_builder import content_part_summary, count_tablature_blocks


def _capo_text(capo: int) -> str:
    """"2nd fret" / "1st fret" / ..."""
    suffix = "th"
    if capo % 100 not in (11, 12, 13):
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(capo % 10, "th")
    return f"{capo}{suffix} fret"


def _strumming_credit(patterns) -> str:
    """The Region 1 "Strumming Pattern" credit. A single unnamed pattern
    shows the decoded stroke-word list it always showed; anything else lists
    the pattern names (the full slot detail is in Tools > Strumming
    Patterns, which can't be read comfortably from one status-bar line)."""
    if not patterns:
        return ""
    if len(patterns) == 1 and not patterns[0].name:
        return strumming_pattern_text(patterns[0].codes) or ""
    return ", ".join(p.name or "Unnamed" for p in patterns)



def _build_music_data(source: UgSource, file_path: str) -> MusicData:
    """Shared by UgReader (network) and UgFileReader (a previously-saved
    .ug file) - both just need to get hold of a UgSource by whatever means,
    then build MusicData identically, so a saved-and-reopened import can
    never drift from how the original live import looked."""
    has_chords, has_tab = content_part_summary(source.content)
    parts_info = _build_parts_info(has_chords, has_tab)

    patterns = source.strum_patterns
    first = patterns[0] if patterns else None
    tempo_bpm = (first.bpm if first and first.bpm else None) or 120
    tempo_display = f"{tempo_bpm} quarter notes per minute"
    if first and first.is_triplet:
        tempo_display += " (shuffle feel)"

    credits = {
        "Title": source.song_name,
        "Artist": source.artist_name,
    }
    if source.tab_type and source.tab_type != "Chords":
        credits["Source"] = f"Ultimate Guitar {source.tab_type} tab"
    if source.tonality:
        credits["Key Signature"] = source.tonality
    if source.tuning:
        credits["Tuning"] = source.tuning
    if source.capo:
        credits["Capo"] = _capo_text(source.capo)
    if source.difficulty:
        credits["Difficulty"] = source.difficulty
    strumming_text = _strumming_credit(patterns)
    if strumming_text:
        credits["Strumming Pattern"] = strumming_text
    tab_bars = count_tablature_blocks(source.content)
    if has_tab and tab_bars:
        credits["Tablature"] = f"{tab_bars} bars imported"
    credits["Tempo"] = tempo_display
    if source.tab_id:
        credits["Ultimate Guitar ID"] = str(source.tab_id)

    music_data = MusicData(
        credits=credits,
        parts_info=parts_info,
        file_path=file_path,
        score=None,
        tempo_bpm=tempo_bpm,
        tempo_beat_unit_quarter_length=1.0,
        tempo_beat_unit_name="quarter",
        ug_source=source,
    )

    if has_tab:
        # Ref 15 AC4-style default: the Tablature voice should speak its
        # note, string, fret and duration immediately, without the user
        # reaching for the F1 attribute menu first (mirrors GpReader's
        # synthetic Chords voice seeding).
        music_data.voice_display_attributes[(TAB_PART_ID, 1, 1)] = {
            "step", "string", "fret", "duration",
        }

    return music_data


def _build_parts_info(has_chords: bool, has_tab: bool) -> list:
    parts = []
    if has_chords or not has_tab:
        parts.append(PartStructureInfo(
            part_id=CHORDS_PART_ID,
            name=CHORDS_PART_NAME,
            gmidi_program=25,  # Acoustic Guitar (nylon) - same default PartStructureInfo itself uses
            staves_clefs={1: "Chord chart"},
            staves_voices={1: [1]},
        ))
        parts.append(PartStructureInfo(
            part_id=LYRICS_PART_ID,
            name=LYRICS_PART_NAME,
            gmidi_program=25,  # unused - the Lyrics part never carries a real midi_pitch/chord_pitches
            staves_clefs={1: "Lyrics"},
            staves_voices={1: [1]},
        ))
    if has_tab:
        parts.append(PartStructureInfo(
            part_id=TAB_PART_ID,
            name=TAB_PART_NAME,
            gmidi_program=26,  # Acoustic Guitar (steel)
            staves_clefs={1: "Tab stave"},
            staves_voices={1: [1]},
        ))
    return parts


class UgReader:
    """Parses an Ultimate Guitar chord-tab URL into MusicData - the UG
    counterpart of MusicXMLReader/MidiReader/GpReader. Unlike those three,
    there is nothing to gracefully degrade to on failure (a bad file still
    has real notes to show; a page that fails to fetch/parse/validate has
    nothing) - read_ug_source's exceptions are left to propagate rather than
    caught into an empty fallback, so the load thread's failed signal
    carries the real reason.

    Builds two synthetic parts, each with exactly one staff and one voice -
    not zero. A part with no staff/voice nodes at all would never appear in
    Region2HierarchyModel.get_active_voice_tuples() (which only finds a
    voice by walking down to a real voice node), making it permanently
    invisible in Region 3 regardless of its Region 2 on/off state - the same
    gotcha CLAUDE.md documents for MIDI's collapse_to_parts. Region 2's
    display is decluttered the same way MIDI's is: MusicData.is_ug also
    triggers collapse_to_parts in main_window.py's _update_ui_regions.

    file_path is set to a synthetic ultimate-guitar-<tab_id>.ug slug -
    nothing on disk, just enough for MusicData.is_ug/persistence to key off
    until (if ever) the user saves it via Save Ultimate Guitar Import
    As..., which swaps in the real saved path (main_window.py) - see
    UgFileReader below for the counterpart that loads such a saved file."""

    def __init__(self, url: str):
        self.url = url

    def load(self) -> MusicData:
        source = read_ug_source(self.url)
        return _build_music_data(source, f"ultimate-guitar-{source.tab_id}.ug")


class UgFileReader:
    """Parses a previously-saved .ug file into MusicData - the local-file
    counterpart of UgReader, used by workers/score_load_worker.py's
    ScoreLoadThread the same way MidiReader/GpReader are: <Format>Reader
    (path).load(). file_path is the real saved path (not a synthetic slug),
    so .rsc persistence/the window title/Edit > Open Local Folder all key
    off it exactly like any other format already does."""

    def __init__(self, file_path: str):
        self.file_path = file_path

    def load(self) -> MusicData:
        source = read_ug_source_file(self.file_path)
        return _build_music_data(source, self.file_path)
