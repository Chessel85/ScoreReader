# models/tuner_settings.py
"""Tools > Tuner (widgets/tuner_dialog.py) - which instrument/string was last
selected, the reference-pitch offset, and which input device to use. Stored
GLOBALLY (persistence/app_settings.py), not per score, the same reasoning as
models/live_midi_input_settings.py - which instrument you're tuning and what
microphone you use is the user's own practice setup, not a property of any
one piece.

Only ever commits the dialog's PREFERENCES - never the transient detected
pitch itself, which has no business being persisted (see the tuner plan).

input_device is matched against sounddevice's own enumerated device name at
capture-open time (audio/tuner_capture.py), the same "no more stable
identifier available" reasoning device_name has in
models/live_midi_input_settings.py. None means "use the system default input
device".

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
    REFERENCE_OFFSET_MAX_SEMITONES,
    REFERENCE_OFFSET_MIN_SEMITONES,
    SIGNAL_THRESHOLD_MAX_PERCENT,
    SIGNAL_THRESHOLD_MIN_PERCENT,
    TUNER_INSTRUMENT_NAMES,
)

DEFAULT_SIGNAL_THRESHOLD_PERCENT = round(NO_SIGNAL_LEVEL_THRESHOLD * 100)  # 2

DEFAULT_INSTRUMENT = TUNER_INSTRUMENT_NAMES[0]  # Guitar


def _clamp(value: int, low: int, high: int, default: int) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


@dataclass
class TunerSettings:
    instrument: str = DEFAULT_INSTRUMENT
    last_string_index: int = 0  # 0-indexed into the instrument's strings tuple
    reference_offset_semitones: int = 0
    a4_reference_hz: int = int(A4_FREQUENCY_HZ)
    # How loud (peak_level, as a whole percent) a pluck must be before the
    # tuner trusts it enough to report a reading at all - see
    # models/tuner_instruments.level_description's own docstring. Exposed as
    # a user control (widgets/tuner_dialog.py's threshold_spin) after a live
    # report that a fixed threshold either missed real, quiet plucks or let
    # a below-threshold "no signal" reading still show a stray cents figure
    # (see controllers/tuner_controller.py's module docstring, FOURTH
    # report) - one number now gates both the "no signal" text and whether
    # a cents figure is ever computed at all.
    signal_threshold_percent: int = DEFAULT_SIGNAL_THRESHOLD_PERCENT
    input_device: Optional[str] = None

    def __post_init__(self):
        self.instrument = str(self.instrument) if self.instrument else DEFAULT_INSTRUMENT
        self.last_string_index = _clamp(self.last_string_index, 0, 15, 0)
        self.reference_offset_semitones = _clamp(
            self.reference_offset_semitones,
            REFERENCE_OFFSET_MIN_SEMITONES,
            REFERENCE_OFFSET_MAX_SEMITONES,
            0,
        )
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
            instrument=self.instrument,
            last_string_index=self.last_string_index,
            reference_offset_semitones=self.reference_offset_semitones,
            a4_reference_hz=self.a4_reference_hz,
            signal_threshold_percent=self.signal_threshold_percent,
            input_device=self.input_device,
        )

    def to_dict(self) -> dict:
        return {
            "instrument": self.instrument,
            "last_string_index": self.last_string_index,
            "reference_offset_semitones": self.reference_offset_semitones,
            "a4_reference_hz": self.a4_reference_hz,
            "signal_threshold_percent": self.signal_threshold_percent,
            "input_device": self.input_device,
        }

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "TunerSettings":
        """A missing key falls back to that field's default, so a settings
        file written before this feature existed simply gets them - the same
        best-effort shape LiveMidiInputSettings.from_dict already has."""
        if not data:
            return cls()
        defaults = cls()
        return cls(
            instrument=data.get("instrument", defaults.instrument),
            last_string_index=data.get("last_string_index", defaults.last_string_index),
            reference_offset_semitones=data.get(
                "reference_offset_semitones", defaults.reference_offset_semitones
            ),
            a4_reference_hz=data.get("a4_reference_hz", defaults.a4_reference_hz),
            signal_threshold_percent=data.get(
                "signal_threshold_percent", defaults.signal_threshold_percent
            ),
            input_device=data.get("input_device", defaults.input_device),
        )
