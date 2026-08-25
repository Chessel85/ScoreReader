# models/tuner_instruments.py
"""Tools > Tuner (widgets/tuner_dialog.py) - static table of supported
instruments and their standard string pitches, numbered the way players
actually refer to them (string 1 = highest-pitched string). stdlib-only,
like every other models/ module (test_models_package_does_not_import_qt).

Harp is deliberately excluded from v1 - a full pedal/lever harp has ~40+
strings across many octaves with its own enharmonic pedal system, and
doesn't fit this "pick instrument, pick one of a handful of strings" model
without a much bigger design (see the tuner plan).

Every supported instrument's standard tuning is entirely natural notes (E,
B, G, D, A, C) - so unlike parsers/midi_timeline_builder.py's sharp/flat
enharmonic spelling, there's no accidental-spelling decision to make here.
"""
import math
from dataclasses import dataclass
from typing import Dict, Tuple

# Scientific pitch notation: MIDI 60 = C4 (middle C), matching the rest of
# this app's octave convention (parsers/midi_timeline_builder.py's
# _spell_pitch).
_NATURAL_PITCH_CLASS: Dict[str, int] = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

A4_FREQUENCY_HZ = 440.0
A4_MIDI_PITCH = 69

# A configurable A4 reference pitch, in Hz - a different axis from
# REFERENCE_OFFSET_*_SEMITONES below: that shifts a STRING away from its own
# standard pitch (e.g. drop-D), this shifts the whole PITCH STANDARD itself.
# 415 covers Baroque pitch, 446 comfortably covers the common 442-443
# orchestral convention with headroom - real tuners' typical range.
A4_REFERENCE_MIN_HZ = 415
A4_REFERENCE_MAX_HZ = 446

# Reference-pitch offset range, in semitones either side of a string's
# standard pitch - the user's "two tones either side... in semitone
# increments" read as +/-2 whole tones = +/-4 semitones. Flagged in the
# tuner plan as an interpretation worth confirming once the dialog exists;
# trivial to change these two constants either way.
REFERENCE_OFFSET_MIN_SEMITONES = -4
REFERENCE_OFFSET_MAX_SEMITONES = 4


def midi_pitch_for(note_name: str, octave: int) -> int:
    return (octave + 1) * 12 + _NATURAL_PITCH_CLASS[note_name]


@dataclass(frozen=True)
class TunerString:
    number: int  # 1-indexed, as players refer to strings (1 = highest)
    note_name: str  # a bare natural pitch class, e.g. "E" - see module docstring
    octave: int  # scientific pitch notation, e.g. 4 for the guitar's high E

    @property
    def label(self) -> str:
        """"String 1 (E4)" - the tuner dialog's string-combo entry text."""
        return f"String {self.number} ({self.note_name}{self.octave})"

    @property
    def midi_pitch(self) -> int:
        return midi_pitch_for(self.note_name, self.octave)


@dataclass(frozen=True)
class TunerInstrument:
    name: str
    strings: Tuple[TunerString, ...]  # string 1 (highest) first


def _strings(*pitches: Tuple[str, int]) -> Tuple[TunerString, ...]:
    return tuple(TunerString(i + 1, name, octave) for i, (name, octave) in enumerate(pitches))


TUNER_INSTRUMENTS: Tuple[TunerInstrument, ...] = (
    TunerInstrument("Guitar", _strings(("E", 4), ("B", 3), ("G", 3), ("D", 3), ("A", 2), ("E", 2))),
    TunerInstrument("Bass Guitar", _strings(("G", 2), ("D", 2), ("A", 1), ("E", 1))),
    TunerInstrument("Violin", _strings(("E", 5), ("A", 4), ("D", 4), ("G", 3))),
    TunerInstrument("Viola", _strings(("A", 4), ("D", 4), ("G", 3), ("C", 3))),
    TunerInstrument("Cello", _strings(("A", 3), ("D", 3), ("G", 2), ("C", 2))),
    TunerInstrument("Double Bass", _strings(("G", 2), ("D", 2), ("A", 1), ("E", 1))),
    # Re-entrant tuning (string 1 is not the lowest-pitched, string 4 is
    # lower than string 3) - as strung, not as pitch-ordered, per how a
    # ukulele player actually refers to their strings.
    TunerInstrument("Ukulele", _strings(("G", 4), ("C", 4), ("E", 4), ("A", 4))),
    # Courses, not individual strings - each pair is tuned to one
    # representative pitch (the tuner plan's own scope for this instrument).
    TunerInstrument("Mandolin", _strings(("E", 5), ("A", 4), ("D", 4), ("G", 3))),
)

