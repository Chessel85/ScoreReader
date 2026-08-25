# controllers/tuner_controller.py
"""Tools > Tuner (widgets/tuner_dialog.py) - owns audio/tuner_capture.py's
TunerCapture lifecycle, marshals its background-thread pitch results onto
Qt's main thread, and gates the QAccessibleAnnouncementEvent speech
feedback to one report per plucked note (see the THIRD live-testing report
below for why it's gated this way, not throttled by time) - speech only,
no synthesized audio-tone cue, reusing the existing announcement mechanism
controllers/region_presenter.py's _announce_measure_change already
established, rather than a new audio path.

Every announcement/status update leads with a raw input LEVEL reading
(models.tuner_instruments.level_description), not just note/cents -
reported live: with a real instrument played through real speakers into a
real microphone, nothing was ever announced, on any device or volume tried.
Root cause was two-fold: (1) TunerDialog's own initial target_changed
emission (at the end of its __init__) fired before main_window.py's
_show_tuner_dialog had connected it to set_target, so _target_string stayed
None until the user changed a control by hand; (2) with no target set, the
old _handle_pitch_result returned immediately with NO feedback at all, so
"the mic isn't hearing anything" and "the mic hears something but nothing
is locking on yet" were indistinguishable from the outside. Fixed by (1)
_show_tuner_dialog now seeding the initial target explicitly once
target_changed is connected, and (2) peak_level being computed and reported
on every single detection cycle regardless of target/pitch-lock state, so a
level reading is always available as an independent diagnostic signal.

GOTCHA, found on the SECOND live-testing report (level diagnostic confirmed
real audio WAS flowing through detect_pitch, yet NVDA still spoke nothing
at all): this controller does NOT perform the actual
QAccessible.updateAccessibility() call - it only computes WHEN to announce
and WHAT to say, then emits announcement_requested(str). The real dispatch
happens in widgets/tuner_dialog.py's own announce() method, using the
DIALOG (a real QWidget) as the event's target. controllers/
region_presenter.py's own _announce_measure_change - the only other place
in this codebase that fires a QAccessibleAnnouncementEvent - targets
self.region_3, a real widget it owns directly; this controller has no
widget of its own to target (TunerController is a plain QObject, mirroring
LiveMidiInputController/VoiceControlController, none of which do
accessibility announcements). The first cut of this file passed `self` (the
controller itself) as the event's target, which almost certainly has no
registered QAccessibleInterface for Qt's platform accessibility bridge to
resolve - so update_accessibility() had nothing to attach the notification
to and silently dropped every single one. Routing the actual dispatch
through the dialog is a structural fix, not just a location move: it works
because QAccessibleAnnouncementEvent needs a real accessible object behind
it, and only a widget has one.

THIRD live-testing report, after the above two fixes actually got a real
guitar tuned successfully: the announcement itself was re-enabled and fired
on a plain ~1s throttle (see the old ANNOUNCE_INTERVAL_SECONDS/
ANNOUNCE_CENTS_JUMP_THRESHOLD), which the user reported as disruptive to
navigate around - NVDA is their only source of information about the
screen, and being talked over on a timer while trying to Tab through the
dialog's controls made it hard to use, not helpful. Replaced with an
onset-triggered, single-report model (a since-superseded ARMED/onset design -
see FOURTH below): pluck a string once, get told the result once, after a
short settle delay - not a stream of updates. reading_edit
(widgets/tuner_dialog.py) is unaffected by any of this - it keeps updating
silently every detection cycle regardless, which is what the user actually
used to confirm the pipeline was alive in the first place.

FOURTH live-testing report, after the onset design above: two separate
problems, both reported together. (a) a below-threshold "no signal" reading
in reading_edit could still show a stray cents figure alongside it (e.g.
"no signal - E: 104 cents flat") - _handle_pitch_result computed cents from
ANY PitchResult the detector returned, without checking peak_level against
NO_SIGNAL_LEVEL_THRESHOLD first, so a faint/spurious detection below the
noise floor still got reported as a real reading. (b) despite the level
diagnostic confirming real signal (3-12% peak_level) while playing, NO
announcement was EVER heard regardless of which control had keyboard focus
- traced to the old two-threshold design (NO_SIGNAL_LEVEL_THRESHOLD=0.02,
ONSET_LEVEL_THRESHOLD=0.03) sitting too close to, and in practice above,
the user's own real plucked levels, so the onset settle timer could go
several plucks without ever completing. Both are fixed together by
replacing the fixed ONSET_LEVEL_THRESHOLD with ONE user-configurable
threshold (TunerSettings.signal_threshold_percent, widgets/tuner_dialog.py's
threshold_spin) that gates BOTH "is this even worth calling a reading" and
"has this settled long enough to report" - see _handle_pitch_result/
_advance_state below. The onset/settle-then-report ARMED design is also
replaced with an explicit two-state WAITING/REPORTING machine, per the
user's own requested design: while waiting, nothing is pushed repeatedly
(no bombardment); once a pluck clears the threshold and settles, the
reading is pushed ONCE ("signal 50 percent. E. 5 cents sharp"); after
REPORT_HOLD_SECONDS the state reverts to WAITING and THAT transition is
also pushed ("Waiting.") - so the user hears both "here's your reading" and
"listening again" regardless of where dialog focus currently is (a plain
QAccessibleAnnouncementEvent isn't tied to focus at all - the FOURTH
report's real bug was the announcement never firing in the first place, not
that it was inaudible once fired).

Constructed once in main_window.py's setup_controllers, like
LiveMidiInputController/VoiceControlController, but does NOT auto-start
listening at app startup - the tuner dialog is the only thing that starts/
stops capture (on show/close), per the plan's "no explicit Start/Stop
Listening control" UI simplification.

Threading: TunerCapture's detection-cycle callback fires on its own
background thread (see audio/tuner_capture.py), not Qt's main thread.
_on_raw_result (that thread) does nothing but emit _raw_pitch_result;
connected to its handler with an explicit Qt.ConnectionType.QueuedConnection,
forcing the actual announcement/UI update onto the main thread's event loop -
the same pattern controllers/live_midi_input_controller.py already
established for audio/midi_input.py's rtmidi callback thread.
"""
import time
from typing import Callable, List, Optional

