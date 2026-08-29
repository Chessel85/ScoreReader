# models/tuner_settings.py
"""Tools > Tuner (widgets/tuner_dialog.py) - the reference-pitch (A4),
signal-sensitivity threshold, and input device, set via the Tuner's
Settings sub-dialog (widgets/tuner_settings_dialog.py). Stored GLOBALLY
(persistence/app_settings.py), not per score, the same reasoning as
models/live_midi_input_settings.py - what microphone/reference pitch you
use is the user's own practice setup, not a property of any one piece.

Only ever commits the dialog's PREFERENCES - never the transient detected
pitch itself, which has no business being persisted.

input_device is matched against sounddevice's own enumerated device name at
capture-open time (audio/tuner_capture.py), the same "no more stable
identifier available" reasoning device_name has in
models/live_midi_input_settings.py. None means "use the system default input
device".

Redesigned alongside models/tuner_instruments.py's move to a generic
chromatic tuner: the old instrument/last_string_index/
reference_offset_semitones fields are gone - there's no instrument/string
selection or per-string drop-tuning offset left to remember. A settings
file saved before this redesign may still carry those now-dead keys;
from_dict below simply never reads them, the same best-effort silent-drop
convention ScoreConfig.apply_config already uses for a saved key the
current code no longer recognises.

stdlib-only, like every other models/ module - see
test_models_package_does_not_import_qt.
"""
from dataclasses import dataclass
from typing import Optional

from models.tuner_instruments import (
    A4_FREQUENCY_HZ,
    A4_REFERENCE_MAX_HZ,
    A4_REFERENCE_MIN_HZ,
    NO_SIGNAL_LEVEL_THRESHOLD,
    SIGNAL_THRESHOLD_MAX_PERCENT,
    SIGNAL_THRESHOLD_MIN_PERCENT,
)

DEFAULT_SIGNAL_THRESHOLD_PERCENT = round(NO_SIGNAL_LEVEL_THRESHOLD * 100)  # 2


def _clamp(value: int, low: int, high: int, default: int) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


@dataclass
class TunerSettings:
    a4_reference_hz: int = int(A4_FREQUENCY_HZ)
    # How loud (peak_level, as a whole percent) a pluck must be before the
    # tuner trusts it enough to report a reading at all - see
    # models/tuner_instruments.level_description's own docstring. Exposed as
    # a user control (widgets/tuner_settings_dialog.py's threshold_spin)
    # after a live report that a fixed threshold either missed real, quiet
    # plucks or let a below-threshold "no signal" reading still show a stray
    # cents figure (see controllers/tuner_controller.py's module docstring,
    # FOURTH report) - one number now gates both the "no signal" text and
    # whether a cents figure is ever computed at all.
    signal_threshold_percent: int = DEFAULT_SIGNAL_THRESHOLD_PERCENT
    input_device: Optional[str] = None

    def __post_init__(self):
        self.a4_reference_hz = _clamp(
            self.a4_reference_hz, A4_REFERENCE_MIN_HZ, A4_REFERENCE_MAX_HZ, int(A4_FREQUENCY_HZ)
        )
        self.signal_threshold_percent = _clamp(
            self.signal_threshold_percent,
            SIGNAL_THRESHOLD_MIN_PERCENT,
            SIGNAL_THRESHOLD_MAX_PERCENT,
            DEFAULT_SIGNAL_THRESHOLD_PERCENT,
        )
        self.input_device = str(self.input_device) if self.input_device else None

    def copy(self) -> "TunerSettings":
        """An independent snapshot - the controller's begin/commit/cancel
        edit session (controllers/tuner_controller.py) needs its own working
        copy, the same reasoning LiveMidiInputSettings.copy() already has."""
        return TunerSettings(
            a4_reference_hz=self.a4_reference_hz,
            signal_threshold_percent=self.signal_threshold_percent,
            input_device=self.input_device,
        )

    def to_dict(self) -> dict:
        return {
            "a4_reference_hz": self.a4_reference_hz,
            "signal_threshold_percent": self.signal_threshold_percent,
            "input_device": self.input_device,
        }

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "TunerSettings":
        """A missing key falls back to that field's default, so a settings
        file written before this feature existed simply gets them - the same
        best-effort shape LiveMidiInputSettings.from_dict already has. A
        settings file written by the OLD per-instrument tuner (carrying
        "instrument"/"last_string_index"/"reference_offset_semitones") is
        handled the same way in reverse: those keys are simply never read
        here, so they're silently dropped rather than rejecting the whole
        settings object."""
        if not data:
            return cls()
        defaults = cls()
        return cls(
            a4_reference_hz=data.get("a4_reference_hz", defaults.a4_reference_hz),
            signal_threshold_percent=data.get(
                "signal_threshold_percent", defaults.signal_threshold_percent
            ),
            input_device=data.get("input_device", defaults.input_device),
        )
