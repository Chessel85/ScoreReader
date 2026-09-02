# models/play_settings.py
"""How the one play transport (Space, Playback > Play Settings) behaves: the
lead-in count-in before it starts, and whether/how it loops.

Reported from real practice use: the old Preview used to sound the instant it
was pressed, leaving no time to get hands back onto the guitar, and it always
played exactly this bar plus the next, once. These settings are what the Play
Settings dialog (widgets/play_settings_dialog.py) edits and
controllers/playback_controller.py's play session reads.

Stored GLOBALLY (persistence/app_settings.py), not per score like the mixer
- a lead-in length is a practice habit that should follow the user from
piece to piece, the same reasoning as the UK/US dialect. Confirmed with the
user. (The absolute playback tempo IS per-score - models/music_data.py's
playback_tempo_bpm - since that is a property of the piece.)

stdlib-only for the same reason as models/mixer_settings.py and
models/score_config_data.py: models/ must stay Qt-free (guarded by
test_models_package_does_not_import_qt).
"""
from dataclasses import dataclass
from typing import Optional

# Clamp bounds. A hand-edited settings.json shouldn't be able to produce a
# zero-length loop (nothing would ever sound) or a count-in long enough to
# look like a hang; the dialog's own spin boxes use the same ranges.
MAX_LEAD_IN_BARS = 8
MAX_LEAD_IN_BEATS = 15
MIN_LOOP_LENGTH_BARS = 1
# Unified cap across the dialog, Alt+PageUp/PageDown, the typed Ctrl+Enter
# loop-length buffer and the "loop length N" voice command. 64 bars is
# already a very long practice loop for any real score.
MAX_LOOP_LENGTH_BARS = 64

# How a repeat barline clipped by the loop window is read (Ctrl+R cycles
# these; the Play Settings combo picks one). Only meaningful when looping is
# on and the score actually has repeat barlines.
#   first     - loop the FIRST play-through (repeat taken, 1st-time ending)
#   second    - loop the SECOND play-through (1st-time ending skipped)
#   alternate - alternate the two on successive loop iterations
LOOP_REPEAT_MODES = ("first", "second", "alternate")
DEFAULT_LOOP_REPEAT_MODE = "first"


def _clamp(value: int, low: int, high: int) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = low
    return max(low, min(high, value))


@dataclass
class PlaySettings:
    """Defaults are the shipped ones, chosen with the user: lead-in on with
    one full bar of clicks to get ready, looping off until it's asked for,
    a two-bar loop window when it is.

    lead_in_beats is EXTRA beats on top of lead_in_bars (so 1 bar + 2 beats
    in 4/4 counts six beats), not a total.

    lead_in_enabled is the single master toggle - it replaces the old
    has_lead_in() (bars/beats both zero) and lead_in_click (the tickbox now
    just IS "play the count-in click"; there is no silent-numbers-only
    count-in any more).
    """

    lead_in_enabled: bool = True
    lead_in_bars: int = 1
    lead_in_beats: int = 0
    loop_enabled: bool = False
    loop_length_bars: int = 2
    loop_lead_in: bool = False
    # How a repeat barline clipped by the loop window is read while looping
    # (see LOOP_REPEAT_MODES above). Only consulted when looping is on and
    # the score carries repeat barlines; an unknown value coerces to "first".
    loop_repeat_mode: str = DEFAULT_LOOP_REPEAT_MODE

    def __post_init__(self):
        self.lead_in_enabled = bool(self.lead_in_enabled)
        self.lead_in_bars = _clamp(self.lead_in_bars, 0, MAX_LEAD_IN_BARS)
        self.lead_in_beats = _clamp(self.lead_in_beats, 0, MAX_LEAD_IN_BEATS)
        self.loop_enabled = bool(self.loop_enabled)
        self.loop_length_bars = _clamp(
            self.loop_length_bars, MIN_LOOP_LENGTH_BARS, MAX_LOOP_LENGTH_BARS
        )
        self.loop_lead_in = bool(self.loop_lead_in)
        if self.loop_repeat_mode not in LOOP_REPEAT_MODES:
            self.loop_repeat_mode = DEFAULT_LOOP_REPEAT_MODE

    def has_lead_in(self) -> bool:
        """A count-in should actually happen: the master toggle is on AND
        there is at least one beat to count."""
        return self.lead_in_enabled and (self.lead_in_bars > 0 or self.lead_in_beats > 0)

    def with_loop_length_bars(self, loop_length_bars: int) -> "PlaySettings":
        """A copy with just loop_length_bars changed - Alt+PageUp/PageDown in
        the Note region (controllers/playback_controller.py.adjust_loop_
        length_bars) and the typed Ctrl+Enter buffer read/write only this
        one field, clamped the same way a typed dialog value is."""
        settings = self.copy()
        settings.loop_length_bars = loop_length_bars
        settings.__post_init__()
        return settings

    def copy(self) -> "PlaySettings":
        """An independent snapshot. A play session snapshots the settings
        when it starts, so editing them mid-loop can't change what the
        running loop is doing half way through."""
        return PlaySettings(
            lead_in_enabled=self.lead_in_enabled,
            lead_in_bars=self.lead_in_bars,
            lead_in_beats=self.lead_in_beats,
            loop_enabled=self.loop_enabled,
            loop_length_bars=self.loop_length_bars,
            loop_lead_in=self.loop_lead_in,
            loop_repeat_mode=self.loop_repeat_mode,
        )

    def to_dict(self) -> dict:
        return {
            "lead_in_enabled": self.lead_in_enabled,
            "lead_in_bars": self.lead_in_bars,
            "lead_in_beats": self.lead_in_beats,
            "loop_enabled": self.loop_enabled,
            "loop_length_bars": self.loop_length_bars,
            "loop_lead_in": self.loop_lead_in,
            "loop_repeat_mode": self.loop_repeat_mode,
        }

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "PlaySettings":
        """A missing key falls back to that field's default, so a settings
        file written by an older version keeps working - the same
        best-effort shape MixerSettings.from_dict has. Also accepts the
        pre-rename Preview keys (lead_in_click, preview_bars, loop,
        loop_includes_lead_in) so an existing settings.json carries over."""
        if not data:
            return cls()
        defaults = cls()
        return cls(
            lead_in_enabled=data.get(
                "lead_in_enabled",
                # No old master toggle: infer "on" unless the old file had a
                # zero-length count-in, matching the old has_lead_in().
                data.get("lead_in_bars", defaults.lead_in_bars) > 0
                or data.get("lead_in_beats", defaults.lead_in_beats) > 0
                if "lead_in_bars" in data or "lead_in_beats" in data
                else defaults.lead_in_enabled,
            ),
            lead_in_bars=data.get("lead_in_bars", defaults.lead_in_bars),
            lead_in_beats=data.get("lead_in_beats", defaults.lead_in_beats),
            loop_enabled=data.get("loop_enabled", data.get("loop", defaults.loop_enabled)),
            loop_length_bars=data.get(
                "loop_length_bars", data.get("preview_bars", defaults.loop_length_bars)
            ),
            loop_lead_in=data.get(
                "loop_lead_in",
                data.get("loop_includes_lead_in", defaults.loop_lead_in),
            ),
            loop_repeat_mode=data.get("loop_repeat_mode", defaults.loop_repeat_mode),
        )
