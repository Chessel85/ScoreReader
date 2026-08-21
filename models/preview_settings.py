# models/preview_settings.py
"""How Preview (Enter in the Note region, Playback > Preview) behaves: the
count-in before it starts, how long it runs, and whether it loops.

Reported from real practice use: Preview used to sound the instant it was
pressed, leaving no time to get hands back onto the guitar, and it always
played exactly this bar plus the next, once. These settings are what the
Preview Settings dialog (widgets/preview_settings_dialog.py) edits and
controllers/playback_controller.py's preview session reads.

Stored GLOBALLY (persistence/app_settings.py), not per score like the mixer
- a lead-in length is a practice habit that should follow the user from
piece to piece, the same reasoning as the UK/US dialect. Confirmed with the
user.

stdlib-only for the same reason as models/mixer_settings.py and
models/score_config_data.py: models/ must stay Qt-free (guarded by
test_models_package_does_not_import_qt).
"""
from dataclasses import dataclass
from typing import Optional

# Clamp bounds. A hand-edited settings.json shouldn't be able to produce a
# zero-length preview (nothing would ever sound) or a count-in long enough
# to look like a hang; the dialog's own spin boxes use the same ranges.
MAX_LEAD_IN_BARS = 8
MAX_LEAD_IN_BEATS = 15
MIN_PREVIEW_BARS = 1
# High enough to read as "no real cap" for Alt+PageUp (controllers/
# playback_controller.py's adjust_preview_bars) - the user's explicit ask
# was no upper limit, but _clamp and the dialog's QSpinBox both need a
# finite bound; 999 bars is already the whole piece for any real score.
MAX_PREVIEW_BARS = 999


def _clamp(value: int, low: int, high: int) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = low
    return max(low, min(high, value))


@dataclass
class PreviewSettings:
    """Defaults are the shipped ones, chosen with the user: one full bar of
    clicks to get ready, today's two-bar preview length, no looping until
    it's asked for.

    lead_in_beats is EXTRA beats on top of lead_in_bars (so 1 bar + 2 beats
    in 4/4 counts six beats), not a total.
    """

    lead_in_bars: int = 1
    lead_in_beats: int = 0
    lead_in_click: bool = True
    preview_bars: int = 2
    loop: bool = False
    loop_includes_lead_in: bool = False

    def __post_init__(self):
        self.lead_in_bars = _clamp(self.lead_in_bars, 0, MAX_LEAD_IN_BARS)
        self.lead_in_beats = _clamp(self.lead_in_beats, 0, MAX_LEAD_IN_BEATS)
        self.preview_bars = _clamp(self.preview_bars, MIN_PREVIEW_BARS, MAX_PREVIEW_BARS)
        self.lead_in_click = bool(self.lead_in_click)
        self.loop = bool(self.loop)
        self.loop_includes_lead_in = bool(self.loop_includes_lead_in)

    def has_lead_in(self) -> bool:
        return self.lead_in_bars > 0 or self.lead_in_beats > 0

    def with_preview_bars(self, preview_bars: int) -> "PreviewSettings":
        """A copy with just preview_bars changed - Alt+PageUp/PageDown in
        the Note region (controllers/playback_controller.py.adjust_preview_
        bars) reads/writes only this one field, clamped the same way a
        typed dialog value is."""
        settings = self.copy()
        settings.preview_bars = preview_bars
        settings.__post_init__()
        return settings

    def copy(self) -> "PreviewSettings":
        """An independent snapshot. A preview session snapshots the settings
        when it starts, so editing them mid-loop can't change what the
        running loop is doing half way through."""
        return PreviewSettings(
            lead_in_bars=self.lead_in_bars,
            lead_in_beats=self.lead_in_beats,
            lead_in_click=self.lead_in_click,
            preview_bars=self.preview_bars,
            loop=self.loop,
            loop_includes_lead_in=self.loop_includes_lead_in,
        )

    def to_dict(self) -> dict:
        return {
            "lead_in_bars": self.lead_in_bars,
            "lead_in_beats": self.lead_in_beats,
            "lead_in_click": self.lead_in_click,
            "preview_bars": self.preview_bars,
            "loop": self.loop,
            "loop_includes_lead_in": self.loop_includes_lead_in,
        }

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "PreviewSettings":
        """A missing key falls back to that field's default, so a settings
        file written by an older version keeps working - the same
        best-effort shape MixerSettings.from_dict has."""
        if not data:
            return cls()
        defaults = cls()
        return cls(
            lead_in_bars=data.get("lead_in_bars", defaults.lead_in_bars),
            lead_in_beats=data.get("lead_in_beats", defaults.lead_in_beats),
            lead_in_click=data.get("lead_in_click", defaults.lead_in_click),
            preview_bars=data.get("preview_bars", defaults.preview_bars),
            loop=data.get("loop", defaults.loop),
            loop_includes_lead_in=data.get(
                "loop_includes_lead_in", defaults.loop_includes_lead_in
            ),
        )
