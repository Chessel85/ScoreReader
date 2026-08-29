# tests/test_tuner_controller.py
"""controllers/tuner_controller.py, exercised entirely with NullTunerCapture -
never touches a real microphone (see tests/conftest.py's
_forbid_real_tuner_capture). Pitch-detection math itself is covered in
tests/audio/test_pitch_detector.py; nearest-note/naming math is covered in
tests/models/test_tuner_instruments.py. This file covers only the
controller's own wiring: the tracking/acquisition search-band state machine
that replaced the old fixed per-string target (see the controller's own
module docstring), A4-reference/threshold updates, the listening lifecycle,
settings persistence (including the Settings sub-dialog's live-revert-on-
cancel behavior, new in this redesign), the always-fires-every-cycle
pitch_result_changed signal (drives reading_edit), and the WAITING/REPORTING
accessible-announcement state machine (see the controller's own module
docstring, THIRD/FOURTH reports, for the two live-tested designs this
replaced - unchanged by the chromatic-tuner redesign).

QApplication.processEvents() is needed after simulate_result, the same
"a queued signal needs the event loop to actually run before asserting"
convention tests/test_live_midi_input_controller.py already uses - the
controller's _raw_pitch_result signal is connected with
Qt.ConnectionType.QueuedConnection specifically so result handling always
happens on the main thread (see the controller's own docstring).

FakeClock stands in for the controller's injectable `clock` parameter, so
SETTLE_DELAY_SECONDS'/REPORT_HOLD_SECONDS' elapsed-time checks can be driven
deterministically without a real sleep()."""
import pytest
from PySide6.QtWidgets import QApplication

from audio.pitch_detector import PitchResult
from audio.tuner_capture import (
    ACQUISITION_CENTER_HZ,
    ACQUISITION_SEARCH_SEMITONES,
    TRACKING_SEARCH_SEMITONES,
)
from controllers.tuner_controller import (
    MIN_ATTACK_RISE_FRACTION,
    MIN_CONFIDENCE,
    REPORT_HOLD_SECONDS,
    SETTLE_DELAY_SECONDS,
    TunerController,
)
from models.tuner_instruments import NO_SIGNAL_LEVEL_THRESHOLD
from models.tuner_settings import TunerSettings
from persistence import app_settings
from tests.support.null_tuner_capture import NullTunerCapture

AUDIBLE_LEVEL = 0.5  # comfortably above the default 2% signal threshold
QUIET_LEVEL = 0.0  # comfortably below it
# Above zero but still below the default threshold - distinct from
# QUIET_LEVEL so a test can tell "true silence" apart from "some signal, but
# not enough to trust".
BELOW_THRESHOLD_LEVEL = NO_SIGNAL_LEVEL_THRESHOLD / 2

# Exactly A4, so nearest_note reports it as "in tune" (0 cents) - a stand-in
# for the old _guitar_string(1) fixed target, now that there's nothing to
# select, only a raw frequency to detect.
NOTE_A4 = 440.0


