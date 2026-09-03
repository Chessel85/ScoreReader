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

# The three-way play extent the Play Settings dialog's "Play mode" combo
# offers and Ctrl+L cycles - it replaces the old loop_enabled tickbox
# ("Repeat (loop) until stopped").
#   to_end        - play from the cursor to the end of the piece, once
#   loop_once     - play the loop-length window once, then stop
#   loop_forever  - loop the loop-length window until playback is stopped
# loop_enabled (below) is True for both loop_once and loop_forever - it is
# still the flag every play-run code path keys off to decide "snap to the
# bar line and run a fixed window"; only the loop-RESTART is gated on
# loop_forever alone.
PLAY_MODE_TO_END = "to_end"
PLAY_MODE_LOOP_ONCE = "loop_once"
PLAY_MODE_LOOP_FOREVER = "loop_forever"
PLAY_MODES = (PLAY_MODE_TO_END, PLAY_MODE_LOOP_ONCE, PLAY_MODE_LOOP_FOREVER)
DEFAULT_PLAY_MODE = PLAY_MODE_TO_END


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

    play_mode is the three-way play extent (see PLAY_MODES above); it
    replaces the old loop_enabled bool. loop_enabled / loop_forever are now
    read-only views derived from it, kept as the names the play-run builder
    already uses.
    """

    lead_in_enabled: bool = True
    lead_in_bars: int = 1
    lead_in_beats: int = 0
    play_mode: str = DEFAULT_PLAY_MODE
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
        if self.play_mode not in PLAY_MODES:
            self.play_mode = DEFAULT_PLAY_MODE
        self.loop_length_bars = _clamp(
            self.loop_length_bars, MIN_LOOP_LENGTH_BARS, MAX_LOOP_LENGTH_BARS
        )
        self.loop_lead_in = bool(self.loop_lead_in)
        if self.loop_repeat_mode not in LOOP_REPEAT_MODES:
            self.loop_repeat_mode = DEFAULT_LOOP_REPEAT_MODE

    @property
    def loop_enabled(self) -> bool:
        """True for either looping mode (loop_once or loop_forever). The
        play-run builder (controllers/playback_controller.py) keys off this
        to decide "snap to the bar line and run a fixed loop_length_bars
        window" - which both looping modes do. "Play to end" is the only
        mode it is False for."""
        return self.play_mode in (PLAY_MODE_LOOP_ONCE, PLAY_MODE_LOOP_FOREVER)

    @property
    def loop_forever(self) -> bool:
        """Only "loop until stopped" - the mode that schedules the
        loop-restart timer. "loop once" plays the window a single time and
        then ends like a plain lead-in run."""
        return self.play_mode == PLAY_MODE_LOOP_FOREVER

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
            play_mode=self.play_mode,
            loop_length_bars=self.loop_length_bars,
            loop_lead_in=self.loop_lead_in,
            loop_repeat_mode=self.loop_repeat_mode,
        )

    def to_dict(self) -> dict:
        return {
            "lead_in_enabled": self.lead_in_enabled,
            "lead_in_bars": self.lead_in_bars,
            "lead_in_beats": self.lead_in_beats,
            "play_mode": self.play_mode,
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
        loop_includes_lead_in) so an existing settings.json carries over,
        and the pre-play_mode loop_enabled bool (maps on -> loop_forever,
        off -> to_end)."""
        if not data:
            return cls()
        defaults = cls()
        play_mode = data.get("play_mode")
        if play_mode not in PLAY_MODES:
            legacy_loop = data.get("loop_enabled", data.get("loop", False))
            play_mode = PLAY_MODE_LOOP_FOREVER if legacy_loop else PLAY_MODE_TO_END
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
            play_mode=play_mode,
            loop_length_bars=data.get(
                "loop_length_bars", data.get("preview_bars", defaults.loop_length_bars)
            ),
            loop_lead_in=data.get(
                "loop_lead_in",
                data.get("loop_includes_lead_in", defaults.loop_lead_in),
            ),
            loop_repeat_mode=data.get("loop_repeat_mode", defaults.loop_repeat_mode),
        )
