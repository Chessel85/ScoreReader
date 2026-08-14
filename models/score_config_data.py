# models/score_config_data.py
"""R2: the ScoreConfig data shape, with no Qt dependency.

This lived in persistence/score_config.py alongside the file I/O, which
imports PySide6.QtCore for QStandardPaths - and since MusicData imports
ScoreConfig (export_config/apply_config), importing anything from models/
pulled in the whole of Qt. That silently broke the invariant
main_window.py's detect_default_uk_terms() relies on ("models/ stays
Qt-free", the stated reason locale detection lives in the UI layer rather
than in models/vocabulary.py).

Split so the layering matches the claim: the data shape lives here, the
Qt-aware reading and writing of it stays in persistence/score_config.py,
which re-exports ScoreConfig so existing imports are unaffected. Note the
dependency direction - persistence imports models, never the reverse.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

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
    independent of its ancestors - NOT "effectively active" (which would
    conflate "this voice was individually switched off" with "this voice is
    merely hidden because its part is off"). Reported bug, live-tested:
    switching a part off with a sub-voice still individually on, then
    reloading, used to bring the sub-voice back off too, because the only
    thing persisted was a single flattened, ancestor-gated voice set that
    couldn't tell those two cases apart. Region2HierarchyModel.
    get_off_node_keys()/apply_off_node_keys() are the lossless read/write
    side of this - MusicData.export_config()/apply_config() only fill in a
    best-effort voices_off of their own (for standalone/test use with no
    Region 2 widget at all), which MainWindow overwrites with the real
    per-node sets before saving.

    All three (not-an-on-list) and voice_display_attributes/attribute_order
    filtered against the freshly-loaded score's own known parts/staves/
    voices/attribute keys are what make loading best-effort: a saved entry
    that no longer corresponds to anything in the current score is simply
    dropped rather than rejecting the whole config."""

    schema_version: int = 1
    parts_off: Set[str] = field(default_factory=set)
    staves_off: Set[StaffKey] = field(default_factory=set)
    voices_off: Set[VoiceKey] = field(default_factory=set)
    metronome_enabled: bool = False
    position_announcer_enabled: bool = False
    voice_display_attributes: Dict[VoiceKey, Set[str]] = field(default_factory=dict)
    attribute_order: List[str] = field(default_factory=list)