class FakeClock:
    """Injectable stand-in for time.monotonic - lets state-machine tests
    control elapsed time deterministically."""

    def __init__(self, start: float = 0.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def capture():
    return NullTunerCapture(available_devices=["My Microphone", "Other Mic"])


@pytest.fixture
def clock():
    return FakeClock()


def _controller(capture, clock, qtbot):
    """qtbot is only depended on to guarantee a QApplication exists (needed
    for the controller's Qt signals/QueuedConnection) - pytest-qt's own
    fixture provides that just by being requested."""
    return TunerController(capture=capture, clock=clock)


def _pluck(capture, target_hz=None, confidence=0.9, level=AUDIBLE_LEVEL):
    """Simulates one detection cycle at the clock's current time."""
    result = None if target_hz is None else PitchResult(frequency_hz=target_hz, confidence=confidence)
    capture.simulate_result(result, level)
    QApplication.processEvents()


def _settle(capture, clock, target_hz, level=AUDIBLE_LEVEL):
    """Plucks and advances the clock until a reading has just been reported -
    the common setup step most REPORTING-state tests below need."""
    _pluck(capture, target_hz, level=level)
    clock.advance(SETTLE_DELAY_SECONDS)
    _pluck(capture, target_hz, level=level)


# --- tracking/acquisition search-band state machine -------------------------

def test_start_listening_seeds_the_acquisition_band(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)

    controller.start_listening(None)

    assert capture.expected_hz == pytest.approx(ACQUISITION_CENTER_HZ)
    assert capture.search_semitones == pytest.approx(ACQUISITION_SEARCH_SEMITONES)
    assert capture.prefer_lower_octave is True


def test_a_confident_result_locks_on_and_narrows_to_the_tracking_band(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)
    controller.start_listening(None)

    _pluck(capture, NOTE_A4)

    assert capture.expected_hz == pytest.approx(NOTE_A4)
    assert capture.search_semitones == pytest.approx(TRACKING_SEARCH_SEMITONES)
    assert capture.prefer_lower_octave is False


def test_genuine_silence_reverts_to_the_acquisition_band(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)
    controller.start_listening(None)
    _pluck(capture, NOTE_A4)  # lock on

    _pluck(capture, target_hz=None, level=QUIET_LEVEL)  # real silence

    assert capture.expected_hz == pytest.approx(ACQUISITION_CENTER_HZ)
    assert capture.search_semitones == pytest.approx(ACQUISITION_SEARCH_SEMITONES)
    assert capture.prefer_lower_octave is True


def test_a_momentary_miss_while_still_loud_does_not_drop_the_lock(capture, clock, qtbot):
    """FIFTH live-testing report's regression, applied to the search band
    this time (see the equivalent WAITING/REPORTING test below for the
    original report): a single cycle's YIN pass can genuinely miss the
    pitch even while the note is unambiguously still sounding well above
    the volume threshold - that must not drop the tracking-mode lock back
    to a wide acquisition search."""
    controller = _controller(capture, clock, qtbot)
    controller.start_listening(None)
    _pluck(capture, NOTE_A4)  # lock on

    _pluck(capture, target_hz=None, level=AUDIBLE_LEVEL)  # loud, but no pitch lock this cycle

    assert capture.expected_hz == pytest.approx(NOTE_A4)
    assert capture.search_semitones == pytest.approx(TRACKING_SEARCH_SEMITONES)
    assert capture.prefer_lower_octave is False


# --- A4 reference / device / threshold wiring -------------------------------

def test_set_a4_reference_changes_the_reported_note_and_cents(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)
    received = []
    controller.pitch_result_changed.connect(received.append)

    _pluck(capture, NOTE_A4)  # in tune under the default 440Hz reference
    controller.set_a4_reference(442)
    _pluck(capture, NOTE_A4)  # now flat of a 442Hz reference

    assert received[0] == "signal 50 percent - A: in tune"
    assert "A:" in received[1] and "flat" in received[1]


def test_start_and_stop_listening_delegate_to_capture(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)

    assert controller.start_listening("My Microphone") is True
    assert controller.is_listening
    assert capture.open_calls == ["My Microphone"]

    controller.stop_listening()

    assert not controller.is_listening
    assert capture.close_count == 1


def test_start_listening_degrades_silently_for_an_unavailable_device(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)

    assert controller.start_listening("Unplugged Device") is False
    assert not controller.is_listening


def test_start_listening_failure_is_announced(capture, clock, qtbot):
    """Reported live: opening the device could fail silently with no way
    for the user to know why nothing was ever heard. Now it's spoken -
    unaffected by the WAITING/REPORTING gate, since this fires directly."""
    controller = _controller(capture, clock, qtbot)
    announcements = []
    controller.announcement_requested.connect(announcements.append)

    controller.start_listening("Unplugged Device")

    assert announcements == ["Could not open the selected audio input device."]


def test_available_devices_reads_through_the_capture(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)

    assert controller.available_devices() == ["My Microphone", "Other Mic"]


def test_commit_settings_edit_persists_via_app_settings(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)
    working = controller.begin_settings_edit()
    working.a4_reference_hz = 442
    working.signal_threshold_percent = 10

    controller.commit_settings_edit(working)

    assert controller.settings.a4_reference_hz == 442
    assert app_settings.load().tuner.a4_reference_hz == 442
    assert app_settings.load().tuner.signal_threshold_percent == 10


def test_cancel_settings_edit_leaves_settings_unchanged(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)
    original = TunerSettings(a4_reference_hz=442)
    controller.settings = original

    controller.begin_settings_edit()
    controller.cancel_settings_edit()

    assert controller.settings is original


def test_cancel_settings_edit_reverts_live_a4_threshold_and_device(capture, clock, qtbot):
    """New in this redesign: unlike before, the outer TunerDialog and its
    running capture stay open across the Settings dialog's own lifetime, so
    Cancel must actively put live state back, not just leave self.settings
    alone (see cancel_settings_edit's own docstring)."""
    controller = _controller(capture, clock, qtbot)
    controller.start_listening("My Microphone")
    controller.commit_settings_edit(
        TunerSettings(a4_reference_hz=440, signal_threshold_percent=2, input_device="My Microphone")
    )
    controller.begin_settings_edit()

    # Live-preview changes, as the Settings dialog would push while open.
    controller.set_a4_reference(442)
    controller.set_signal_threshold(20)  # above AUDIBLE_LEVEL (50%)... no, below it - raised well above 2%
    controller.start_listening("Other Mic")

    controller.cancel_settings_edit()

    assert capture.device_name == "My Microphone"

    # A4 reverted: NOTE_A4 (exactly 440Hz) should read as "in tune" again,
    # not flat of a 442Hz reference.
    received = []
    controller.pitch_result_changed.connect(received.append)
    _pluck(capture, NOTE_A4)
    assert received == ["signal 50 percent - A: in tune"]

    # Threshold reverted to 2%: a level that would have been silently
    # discarded under the previewed 20% threshold now reports again.
    announcements = []
    controller.announcement_requested.connect(announcements.append)
    _settle(capture, clock, NOTE_A4, level=BELOW_THRESHOLD_LEVEL * 4)  # ~4%, above 2%, below 20%
    assert announcements == ["signal 4 percent. A. in tune"]


# --- pitch_result_changed: fires every cycle, unaffected by the state machine

def test_in_tune_result_reaches_pitch_result_changed_with_near_zero_cents(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)
    received = []
    controller.pitch_result_changed.connect(received.append)

    _pluck(capture, NOTE_A4)

    assert received == ["signal 50 percent - A: in tune"]


def test_no_pitch_result_still_reports_level_with_none_cents(capture, clock, qtbot):
    """A None PitchResult (buffer too short, or nothing in the search band)
    must still carry the level reading through - level diagnostics work
    independently of whether a pitch was matched."""
    controller = _controller(capture, clock, qtbot)
    received = []
    controller.pitch_result_changed.connect(received.append)

    _pluck(capture, target_hz=None)

    assert received == ["signal 50 percent - waiting"]


def test_pitch_result_changed_fires_every_cycle_even_mid_settle(capture, clock, qtbot):
    """reading_edit must keep updating live even while the state machine is
    still waiting out SETTLE_DELAY_SECONDS - only the SPOKEN announcement is
    gated, never this per-cycle signal."""
    controller = _controller(capture, clock, qtbot)
    received = []
    controller.pitch_result_changed.connect(received.append)

    _pluck(capture, NOTE_A4)  # onset, not yet settled
    clock.advance(SETTLE_DELAY_SECONDS / 2)
    _pluck(capture, NOTE_A4)  # still not settled

    assert len(received) == 2


def test_a_result_below_threshold_is_discarded_before_cents_are_computed(capture, clock, qtbot):
    """FOURTH live-testing report's regression test: a below-threshold
    peak_level used to still surface a computed cents figure alongside "no
    signal" (e.g. reading_edit showing "no signal - E: 104 cents flat").
    A result arriving below threshold must be treated as no result at all."""
    controller = _controller(capture, clock, qtbot)
    received = []
    controller.pitch_result_changed.connect(received.append)

    _pluck(capture, NOTE_A4, level=BELOW_THRESHOLD_LEVEL)

    assert received == ["no signal - waiting"]


# --- WAITING/REPORTING accessible announcement ------------------------------

def test_a_quiet_signal_below_threshold_never_reports(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)
    announcements = []
    controller.announcement_requested.connect(announcements.append)

    for _ in range(5):
        _pluck(capture, NOTE_A4, level=BELOW_THRESHOLD_LEVEL)
        clock.advance(SETTLE_DELAY_SECONDS)

    assert announcements == []


def test_pure_silence_never_announces(capture, clock, qtbot):
    """No note played, nothing spoken - unlike the old time-throttle design,
    where the very first result (even silence) always announced
    immediately."""
    controller = _controller(capture, clock, qtbot)
    announcements = []
    controller.announcement_requested.connect(announcements.append)

    for _ in range(5):
        _pluck(capture, target_hz=None, level=QUIET_LEVEL)
        clock.advance(SETTLE_DELAY_SECONDS)

    assert announcements == []


def test_a_pluck_does_not_announce_before_the_settle_delay_elapses(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)
    announcements = []
    controller.announcement_requested.connect(announcements.append)

    _pluck(capture, NOTE_A4)  # onset detected
    clock.advance(SETTLE_DELAY_SECONDS * 0.5)
    _pluck(capture, NOTE_A4)  # still settling

    assert announcements == []


def test_a_pluck_announces_exactly_once_after_settling(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)
    announcements = []
    controller.announcement_requested.connect(announcements.append)

    _settle(capture, clock, NOTE_A4)

    assert announcements == ["signal 50 percent. A. in tune"]


def test_a_cycle_with_no_pitch_lock_does_not_reset_the_settle_streak(capture, clock, qtbot):
    """FIFTH live-testing report's regression test: real playing was
    "inconsistent" - a loud, clean first pluck usually reported, but a
    second pluck of the same volume often got no response. Root cause: a
    single detection cycle's YIN pass can genuinely miss the pitch (result/
    cents come back None) even while the note is unambiguously still
    sounding well above the volume threshold - that must not restart the
    settle timer, or a real sustained pluck can go unreported."""
    controller = _controller(capture, clock, qtbot)
    announcements = []
    controller.announcement_requested.connect(announcements.append)

    _pluck(capture, NOTE_A4)  # onset
    clock.advance(SETTLE_DELAY_SECONDS / 2)
    _pluck(capture, target_hz=None, level=AUDIBLE_LEVEL)  # loud, but no pitch lock this cycle
    clock.advance(SETTLE_DELAY_SECONDS / 2)
    _pluck(capture, NOTE_A4)  # settled - reports, unaffected by the missed cycle

    assert announcements == ["signal 50 percent. A. in tune"]


def test_settle_delay_elapsing_without_a_pitch_lock_waits_for_one_rather_than_reporting_nothing(
    capture, clock, qtbot
):
    controller = _controller(capture, clock, qtbot)
    announcements = []
    controller.announcement_requested.connect(announcements.append)

    _pluck(capture, NOTE_A4)  # onset
    clock.advance(SETTLE_DELAY_SECONDS)
    _pluck(capture, target_hz=None, level=AUDIBLE_LEVEL)  # settle delay elapsed, but no lock yet
    assert announcements == []

    _pluck(capture, NOTE_A4)  # a later cycle with a lock, same clock time - reports now
    assert announcements == ["signal 50 percent. A. in tune"]


def test_a_sustained_pluck_does_not_re_announce_before_the_hold_expires(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)
    announcements = []
    controller.announcement_requested.connect(announcements.append)

    _settle(capture, clock, NOTE_A4)  # first (only, so far) report
    for _ in range(3):
        clock.advance(SETTLE_DELAY_SECONDS)  # 3 * 0.35s stays under REPORT_HOLD_SECONDS (1.5s)
        _pluck(capture, NOTE_A4)  # still ringing, same pluck, still holding

    assert announcements == ["signal 50 percent. A. in tune"]


def test_reporting_reverts_to_waiting_after_the_hold_and_announces_it(capture, clock, qtbot):
    """The user's own requested design: "says something like 5 cents sharp,
    then after a second or two, reverts to waiting" - the revert itself is
    also pushed, not just displayed, so it reaches the user regardless of
    where dialog focus currently is."""
    controller = _controller(capture, clock, qtbot)
    announcements = []
    controller.announcement_requested.connect(announcements.append)

    _settle(capture, clock, NOTE_A4)  # first report
    clock.advance(REPORT_HOLD_SECONDS)
    _pluck(capture, target_hz=None, level=QUIET_LEVEL)  # first cycle after the hold expires

    assert announcements == ["signal 50 percent. A. in tune", "Waiting."]


def test_a_sustained_pluck_cycles_report_waiting_report_while_it_keeps_ringing(capture, clock, qtbot):
    """A held note doesn't just report once ever - once the hold reverts to
    WAITING, a still-ringing note settles and reports again, cycling for as
    long as it stays above threshold."""
    controller = _controller(capture, clock, qtbot)
    announcements = []
    controller.announcement_requested.connect(announcements.append)

    _settle(capture, clock, NOTE_A4)  # first report
    clock.advance(REPORT_HOLD_SECONDS)
    _pluck(capture, NOTE_A4)  # reverts to Waiting (this cycle only reverts - see
    # _advance_state's docstring: a REPORTING cycle either checks the hold
    # or returns, it never also starts tracking a new onset in the same call)
    _settle(capture, clock, NOTE_A4)  # still ringing - registers onset, then settles again

    assert announcements == [
        "signal 50 percent. A. in tune",
        "Waiting.",
        "signal 50 percent. A. in tune",
    ]


def test_silence_then_a_new_pluck_announces_again(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)
    announcements = []
    controller.announcement_requested.connect(announcements.append)

    _settle(capture, clock, NOTE_A4)  # first report
    clock.advance(REPORT_HOLD_SECONDS)
    _pluck(capture, target_hz=None, level=QUIET_LEVEL)  # reverts to Waiting (silence)

    clock.advance(0.1)
    _settle(capture, clock, NOTE_A4)  # second pluck

    assert announcements == [
        "signal 50 percent. A. in tune",
        "Waiting.",
        "signal 50 percent. A. in tune",
    ]


def test_start_listening_resets_state(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)
    announcements = []
    controller.announcement_requested.connect(announcements.append)

    _pluck(capture, NOTE_A4)  # onset in flight
    controller.start_listening("My Microphone")  # reopen mid-onset
    clock.advance(SETTLE_DELAY_SECONDS)
    _pluck(capture, NOTE_A4)  # this is the FIRST cycle since reopening

    assert announcements == []


# --- configurable signal threshold ------------------------------------------

def test_set_signal_threshold_raising_it_prevents_a_previously_reportable_level(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)
    controller.set_signal_threshold(60)  # 60% - above AUDIBLE_LEVEL (50%)
    announcements = []
    controller.announcement_requested.connect(announcements.append)

    for _ in range(5):
        _pluck(capture, NOTE_A4, level=AUDIBLE_LEVEL)
        clock.advance(SETTLE_DELAY_SECONDS)

    assert announcements == []


def test_set_signal_threshold_lowering_it_allows_a_previously_too_quiet_level(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)
    controller.set_signal_threshold(1)  # 1% - below BELOW_THRESHOLD_LEVEL (1%)
    announcements = []
    controller.announcement_requested.connect(announcements.append)

    _settle(capture, clock, NOTE_A4, level=BELOW_THRESHOLD_LEVEL)

    assert announcements == ["signal 1 percent. A. in tune"]


def test_set_signal_threshold_mid_settle_discards_the_in_flight_state(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)
    announcements = []
    controller.announcement_requested.connect(announcements.append)

    _pluck(capture, NOTE_A4)  # onset in flight
    clock.advance(SETTLE_DELAY_SECONDS * 0.5)

    controller.set_signal_threshold(10)  # changed before it settles

    clock.advance(SETTLE_DELAY_SECONDS * 0.6)  # would have settled by now, pre-reset
    _pluck(capture, NOTE_A4)  # this is the FIRST cycle since the threshold change

    assert announcements == []


def test_signal_threshold_change_does_not_require_a_fresh_attack_for_a_still_sounding_note(
    capture, clock, qtbot
):
    """_reset_state() (set_signal_threshold/start_listening's shared
    REPORT/settle-timing reset) deliberately does not clear
    _attack_validated/_previous_peak_level - those describe the real audio
    signal's own history, not the configured threshold. Changing the
    threshold while a note is still ringing at a steady level (no fresh
    sharp rise to offer) must not block a later report."""
    controller = _controller(capture, clock, qtbot)
    announcements = []
    controller.announcement_requested.connect(announcements.append)

    _settle(capture, clock, NOTE_A4)  # first report
    clock.advance(REPORT_HOLD_SECONDS)

    controller.set_signal_threshold(3)  # nudge the threshold mid-ring, steady level
    clock.advance(SETTLE_DELAY_SECONDS)
    _pluck(capture, NOTE_A4)  # steady level, zero rise - onset via retained attack_validated
    clock.advance(SETTLE_DELAY_SECONDS)
    _pluck(capture, NOTE_A4)  # settles - reports again

    assert announcements == [
        "signal 50 percent. A. in tune",
        "signal 50 percent. A. in tune",
    ]


# --- confidence gate + attack (sharp-rise) gate, SIXTH report --------------

def test_a_low_confidence_result_never_reports_even_if_sustained(capture, clock, qtbot):
    """A low-confidence detection (e.g. non-tonal background noise that
    happens to cross the volume threshold) is treated exactly like no
    result at all - never contributes to pitch_result_changed's cents, and
    never settles/reports, no matter how long it's sustained."""
    controller = _controller(capture, clock, qtbot)
    announcements = []
    controller.announcement_requested.connect(announcements.append)
    received = []
    controller.pitch_result_changed.connect(received.append)
    low_confidence = MIN_CONFIDENCE - 0.1

    for _ in range(5):
        _pluck(capture, NOTE_A4, confidence=low_confidence)
        clock.advance(SETTLE_DELAY_SECONDS)

    assert announcements == []
    assert all(text.endswith("waiting") for text in received)


def test_a_gradual_rise_never_reports(capture, clock, qtbot):
    """SIXTH live-testing report's core regression test for the attack
    gate: a source that creeps up smoothly (a fan spinning up, a voice
    getting louder) rather than jumping sharply in a single ~0.2s cycle
    must never validate as an attack, no matter how high it eventually
    climbs above threshold or how long it holds there."""
    controller = _controller(capture, clock, qtbot)
    announcements = []
    controller.announcement_requested.connect(announcements.append)
    min_rise = NO_SIGNAL_LEVEL_THRESHOLD * MIN_ATTACK_RISE_FRACTION
    step = min_rise / 2  # comfortably under the per-cycle rise requirement

    level = 0.0
    for _ in range(20):
        level += step
        _pluck(capture, NOTE_A4, level=level)
        clock.advance(SETTLE_DELAY_SECONDS)
    # Comfortably above the default 2% threshold by now and holding steady -
    # still never validated, since no single cycle ever jumped sharply.
    for _ in range(5):
        _pluck(capture, NOTE_A4, level=level)
        clock.advance(SETTLE_DELAY_SECONDS)

    assert announcements == []
