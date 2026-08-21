# models/live_midi_input_settings.py
"""Live MIDI input: play a connected MIDI keyboard/controller and hear it
through Recall Score's own synth (F/S/D-adjacent playback feature, requested
after the 44d447a MIDI-controller-collision fix). Stored GLOBALLY
(persistence/app_settings.py), not per score, the same reasoning as
models/preview_settings.py - which device is plugged in and what it sounds
like is the user's hardware setup, not a property of any one piece.
Confirmed with the user.

device_name is matched by rtmidi's own enumerated port name at connect time
(audio/midi_input.py) - there is no more stable cross-session device
identifier available. enabled=True with a device_name that isn't present
this session degrades silently (see controllers/live_midi_input_controller.py)
rather than erroring - the confirmed "auto-connect if present, otherwise say
nothing" behaviour.

gm_program is 1-indexed, matching PartStructureInfo.gmidi_program/
models/gm_instruments.py's own convention.

volume_percent/pan_percent are plain 0-100/-100..100 ints, converted to CC
via models/mixer_settings.py's volume_percent_to_cc/pan_percent_to_cc at the
one place that actually needs Qt anyway (the controller) - this module does
NOT import mixer_settings, so it stays independent of MixerSettings' own
per-score dict shape (there is deliberately no MixerSettings sentinel key
for live input: that class's whole shape is built around per-score
persistence via MusicData.export_config/apply_config, and bolting a global
concern onto it would mean either round-tripping through every score's .rsc
file for no reason, or special-casing one key to be exempt from that).

stdlib-only, like every other models/ module - see
test_models_package_does_not_import_qt.
"""
from dataclasses import dataclass
from typing import Optional

DEFAULT_GM_PROGRAM = 1  # Acoustic Grand Piano


def _clamp(value: int, low: int, high: int, default: int) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


@dataclass
class LiveMidiInputSettings:
    enabled: bool = False
    device_name: Optional[str] = None
    gm_program: int = DEFAULT_GM_PROGRAM
    volume_percent: int = 100
    pan_percent: int = 0

    def __post_init__(self):
        self.enabled = bool(self.enabled)
        self.device_name = str(self.device_name) if self.device_name else None
        self.gm_program = _clamp(self.gm_program, 1, 128, DEFAULT_GM_PROGRAM)
        self.volume_percent = _clamp(self.volume_percent, 0, 100, 100)
        self.pan_percent = _clamp(self.pan_percent, -100, 100, 0)

    def copy(self) -> "LiveMidiInputSettings":
        """An independent snapshot - the dialog's begin/preview/commit/
        cancel edit session (controllers/live_midi_input_controller.py)
        needs its own working copy, the same reasoning MixerSettings.copy()
        and PreviewSettings.copy() already have."""
        return LiveMidiInputSettings(
            enabled=self.enabled,
            device_name=self.device_name,
            gm_program=self.gm_program,
            volume_percent=self.volume_percent,
            pan_percent=self.pan_percent,
        )

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "device_name": self.device_name,
            "gm_program": self.gm_program,
            "volume_percent": self.volume_percent,
            "pan_percent": self.pan_percent,
        }

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "LiveMidiInputSettings":
        """A missing key falls back to that field's default, so a settings
        file written before this feature existed simply gets them - the same
        best-effort shape PreviewSettings.from_dict/MixerSettings.from_dict
        already have."""
        if not data:
            return cls()
        defaults = cls()
        return cls(
            enabled=data.get("enabled", defaults.enabled),
            device_name=data.get("device_name", defaults.device_name),
            gm_program=data.get("gm_program", defaults.gm_program),
            volume_percent=data.get("volume_percent", defaults.volume_percent),
            pan_percent=data.get("pan_percent", defaults.pan_percent),
        )
