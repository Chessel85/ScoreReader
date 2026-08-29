# models/score_config_data.py
"""The ScoreConfig data shape, deliberately free of any Qt dependency.

models/ must stay Qt-free (it is why locale detection lives in
main_window.py rather than models/vocabulary.py), and MusicData imports
ScoreConfig - so the shape cannot live next to persistence/score_config.py's
QStandardPaths use without dragging Qt into every models/ import. Reading
and writing stays there and re-exports ScoreConfig, so import sites are
unaffected. Dependency direction: persistence imports models, never the
reverse. Guarded by test_models_package_does_not_import_qt.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from models.mixer_settings import MixerSettings

VoiceKey = Tuple[str, int, int]
StaffKey = Tuple[str, int]
PercussionItemKey = Tuple[str, int]


@dataclass
class ScoreConfig:
    """Per-file config (Ref 27): which part/staff/voice combinations are
    muted or soloed, which optional attributes are shown against notes in
    each voice, the order those attributes render in, and whether the
    metronome was on - everything MainWindow needs to restore a score to how
    the user last left it. Deliberately excludes language
    (persistence/app_settings.py - a global preference, not a per-file one)
    and Region 2's expand/collapse state, which is a pure navigation
    convenience that always resets to fully expanded on load, never saved.

    parts_muted/staves_muted/voices_muted (and the parts_soloed/staves_soloed/
    voices_soloed counterparts) are each that node's OWN toggle state,
    independent of its ancestors - NOT the "effectively active" set, which
    cannot distinguish "this voice was individually muted" from "this voice
    is merely silenced because its part is muted", and so loses the voice's
    own state on reload. Region2HierarchyModel.get_muted_node_keys()/
    apply_muted_node_keys() (and the soloed counterparts) are the lossless
    read/write side; MusicData.export_config() fills in only a best-effort
    voices_muted for standalone use, which MainWindow overwrites before
    saving.

    Storing muted/soloed sets (rather than the complementary "active" list)
    and filtering them against the freshly loaded score is what makes
    loading best-effort: an entry matching nothing in the current score is
    dropped, not fatal."""

    schema_version: int = 3
    parts_muted: Set[str] = field(default_factory=set)
    staves_muted: Set[StaffKey] = field(default_factory=set)
    voices_muted: Set[VoiceKey] = field(default_factory=set)
    parts_soloed: Set[str] = field(default_factory=set)
    staves_soloed: Set[StaffKey] = field(default_factory=set)
    voices_soloed: Set[VoiceKey] = field(default_factory=set)
    metronome_enabled: bool = False
    position_announcer_enabled: bool = False
    voice_display_attributes: Dict[VoiceKey, Set[str]] = field(default_factory=dict)
    attribute_order: List[str] = field(default_factory=list)
    # Wishlist #4/#7: per-instrument volume/pan and the global mute. Empty
    # by default, which means "nothing overridden" - see MixerSettings.
    mixer: MixerSettings = field(default_factory=MixerSettings)
    # S5: per-part display-name/instrument overrides, keyed by part_id.
    # Same "explicit overrides only" shape as mixer above - empty means
    # every part keeps showing exactly what the file itself declared.
    part_name_overrides: Dict[str, str] = field(default_factory=dict)
    part_program_overrides: Dict[str, int] = field(default_factory=dict)
    # Wishlist #8 follow-up: per-percussion-item sound/name overrides and
    # the "Apply MusicXML offset for percussion" checkbox - see
    # MusicData.percussion_item_overrides/percussion_item_name_overrides/
    # percussion_auto_correct_enabled, which this mirrors verbatim.
    percussion_item_overrides: Dict[PercussionItemKey, int] = field(default_factory=dict)
    percussion_item_name_overrides: Dict[PercussionItemKey, str] = field(default_factory=dict)
    percussion_auto_correct_enabled: bool = False
    # S6: a single whole-piece key signature override. None/None means "use
    # the file's own key(s)" - not tied to score content the way the part
    # overrides above are, so apply_config() applies it unconditionally
    # rather than filtering against known part_ids.
    key_signature_override_fifths: Optional[int] = None
    key_signature_override_mode: Optional[str] = None
    # Ref 12: the absolute playback tempo the user set for this piece, in
    # quarter-note BPM (denominator-independent). None means "use the
    # score's own opening tempo". Per-score, unlike the global lead-in /
    # looping habits in persistence/app_settings.py.
    playback_tempo_bpm: Optional[float] = None
    # Options > Reorder Parts... - the part_id order the user chose, which
    # in turn controls Region 3's note-row order (most importantly, which
    # part's row a screen reader lands on first after every navigation
    # step - Region 3's "current" row is always row 0). Empty means "use
    # the score's own natural order" - see MusicData.reorder_parts, which
    # is best-effort against whatever parts the freshly loaded score
    # actually has.
    part_order: List[str] = field(default_factory=list)
    # Where the cursor was in the timeline when the score was last saved -
    # so reopening the file returns to the same place instead of always
    # starting over at index 0. Best-effort like everything else here: an
    # out-of-range value (the score changed since) is dropped in
    # MusicData.apply_config, leaving the default of 0.
    last_position_index: int = 0
