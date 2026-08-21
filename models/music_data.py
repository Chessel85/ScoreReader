# models/music_data.py
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from models import vocabulary
from models.coda_mark import CodaMark
from models.ending_span import EndingSpan
from models.event_slice import EventSlice
from models.fine_mark import FineMark
from models.gm_percussion_map import GM_PERCUSSION_BANK, GM_PERCUSSION_PROGRAM, detect_percussion_key_shift
from models.hairpin_span import HairpinSpan
from models.key_signatures import key_signature_display_name
from models.mixer_settings import MixerSettings
from models.navigation_jump import NavigationJump
from models.note_data import NoteData
from models.parts_structure import PartStructureInfo
from models.performance_region_row import PerformanceRegionRow
from models.playback_jump_state import PlaybackJumpState
from models.repeat_span import RepeatSpan
from models.score_config_data import ScoreConfig
from models.segno_mark import SegnoMark
from models.tempo_change import TempoChange
from models.to_coda_mark import ToCodaMark
from parsers.gp_timeline_builder import GpTimelineBuilder
from parsers.midi_timeline_builder import MidiTimelineBuilder, _spell_pitch
from parsers.timeline_builder import CHORDS_PART_ID, LYRICS_PART_ID, TimelineBuilder
from parsers.ug_source import strum_directions
from parsers.ug_timeline_builder import UgTimelineBuilder


