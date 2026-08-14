# models/mixer_settings.py
"""Per-score mixer state: volume and pan per instrument, plus the click,
the spoken position announcer and the performance cue (wishlist #4), and
the global mute (wishlist #7).

Groundwork only - nothing in the app writes to this yet and no UI exposes
it. It is stdlib-only for the same reason as models/score_config_data.py:
models/ must stay Qt-free (guarded by test_models_package_does_not_import_qt).

**Only explicit overrides are stored.** A part absent from part_volumes has
no volume set at all, and the playback path must send no CC for it, leaving
FluidSynth exactly as it is today. That is what makes an empty MixerSettings
- the default for every score without a saved mixer - byte-for-byte
identical to having no mixer at all, rather than "identical because the
defaults happen to match".
"""
from dataclasses import dataclass, field
from typing import Dict, Optional

# MIDI CC value range. 100 is FluidSynth's own default channel volume and 64
# is centre pan; they are named here for the UI to start from, NOT applied
# as defaults - see the module docstring.
MIN_LEVEL = 0
MAX_LEVEL = 127
DEFAULT_VOLUME = 100
CENTRE_PAN = 64

# Keys for the three non-instrument channels, which have no part_id.
CLICK = "click"
ANNOUNCER = "announcer"
CUE = "cue"


def clamp(value: int) -> int:
    return max(MIN_LEVEL, min(MAX_LEVEL, int(value)))


@dataclass
class MixerSettings:
    """volume/pan overrides keyed by part_id, or by CLICK/ANNOUNCER/CUE for
    the three reserved channels. Empty means "nothing overridden"."""

    muted: bool = False
    volumes: Dict[str, int] = field(default_factory=dict)
    pans: Dict[str, int] = field(default_factory=dict)

    def volume_for(self, key: str) -> Optional[int]:
        """The override, or None when there is none - callers must skip
        sending CC entirely on None rather than substituting a default."""
        return self.volumes.get(key)

    def pan_for(self, key: str) -> Optional[int]:
        return self.pans.get(key)

    def set_volume(self, key: str, value: int) -> None:
        self.volumes[key] = clamp(value)

    def set_pan(self, key: str, value: int) -> None:
        self.pans[key] = clamp(value)

    def clear(self, key: str) -> None:
        """Drop a part's overrides, returning it to the engine's own
        defaults."""
        self.volumes.pop(key, None)
        self.pans.pop(key, None)

    def is_empty(self) -> bool:
        return not self.muted and not self.volumes and not self.pans

    def to_dict(self) -> dict:
        return {
            "muted": self.muted,
            "volumes": dict(self.volumes),
            "pans": dict(self.pans),
        }

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "MixerSettings":
        if not data:
            return cls()
        return cls(
            muted=bool(data.get("muted", False)),
            volumes={str(k): clamp(v) for k, v in (data.get("volumes") or {}).items()},
            pans={str(k): clamp(v) for k, v in (data.get("pans") or {}).items()},
        )