TUNER_INSTRUMENT_NAMES: Tuple[str, ...] = tuple(instrument.name for instrument in TUNER_INSTRUMENTS)
_INSTRUMENTS_BY_NAME: Dict[str, TunerInstrument] = {i.name: i for i in TUNER_INSTRUMENTS}


def tuner_instrument_by_name(name: str) -> TunerInstrument:
    """Falls back to the first instrument (Guitar) for an unrecognised
    name - the same "best-effort, never raise" reasoning ScoreConfig's
    apply_config already uses for a saved value the current state doesn't
    recognise."""
    return _INSTRUMENTS_BY_NAME.get(name, TUNER_INSTRUMENTS[0])


def expected_frequency_hz(
    tuner_string: TunerString, offset_semitones: int = 0, a4_hz: float = A4_FREQUENCY_HZ
) -> float:
    """Equal temperament. offset_semitones shifts the target away from the
    string's own standard pitch (e.g. tuning a whole step down); a4_hz
    shifts the pitch standard itself (e.g. Baroque 415Hz or orchestral
    442Hz) - see A4_REFERENCE_MIN_HZ/MAX_HZ above for the two are distinct.
    Defaults to the standard 440Hz concert pitch, so every existing caller
    that doesn't pass a4_hz explicitly is unaffected."""
    midi_pitch = tuner_string.midi_pitch + offset_semitones
    return a4_hz * (2 ** ((midi_pitch - A4_MIDI_PITCH) / 12))


def cents_deviation(detected_hz: float, target_hz: float) -> float:
    """Signed cents: positive = sharp (detected above target), negative =
    flat. 1200 cents = one octave, the standard musical-interval unit."""
    if detected_hz <= 0 or target_hz <= 0:
        return 0.0
    return 1200.0 * math.log2(detected_hz / target_hz)


# Within this many cents of the target, a string reads as "in tune" -
# comfortably inside a typical tuner's tolerance and under the ~5-10 cent
# threshold of human pitch discrimination (see the tuner plan's forecast).
IN_TUNE_CENTS_TOLERANCE = 5


def cents_description(cents: float) -> str:
    """Shared by controllers/tuner_controller.py's spoken announcement and
    widgets/tuner_dialog.py's visual status label, so the two can't drift
    apart the way MusicXMLReader's two independent name reads once did
    (R5) - one formatting rule, read from both places."""
    rounded = round(cents)
    if abs(rounded) <= IN_TUNE_CENTS_TOLERANCE:
        return "in tune"
    direction = "sharp" if rounded > 0 else "flat"
    return f"{abs(rounded)} cents {direction}"


# Below this peak amplitude (0.0-1.0, a full-scale float sample buffer),
# there's nothing worth calling "signal" - room noise/mic self-noise alone
# can sit just above zero. Reported live: with the tuner open and an
# instrument played through real speakers into a real microphone, nothing
# was ever announced at all, on any device or volume tried - this diagnostic
# (an audio input LEVEL reading, independent of whether a pitch was
# confidently matched) exists to tell "the mic isn't picking anything up"
# apart from "the mic hears something but pitch detection isn't locking on",
# which looked identical before this existed. Now also the DEFAULT for
# TunerSettings.signal_threshold_percent (2) - a live-adjustable, per-user
# copy of this same value; see that field's own docstring for why a single
# hardcoded threshold wasn't enough (reported live: a real guitar's plucked
# level sat at 3-12%, close enough to whatever fixed threshold was tried
# that it needed to be user-tunable, not a constant).
NO_SIGNAL_LEVEL_THRESHOLD = 0.02

# TunerSettings.signal_threshold_percent's clamp range (a whole-percent UI
# value, 0.0-1.0 peak_level * 100) - 1% keeps meaningful headroom above pure
# mic self-noise, 50% is already louder than any normal pluck should need.
SIGNAL_THRESHOLD_MIN_PERCENT = 1
SIGNAL_THRESHOLD_MAX_PERCENT = 50


def level_description(peak_level: float, threshold: float = NO_SIGNAL_LEVEL_THRESHOLD) -> str:
    """Shared by controllers/tuner_controller.py's spoken announcement and
    widgets/tuner_dialog.py's visual status label, same reasoning as
    cents_description above. `threshold` defaults to the module constant so
    every existing caller is unaffected; the dialog/controller instead pass
    the user's own configured TunerSettings.signal_threshold_percent (as a
    0.0-1.0 fraction), so the displayed "no signal" boundary always matches
    what actually gates a spoken reading."""
    if peak_level < threshold:
        return "no signal"
    return f"signal {round(peak_level * 100)} percent"
