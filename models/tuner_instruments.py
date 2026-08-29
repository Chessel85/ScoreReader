# models/tuner_instruments.py
"""Tools > Tuner (widgets/tuner_dialog.py) - a generic chromatic tuner: no
instrument/string selection, no per-string drop-tuning offset. The dialog
auto-detects whatever note is currently sounding (controllers/
tuner_controller.py's tracking/acquisition search-band state machine,
audio/pitch_detector.py's detect_pitch) and this module supplies the pure
math for "what's the nearest chromatic note to this frequency, and what do
I call it" - nearest_note()/nearest_note_name() below.

Redesigned from the original "pick instrument, pick one of a handful of
strings, tune to that fixed target" model (which had TUNER_INSTRUMENTS,
TunerString, expected_frequency_hz, a per-string reference-offset control)
after live use showed the picker UI was the main friction: a player already
knows what note each string should be, so having the tuner ask them to
re-select a string every time they moved to a different one was pure
overhead. stdlib-only, like every other models/ module
(test_models_package_does_not_import_qt).
"""
import math
from typing import Tuple

from models.pitch_spelling import spell_pitch

A4_FREQUENCY_HZ = 440.0
A4_MIDI_PITCH = 69

# A configurable A4 reference pitch, in Hz - shifts the whole pitch
# STANDARD (e.g. Baroque 415Hz, orchestral 442Hz), not any individual note.
# 415 covers Baroque pitch, 446 comfortably covers the common 442-443
# orchestral convention with headroom - real tuners' typical range.
A4_REFERENCE_MIN_HZ = 415
A4_REFERENCE_MAX_HZ = 446


def nearest_note(frequency_hz: float, a4_hz: float = A4_FREQUENCY_HZ) -> Tuple[int, float]:
    """(midi_pitch, cents) for the nearest equal-tempered CHROMATIC note to
    frequency_hz - the whole basis of a chromatic auto-detecting tuner. All
    12 semitones, not just natural pitch classes - unlike the old fixed
    per-string target, there's no known target here to compare against, so
    every detected frequency is quantized to whichever of the 12 semitones
    it's actually closest to. cents keeps cents_deviation's own sign
    convention (positive = sharp). frequency_hz<=0 returns (A4_MIDI_PITCH,
    0.0), the same "never raise, return something inert" convention
    cents_deviation itself already has."""
    if frequency_hz <= 0:
        return A4_MIDI_PITCH, 0.0
    midi_pitch = round(12 * math.log2(frequency_hz / a4_hz) + A4_MIDI_PITCH)
    target_hz = a4_hz * (2 ** ((midi_pitch - A4_MIDI_PITCH) / 12))
    return midi_pitch, cents_deviation(frequency_hz, target_hz)


def nearest_note_name(midi_pitch: int) -> Tuple[str, int]:
    """(spoken note name, octave) for a MIDI pitch - always sharp, never
    flat, always the whole word ("D sharp", never "D#"/"Eb") - a chromatic
    tuner has no key-signature context to make a flat-vs-sharp spelling
    decision with, so always-sharp is both the simplest rule and what was
    requested. A thin wrapper around models/pitch_spelling.spell_pitch:
    fifths=0 lands in that function's non-negative-fifths branch, which is
    already exactly this always-sharp table - reused rather than
    duplicated, since it's already tested and relied on elsewhere (MIDI
    import, key-signature overrides)."""
    return spell_pitch(midi_pitch, fifths=0)


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