@dataclass
class MusicData:
    score: Optional[Any] = None
    credits: Dict[str, str] = field(default_factory=dict)
    parts_info: List[PartStructureInfo] = field(default_factory=list)
    file_path: str = ""
    tempo_bpm: int = 120

    # A9: tempo_bpm is ALWAYS quarter-note BPM (playback timing).
    # tempo_beat_unit_* are the ratio and label converting it back to the
    # score's own beat unit - a score marked eighth=96 has tempo_bpm=48 and
    # quarter_length=0.5, so 48/0.5 = 96, the number the user actually
    # reads. Anything user-facing (Region 1, status bar, tempo dialog, F/S/D)
    # must go through the display units, never the raw quarter BPM.
    tempo_beat_unit_quarter_length: float = 1.0
    tempo_beat_unit_name: str = "quarter"

    # Ref 12 AC1: a temporary offset from the score's tempo, never a
    # mutation of tempo_bpm - Region 1 keeps showing the score's own tempo.
    # Stored in DISPLAY units (see above) so F/S's "+10" means +10 of what
    # the user reads.
    playback_tempo_offset: float = 0.0

    # Ref 12 multi-tempo scope: every tempo marking after the first, sorted
    # by position, from TimelineBuilder. tempo_bpm above stays the OPENING
    # tempo (Region 1's summary); this list is what lets the status bar,
    # dialog and Sequencer use the tempo actually in effect at a position.
    tempo_changes: List[TempoChange] = field(default_factory=list)

    # Pre-parsed ElementTree root from MusicXMLReader, so TimelineBuilder
    # need not re-parse. None when MusicData(file_path=...) is built
    # directly, in which case TimelineBuilder parses the file itself.
    xml_root: Optional[Any] = None

    # Pre-parsed MidiSource from MidiReader (parsers/midi_source.py), the
    # MIDI counterpart of xml_root - same reasoning, same fallback when None.
    midi_source: Optional[Any] = None

    # Pre-parsed GpSource from GpReader (parsers/gp_source.py), the Guitar
    # Pro counterpart of xml_root/midi_source - same reasoning, same
    # fallback when None.
    gp_source: Optional[Any] = None

    # Pre-parsed UgSource from UgReader (parsers/ug_source.py), the
    # Ultimate Guitar counterpart of xml_root/midi_source/gp_source. Unlike
    # those three, there is no fallback re-parse from file_path alone - a UG
    # import's file_path is a synthetic slug with nothing fetchable at it
    # (see UgReader/UgTimelineBuilder), so this must always be provided.
    ug_source: Optional[Any] = None

    timeline_slices: List[EventSlice] = field(default_factory=list)
    active_event_index: int = 0

    # (part_id, staff, voice) tuples currently shown/played (Ref 7).
    # None means unfiltered. Must default to None, NOT an empty set - an
    # empty set means "nothing visible", and callers that never set a filter
    # expect the full note list.
    active_voice_filter: Optional[Set[Tuple[str, int, int]]] = None

    # Ref 15 AC4: which optional attributes each voice shows in Region 3.
    # A voice absent from this dict falls back to DEFAULT_DISPLAY_ATTRIBUTES,
    # NOT an empty set - most voices are never touched by the context menu
    # and must keep showing the plain note name.
    voice_display_attributes: Dict[Tuple[str, int, int], Set[str]] = field(default_factory=dict)

    # F2/Ref 15 AC4: the live, mutable rendering order Region 3/4 both read.
    # Defaults empty rather than to DISPLAY_ATTRIBUTE_ORDER because that
    # constant is defined further down the class body and isn't bound yet
    # here; __post_init__ fills it in, so "empty" never escapes.
    attribute_order: List[str] = field(default_factory=list)

    # Ref 14: gates both whether a beat sounds a click and whether a beat
    # with no note counts as a navigable event at all (_slice_is_navigable,
    # AC4). Off by default per load - MusicData is rebuilt on every load, so
    # nothing needs an explicit reset.
    metronome_enabled: bool = False

    # Ref 28: unlike metronome_enabled, toggling this never touches
    # timeline_slices - AC5 requires the announcer to speak only where an
    # event already exists and never create one, so there is nothing to
    # splice in or out.
    position_announcer_enabled: bool = False

    # Wishlist #4: per-score volume/pan overrides, live on MusicData like
    # every other per-score setting above - export_config()/apply_config()
    # carry it the same way, so it survives a load/save round trip instead
    # of being read once at load and discarded (which is what happened
    # before this field existed: PlaybackController.attach_score received a
    # mixer only as a local variable, and the next save silently wrote back
    # an empty one).
    mixer: MixerSettings = field(default_factory=MixerSettings)

    # S5: per-part display-name/instrument overrides the user set via
    # widgets/instrument_dialog.py, keyed by part_id. Bookkeeping only -
    # apply_part_overrides() is what actually mutates parts_info/NoteData -
    # kept so export_config() can persist exactly what was overridden
    # rather than every part's current value, same "explicit overrides
    # only" shape as mixer above.
    part_name_overrides: Dict[str, str] = field(default_factory=dict)
    part_program_overrides: Dict[str, int] = field(default_factory=dict)

    # Wishlist #8 follow-up: per-percussion-item playback/name overrides,
    # set via widgets/instrument_dialog.py, same "explicit overrides only"
    # bookkeeping shape as the two above. Keyed by (part_id, the item's
    # ORIGINAL file-declared key - NoteData.percussion_source_key), NOT by
    # its current display name - a name is itself overridable
    # (percussion_item_name_overrides), and keying by name would orphan a
    # sound override the moment the item was renamed.
    percussion_item_overrides: Dict[Tuple[str, int], int] = field(default_factory=dict)
    percussion_item_name_overrides: Dict[Tuple[str, int], str] = field(default_factory=dict)
    # "Apply MusicXML offset for percussion" (Edit > Instruments...) -
    # best-effort auto-correction, cross-referencing each percussion item's
    # OWN declared name against its OWN declared key via
    # models.gm_percussion_map.gm_percussion_key_for_name. Off by default -
    # every other override in this app starts as "nothing changed" and this
    # is no different, even though the file that motivated it (Hit It.mxl)
    # needed it for every one of its percussion instruments. MusicXML-only
    # in effect: a MIDI note's name is already DERIVED from its key
    # (gm_percussion_name), so there is nothing for it to disagree with -
    # see apply_percussion_overrides.
    percussion_auto_correct_enabled: bool = False

    # S6: a single whole-piece key signature override, set via the
    # Instruments & Key dialog. None means "use the file's own key(s)".
    key_signature_override_fifths: Optional[int] = None
    key_signature_override_mode: Optional[str] = None

    # F4/D-6: UK vs US terminology. main_window.py owns the real startup
    # default (OS-locale-detected) and re-applies it after every load, since
    # MusicData is wholly replaced then and this is a session preference,
    # not a per-score one like metronome_enabled.
    uk_terms: bool = False

    # Ref 29: repeat-barline pairs, 1st/2nd endings and hairpins, from
    # TimelineBuilder, same side-channel pattern as tempo_changes above.
    # total_measures is the whole-score bar count for the Performance
    # Report - NOT derived from timeline_slices, which would undercount a
    # trailing all-rest measure.
    repeat_spans: List[RepeatSpan] = field(default_factory=list)
    ending_spans: List[EndingSpan] = field(default_factory=list)
    hairpin_spans: List[HairpinSpan] = field(default_factory=list)
    total_measures: int = 0

    # Segno/Coda/D.C./D.S./Fine navigation marks, same side-channel pattern
    # as repeat_spans/ending_spans/hairpin_spans above. MusicXML-only, like
    # every other field on this line - MIDI/GP/UG builders stub these to
    # empty lists (see e.g. parsers/midi_timeline_builder.py). Consumed by
    # next_playback_index (playback/preview repeat-and-jump stepping) and
    # get_performance_region_rows/get_performance_report_lines (display).
    segno_marks: List[SegnoMark] = field(default_factory=list)
    coda_marks: List[CodaMark] = field(default_factory=list)
    to_coda_marks: List[ToCodaMark] = field(default_factory=list)
    fine_marks: List[FineMark] = field(default_factory=list)
    navigation_jumps: List[NavigationJump] = field(default_factory=list)

    @property
    def is_midi(self) -> bool:
        """True for a score loaded from a Standard MIDI File, as opposed to
        MusicXML - the same extension check __post_init__ uses to pick a
        timeline builder, exposed once here so other call sites (Ref 25/S2's
        Region 2 collapse) don't each repeat it."""
        return self.file_path.lower().endswith((".mid", ".midi"))

    @property
    def is_gp(self) -> bool:
        """True for a score loaded from a Guitar Pro (.gp) file - the same
        extension check __post_init__ uses to pick a timeline builder."""
        return self.file_path.lower().endswith(".gp")

    @property
    def is_ug(self) -> bool:
        """True for a score imported from Ultimate Guitar - the same
        synthetic-extension check __post_init__ uses to pick a timeline
        builder (see UgReader for where file_path gets its .ug suffix).
        Also drives Region 2's collapse_to_parts, same as is_midi - both
        of UG's synthetic parts (Chords/Lyrics) are flat, nothing useful to
        toggle below the part level."""
        return self.file_path.lower().endswith(".ug")

    @property
    def collapsed_part_ids(self) -> Union[bool, Set[str]]:
        """Region 2's collapse_to_parts argument (widgets/region2_manager.py):
        True to flatten every part (MIDI, a pure Ultimate Guitar import,
        where a real staff/voice concept doesn't exist anywhere in the
        score), or the specific set of part_ids to flatten for a score that
        mixes real notated parts with synthetic ones - a MusicXML file
        carrying its own <harmony>/<lyric> markup keeps its real
        instrument's staff/voice tree intact and flattens only the
        synthetic Chords/Lyrics parts, whose "Chord chart"/"Voice 1" labels
        have nothing real underneath them (reported: showing them as a
        3-level tree read as redundant, made-up navigation - the same
        "chords don't have layers below them" call already made for GP's
        synthetic Chords voice and a pure UG import's Chords/Lyrics parts).

        Region 2 follow-up (wishlist #8): a MIDI percussion part is no
        longer collapsed - unlike every other MIDI part, its "voices" are
        now real, independently mute/soloable rows (one per distinct
        drum/cymbal, via PartStructureInfo.staves_voices - see
        parsers/midi_reader.py), not a fake single always-voice-1 concept
        with nothing to gain from expanding. Every other MIDI part still
        collapses exactly as before."""
        if self.is_ug:
            return True
        if self.is_midi:
            return {p.part_id for p in self.parts_info if not p.is_percussion}
        return {p.part_id for p in self.parts_info if p.part_id in (CHORDS_PART_ID, LYRICS_PART_ID)}

    @property
    def ug_strum_pattern(self) -> List[str]:
        """The whole-song strum pattern ("down"/"up"/"mute" per stroke),
        decoded from ug_source.strum_codes - empty for a UG tab with no
        strumming block, or any non-UG score. Computed on read rather than
        cached: cheap (a handful of dict lookups over a short list), so
        there's no invalidation concern to manage. Consumed by
        audio/strum_schedule.py's sound_events() to decide whether a UG
        Chords bar plays as a real strummed pattern or a flat chord."""
        if self.ug_source is None:
            return []
        return strum_directions(self.ug_source.strum_codes)

    def __post_init__(self):
        # DISPLAY_ATTRIBUTE_ORDER is the fixed default; attribute_order is
        # the live copy the reorder dialog mutates. A caller-supplied order
        # is honoured as-is.
        if not self.attribute_order:
            self.attribute_order = list(self.DISPLAY_ATTRIBUTE_ORDER)
        if self.file_path:
            if self.is_midi:
                builder = MidiTimelineBuilder(self.file_path, self.parts_info, source=self.midi_source)
            elif self.is_gp:
                builder = GpTimelineBuilder(self.file_path, self.parts_info, source=self.gp_source)
            elif self.is_ug:
                builder = UgTimelineBuilder(self.file_path, self.parts_info, source=self.ug_source)
            else:
                builder = TimelineBuilder(self.file_path, self.parts_info, root=self.xml_root)
            self.timeline_slices = builder.build()
            self.tempo_changes = builder.tempo_changes
            self._beat_markers = builder.beat_markers
            self.repeat_spans = builder.repeat_spans
            self.ending_spans = builder.ending_spans
            self.hairpin_spans = builder.hairpin_spans
            self.segno_marks = builder.segno_marks
            self.coda_marks = builder.coda_marks
            self.to_coda_marks = builder.to_coda_marks
            self.fine_marks = builder.fine_marks
            self.navigation_jumps = builder.navigation_jumps
            self.total_measures = builder.total_measures
            self.active_event_index = 0
            self._set_percussion_voice_names()
        else:
            self._beat_markers: List[EventSlice] = []
        # The real, marker-free timeline, kept stable so
        # set_metronome_enabled can restore exactly this when the metronome
        # goes off again.
        self._real_timeline_slices = self.timeline_slices
        # Safe to cache forever: timeline_slices is never reassigned after
        # this point. The filter-dependent caches are separate, below.
        self._measure_numbers_cache: Optional[List[int]] = None
        self._invalidate_visibility_cache()

    def _invalidate_visibility_cache(self) -> None:
        """These lookups run on every navigation keypress, and the
        by-measure ones once per measure scanned - O(N*M) uncached across a
        long run of filtered-out measures. They depend only on
        active_voice_filter, so they are computed on demand and dropped
        whenever it changes."""
        self._sounding_bounds_cache: Optional[Tuple[int, int]] = None
        self._sounding_bounds_computed: bool = False
        self._first_visible_index_by_measure_cache: Optional[Dict[int, int]] = None
        # Ref 29: same caching rationale, for Region 5's Ctrl+End ("last
        # note of the end bar") lookup.
        self._last_visible_index_by_measure_cache: Optional[Dict[int, int]] = None

    def get_current_slice(self) -> Optional[EventSlice]:
        if 0 <= self.active_event_index < len(self.timeline_slices):
            return self.timeline_slices[self.active_event_index]
        return None

    def _slice_has_visible_notes(self, index: int) -> bool:
        """True if timeline_slices[index] has at least one note passing the
        Region 2 filter (Ref 7). Lets timeline navigation skip slices that
        only contain notes from deactivated parts/staves/voices, so e.g.
        stepping through a still-active semibreve viola part isn't
        interrupted by a deactivated flute's crotchet-rate slices."""
        if not (0 <= index < len(self.timeline_slices)):
            return False
        notes = self.timeline_slices[index].notes
        if not notes:
            return False
        if self.active_voice_filter is None:
            return True
        return any(
            (n.part_id, n.staff, n.voice) in self.active_voice_filter for n in notes
        )

    def set_metronome_enabled(self, enabled: bool) -> None:
        """Ref 14 toggle.

        timeline_slices is rebuilt rather than permanently merged, so with
        the metronome off it holds exactly "one entry per (measure, offset)
        with at least one sounding note" - the invariant the rest of the
        codebase assumes. Turning it on splices in TimelineBuilder's
        synthetic beat markers; turning it off restores the untouched real
        list. Indices shift either way, so the cursor is relocated to the
        equivalent real position rather than left on an arbitrary slice.
        """
        if enabled == self.metronome_enabled:
            return

        current = self.get_current_slice()
        self.metronome_enabled = enabled

        if enabled:
            merged = list(self._real_timeline_slices) + list(self._beat_markers)
            merged.sort(key=lambda s: (s.measure, s.quarters_from_start))
            self.timeline_slices = merged
        else:
            self.timeline_slices = self._real_timeline_slices

        if current is not None and self.timeline_slices:
            # Last slice at or before the current position: an exact match
            # where one exists, else the nearest preceding real event (which
            # is the case when toggling off while sitting on a marker, since
            # markers have no counterpart in the real-only list).
            match_index = 0
            for i, s in enumerate(self.timeline_slices):
                if s.quarters_from_start <= current.quarters_from_start:
                    match_index = i
                else:
                    break
            self.active_event_index = match_index

        self._invalidate_visibility_cache()

    def toggle_metronome(self) -> None:
        self.set_metronome_enabled(not self.metronome_enabled)

    def set_position_announcer_enabled(self, enabled: bool) -> None:
        """Ref 28 toggle. No timeline rebuild/cursor relocation needed,
        unlike set_metronome_enabled - see position_announcer_enabled's own
        comment for why."""
        self.position_announcer_enabled = enabled

    def toggle_position_announcer(self) -> None:
        self.set_position_announcer_enabled(not self.position_announcer_enabled)

    def _slice_is_navigable(self, index: int) -> bool:
        """Ref 14 AC4: with the metronome on, a whole beat is steppable even
        with no note there (whole beats are integers in ts-relative units,
        Ref 18). Used at every navigation/stepping call site, but NOT by
        _sounding_bounds below, which stays anchored to real sounding notes
        so metronome mode can't resurrect trailing rest-only padding."""
        if self._slice_has_visible_notes(index):
            return True
        # Own bounds check: _slice_has_visible_notes returns False both for
        # "out of range" and "nothing visible", so it can't be relied on to
        # have validated the index.
        if not self.metronome_enabled or not (0 <= index < len(self.timeline_slices)):
            return False
        return float(self.timeline_slices[index].beat_position).is_integer()

    def _slice_has_visible_sounding_note(self, index: int) -> bool:
        """True if this slice has a visible note that actually sounds (not a
        rest). Bounds navigation via _sounding_bounds(): a rest between two
        sounding notes stays individually reachable (Ref 16), but a run of
        rests padding the final bar out to full length is not a further
        event to step onto (Ref 2/3/5).
        """
        if not (0 <= index < len(self.timeline_slices)):
            return False
        notes = self.timeline_slices[index].notes
        if self.active_voice_filter is not None:
            notes = [
                n for n in notes
                if (n.part_id, n.staff, n.voice) in self.active_voice_filter
            ]
        return any(n.midi_pitch is not None for n in notes)

    def _sounding_bounds(self) -> Optional[Tuple[int, int]]:
        """(first, last) index of a visible event with a real sounding note.

        This is the true navigable range for Left/Right/Ctrl+Left/Right/
        Home/End - leading or trailing rest-only padding sits outside it.
        None if nothing currently visible sounds at all. Cached per
        active_voice_filter state - see _invalidate_visibility_cache.
        """
        if not self._sounding_bounds_computed:
            first_idx = None
            last_idx = None
            for i in range(len(self.timeline_slices)):
                if self._slice_has_visible_sounding_note(i):
                    if first_idx is None:
                        first_idx = i
                    last_idx = i
            if first_idx is None:
                # Nothing in the current filter actually sounds - e.g. a UG
                # import with only its Lyrics part visible (silent by
                # design, see parsers/ug_timeline_builder.py) and its
                # Chords part switched off in Region 2. Falling back to
                # "has any visible note" bounds means there's still
                # something to navigate - a part with real, visible
                # content should never become entirely unreachable just
                # because none of it makes sound. This is strictly a
                # fallback: whenever anything does sound, the stricter
                # pass above already found real bounds and this branch
                # never runs, so every existing format's trailing-rest-
                # padding exclusion (Ref 2/3/5) is unaffected.
                for i in range(len(self.timeline_slices)):
                    if self._slice_has_visible_notes(i):
                        if first_idx is None:
                            first_idx = i
                        last_idx = i
            self._sounding_bounds_cache = (
                (first_idx, last_idx) if first_idx is not None else None
            )
            self._sounding_bounds_computed = True
        return self._sounding_bounds_cache

    def move_timeline_left(self) -> bool:
        bounds = self._sounding_bounds()
        if bounds is None:
            return False
        first_idx, _ = bounds
        idx = self.active_event_index
        while idx > first_idx:
            idx -= 1
            if self._slice_is_navigable(idx):
                self.active_event_index = idx
                return True
        return False

    def move_timeline_right(self) -> bool:
        bounds = self._sounding_bounds()
        if bounds is None:
            return False
        _, last_idx = bounds
        idx = self.active_event_index
        while idx < last_idx:
            idx += 1
            if self._slice_is_navigable(idx):
                self.active_event_index = idx
                return True
        return False

    def measure_numbers(self) -> List[int]:
        """Distinct measure numbers present in the timeline, in ascending
        order. Cached forever - timeline_slices is fixed after construction."""
        if self._measure_numbers_cache is None:
            self._measure_numbers_cache = list(
                dict.fromkeys(s.measure for s in self.timeline_slices)
            )
        return self._measure_numbers_cache

    def first_event_index_of_measure(self, measure_number: int) -> Optional[int]:
        """Index of the first timeline event in the measure, or None if it
        has none - Ref 6 turns that into a boundary cue and no movement."""
        for i, s in enumerate(self.timeline_slices):
            if s.measure == measure_number:
                return i
        return None

    def last_event_index(self) -> int:
        """Index of the last timeline event, or -1 if the timeline is empty."""
        return len(self.timeline_slices) - 1

    def _first_visible_index_by_measure(self) -> Dict[int, int]:
        """measure_number -> index of its first visible event, cached per
        filter state so move_timeline_*_by_measure's walk is O(1) per
        measure instead of re-scanning the timeline for each one."""
        if self._first_visible_index_by_measure_cache is None:
            cache: Dict[int, int] = {}
            for i, s in enumerate(self.timeline_slices):
                if s.measure not in cache and self._slice_is_navigable(i):
                    cache[s.measure] = i
            self._first_visible_index_by_measure_cache = cache
        return self._first_visible_index_by_measure_cache

    def first_visible_event_index_of_measure(self, measure_number: int) -> Optional[int]:
        """Like first_event_index_of_measure, but skips slices with no note
        passing the active Region 2 filter (Ref 7) - keeps Ctrl+Left/Right
        (C2) sympathetic to what's actually visible, the same way plain
        Left/Right already are via _slice_has_visible_notes."""
        return self._first_visible_index_by_measure().get(measure_number)

    def _last_visible_index_by_measure(self) -> Dict[int, int]:
        """measure_number -> index of its LAST visible event. Region 5's
        Ctrl+End jumps to the last sounding note of a span's end bar; this
        is the only place in the app with that concept."""
        if self._last_visible_index_by_measure_cache is None:
            cache: Dict[int, int] = {}
            for i, s in enumerate(self.timeline_slices):
                if self._slice_is_navigable(i):
                    cache[s.measure] = i
            self._last_visible_index_by_measure_cache = cache
        return self._last_visible_index_by_measure_cache

    def last_visible_event_index_of_measure(self, measure_number: int) -> Optional[int]:
        """Ref 29: like first_visible_event_index_of_measure, but the LAST
        visible event of the measure - Region 5's Ctrl+End target."""
        return self._last_visible_index_by_measure().get(measure_number)

    def slice_index_at_or_after_quarters(self, quarters_from_start: float) -> Optional[int]:
        """First slice index at or after an elapsed-quarters position -
        resolves a hairpin row's jump target, which the measure-only
        lookups can't since a wedge may start or stop mid-measure."""
        for i, s in enumerate(self.timeline_slices):
            if s.quarters_from_start >= quarters_from_start:
                return i
        return None

    def move_timeline_left_by_measure(self) -> bool:
        """Ctrl+Left (Ref 3): to the first visible event of this measure, or
        the previous measure's if already there. The pickup bar needs no
        special case - it is just the first entry in measure_numbers().
        Bounded by _sounding_bounds() like plain Left, so a trailing
        rest-only measure is never a target."""
        current = self.get_current_slice()
        if current is None:
            return False

        bounds = self._sounding_bounds()
        if bounds is None:
            return False
        first_idx, last_idx = bounds

        measures = self.measure_numbers()
        try:
            pos = measures.index(current.measure)
        except ValueError:
            return False

        first_in_current = self.first_visible_event_index_of_measure(current.measure)
        if (
            first_in_current is not None
            and first_idx <= first_in_current <= last_idx
            and self.active_event_index != first_in_current
        ):
            self.active_event_index = first_in_current
            return True

        for prev_measure in reversed(measures[:pos]):
            target = self.first_visible_event_index_of_measure(prev_measure)
            if target is not None and first_idx <= target <= last_idx:
                self.active_event_index = target
                return True
        return False

    def move_timeline_right_by_measure(self) -> bool:
        """Ctrl+Right (Ref 3): jump to the first visible event of the next
        measure, skipping any measure left with no visible events or bounded
        out by _sounding_bounds() (e.g. a trailing rest-only final bar)."""
        current = self.get_current_slice()
        if current is None:
            return False

        bounds = self._sounding_bounds()
        if bounds is None:
            return False
        first_idx, last_idx = bounds

        measures = self.measure_numbers()
        try:
            pos = measures.index(current.measure)
        except ValueError:
            return False

        for next_measure in measures[pos + 1:]:
            target = self.first_visible_event_index_of_measure(next_measure)
            if target is not None and first_idx <= target <= last_idx:
                self.active_event_index = target
                return True
        return False

    def jump_to_measure(self, measure_number: int) -> bool:
        """Ref 6: jump to the first visible event of measure_number, typed
        digit-by-digit in the Note region (C4). Bounded by _sounding_bounds()
        the same way move_timeline_*_by_measure is, so a measure that exists
        only as trailing rest-only padding is not a valid target either.
        False (position unchanged) for an unknown measure number - callers
        play the boundary cue (AC4)."""
        bounds = self._sounding_bounds()
        if bounds is None:
            return False
        first_idx, last_idx = bounds

        target = self.first_visible_event_index_of_measure(measure_number)
        if target is None or not (first_idx <= target <= last_idx):
            return False

        self.active_event_index = target
        return True

    def move_timeline_home(self) -> bool:
        """Home (Ref 5): to the first event with a real sounding note.

        Unlike Left/Right this can never mean "moved past a boundary" - it
        jumps to a known limit - so callers never sound the boundary cue off
        this return value.
        """
        bounds = self._sounding_bounds()
        if bounds is None:
            return False
        self.active_event_index = bounds[0]
        return True

    def last_sounding_event_index(self) -> Optional[int]:
        """The true end of playable content, excluding trailing rest-only
        padding - bounds how far a phrase audition can run, as Home/End
        already bound navigation."""
        bounds = self._sounding_bounds()
        return bounds[1] if bounds else None

    def move_timeline_end(self) -> bool:
        """End (Ref 5): jump to the last event with a real sounding note -
        e.g. a final bar padded out with rests in every voice does not push
        this past the piece's actual last note."""
        bounds = self._sounding_bounds()
        if bounds is None:
            return False
        self.active_event_index = bounds[1]
        return True

    def get_region_1_data(self) -> Dict[str, str]:
        """credits' "Tempo" entry is baked at parse time in US units, so it
        is rebuilt here to reflect a live UK/US toggle without a reload.
        Built from tempo_bpm directly, not the cursor-aware
        tempo_beat_unit_name_at, because Region 1 always shows the score's
        OPENING tempo (A9)."""
        data = dict(self.credits)
        if "Tempo" in data:
            number = self.tempo_bpm / self.tempo_beat_unit_quarter_length
            number_str = str(int(number)) if float(number).is_integer() else str(round(number, 2))
            unit = vocabulary.duration_name(self.tempo_beat_unit_name, self.uk_terms)
            data["Tempo"] = f"{number_str} {unit} notes per minute"
        # S6: same "rebuild live, don't touch the parsed original" pattern
        # as Tempo above.
        if self.key_signature_override_fifths is not None:
            data["Key Signature"] = key_signature_display_name(
                self.key_signature_override_fifths, self.key_signature_override_mode
            )
        return data

    def get_score_structure(self) -> List[Dict[str, Any]]:
        """The parts/staves/voices shape Region2HierarchyModel expects
        (Ref 7). A pure transform of parts_info, no XML access."""
        structure = []
        for p in self.parts_info:
            staves = [
                {
                    "id": s_id,
                    "name": p.staves_clefs.get(s_id, "Standard stave"),
                    "voices": p.staves_voices[s_id],
                    "voice_names": {
                        v_id: p.voice_names[(s_id, v_id)]
                        for v_id in p.staves_voices[s_id]
                        if (s_id, v_id) in p.voice_names
                    },
                }
                for s_id in sorted(p.staves_voices.keys())
            ]
            structure.append({"id": p.part_id, "name": p.name, "staves": staves})
        return structure

    def set_active_voice_filter(self, active_tuples: Set[Tuple[str, int, int]]) -> None:
        self.active_voice_filter = set(active_tuples)
        self._invalidate_visibility_cache()

    def _all_voice_tuples(self) -> Set[Tuple[str, int, int]]:
        """Every (part_id, staff, voice) the score has - the universe
        export_config/apply_config filter saved keys against. Scans the
        notes rather than parts_info, which is only populated by
        MusicXMLReader.load() and so is empty for a directly-built
        MusicData even though the notes are all there."""
        return {
            (n.part_id, n.staff, n.voice)
            for event_slice in self._real_timeline_slices
            for n in event_slice.notes
        }

    def _visible_notes(self, index: Optional[int] = None) -> List[NoteData]:
        """Notes at the given slice passing the Region 2 filter (Ref 7), or
        at the cursor when index is None.

        Every UI-facing accessor reads through this, which is what makes a
        row index mean the same note in Region 3, Region 4 and playback
        alike. The explicit-index form is for the Sequencer, which plays by
        absolute index without disturbing the cursor or Region 3's
        selection (so phrase audition can leave the cursor untouched).
        """
        if index is None:
            current = self.get_current_slice()
        else:
            current = self.timeline_slices[index] if 0 <= index < len(self.timeline_slices) else None
        if not current or not current.notes:
            return []
        if self.active_voice_filter is None:
            return current.notes
        return [
            n for n in current.notes
            if (n.part_id, n.staff, n.voice) in self.active_voice_filter
        ]

    # Ref 15 AC4: the fixed DEFAULT rendering order for Region 3's optional
    # extra attributes and Region 4's rows - every fresh MusicData starts
    # attribute_order (see __post_init__) as a copy of this. F2's
    # attribute-order dialog mutates that live copy, never this constant.
    DISPLAY_ATTRIBUTE_ORDER = [
        "step", "octave", "midi", "measure", "beat position", "duration",
        "part", "stave", "voice", "string", "fret",
        "dynamic", "articulation", "fingering", "pluck", "strum",
    ]
    # A voice with no entry in voice_display_attributes uses this - today's
    # plain-note-name behaviour, not an empty display.
    DEFAULT_DISPLAY_ATTRIBUTES = frozenset({"step"})

    def notes_for_indices(self, selected_indices: List[int]) -> List[NoteData]:
        """The NoteData behind Region 3's selected rows, for callers needing
        the notes themselves rather than indices or pitches."""
        notes = self._visible_notes()
        return [notes[i] for i in selected_indices if 0 <= i < len(notes)]

    def _note_attribute_pairs(self, note: NoteData) -> Dict[str, str]:
        """Attribute name -> value for one note, shared by Region 3 and
        Region 4 so the two can never disagree on a name or value.

        Only keys the note actually has a value for are included (a rest has
        no octave or midi). That absence is the mechanism that stops either
        region rendering a row for data that doesn't exist."""
        if note.duration_name_us is not None:
            dur_str = vocabulary.duration_name(note.duration_name_us, self.uk_terms)
        else:
            # No <type> in the source XML (rare) - fall back to the raw
            # time-signature-relative number rather than guessing a name.
            dur_str = str(int(note.ts_duration)) if note.ts_duration.is_integer() else str(note.ts_duration)
        step_str = note.step_name
        if note.grace_notes:
            # Ref MusicXML <grace> support: "B grace A" rather than a
            # separate phantom chord tone (reported bug - see
            # parsers/timeline_builder.py's pending_grace). Shared by both
            # Region 3 and Region 4 since both read this same "step" pair.
            grace_str = ", ".join(g.step_name for g in note.grace_notes)
            step_str = f"{grace_str} grace {step_str}"
        pairs = {"step": step_str}
        if note.octave is not None:
            pairs["octave"] = str(note.octave)
        if note.midi_pitch is not None:
            pairs["midi"] = str(note.midi_pitch)
        pairs["measure"] = str(note.measure)
        pairs["beat position"] = str(note.beat_position)
        pairs["duration"] = dur_str
        pairs["part"] = note.part_name
        pairs["stave"] = self.get_stave_name_for_part(note.part_id, note.staff)
        pairs["voice"] = str(note.voice)
        if note.string is not None:
            pairs["string"] = str(note.string)
        if note.fret is not None:
            pairs["fret"] = str(note.fret)
        if note.dynamic is not None:
            pairs["dynamic"] = note.dynamic
        if note.articulation is not None:
            pairs["articulation"] = note.articulation
        if note.fingering is not None:
            pairs["fingering"] = note.fingering
        if note.pluck is not None:
            pairs["pluck"] = note.pluck
        if note.strum is not None:
            pairs["strum"] = note.strum
        return pairs

    def _region_4_rows(self, selected_notes: List[NoteData]) -> List[Tuple[str, str, NoteData, str]]:
        """(display_key, attribute_key, note, value) per Region 4 row.
        display_key carries the "note N " prefix used for a chord;
        attribute_key never does. Shared by the rendering dict and the
        context menu's row->target mapping. Order follows attribute_order -
        the same live order Region 3 uses - not _note_attribute_pairs'
        insertion order, so the two regions can't disagree on sequence."""
        is_chord = len(selected_notes) > 1
        rows = []
        for idx, n in enumerate(selected_notes, start=1):
            prefix = f"note {idx} " if is_chord else ""
            pairs = self._note_attribute_pairs(n)
            for attribute_key in self.attribute_order:
                if attribute_key not in pairs:
                    continue
                label = vocabulary.attribute_label(attribute_key, self.uk_terms)
                rows.append((f"{prefix}{label}", attribute_key, n, pairs[attribute_key]))
        return rows

    # Attribute keys whose value alone is self-explanatory in Region 3's
    # comma-joined note text, so the "<Label> " prefix _format_note_for_region_3
    # adds for every other attribute is dropped: "step" ("F sharp") needs no
    # "Step" prefix, and per user request "duration" doesn't either WHEN it
    # is a real word - "quaver" already says what it is without "Duration
    # quaver". A bare number has no such self-evidence (could be mistaken
    # for a measure/beat/pitch value), so it keeps the "Duration" prefix -
    # see _format_note_for_region_3, which checks note.duration_name_us
    # itself rather than relying on this set for "duration".
    # Region 4's table always labels its "Duration" row regardless; only
    # this inline rendering ever omits the prefix.
    REGION_3_UNPREFIXED_ATTRIBUTES = frozenset({"step", "duration"})

    def _format_note_for_region_3(self, note: NoteData) -> str:
        """Ref 15 AC4: the note name plus whichever extras its voice has
        switched on, comma-separated. An attribute renders only when it is
        both configured on AND present on the note. A voice with everything
        off renders "" - a blank but still selectable, still audible row."""
        voice_key = (note.part_id, note.staff, note.voice)
        wanted = self.voice_display_attributes.get(voice_key, self.DEFAULT_DISPLAY_ATTRIBUTES)
        pairs = self._note_attribute_pairs(note)
        parts = []
        for key in self.attribute_order:
            if key not in wanted or key not in pairs:
                continue
            unprefixed = key in self.REGION_3_UNPREFIXED_ATTRIBUTES
            if key == "duration" and note.duration_name_us is None:
                # No clean word match (MIDI's per-track "too many weird
                # names" fallback, or MusicXML's rare no-<type> case) - the
                # raw number needs the label, unlike a self-explanatory word.
                unprefixed = False
            if unprefixed:
                parts.append(pairs[key])
            else:
                label = vocabulary.attribute_label(key, self.uk_terms)
                parts.append(f"{label} {pairs[key]}")
        return ", ".join(parts)

    def get_region_3_data(self) -> List[str]:
        notes = self._visible_notes()
        if not notes:
            current = self.get_current_slice()
            if (
                self.metronome_enabled
                and current is not None
                and float(current.beat_position).is_integer()
            ):
                return ["Click"]
            return ["None"]
        return [self._format_note_for_region_3(n) for n in notes]

    def get_region_4_data_for_indices(self, selected_indices: List[int]) -> Dict[str, str]:
        selected_notes = self.notes_for_indices(selected_indices)
        if not selected_notes:
            return {"Status": "No note selected"}
        return {
            display_key: value
            for display_key, _, _, value in self._region_4_rows(selected_notes)
        }

    def get_region_4_row_targets(self, selected_indices: List[int]) -> List[Tuple[str, NoteData]]:
        """(attribute_key, note) per Region 4 row, in the same order as
        get_region_4_data_for_indices - lets MainWindow map "the Region 4 row
        the context menu was opened on" back to what it should toggle
        (Ref 15 AC4)."""
        selected_notes = self.notes_for_indices(selected_indices)
        if not selected_notes:
            return []
        return [
            (attribute_key, note)
            for _, attribute_key, note, _ in self._region_4_rows(selected_notes)
        ]

    def note_has_display_attribute(self, note: NoteData, attribute_key: str) -> bool:
        """Whether `note`'s own voice currently shows `attribute_key` in
        Region 3 - drives the Add-vs-Remove variant of the Ref 15 AC4
        context menu."""
        voice_key = (note.part_id, note.staff, note.voice)
        return attribute_key in self.voice_display_attributes.get(voice_key, self.DEFAULT_DISPLAY_ATTRIBUTES)

    def _voice_tuples_for_scope(self, note: NoteData, scope: str) -> Set[Tuple[str, int, int]]:
        """Every (part_id, staff, voice) tuple `scope` fans out to from
        `note`'s own position - "voice" is just the note's own tuple,
        "stave"/"part" walk parts_info's staves_voices for siblings, "score"
        is every voice in every part. Ref 15 AC4."""
        if scope == "voice":
            return {(note.part_id, note.staff, note.voice)}
        if scope == "score":
            return {
                (p.part_id, s, v)
                for p in self.parts_info
                for s, vs in p.staves_voices.items()
                for v in vs
            }
        part = next((p for p in self.parts_info if p.part_id == note.part_id), None)
        if part is None:
            return {(note.part_id, note.staff, note.voice)}
        if scope == "stave":
            return {(note.part_id, note.staff, v) for v in part.staves_voices.get(note.staff, [])}
        if scope == "part":
            return {
                (note.part_id, s, v)
                for s, vs in part.staves_voices.items()
                for v in vs
            }
        raise ValueError(f"Unknown display-attribute scope: {scope!r}")

    def set_display_attribute(
        self, attribute_key: str, scope: str, notes: List[NoteData], add: bool
    ) -> None:
        """Ref 15 AC4: add or remove `attribute_key` for every voice `scope`
        reaches from each note. Plural because a chord selection unions the
        scope across all selected notes - a stave-scope action from a
        two-part chord affects both parts' staves, not just the one the menu
        was opened on."""
        voice_keys: Set[Tuple[str, int, int]] = set()
        for note in notes:
            voice_keys |= self._voice_tuples_for_scope(note, scope)
        for voice_key in voice_keys:
            current = set(self.voice_display_attributes.get(voice_key, self.DEFAULT_DISPLAY_ATTRIBUTES))
            if add:
                current.add(attribute_key)
            else:
                current.discard(attribute_key)
            self.voice_display_attributes[voice_key] = current

    def move_attribute_order(self, attribute_key: str, up: bool, within: Optional[List[str]] = None) -> bool:
        """F2/Ref 15 AC4: move `attribute_key` one step earlier (up) or later
        in attribute_order, the single global order Region 3 and 4 both
        render from. Returns False at a boundary or for an unknown key,
        matching move_timeline_left/right's convention.

        `within`, if given, is a subset of attribute_order (the dialog's
        per-node filtered list) and the move is relative to the nearest
        neighbour IN THAT SUBSET. Entries not in `within` that sit between
        the two are carried along, keeping their order relative to each
        other. That is what lets a filtered dialog move its visible list by
        exactly one row per click without knowing about hidden attributes.

        Taking the neighbour's index BEFORE popping attribute_key, then
        inserting at that same index, is what makes one pop/insert pair
        correct in both directions with no branching."""
        order = self.attribute_order
        if attribute_key not in order:
            return False
        sequence = within if within is not None else order
        if attribute_key not in sequence:
            return False
        pos = sequence.index(attribute_key)
        neighbor_pos = pos - 1 if up else pos + 1
        if not (0 <= neighbor_pos < len(sequence)):
            return False
        neighbor_key = sequence[neighbor_pos]
        source_index = order.index(attribute_key)
        target_index = order.index(neighbor_key)
        order.pop(source_index)
        order.insert(target_index, attribute_key)
        return True

    def attribute_keys_for_voices(self, voice_tuples: Set[Tuple[str, int, int]]) -> List[str]:
        """Every attribute key that has a value on at least one note
        belonging to one of `voice_tuples`, anywhere in the score (not just
        the current slice), ordered per attribute_order. Powers the F2
        attribute-order dialog's per-Region-2-node list - scans
        _real_timeline_slices (the stable, marker-free timeline) rather than
        timeline_slices, since the metronome can temporarily replace the
        latter with a merged view that includes marker-only slices."""
        present: Set[str] = set()
        for event_slice in self._real_timeline_slices:
            for note in event_slice.notes:
                if (note.part_id, note.staff, note.voice) in voice_tuples:
                    present |= self._note_attribute_pairs(note).keys()
        return [key for key in self.attribute_order if key in present]

    def reorder_parts(self, part_id_order: List[str]) -> None:
        """Options > Reorder Parts... - the order parts_info lists parts
        in, live and user-controlled (the same "mutable order the render
        layer reads" pattern attribute_order already established, just for
        parts instead of attributes). Affects Region 2's part-row order
        (main_window.py reorders Region2HierarchyModel.roots to match
        separately, without a full rebuild - see
        Region2ListWidget.reorder_parts, since a load_score_structure
        rebuild would discard on/off toggles) and, in turn, Region 3's
        note-row order: a stable re-sort of every EventSlice.notes list by
        the new part order, so e.g. a UG score's Chords/Lyrics rows come
        back in whichever order the user chose - most importantly
        controlling which part's row a screen reader lands on first after
        every navigation step, since Region 3's "current" row is always
        row 0 (this is the whole point of the feature: NVDA reading the
        chord name when the user wanted to hear the lyric, or vice versa).

        Best-effort, like every other saved-config restore in this class:
        an unknown part_id in part_id_order is ignored; a known part_id
        missing from it keeps its existing relative order, appended after
        every part that was explicitly ordered - so a stale or partial
        saved order still applies everything it can rather than being
        rejected outright."""
        known_ids = [p.part_id for p in self.parts_info]
        ordered = [pid for pid in part_id_order if pid in known_ids]
        ordered += [pid for pid in known_ids if pid not in ordered]
        order_index = {pid: i for i, pid in enumerate(ordered)}

        self.parts_info.sort(key=lambda p: order_index[p.part_id])

        def note_sort_key(note: NoteData) -> int:
            return order_index.get(note.part_id, len(ordered))

        for event_slice in self.timeline_slices:
            event_slice.notes.sort(key=note_sort_key)

    def export_config(self) -> ScoreConfig:
        """Ref 27: this score's state as a ScoreConfig. voices_muted is the
        complement of active_voice_filter, not the active list - a muted-set
        is what lets a changed score still load best-effort (see
        apply_config). MainWindow overwrites it with Region 2's own
        per-node state, which is lossless where this derived version is
        not (and MusicData has no solo concept at all, so parts_soloed/
        staves_soloed/voices_soloed stay at their empty defaults here -
        also only ever filled in by Region 2's own state)."""
        voices_muted: Set[Tuple[str, int, int]] = set()
        if self.active_voice_filter is not None:
            voices_muted = self._all_voice_tuples() - self.active_voice_filter
        return ScoreConfig(
            voices_muted=voices_muted,
            metronome_enabled=self.metronome_enabled,
            position_announcer_enabled=self.position_announcer_enabled,
            voice_display_attributes={
                k: set(v) for k, v in self.voice_display_attributes.items()
            },
            attribute_order=list(self.attribute_order),
            mixer=self.mixer.copy(),
            part_name_overrides=dict(self.part_name_overrides),
            part_program_overrides=dict(self.part_program_overrides),
            key_signature_override_fifths=self.key_signature_override_fifths,
            key_signature_override_mode=self.key_signature_override_mode,
            part_order=[p.part_id for p in self.parts_info],
            percussion_item_overrides=dict(self.percussion_item_overrides),
            percussion_item_name_overrides=dict(self.percussion_item_name_overrides),
            percussion_auto_correct_enabled=self.percussion_auto_correct_enabled,
        )

    def apply_config(self, config: ScoreConfig) -> None:
        """Ref 27: restore a saved ScoreConfig, best-effort. An entry that no
        longer matches anything in THIS score (renamed part, deleted voice,
        unknown attribute key) is dropped silently rather than rejecting the
        whole config, so a stale .rsc still applies everything it can."""
        known_voices = self._all_voice_tuples()
        active = known_voices - (config.voices_muted & known_voices)
        self.set_active_voice_filter(active)

        self.voice_display_attributes = {
            voice_key: set(attrs)
            for voice_key, attrs in config.voice_display_attributes.items()
            if voice_key in known_voices
        }

        known_attribute_keys = set(self.DISPLAY_ATTRIBUTE_ORDER)
        ordered = [key for key in config.attribute_order if key in known_attribute_keys]
        ordered += [key for key in self.DISPLAY_ATTRIBUTE_ORDER if key not in ordered]
        self.attribute_order = ordered

        self.set_metronome_enabled(config.metronome_enabled)
        self.set_position_announcer_enabled(config.position_announcer_enabled)
        self.mixer = config.mixer.copy()

        known_part_ids = {p.part_id for p in self.parts_info}
        self.apply_part_overrides(
            {k: v for k, v in config.part_name_overrides.items() if k in known_part_ids},
            {k: v for k, v in config.part_program_overrides.items() if k in known_part_ids},
        )

        self.apply_key_signature_override(
            config.key_signature_override_fifths, config.key_signature_override_mode
        )

        if config.part_order:
            self.reorder_parts(config.part_order)

        known_percussion_items = {
            (n.part_id, n.percussion_source_key)
            for s in self._real_timeline_slices
            for n in s.notes
            if n.percussion_source_key is not None
        }
        self.percussion_item_overrides = {
            k: v for k, v in config.percussion_item_overrides.items() if k in known_percussion_items
        }
        self.percussion_item_name_overrides = {
            k: v for k, v in config.percussion_item_name_overrides.items() if k in known_percussion_items
        }
        self.percussion_auto_correct_enabled = config.percussion_auto_correct_enabled
        self.apply_percussion_overrides()

    def get_midi_notes_for_indices(self, selected_indices: List[int]) -> List[int]:
        notes = self._visible_notes()
        if not notes or not selected_indices:
            return []
        pitches: List[int] = []
        for i in selected_indices:
            if not (0 <= i < len(notes)):
                continue
            note = notes[i]
            if note.chord_pitches is not None:
                # Guitar Pro's synthetic Chords voice: one NoteData per
                # strum event carries the whole chord here rather than one
                # pitch in midi_pitch (see NoteData.chord_pitches).
                pitches.extend(note.chord_pitches)
            elif note.midi_pitch is not None:
                pitches.append(note.midi_pitch)
        return pitches

    def get_performance_region_rows(self, index: Optional[int] = None) -> List[PerformanceRegionRow]:
        """Ref 29: Region 5's rows - a start and an end line per span active
        at the given position (default: the cursor), plus (S7) a one-shot
        row for a key-signature, time-signature, or immediate/point tempo
        change landing exactly here.

        Repeat/ending containment is a measure-number range check (barlines
        fall at measure boundaries); hairpins compare quarters_from_start,
        since a wedge can start or stop mid-measure. The order (repeats,
        endings, hairpins, then the one-shot rows, each in span-list order)
        must stay stable - MainWindow diffs the resulting label list to
        detect a real change. Wording goes through vocabulary.bar_word,
        never a hardcoded "bar"/"measure"."""
        resolved_index = self.active_event_index if index is None else index
        slice_ = (
            self.timeline_slices[resolved_index]
            if 0 <= resolved_index < len(self.timeline_slices)
            else None
        )
        if slice_ is None:
            return []

        bar_word = vocabulary.bar_word(self.uk_terms)
        rows: List[PerformanceRegionRow] = []

        for span in self.repeat_spans:
            if span.start_measure <= slice_.measure <= span.end_measure:
                rows.append(
                    PerformanceRegionRow(
                        label=f"Repeat start: {bar_word} {span.start_measure}",
                        jump_target_measure=span.start_measure,
                    )
                )
                rows.append(
                    PerformanceRegionRow(
                        label=f"Repeat end: {bar_word} {span.end_measure}",
                        jump_target_measure=span.end_measure,
                    )
                )

        for span in self.ending_spans:
            if span.start_measure <= slice_.measure <= span.end_measure:
                rows.append(
                    PerformanceRegionRow(
                        label=f"Ending {span.number} start: {bar_word} {span.start_measure}",
                        jump_target_measure=span.start_measure,
                    )
                )
                rows.append(
                    PerformanceRegionRow(
                        label=f"Ending {span.number} end: {bar_word} {span.end_measure}",
                        jump_target_measure=span.end_measure,
                    )
                )

        for span in self.hairpin_spans:
            if span.start_quarters_from_start <= slice_.quarters_from_start <= span.end_quarters_from_start:
                kind_label = span.kind.capitalize()
                rows.append(
                    PerformanceRegionRow(
                        label=(
                            f"{kind_label} start: "
                            f"{self._bar_beat_label(bar_word, span.start_measure, span.start_beat_position)}"
                        ),
                        jump_target_measure=span.start_measure,
                        jump_target_quarters=span.start_quarters_from_start,
                    )
                )
                rows.append(
                    PerformanceRegionRow(
                        label=(
                            f"{kind_label} end: "
                            f"{self._bar_beat_label(bar_word, span.end_measure, span.end_beat_position)}"
                        ),
                        jump_target_measure=span.end_measure,
                        jump_target_quarters=span.end_quarters_from_start,
                    )
                )

        # Segno/Coda/D.C./D.S./Fine: one-shot rows, like the time-sig/tempo
        # rows below - unlike repeat/ending/hairpin spans, each of these is a
        # single point, not a start/end pair, so the gate is a direct
        # "does this mark sit at the resolved slice's own measure" check,
        # not a diff against the previous slice (those marks aren't sticky
        # per-slice values the way key/time-sig/tempo are). jump_target_*
        # is always this row's OWN position (a harmless Ctrl+Home/Ctrl+End
        # no-op, same as the time-sig/tempo rows) - jumping to where a mark
        # actually points is out of scope; NavigationController.jump_to_span
        # has no concept of that.
        def _label_suffix(label: str) -> str:
            return f" {label}" if label and label != "1" else ""

        for segno in self.segno_marks:
            if segno.measure == slice_.measure:
                rows.append(
                    PerformanceRegionRow(
                        label=f"Segno{_label_suffix(segno.label)}",
                        jump_target_measure=slice_.measure,
                        jump_target_quarters=slice_.quarters_from_start,
                    )
                )

        for coda in self.coda_marks:
            if coda.measure == slice_.measure:
                rows.append(
                    PerformanceRegionRow(
                        label=f"Coda{_label_suffix(coda.label)}",
                        jump_target_measure=slice_.measure,
                        jump_target_quarters=slice_.quarters_from_start,
                    )
                )

        for to_coda in self.to_coda_marks:
            if to_coda.measure == slice_.measure:
                rows.append(
                    PerformanceRegionRow(
                        label=f"To coda{_label_suffix(to_coda.label)}",
                        jump_target_measure=slice_.measure,
                        jump_target_quarters=slice_.quarters_from_start,
                    )
                )

        for fine in self.fine_marks:
            if fine.measure == slice_.measure:
                rows.append(
                    PerformanceRegionRow(
                        label="Fine",
                        jump_target_measure=slice_.measure,
                        jump_target_quarters=slice_.quarters_from_start,
                    )
                )

        for nj in self.navigation_jumps:
            if nj.measure == slice_.measure:
                rows.append(
                    PerformanceRegionRow(
                        label="Da capo" if nj.kind == "dacapo" else "Dal segno",
                        jump_target_measure=slice_.measure,
                        jump_target_quarters=slice_.quarters_from_start,
                    )
                )

        # S7: a one-shot alert - unlike the three span kinds above, this has
        # no start/end pair, it just fires once at the transition itself.
        # "Previous" is the immediately preceding entry in whichever list
        # slice_ came from (self.timeline_slices), so this works whether or
        # not the metronome's synthetic beat markers are currently spliced
        # in - a marker slice carries the same real key/time_sig/tempo as
        # its own position, same as a real one. Never fires at index 0 (the
        # score's OPENING key/time signature/tempo - already shown in
        # Region 1 and the status bar, alerting on it here on every load
        # would just be noise). A score whose key never changes - the
        # common case - therefore never gets a key-signature row at all;
        # that silence is this same "no alert on the opening value, no
        # alert on no-op repetition" rule, not a separate suppression.
        previous = self.timeline_slices[resolved_index - 1] if resolved_index > 0 else None
        if previous is not None:
            # A key-signature override (S6) forces one constant display key
            # score-wide, so the file's own per-slice key_fifths can no
            # longer disagree with itself in effect - suppress the alert
            # while one is active rather than comparing raw, overridden-away
            # values.
            if self.key_signature_override_fifths is None and previous.key_fifths != slice_.key_fifths:
                key_name = key_signature_display_name(slice_.key_fifths, None)
                rows.append(
                    PerformanceRegionRow(
                        label=f"Key signature change: {key_name}",
                        jump_target_measure=slice_.measure,
                        jump_target_quarters=slice_.quarters_from_start,
                    )
                )
            if previous.time_sig != slice_.time_sig:
                ts_num, ts_den = slice_.time_sig
                rows.append(
                    PerformanceRegionRow(
                        label=f"Time signature change: {ts_num}/{ts_den}",
                        jump_target_measure=slice_.measure,
                        jump_target_quarters=slice_.quarters_from_start,
                    )
                )
            if self._tempo_change_at(resolved_index - 1) != self._tempo_change_at(resolved_index):
                number = self._format_tempo_number(self.score_tempo_display_bpm(resolved_index))
                unit = self.tempo_beat_unit_name_at(resolved_index)
                rows.append(
                    PerformanceRegionRow(
                        label=f"Tempo change: {number} {unit} notes per minute",
                        jump_target_measure=slice_.measure,
                        jump_target_quarters=slice_.quarters_from_start,
                    )
                )

        return rows

    def is_at_beginning_repeat_target(self, index: Optional[int] = None) -> bool:
        """True when the resolved slice is the first note of measure 1 AND a
        repeat sends playback back there (a RepeatSpan with start_measure ==
        1) - "there is a repeat that takes the user back to the beginning"
        (the user's own framing, requested after Ref 29 shipped). Landing
        here after already having been inside that same still-active span -
        stepping back from bar 2, or starting playback from bar 1 without
        first navigating away - would otherwise never re-fire Region 5's
        change cue, since RegionPresenter.refresh_region_5's row-label diff
        sees no difference from last time. This is a deliberate, narrow
        carve-out for that one case, not a general "re-fire on every
        repeat-start arrival" rule - an ordinary mid-score practice repeat
        (e.g. bars 4-5) keeps the existing dedup untouched."""
        resolved_index = self.active_event_index if index is None else index
        if not (0 <= resolved_index < len(self.timeline_slices)):
            return False
        slice_ = self.timeline_slices[resolved_index]
        if slice_.measure != 1 or slice_.beat_position != 1.0:
            return False
        return any(span.start_measure == 1 for span in self.repeat_spans)

    @staticmethod
    def _format_tempo_number(value: float) -> str:
        """Whole numbers print bare ("100"), not "100.0" - same rounding
        _tempo_status_field already uses for the live playback-tempo field,
        factored out here so this row's wording matches it exactly."""
        return str(int(value)) if float(value).is_integer() else str(round(value, 2))

    @staticmethod
    def _bar_beat_label(bar_word: str, measure: int, beat_position: float) -> str:
        """"bar N" on the downbeat (the bar number already pins it down, and
        repeat/ending rows are always this case since barlines fall at
        measure boundaries); "bar N beat B" otherwise, worded exactly as
        get_status_bar_fields does so it reads the same everywhere. Only
        markers actually falling mid-bar name a beat (user's decision)."""
        if float(beat_position) == 1.0:
            return f"{bar_word} {measure}"
        beat_str = str(int(beat_position)) if float(beat_position).is_integer() else str(beat_position)
        return f"{bar_word} {measure} beat {beat_str}"

    def get_performance_report_lines(self) -> List[str]:
        """Ref 29: the Performance Report's content - a whole-score summary,
        deliberately independent of the Region 2 filter (unlike every other
        accessor here), since it describes the piece, not the current view."""
        # Reuses get_region_1_data() wholesale rather than cherry-picking
        # keys like "Title"/"Composer": credit keys come from each file's own
        # <credit-type> text, so no fixed name is guaranteed to exist.
        lines: List[str] = [f"{k}: {v}" for k, v in self.get_region_1_data().items()]

        bar_word = vocabulary.bar_word(self.uk_terms).capitalize()
        anacrusis_present = any(s.measure == 0 for s in self.timeline_slices)
        lines.append(f"Anacrusis: {'Present' if anacrusis_present else 'Not present'}")
        lines.append(f"Number of {bar_word.lower()}s: {self.total_measures}")

        note_counts: Dict[str, int] = {}
        for s in self._real_timeline_slices:
            for n in s.notes:
                if n.midi_pitch is not None:
                    note_counts[n.part_name] = note_counts.get(n.part_name, 0) + 1
        lines.append(f"Instruments: {len(self.parts_info)}")
        for p in self.parts_info:
            lines.append(f"{p.name}: {note_counts.get(p.name, 0)} notes")

        lines.append(f"Repeated sections: {len(self.repeat_spans)}")
        for span in self.repeat_spans:
            lines.append(
                f"Repeat: {bar_word} {span.start_measure} to {bar_word} {span.end_measure}"
            )

        lines.append(f"Endings: {len(self.ending_spans)}")
        for span in self.ending_spans:
            lines.append(
                f"Ending {span.number}: {bar_word} {span.start_measure} to {bar_word} {span.end_measure}"
            )

        lines.append(f"Performance markers: {len(self.hairpin_spans)}")
        for span in self.hairpin_spans:
            lines.append(
                f"{span.kind.capitalize()}: {bar_word} {span.start_measure} to {bar_word} {span.end_measure}"
            )

        def _label_suffix(label: str) -> str:
            return f" {label}" if label and label != "1" else ""

        lines.append(f"Segno marks: {len(self.segno_marks)}")
        for segno in self.segno_marks:
            lines.append(f"Segno{_label_suffix(segno.label)}: {bar_word} {segno.measure}")

        lines.append(f"Coda marks: {len(self.coda_marks)}")
        for coda in self.coda_marks:
            lines.append(f"Coda{_label_suffix(coda.label)}: {bar_word} {coda.measure}")

        lines.append(f"Fine marks: {len(self.fine_marks)}")
        for fine in self.fine_marks:
            lines.append(f"Fine: {bar_word} {fine.measure}")

        lines.append(f"Navigation jumps: {len(self.navigation_jumps)}")
        for nj in self.navigation_jumps:
            name = "Da capo" if nj.kind == "dacapo" else "Dal segno"
            lines.append(f"{name}: {bar_word} {nj.measure}")

        return lines

    # Ref 12 AC2: hard bounds, in the score's DISPLAY units - what the user
    # reads and types, not the internal quarter-note equivalent.
    MIN_TEMPO_BPM = 30
    MAX_TEMPO_BPM = 300

    def _tempo_change_at(self, index: Optional[int] = None) -> Tuple[int, float, str]:
        """(tempo_bpm, beat_unit_quarter_length, beat_unit_name) in effect at
        an index, or the cursor. Falls back to the score's opening tempo
        before the first marking. tempo_changes is sorted by position
        (TimelineBuilder's job), so the last entry not past it wins."""
        idx = self.active_event_index if index is None else index
        quarters = self.timeline_slices[idx].quarters_from_start if 0 <= idx < len(self.timeline_slices) else 0.0

        result = (self.tempo_bpm, self.tempo_beat_unit_quarter_length, self.tempo_beat_unit_name)
        for change in self.tempo_changes:
            if change.quarters_from_start > quarters:
                break
            result = (change.tempo_bpm, change.beat_unit_quarter_length, change.beat_unit_name)
        return result

    def score_tempo_display_bpm(self, index: Optional[int] = None) -> float:
        """The tempo actually in effect at `index` (or the cursor), in the
        beat unit it was authored in (A9) - e.g. 96 for a passage marked
        eighth=96, not the quarter-note-equivalent BPM used internally for
        playback timing."""
        bpm, beat_unit_ql, _ = self._tempo_change_at(index)
        return bpm / beat_unit_ql

    def effective_tempo_display_bpm(self, index: Optional[int] = None) -> float:
        """score_tempo_display_bpm() plus the current offset - what F/S/D,
        the status bar and the Tempo Offset dialog show and read (Ref 12),
        in the same units Region 1 already displays the score's tempo in
        (A9). playback_tempo_offset is stored in these display units
        directly (not quarter-note terms) precisely so this is a plain sum."""
        return self.score_tempo_display_bpm(index) + self.playback_tempo_offset

    def effective_tempo_bpm(self, index: Optional[int] = None) -> float:
        """Quarter-note BPM for real playback timing (Sequencer,
        get_duration_ms_for_index) - converts the display-unit offset back
        to quarter-note terms via whichever beat unit is in effect at
        `index`."""
        bpm, beat_unit_ql, _ = self._tempo_change_at(index)
        display = bpm / beat_unit_ql + self.playback_tempo_offset
        return display * beat_unit_ql

    def tempo_beat_unit_name_at(self, index: Optional[int] = None) -> str:
        """The beat unit label (e.g. "eighth"/"quaver") in effect at `index`
        (or the cursor) - lets the status bar show the right unit even where
        a mid-score tempo marking changes beat unit, not just the number.
        F4/D-6: translated per self.uk_terms - both current callers
        (_tempo_status_field below, and main_window.py's Tempo Offset dialog
        construction) are display-only, so this is the single change point
        that covers both."""
        _, _, name = self._tempo_change_at(index)
        return vocabulary.duration_name(name, self.uk_terms)

    def set_playback_tempo_offset(self, offset: float) -> None:
        """Clamp so effective_tempo_display_bpm() stays within
        [MIN_TEMPO_BPM, MAX_TEMPO_BPM] (Ref 12 AC2) - bounds on what the
        user reads and types, not on tempo_bpm's quarter-note equivalent -
        without touching tempo_bpm itself (AC1). Clamped against the tempo
        at the cursor, which can change mid-score."""
        base = self.score_tempo_display_bpm()
        min_offset = self.MIN_TEMPO_BPM - base
        max_offset = self.MAX_TEMPO_BPM - base
        self.playback_tempo_offset = max(min_offset, min(max_offset, offset))

    def reset_playback_tempo(self) -> None:
        """Ref 12 AC4: reset control returns to the score's own tempo."""
        self.playback_tempo_offset = 0.0

    # Channels no real part may use. Each value is duplicated from the
    # audio/ module that owns it rather than imported - models/ must not
    # depend on audio/. Keeping parts off these is what stops an instrument
    # colliding with the click, the spoken position word or the change cue.
    #
    # Named METRONOME_CLICK_CHANNEL, not PERCUSSION_CHANNEL (its old name,
    # before wishlist #8): a REAL percussion part (is_percussion=True) is
    # NOT routed here - it gets an ordinary channel like any other part,
    # program-selected to the GM percussion bank instead (see
    # get_playback_events_for_indices). This channel is reserved only
    # because audio/metronome.py's click sound already owns it - the old
    # name would now wrongly suggest real percussion notes land here too.
    METRONOME_CLICK_CHANNEL = 9    # audio/metronome.py METRONOME_CHANNEL
    POSITION_ANNOUNCER_CHANNEL = 8  # audio/position_announcer.py
    PERFORMANCE_CUE_CHANNEL = 7     # audio/performance_cue.py
    LIVE_MIDI_INPUT_CHANNEL = 6     # audio/midi_input.py LIVE_MIDI_INPUT_CHANNEL
    RESERVED_CHANNELS = {
        POSITION_ANNOUNCER_CHANNEL, METRONOME_CLICK_CHANNEL,
        PERFORMANCE_CUE_CHANNEL, LIVE_MIDI_INPUT_CHANNEL,
    }
    MAX_MIDI_CHANNELS = 16

    def get_channel_for_part(self, part_id: str) -> int:
        """One MIDI channel per part, in part-list order, skipping
        RESERVED_CHANNELS. Wraps if a score has more melodic parts than the
        16 channels minus reservations allow.

        The usable list is built per call, not as a class attribute: only a
        comprehension's outermost iterable is evaluated in the enclosing
        class scope, not its condition, so referring to RESERVED_CHANNELS
        there raises NameError. 16 elements is too cheap to be worth caching
        another way.
        """
        usable_channels = [
            c for c in range(self.MAX_MIDI_CHANNELS) if c not in self.RESERVED_CHANNELS
        ]
        for idx, p in enumerate(self.parts_info):
            if p.part_id == part_id:
                return usable_channels[idx % len(usable_channels)]
        return 0

    def get_gmidi_program_for_part(self, part_id: str) -> int:
        for p in self.parts_info:
            if p.part_id == part_id:
                return p.gmidi_program
        return 25

    def is_percussion_part(self, part_id: str) -> bool:
        """Wishlist #8: whether this part's notes are unpitched percussion
        (a MusicXML percussion clef, or a MIDI channel-10 track) rather than
        real GM instrument notes - see PartStructureInfo.is_percussion.
        get_playback_events_for_indices reads this to route the part's
        channel to the GM percussion bank instead of its (meaningless, for
        percussion) gmidi_program."""
        for p in self.parts_info:
            if p.part_id == part_id:
                return p.is_percussion
        return False

    def apply_part_overrides(
        self, name_overrides: Dict[str, str], program_overrides: Dict[str, int]
    ) -> None:
        """S5: the instrument dialog's OK, and apply_config() restoring a
        saved score. Mutates PartStructureInfo in place - every other
        reader (get_score_structure, mixer_rows, get_gmidi_program_for_part,
        get_playback_events_for_indices) already reads parts_info live, so
        this is enough to make a renamed/reprogrammed part show and sound
        correctly everywhere with no further wiring.

        NoteData.part_name is kept in sync explicitly: TimelineBuilder/
        MidiTimelineBuilder bake it in at parse time from parts_info's name
        at THAT moment, and get_performance_report_lines joins the two by
        matching text - the exact "two independent copies of a name have to
        agree verbatim" bug class R5 fixed for the reader's own two XML
        passes (see CLAUDE.md). Renaming only parts_info and not the
        already-built notes would silently reopen it.
        """
        self.part_name_overrides.update(name_overrides)
        self.part_program_overrides.update(program_overrides)
        for p in self.parts_info:
            if p.part_id in name_overrides:
                p.name = name_overrides[p.part_id]
            if p.part_id in program_overrides:
                p.gmidi_program = program_overrides[p.part_id]
        if name_overrides:
            for s in self._real_timeline_slices:
                for n in s.notes:
                    if n.part_id in name_overrides:
                        n.part_name = name_overrides[n.part_id]

    def _set_percussion_voice_names(self) -> None:
        """Wishlist #8 follow-up: a percussion voice's label is its one
        item's display name ("Closed Hi-Hat") instead of the generic
        "Voice N" - the same voice_names override slot Guitar Pro's
        synthetic Chords voice already uses to show "Chords" instead of
        "Voice 1" (parsers/gp_reader.py). Each voice holds exactly one
        item by construction (TimelineBuilder/MidiTimelineBuilder set
        NoteData.voice to the item's own declared key - see there - so two
        different items can never share one voice number), which is also
        why both readers already set this same label directly at parse
        time; this exists as (a) a safety net and (b) the refresh path
        after an Instruments-dialog rename, called again at the end of
        apply_percussion_overrides so a rename is picked up.
        """
        # _real_timeline_slices doesn't exist yet on the __post_init__ call
        # (it's assigned right after this point) - timeline_slices is
        # exactly it at that moment too, since metronome markers are only
        # ever spliced in later, via set_metronome_enabled.
        slices = getattr(self, "_real_timeline_slices", self.timeline_slices)
        names_by_voice: Dict[Tuple[str, int, int], str] = {}
        for s in slices:
            for n in s.notes:
                if n.percussion_source_key is None:
                    continue
                names_by_voice[(n.part_id, n.staff, n.voice)] = n.step_name
        for part in self.parts_info:
            for staff, voices in part.staves_voices.items():
                for voice in voices:
                    name = names_by_voice.get((part.part_id, staff, voice))
                    if name:
                        part.voice_names[(staff, voice)] = name

    def get_percussion_items_for_part(
        self, part_id: str
    ) -> List[Tuple[Tuple[str, int], str, int]]:
        """(item_key, current display name, current effective sounding key)
        for every distinct percussion item in this part, in first-seen
        order - the row list widgets/instrument_dialog.py builds for a
        percussion part. item_key is exactly what
        percussion_item_overrides/percussion_item_name_overrides are keyed
        by, so a row's edits can be written straight back without any
        further lookup."""
        seen: Dict[Tuple[str, int], Tuple[str, int]] = {}
        for s in self._real_timeline_slices:
            for n in s.notes:
                if n.part_id != part_id or n.percussion_source_key is None:
                    continue
                item_key = (n.part_id, n.percussion_source_key)
                if item_key not in seen:
                    seen[item_key] = (n.step_name, n.midi_pitch)
        return [(key, name, sounding_key) for key, (name, sounding_key) in seen.items()]

    def apply_percussion_overrides(self) -> None:
        """Wishlist #8 follow-up: (re)applies percussion_item_overrides/
        percussion_item_name_overrides/percussion_auto_correct_enabled to
        every percussion note - called from apply_config() (restoring a
        saved score) and after the Instruments dialog's OK.

        Priority per item, highest first: an explicit
        percussion_item_overrides entry > auto-correct (only when
        percussion_auto_correct_enabled, and only for a MusicXML-sourced
        note - a MIDI note's name is already derived FROM its key, so it can
        never disagree with it) > the file's own original
        percussion_source_key. Always re-derived from percussion_source_key,
        never from the note's own possibly-already-overridden midi_pitch -
        so toggling the checkbox off, or clearing an item override, is
        lossless with no re-parse (the same role file_key_fifths plays for
        apply_key_signature_override).

        Auto-correct applies ONE shift per PART (models.gm_percussion_map.
        detect_percussion_key_shift), not a per-item name guess - see that
        function's docstring for why a short name like "Snare" can't be
        reliably matched to a GM name on its own. Two passes: names first
        (so a user rename is what shift-detection and any later re-open of
        the dialog both see), then the shift is detected per part from the
        now-current names, then sounds are resolved.
        """
        for s in self._real_timeline_slices:
            for n in s.notes:
                if n.percussion_source_key is None:
                    continue
                item_key = (n.part_id, n.percussion_source_key)
                if item_key in self.percussion_item_name_overrides:
                    n.step_name = self.percussion_item_name_overrides[item_key]

        shift_by_part: Dict[str, Optional[int]] = {}
        if self.percussion_auto_correct_enabled and not self.is_midi:
            items_by_part: Dict[str, List[Tuple[str, int]]] = {}
            for s in self._real_timeline_slices:
                for n in s.notes:
                    if n.percussion_source_key is None:
                        continue
                    items_by_part.setdefault(n.part_id, []).append(
                        (n.step_name, n.percussion_source_key)
                    )
            shift_by_part = {
                part_id: detect_percussion_key_shift(items) for part_id, items in items_by_part.items()
            }

        for s in self._real_timeline_slices:
            for n in s.notes:
                if n.percussion_source_key is None:
                    continue
                item_key = (n.part_id, n.percussion_source_key)
                if item_key in self.percussion_item_overrides:
                    n.midi_pitch = self.percussion_item_overrides[item_key]
                    continue
                shift = shift_by_part.get(n.part_id)
                if shift is not None:
                    n.midi_pitch = n.percussion_source_key - shift
                else:
                    n.midi_pitch = n.percussion_source_key

        self._set_percussion_voice_names()

    def apply_key_signature_override(
        self, fifths: Optional[int], mode: Optional[str]
    ) -> None:
        """S6: the Instruments & Key dialog's OK, and apply_config()
        restoring a saved score. fifths=None clears the override, back to
        the file's own key(s).

        For a MIDI-loaded score, also re-spells every note against the new
        fifths - MIDI has no real notation to derive spelling from
        (parsers/midi_timeline_builder.py's _spell_pitch is a bare
        pitch-class table), so a wrong or missing file key produces wrong
        enharmonic spelling until corrected here. Symmetric by design:
        clearing the override re-derives each note's spelling from its own
        file_key_fifths (the fifths MidiTimelineBuilder actually spelled it
        against at parse time) rather than a separate cached "original text"
        - so this needs no distinct restore path.

        MusicXML notes are never touched - their spelling comes straight
        from the file's own <step>/<alter> and never depended on key in the
        first place. This only ever changes what key is DISPLAYED for an
        XML score (get_region_1_data/get_status_bar_fields below)."""
        self.key_signature_override_fifths = fifths
        self.key_signature_override_mode = mode if fifths is not None else None
        if not self.is_midi:
            return
        for s in self._real_timeline_slices:
            for n in s.notes:
                if n.midi_pitch is None or n.file_key_fifths is None:
                    continue
                effective = fifths if fifths is not None else n.file_key_fifths
                n.step_name, _ = _spell_pitch(n.midi_pitch, effective)

    def get_stave_name_for_part(self, part_id: str, staff: int) -> str:
        """Spoken-friendly stave name for Region 4 ("Treble stave"), worded
        exactly as Region 2 does so a note matches the stave it was toggled
        under. D-15: deliberately NOT translated by the uk_terms toggle."""
        for p in self.parts_info:
            if p.part_id == part_id:
                return p.staves_clefs.get(staff, "Standard stave")
        return "Standard stave"

    def get_playback_events_for_indices(
        self, selected_indices: List[int], index: Optional[int] = None
    ) -> List[Tuple[int, Optional[int], List[int], int]]:
        """Group selected notes by part for simultaneous multi-part playback.

        Each group is (channel, zero-indexed GM program, midi pitches,
        duration_ms[, bank]), so a chord spanning two parts sounds both
        instruments rather than collapsing onto parts_info[0]'s (Ref 8).
        duration_ms is PER PART - the max quarter_length among that part's
        own notes here, not the slice-wide minimum - so no part is clamped
        to whichever other part happens to have the shortest note at this
        instant (Ref 9 AC2, Ref 13 AC2). The max, not the min, so a chord
        with slightly inconsistent source data rings for its longest member.

        Wishlist #8: a percussion part's group carries a trailing bank=128
        instead of its (meaningless, for percussion) gmidi_program - the
        same "trailing optional field" shape duration_ms already uses, so
        every existing 4-tuple caller (SynthEngine.play_chord's
        `event[3] if len(event) > 3 else duration_ms`) needs no change; only
        play_chord's bank read is new.

        index: read an explicit slice instead of the cursor (Sequencer).
        """
        notes = self._visible_notes(index)
        if not notes:
            return []

        notes_by_part: Dict[str, List[int]] = {}
        quarter_length_by_part: Dict[str, float] = {}
        part_order: List[str] = []
        for i in selected_indices:
            if not (0 <= i < len(notes)):
                continue
            note = notes[i]
            # Guitar Pro's synthetic Chords voice: one NoteData per strum
            # event carries the whole chord in chord_pitches rather than a
            # single midi_pitch, so the group sounds every string, not just
            # a representative one (see NoteData.chord_pitches).
            pitches = note.chord_pitches if note.chord_pitches is not None else (
                [note.midi_pitch] if note.midi_pitch is not None else []
            )
            if not pitches:
                continue
            if note.part_id not in notes_by_part:
                notes_by_part[note.part_id] = []
                quarter_length_by_part[note.part_id] = 0.0
                part_order.append(note.part_id)
            notes_by_part[note.part_id].extend(pitches)
            quarter_length_by_part[note.part_id] = max(
                quarter_length_by_part[note.part_id], note.quarter_length
            )

        events = []
        for part_id in part_order:
            channel = self.get_channel_for_part(part_id)
            duration_ms = self._quarters_to_ms(quarter_length_by_part[part_id], index)
            if self.is_percussion_part(part_id):
                events.append(
                    (channel, GM_PERCUSSION_PROGRAM, notes_by_part[part_id], duration_ms, GM_PERCUSSION_BANK)
                )
            else:
                program = max(0, self.get_gmidi_program_for_part(part_id) - 1)
                events.append((channel, program, notes_by_part[part_id], duration_ms))
        return events

    def get_grace_note_events_for_indices(
        self, selected_indices: List[int], index: Optional[int] = None
    ) -> List[Tuple[int, Optional[int], List[int]]]:
        """Grace note(s) attached to the selected notes (NoteData.grace_notes,
        see models/note_data.py), grouped by part - same (channel, program,
        pitches) shape as get_playback_events_for_indices but with no
        duration_ms, since these are meant to sound BRIEFLY before the main
        chord, not for their own notated length (there isn't one - a grace
        note carries no <duration>). audio/strum_schedule.py's sound_events
        is what actually schedules them ahead of the main chord via
        SynthEngine.play_chord_with_grace; empty when nothing selected
        carries a grace note, the common case, which callers use to fall
        straight through to the plain play_chord path unchanged.
        """
        notes = self._visible_notes(index)
        if not notes:
            return []

        pitches_by_part: Dict[str, List[int]] = {}
        part_order: List[str] = []
        for i in selected_indices:
            if not (0 <= i < len(notes)):
                continue
            note = notes[i]
            if not note.grace_notes:
                continue
            grace_pitches = [g.midi_pitch for g in note.grace_notes if g.midi_pitch is not None]
            if not grace_pitches:
                continue
            if note.part_id not in pitches_by_part:
                pitches_by_part[note.part_id] = []
                part_order.append(note.part_id)
            pitches_by_part[note.part_id].extend(grace_pitches)

        events = []
        for part_id in part_order:
            channel = self.get_channel_for_part(part_id)
            program = max(0, self.get_gmidi_program_for_part(part_id) - 1)
            events.append((channel, program, pitches_by_part[part_id]))
        return events

    def get_grace_note_events_at_index(self, index: int) -> List[Tuple[int, Optional[int], List[int]]]:
        """The Sequencer's (index-based) equivalent of
        get_grace_note_events_for_indices, mirroring get_playback_events_at_index."""
        notes = self._visible_notes(index)
        if not notes:
            return []
        return self.get_grace_note_events_for_indices(list(range(len(notes))), index=index)

    def get_current_duration_ms(self) -> int:
        return self.get_duration_ms_for_index(self.active_event_index)

    def get_duration_ms_for_index(self, index: int) -> int:
        """Slice-wide duration at an arbitrary index - used only by the
        Sequencer to know how long to stay playing after the final step.
        Real per-note note-off timing is per group; see
        get_playback_events_for_indices."""
        if not (0 <= index < len(self.timeline_slices)):
            return 500
        quarter_length = self.timeline_slices[index].quarter_length
        return self._quarters_to_ms(quarter_length, index)

    def _quarters_to_ms(self, quarter_length: float, index: Optional[int]) -> int:
        ms = (quarter_length * 60000.0) / float(self.effective_tempo_bpm(index))
        return max(100, int(ms))

    def bar_bounds_quarters(self, index: int) -> Optional[Tuple[float, float]]:
        """(start, end) of the bar containing this slice, in elapsed
        quarters from the start of the piece - what Preview's loop needs to
        restart exactly on the bar line rather than when the last note stops
        ringing (a bar ending in rests would otherwise repeat early and out
        of time).

        Derived from the slice itself rather than from a per-measure table
        the four timeline builders would each have to publish: beat_position
        is ts-relative (Ref 18), so the distance back to the bar line is
        (beat_position - 1) beats of 4/ts_den quarters each. A pickup bar
        (Ref 17) gives its NOTIONAL bar, whose end is the real bar line -
        which is the endpoint that matters here.
        """
        if not (0 <= index < len(self.timeline_slices)):
            return None
        current = self.timeline_slices[index]
        ts_num, ts_den = current.time_sig
        beat_quarters = 4.0 / float(ts_den or 4)
        start = current.quarters_from_start - (current.beat_position - 1.0) * beat_quarters
        return start, start + float(ts_num or 4) * beat_quarters

    def span_ms_to_quarters(self, start_index: int, end_quarters: float) -> int:
        """Real milliseconds from the slice at start_index to an elapsed-
        quarters point later in the piece.

        Walks the slices in between rather than dividing once, so a tempo
        change inside the span is honoured - the same "the tempo in force
        beforehand governs the time taken to get there" rule as
        Sequencer._delay_ms_to, which this mirrors.
        """
        if not (0 <= start_index < len(self.timeline_slices)):
            return 0
        total_ms = 0.0
        index = start_index
        position = self.timeline_slices[start_index].quarters_from_start
        while index + 1 < len(self.timeline_slices):
            next_quarters = self.timeline_slices[index + 1].quarters_from_start
            if next_quarters >= end_quarters:
                break
            if next_quarters > position:
                total_ms += (next_quarters - position) * 60000.0 / float(
                    self.effective_tempo_bpm(index)
                )
                position = next_quarters
            index += 1
        if end_quarters > position:
            total_ms += (end_quarters - position) * 60000.0 / float(
                self.effective_tempo_bpm(index)
            )
        return max(0, int(round(total_ms)))

    def get_playback_events_at_index(self, index: int) -> List[Tuple[int, Optional[int], List[int], int]]:
        """All visible notes at timeline index `index`, grouped by part
        (Ref 8) - the Sequencer (E4) equivalent of
        get_playback_events_for_indices for Region 3's selection, playing a
        slice by absolute index independent of active_event_index."""
        notes = self._visible_notes(index)
        if not notes:
            return []
        return self.get_playback_events_for_indices(list(range(len(notes))), index=index)

    def next_visible_event_index(
        self, index: int, end_index: Optional[int] = None
    ) -> Optional[int]:
        """Next index after `index` passing the Region 2 filter - rests
        INCLUDED, unlike _sounding_bounds()'s navigation range, because
        playback must advance through a rest and take up its time rather
        than skip it. Visits metronome beat markers too when the metronome
        is on, which is what makes the Sequencer click on a silent beat with
        no extra scheduling. None means the end of playback."""
        limit = end_index if end_index is not None else len(self.timeline_slices) - 1
        idx = index
        while idx < limit:
            idx += 1
            if self._slice_is_navigable(idx):
                return idx
        return None

    def _dacapo_target_measure(self) -> int:
        """Da Capo means the true beginning of the piece - measure 0 when a
        pickup bar exists (Ref 17's pickup numbering), not a hardcoded 1."""
        measures = self.measure_numbers()
        return measures[0] if measures else 1

    def _resolve_coda_target(self, to_coda: "ToCodaMark") -> Optional[int]:
        """The CodaMark a ToCodaMark jumps to: an exact label match first
        (the normal <sound tocoda="X">/<sound coda="X"> case), else the
        nearest CodaMark after this ToCodaMark's own measure (the text-only
        fallback, where neither mark carries a real label to match)."""
        for coda in self.coda_marks:
            if to_coda.label and coda.label == to_coda.label:
                return coda.measure
        candidates = [c.measure for c in self.coda_marks if c.measure > to_coda.measure]
        return min(candidates) if candidates else None

    def next_playback_index(
        self,
        index: int,
        jump_state: PlaybackJumpState,
        end_index: Optional[int] = None,
        jump_lower_bound: int = 0,
    ) -> Optional[int]:
        """Repeat/ending/Segno/Coda/D.C./D.S./Fine-aware sibling of
        next_visible_event_index, for PLAYBACK AND PREVIEW ONLY - arrow-key
        navigation keeps calling the plain, stateless next_visible_event_index
        and is entirely untouched by this method's existence.

        jump_state is per-RUN, owned by the caller (Sequencer.play_from
        creates a fresh PlaybackJumpState alongside its other per-run resets)
        - MusicData itself stays the stateless, shared source of truth it is
        everywhere else.

        A jump is only followed when its target index falls within
        [jump_lower_bound, effective end] - this single rule is what makes
        one algorithm correct for both callers: full playback passes
        jump_lower_bound=0 (every jump in the piece is reachable, including
        one that lands before wherever this particular run happened to
        start), while Preview passes jump_lower_bound=start_index (its own
        window start) with its own short end_index, so a repeat/ending fully
        inside the previewed bars is followed while a D.C./D.S./Coda whose
        target lies outside that short window is silently skipped - it just
        falls through to plain linear stepping, exactly as it does today.

        When the score has none of these marks (every list below is empty),
        this degrades to a single next_visible_event_index call.

        Also sets jump_state.last_step_was_jump - see its own docstring.
        Default False here; each jump branch below sets it True right
        before returning.
        """
        jump_state.last_step_was_jump = False
        effective_end = end_index if end_index is not None else len(self.timeline_slices) - 1

        def in_bounds(target: Optional[int]) -> bool:
            return target is not None and jump_lower_bound <= target <= effective_end

        if 0 <= index < len(self.timeline_slices):
            m = self.timeline_slices[index].measure
            if self.last_visible_event_index_of_measure(m) == index:
                if not jump_state.jump_taken:
                    for i, rs in enumerate(self.repeat_spans):
                        if rs.end_measure == m and i not in jump_state.repeats_taken:
                            target = self.first_visible_event_index_of_measure(rs.start_measure)
                            if in_bounds(target):
                                jump_state.repeats_taken.add(i)
                                for j, es in enumerate(self.ending_spans):
                                    if es.start_measure <= m <= es.end_measure:
                                        jump_state.endings_to_skip.add(j)
                                jump_state.last_step_was_jump = True
                                return target
                            break

                    for nj in self.navigation_jumps:
                        if nj.measure != m:
                            continue
                        if nj.kind == "dacapo":
                            target_measure = self._dacapo_target_measure()
                        else:
                            label = nj.target_label or "1"
                            segno = next(
                                (s for s in self.segno_marks if (s.label or "1") == label), None
                            )
                            if segno is None:
                                continue
                            target_measure = segno.measure
                        target = self.first_visible_event_index_of_measure(target_measure)
                        if in_bounds(target):
                            jump_state.jump_taken = True
                            jump_state.last_step_was_jump = True
                            return target
                        break

                if jump_state.jump_taken:
                    for tc in self.to_coda_marks:
                        if tc.measure == m:
                            coda_measure = self._resolve_coda_target(tc)
                            if coda_measure is not None:
                                target = self.first_visible_event_index_of_measure(coda_measure)
                                if in_bounds(target):
                                    jump_state.last_step_was_jump = True
                                    return target
                            break

                    if any(fm.measure == m for fm in self.fine_marks):
                        return None

        candidate = self.next_visible_event_index(index, effective_end)
        if candidate is None or not jump_state.endings_to_skip:
            return candidate

        seen = 0
        while candidate is not None and seen <= len(self.ending_spans):
            candidate_measure = self.timeline_slices[candidate].measure
            hit = next(
                (
                    j for j in jump_state.endings_to_skip
                    if self.ending_spans[j].start_measure == candidate_measure
                ),
                None,
            )
            if hit is None:
                break
            redirected = self.first_visible_event_index_of_measure(
                self.ending_spans[hit].end_measure + 1
            )
            if not in_bounds(redirected):
                break
            candidate = redirected
            jump_state.last_step_was_jump = True
            seen += 1
        return candidate

    def playback_span_ms(self, start_index: int, end_index: int, end_quarters: float) -> int:
        """Jump-aware sibling of span_ms_to_quarters (left untouched, still
        used elsewhere) - needed because Preview's own loop-restart timing
        (_build_preview_run's iteration_ms) must know the REAL elapsed time a
        repeat/jump-aware run through [start_index, end_index] takes, not the
        flat, jump-unaware walk span_ms_to_quarters does. Without this, a
        repeat fully inside the preview window would make the real Sequencer
        run take longer than the separately-scheduled loop-restart timer
        expects, truncating the repeat mid-replay.

        Simulates the walk with a throwaway PlaybackJumpState (this is not a
        real playback run - nothing actually sounds), using the same
        jump_lower_bound=start_index Preview itself passes to Sequencer.
        play_from, then adds the same tail-to-end_quarters segment
        span_ms_to_quarters computes, so the loop still restarts on the true
        bar line rather than when the last simulated note's ring-out ends.
        When nothing inside the window jumps, this is numerically identical
        to span_ms_to_quarters.
        """
        if not (0 <= start_index < len(self.timeline_slices)):
            return 0
        jump_state = PlaybackJumpState()
        total_ms = 0.0
        index = start_index
        position = self.timeline_slices[start_index].quarters_from_start
        guard = len(self.timeline_slices) * 2 + 4
        while guard > 0:
            guard -= 1
            next_index = self.next_playback_index(index, jump_state, end_index, start_index)
            # Deliberately NOT "if index == end_index: break" here - reaching
            # end_index must still get its own next_playback_index call
            # before stopping, or a repeat/jump whose TRIGGER point is
            # end_index itself (e.g. a repeat spanning exactly the previewed
            # window, a common case since a repeat is often exactly the
            # requested bar count) would never be detected: next_index is
            # None only once next_playback_index has genuinely found nothing
            # further to do at end_index (bounded by the SAME end_index it
            # was passed), which is what actually ends this walk.
            if next_index is None:
                break
            next_quarters = self.timeline_slices[next_index].quarters_from_start
            if jump_state.last_step_was_jump:
                # A jump (backward repeat/D.C./D.S., or a forward
                # ending-skip/To Coda) - the departing note still rings its
                # own duration first regardless of which direction the jump
                # moves in elapsed-quarters, the same jump-aware handling
                # Sequencer._delay_ms_to applies for the real run.
                total_ms += self.get_duration_ms_for_index(index)
            elif next_quarters > position:
                total_ms += (next_quarters - position) * 60000.0 / float(
                    self.effective_tempo_bpm(index)
                )
            position = next_quarters
            index = next_index
        if end_quarters > position:
            total_ms += (end_quarters - position) * 60000.0 / float(
                self.effective_tempo_bpm(index)
            )
        return max(0, int(round(total_ms)))

    def get_status_bar_fields(self) -> List[str]:
        """The first four status-bar fields in Tab order: position, key,
        time signature, playback tempo. All read the CURRENT slice, not the
        score's opening values - any of them can change mid-score, unlike
        Region 1's one-off summary. The tempo field is the only way a
        screen-reader user can check playback tempo without an
        announcement."""
        bar_word = vocabulary.bar_word(self.uk_terms).capitalize()
        current = self.get_current_slice()
        if current is None:
            return [f"{bar_word} - beat -", "Key: -", "Time: -", self._tempo_status_field()]

        beat = current.beat_position
        beat_str = str(int(beat)) if float(beat).is_integer() else str(beat)
        ts_num, ts_den = current.time_sig
        # S6: the override, when set, wins everywhere - not just where the
        # file's own key is missing/wrong (matches how apply_part_overrides
        # already behaves for name/program).
        if self.key_signature_override_fifths is not None:
            key_name = key_signature_display_name(
                self.key_signature_override_fifths, self.key_signature_override_mode
            )
        else:
            key_name = key_signature_display_name(current.key_fifths, None)

        return [
            f"{bar_word} {current.measure} beat {beat_str}",
            f"Key: {key_name}",
            f"Time: {ts_num}/{ts_den}",
            self._tempo_status_field(),
        ]

    def _tempo_status_field(self) -> str:
        """Reads effective_tempo_display_bpm(), i.e. the score's own units
        (96 for eighth=96), never effective_tempo_bpm()'s internal
        quarter-note equivalent (48) - see the tempo_bpm field comment."""
        effective_str = self._format_tempo_number(self.effective_tempo_display_bpm())
        unit = f"{self.tempo_beat_unit_name_at()} notes per minute"
        if self.playback_tempo_offset == 0.0:
            return f"Playback tempo: {effective_str} {unit} (score default)"
        return f"Playback tempo: {effective_str} {unit}"