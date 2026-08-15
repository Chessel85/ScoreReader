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


@dataclass
class ScoreConfig:
    """Per-file config (Ref 27): which part/staff/voice combinations are
    switched off, which optional attributes are shown against notes in each
    voice, the order those attributes render in, and whether the metronome
    was on - everything MainWindow needs to restore a score to how the user
    last left it. Deliberately excludes language (persistence/app_settings.py
    - a global preference, not a per-file one).

    parts_off/staves_off/voices_off are each that node's OWN toggle state,
    independent of its ancestors - NOT the "effectively active" set, which
    cannot distinguish "this voice was switched off" from "this voice is
    merely hidden because its part is off", and so loses the voice's own
    state on reload. Region2HierarchyModel.get_off_node_keys()/
    apply_off_node_keys() are the lossless read/write side;
    MusicData.export_config() fills in only a best-effort voices_off for
    standalone use, which MainWindow overwrites before saving.

    Storing OFF-lists (rather than ON-lists) and filtering them against the
    freshly loaded score is what makes loading best-effort: an entry
    matching nothing in the current score is dropped, not fatal."""

    schema_version: int = 1
    parts_off: Set[str] = field(default_factory=set)
    staves_off: Set[StaffKey] = field(default_factory=set)
    voices_off: Set[VoiceKey] = field(default_factory=set)
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
    # S6: a single whole-piece key signature override. None/None means "use
    # the file's own key(s)" - not tied to score content the way the part
    # overrides above are, so apply_config() applies it unconditionally
    # rather than filtering against known part_ids.
    key_signature_override_fifths: Optional[int] = None
    key_signature_override_mode: Optional[str] = None