from PySide6.QtCore import QObject, Qt, Signal

from audio.pitch_detector import PitchResult
from audio.tuner_capture import TunerCapture
from models.tuner_instruments import (
    TunerString,
    cents_deviation,
    cents_description,
    expected_frequency_hz,
    level_description,
)
from models.tuner_settings import TunerSettings
from persistence import app_settings

# How long a pluck must stay above the user's configured signal threshold
# before it's trusted enough to report - gives the string's attack
# transient time to decay into a stable fundamental. A starting point, not
# a settled value.
SETTLE_DELAY_SECONDS = 0.35

# How long a REPORTING state is held (both the spoken reading and
# reading_edit's text) before automatically reverting to WAITING - the
# user's own requested design ("says something like 5 cents sharp, then
# after a second or two, reverts to waiting"), not gated on the signal
# dropping again: a sustained note is expected to cycle WAITING -> settle ->
# REPORTING -> hold -> WAITING for as long as it keeps ringing above
# threshold, rather than reporting continuously or only once ever.
REPORT_HOLD_SECONDS = 1.5

# A detected pitch must clear this confidence (audio/pitch_detector.py's
# PitchResult.confidence, 0.0-1.0 - "1 minus the YIN dip's own remaining
# aperiodicity") before it's trusted at all - see _advance_state's own
# docstring, SIXTH report, for why: a real tone reliably scores near 1.0,
# non-tonal noise scores <=0.5 (tests/audio/test_pitch_detector.py::
# test_silence_returns_low_confidence), so this is a real, already-computed
# noise/tone discriminator that was simply never read before. FLAGGED FOR
# LIVE TUNING like every other threshold here. Deliberately not a user-
# facing setting like signal_threshold_percent - a raw 0-1 confidence
# number isn't a meaningful thing to hand a non-technical user.
MIN_CONFIDENCE = 0.85

