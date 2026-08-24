# models/voice_control_settings.py
"""Hands-free voice control (feature/voice-control-vosk, Ref 19): which
microphone to listen on and how strict the confidence gate is. Stored
GLOBALLY (persistence/app_settings.py), not per score, the same reasoning as
models/live_midi_input_settings.py - which microphone is plugged in and how
sensitive it should be is the user's hardware setup, not a property of any
one piece.

device_name is matched by sounddevice's own enumerated device name at
connect time (audio/voice_recognition.py) - there is no more stable
cross-session device identifier available, the same convention
live_midi_input_settings.py's device_name already has for MIDI ports.
enabled=True with a device_name that isn't present this session degrades
silently (see controllers/voice_control_controller.py) rather than erroring.

confidence_threshold is a 0-100 percent floor: a recognition result below it
is dropped before it can be dispatched as a command (audio/
voice_recognition.py's _handle_final_result) - the main accuracy control
this feature exposes to the user, and the only one - a "minimum volume"
control was considered and deliberately dropped: it doesn't sharpen the
real accuracy/false-accept tradeoff the way confidence does (a loud
instrument strum clears a volume gate as easily as a real command would),
so it was never wired to anything and has been removed rather than kept as
dead settings.

stdlib-only, like every other models/ module - see
test_models_package_does_not_import_qt.
"""
from dataclasses import dataclass
from typing import Optional

DEFAULT_CONFIDENCE_THRESHOLD = 70.0


def _clamp(value: float, low: float, high: float, default: float) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


@dataclass
class VoiceControlSettings:
    enabled: bool = False
    device_name: Optional[str] = None
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD

    def __post_init__(self):
        self.enabled = bool(self.enabled)
        self.device_name = str(self.device_name) if self.device_name else None
        self.confidence_threshold = _clamp(
            self.confidence_threshold, 0.0, 100.0, DEFAULT_CONFIDENCE_THRESHOLD
        )

    def copy(self) -> "VoiceControlSettings":
        """An independent snapshot - the settings dialog's begin/commit/
        cancel edit session (controllers/voice_control_controller.py) needs
        its own working copy, the same reasoning LiveMidiInputSettings.copy()
        already has."""
        return VoiceControlSettings(
            enabled=self.enabled,
            device_name=self.device_name,
            confidence_threshold=self.confidence_threshold,
        )

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "device_name": self.device_name,
            "confidence_threshold": self.confidence_threshold,
        }

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "VoiceControlSettings":
        """A missing key falls back to that field's default, so a settings
        file written before this feature existed simply gets them - the same
        best-effort shape LiveMidiInputSettings.from_dict already has."""
        if not data:
            return cls()
        defaults = cls()
        return cls(
            enabled=data.get("enabled", defaults.enabled),
            device_name=data.get("device_name", defaults.device_name),
            confidence_threshold=data.get("confidence_threshold", defaults.confidence_threshold),
        )