# How large a single-cycle jump in peak_level counts as a genuine attack,
# rather than gradual background noise creeping above the signal threshold
# over several cycles - see _advance_state's own docstring, SIXTH report.
# Expressed as a FRACTION of the user's own configured signal threshold,
# not a flat 0.0-1.0 constant - a flat value would be mathematically
# impossible to clear once the threshold itself was set below it (a user
# can set signal_threshold_percent as low as 1%, and a real pluck's own
# peak_level can be that low too - live-tested regression: a flat 0.02
# requirement was larger than a 1% threshold could ever produce from a
# silent baseline, so nothing could ever validate at low thresholds). A
# real plucked/bowed attack rises from near-silence to its peak within
# milliseconds, far faster than one ~0.2s detection cycle, so even a quiet
# real pluck (the user's own real levels have been as low as 3-12%) should
# clear half its own threshold easily; a source that ramps up smoothly (a
# fan spinning up, a voice getting louder) shouldn't. FLAGGED FOR LIVE
# TUNING like every other threshold here.
MIN_ATTACK_RISE_FRACTION = 0.5


class TunerController(QObject):
    """pitch_result_changed carries (PitchResult|None, cents|None, peak_level)
    so the dialog's live status label can update on every detection cycle
    even though speech is throttled separately below. peak_level (0.0-1.0)
    is reported on EVERY cycle regardless of whether a pitch was confidently
    matched or a target is even selected yet - see level_description's own
    docstring for why: without it, "the mic isn't hearing anything" and "the
    mic hears something but nothing is locking on" were indistinguishable
    from the outside, which is exactly what was reported live.

    announcement_requested carries the fully-composed message string once
    the WAITING/REPORTING state machine below decides a pluck has settled
    (or that a held reading has expired back to waiting) - this controller
    does NOT call QAccessible.updateAccessibility() itself (see the module
    docstring's GOTCHA); widgets/tuner_dialog.py's announce() does that,
    using itself (a real widget) as the event's target."""

    pitch_result_changed = Signal(object, object, float)  # Optional[PitchResult], Optional[float] cents, peak_level
    announcement_requested = Signal(str)

    _raw_pitch_result = Signal(object, float)  # internal, thread-marshaling only

    def __init__(
        self,
        parent=None,
        capture: Optional[TunerCapture] = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        super().__init__(parent)
        self.settings: TunerSettings = app_settings.load().tuner
        self._capture = capture if capture is not None else TunerCapture()
        self._capture.set_callback(self._on_raw_result)
        self._raw_pitch_result.connect(self._handle_pitch_result, Qt.ConnectionType.QueuedConnection)
        self._target_string: Optional[TunerString] = None
        self._reference_offset_semitones: int = 0
        self._a4_hz: float = 440.0
        self._signal_threshold_percent: int = self.settings.signal_threshold_percent
        # clock is injectable so tests can control SETTLE_DELAY_SECONDS'/
        # REPORT_HOLD_SECONDS' elapsed-time checks deterministically,
        # without a real sleep.
        self._clock = clock
        # WAITING/REPORTING state (see _advance_state): _reporting=False
        # means WAITING - _signal_since tracks when the CURRENT above-
        # threshold streak started (for the settle delay), reset to None
        # whenever the signal drops back below threshold. _reporting=True
        # means REPORTING - _reported_at is when that state was entered,
        # used to time the automatic revert to WAITING.
        self._reporting: bool = False
        self._signal_since: Optional[float] = None
        self._reported_at: Optional[float] = None
        # Attack (sharp-rise) gate, SIXTH report - see _advance_state's own
        # docstring. _attack_validated=True means the CURRENT continuously-
        # sounding event has been confirmed to have started with a genuine
        # sharp rise in level, not just a gradual creep above threshold; it
        # survives a REPORTING->WAITING revert (a still-ringing note doesn't
        # need to re-prove itself) and only clears on real silence.
        # _previous_peak_level is the prior cycle's peak_level, tracked every
        # cycle unconditionally, used only to measure that rise.
        self._attack_validated: bool = False
        self._previous_peak_level: float = 0.0
        self._edit_snapshot: Optional[TunerSettings] = None

    # --- device/target -----------------------------------------------------

    def available_devices(self) -> List[str]:
        return self._capture.list_devices()

    def set_target(
        self, tuner_string: TunerString, reference_offset_semitones: int, a4_hz: float = 440.0
    ) -> None:
        """Called whenever the dialog's instrument/string/offset/A4-
        reference selection changes, live - if capture is already open it
        keeps running; only the frequency band detect_pitch searches is
        updated (see TunerCapture.set_target). Resets the WAITING/REPORTING
        state so a pluck already ringing against the OLD target doesn't get
        reported against the new one."""
        self._target_string = tuner_string
        self._reference_offset_semitones = reference_offset_semitones
        self._a4_hz = a4_hz
        expected_hz = expected_frequency_hz(tuner_string, reference_offset_semitones, a4_hz)
        self._capture.set_target(expected_hz)
        self._reset_state()

    def set_signal_threshold(self, percent: int) -> None:
        """Called whenever the dialog's threshold_spin changes, live - see
        TunerSettings.signal_threshold_percent's own docstring. Resets state
        for the same reason set_target does: a pluck already mid-settle
        against the OLD threshold shouldn't be judged against a new one."""
        self._signal_threshold_percent = percent
        self._reset_state()

    def _reset_state(self) -> None:
        """Called from set_target/set_signal_threshold/start_listening -
        clears only the REPORT/settle TIMING state (a pluck already mid-
        settle or held against the OLD target/threshold shouldn't be judged
        against a new one). Deliberately does NOT touch _attack_validated/
        _previous_peak_level - those describe the real audio signal's own
        recent dynamics, not anything about which target/threshold is
        selected, so switching a string or nudging the threshold shouldn't
        erase a genuinely-already-validated sharp rise (see _advance_state's
        own docstring, SIXTH report). start_listening resets those two
        separately, below - that one DOES discard real audio history, since
        TunerCapture.open() zeroes its buffer."""
        self._reporting = False
        self._signal_since = None
        self._reported_at = None

    # --- listening lifecycle (dialog show/close) ----------------------------

    def start_listening(self, device_name: Optional[str]) -> bool:
        self._reset_state()
        # TunerCapture.open() zeroes its rolling buffer - any prior attack/
        # rise history belongs to audio that no longer exists (see
        # _reset_state's own docstring for why this is separate from it).
        self._attack_validated = False
        self._previous_peak_level = 0.0
        opened = self._capture.open(device_name)
        if not opened:
            self._announce_raw("Could not open the selected audio input device.")
        return opened

    def stop_listening(self) -> None:
        self._capture.close()

    @property
    def is_listening(self) -> bool:
        return self._capture.is_open

    # --- settings dialog (begin/commit/cancel, mirrors                    --
    # --- LiveMidiInputController's begin_settings_edit/commit/cancel)      --

    def begin_settings_edit(self) -> TunerSettings:
        self._edit_snapshot = self.settings.copy()
        return self.settings.copy()

    def commit_settings_edit(self, new_settings: TunerSettings) -> None:
        self.settings = new_settings.copy()
        app_settings.set_tuner_settings(self.settings)
        self._edit_snapshot = None

    def cancel_settings_edit(self) -> None:
        self._edit_snapshot = None

    # --- capture thread -> Qt main thread -----------------------------------

    def _on_raw_result(self, result: Optional[PitchResult], peak_level: float) -> None:
        """TunerCapture's own detection-cycle thread. Does nothing but emit -
        see class docstring."""
        self._raw_pitch_result.emit(result, peak_level)

    def _handle_pitch_result(self, result: Optional[PitchResult], peak_level: float) -> None:
        """Qt main thread only (see class docstring). Unlike the first cut of
        this method, this no longer returns early when no target is selected
        or no pitch was confidently matched - peak_level alone is still
        reported in that case, so "nothing to say yet" and "the mic isn't
        hearing anything" stay distinguishable (see the class docstring).

        FOURTH report fix: below the user's configured signal threshold, a
        detected result is discarded entirely (not just left unreported) -
        cents must never be computed from a result that arrived alongside a
        "no signal" level, which is what previously let reading_edit show
        e.g. "no signal - E: 104 cents flat".

        SIXTH report fix: a result below MIN_CONFIDENCE is discarded the
        same way - see that constant's own docstring. Confidence is checked
        here (not in _advance_state) so a low-confidence detection reads as
        plain "no result" everywhere downstream, the same as a too-quiet
        one."""
        threshold = self._signal_threshold_percent / 100.0
        if peak_level < threshold or (result is not None and result.confidence < MIN_CONFIDENCE):
            result = None
        cents = None
        if result is not None and self._target_string is not None:
            expected_hz = expected_frequency_hz(
                self._target_string, self._reference_offset_semitones, self._a4_hz
            )
            cents = cents_deviation(result.frequency_hz, expected_hz)
        self.pitch_result_changed.emit(result, cents, peak_level)
        self._advance_state(cents, peak_level, threshold)

    # --- WAITING/REPORTING accessible speech ----------------------------------

    def _advance_state(self, cents: Optional[float], peak_level: float, threshold: float) -> None:
        """Runs every detection cycle (~0.2s). Replaces the old onset/ARMED
        design (see the module docstring's FOURTH report) with an explicit
        two-state machine:

        WAITING (_reporting=False): a pluck must clear `threshold` and hold
        for SETTLE_DELAY_SECONDS before it's trusted - once it does (AND a
        cents value is actually available - see the FIFTH report below),
        this reports the reading (once) and enters REPORTING. The streak
        resets - abandoning this pluck attempt - only when peak_level itself
        drops back below threshold (real silence); it does NOT itself push
        a "Waiting." announcement (there's nothing new to say - the dialog
        was already waiting).

        REPORTING (_reporting=True): held for REPORT_HOLD_SECONDS regardless
        of whether the note is still ringing, then reverts to WAITING and
        pushes "Waiting." - this is the transition the user asked for
        ("after a second or two, reverts to waiting"). If the note is still
        sounding above threshold once back in WAITING, the cycle naturally
        repeats (settle, report, hold, revert) for as long as it rings.

        FIFTH live-testing report: real playing produced "inconsistent"
        results - a loud, clean first pluck on a freshly-selected string
        usually reported, but a second pluck of the same volume often got no
        response at all, and switching strings wasn't a reliable way to
        recover it either. Root cause: the streak used to reset to None
        whenever a single detection cycle's `cents` came back None - but
        audio/pitch_detector.py's YIN search can genuinely miss the pitch on
        an individual ~0.2s cycle (attack-transient noise, phase/windowing
        effects) even while the note is unambiguously still sounding well
        above the volume threshold; on real audio this happened often enough
        that the settle timer rarely survived SETTLE_DELAY_SECONDS
        uninterrupted. The streak is now gated on peak_level ALONE (loud
        enough = still the same pluck, keep waiting); cents is only required
        at the moment of actually announcing, and if it isn't available yet
        on the cycle where the settle delay elapses, this simply keeps
        waiting for a later cycle that has one - it does not restart the
        clock.

        SIXTH live-testing report: user's own framing - "latch onto a sound
        we think needs tuning... don't respond when there is just
        background noise above the threshold." What real tuning software
        does about this (hardware clip-on/pedal and app-based alike, short
        of a piezo pickup which isn't available to a microphone-based app):
        gate on the detector's own periodicity/confidence score, AND
        recognise a note by its ATTACK, not by continuous level alone (the
        same "note-on" concept MIDI already has) - a real onset detector
        keys off the SHARPNESS of a rise (a large jump in energy within a
        single frame), not merely "was quiet a moment ago, now loud". An
        earlier cut of this gate used the weaker "was recently quiet"
        check - caught during design review before it ever shipped: that
        doesn't actually distinguish a plucked/bowed attack from noise that
        just gradually creeps up past the threshold over several cycles
        (a fan spinning up, a voice getting louder) - both look identical
        to a boolean quiet/loud check, since "was quiet, now loud" is true
        of a gradual rise too, just spread across more cycles.

        The confidence half is MIN_CONFIDENCE, applied in
        _handle_pitch_result. The attack half is `_attack_validated`/
        `_previous_peak_level` below: a streak is only allowed to START
        timing (`_signal_since` going from None to a real value) once this
        continuously-sounding event has been confirmed to begin with a
        genuine jump of at least `threshold * MIN_ATTACK_RISE_FRACTION` in
        a single ~0.2s cycle - a source that ramps up gradually never
        clears that per-cycle jump and so never latches on, even once it's
        comfortably above `threshold`. `_attack_validated` deliberately survives
        `_enter_waiting()` - a still-ringing note that already earned one
        report (FIFTH report's cycling behaviour) doesn't need to re-prove
        its attack on every report/waiting/report cycle, only a genuine
        return to silence clears it, so the NEXT sound (whatever it is) has
        to earn it fresh. Accepted, unavoidable limitation: a source that is
        ALREADY elevated at the very first detection cycle this
        TunerController instance ever observes (before `_previous_peak_level`
        has any real history) is compared against the 0.0 startup default,
        so an already-loud noise source present at the moment the dialog is
        first opened can still validate on that one cycle - there's no way
        to know what came before the first sample was ever captured."""
        now = self._clock()
        rise = peak_level - self._previous_peak_level
        self._previous_peak_level = peak_level
        if self._reporting:
            if self._reported_at is not None and now - self._reported_at >= REPORT_HOLD_SECONDS:
                self._enter_waiting()
            return
        if peak_level < threshold:
            self._signal_since = None
            self._attack_validated = False
            return
        if self._signal_since is None:
            if not self._attack_validated:
                if rise < threshold * MIN_ATTACK_RISE_FRACTION:
                    return  # above threshold, but no sharp rise - not a fresh attack
                self._attack_validated = True
            self._signal_since = now
            return
        if now - self._signal_since >= SETTLE_DELAY_SECONDS and cents is not None:
            self._signal_since = None
            self._reporting = True
            self._reported_at = now
            self._announce(cents, peak_level, threshold)

    def _enter_waiting(self) -> None:
        self._reporting = False
        self._reported_at = None
        self._signal_since = None
        self._announce_raw("Waiting.")

    def _announce(self, cents: Optional[float], peak_level: float, threshold: float) -> None:
        level_text = level_description(peak_level, threshold)
        if cents is None or self._target_string is None:
            message = f"{level_text}."
        else:
            message = f"{level_text}. {self._target_string.note_name}. {cents_description(cents)}"
        self._announce_raw(message)

    def _announce_raw(self, message: str) -> None:
        """Only emits - see the module docstring's GOTCHA for why this
        controller never calls QAccessible.updateAccessibility() itself.
        The dialog performs the real dispatch, through itself, once
        connected (main_window.py's _show_tuner_dialog)."""
        self.announcement_requested.emit(message)
