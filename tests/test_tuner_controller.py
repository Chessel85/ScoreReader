# tests/test_tuner_controller.py
"""controllers/tuner_controller.py, exercised entirely with NullTunerCapture -
never touches a real microphone (see tests/conftest.py's
_forbid_real_tuner_capture). Pitch-detection math itself is covered in
tests/audio/test_pitch_detector.py; this file covers only the controller's
own wiring: target/A4-reference/threshold updates reaching capture, the
listening lifecycle, settings persistence, the always-fires-every-cycle
pitch_result_changed signal (drives reading_edit), and the WAITING/REPORTING
accessible-announcement state machine (see the controller's own module
docstring, THIRD/FOURTH reports, for the two live-tested designs this
replaced).

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
from controllers.tuner_controller import (
    MIN_ATTACK_RISE_FRACTION,
    MIN_CONFIDENCE,
    REPORT_HOLD_SECONDS,
    SETTLE_DELAY_SECONDS,
    TunerController,
)
from models.tuner_instruments import (
    NO_SIGNAL_LEVEL_THRESHOLD,
    expected_frequency_hz,
    tuner_instrument_by_name,
)
from models.tuner_settings import TunerSettings
from persistence import app_settings
from tests.support.null_tuner_capture import NullTunerCapture

AUDIBLE_LEVEL = 0.5  # comfortably above the default 2% signal threshold
QUIET_LEVEL = 0.0  # comfortably below it
# Above zero but still below the default threshold - distinct from
# QUIET_LEVEL so a test can tell "true silence" apart from "some signal, but
# not enough to trust".
BELOW_THRESHOLD_LEVEL = NO_SIGNAL_LEVEL_THRESHOLD / 2


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


def _guitar_string(number: int):
    return tuner_instrument_by_name("Guitar").strings[number - 1]


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


# --- target/capture/threshold wiring (unaffected by the state-machine) -----

def test_set_target_updates_the_capture_search_band(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)

    controller.set_target(_guitar_string(1), 0)  # high E4

    assert capture.expected_hz == pytest.approx(expected_frequency_hz(_guitar_string(1), 0))


def test_set_target_applies_the_reference_offset(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)

    controller.set_target(_guitar_string(6), -2)  # low E2, two semitones flat

    assert capture.expected_hz == pytest.approx(expected_frequency_hz(_guitar_string(6), -2))


def test_set_target_applies_the_a4_reference(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)

    controller.set_target(_guitar_string(1), 0, a4_hz=442)

    assert capture.expected_hz == pytest.approx(expected_frequency_hz(_guitar_string(1), 0, 442))


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
    working.instrument = "Cello"
    working.reference_offset_semitones = 2

    controller.commit_settings_edit(working)

    assert controller.settings.instrument == "Cello"
    assert app_settings.load().tuner.instrument == "Cello"
    assert app_settings.load().tuner.reference_offset_semitones == 2


def test_cancel_settings_edit_leaves_settings_unchanged(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)
    original = TunerSettings(instrument="Guitar")
    controller.settings = original

    controller.begin_settings_edit()
    controller.cancel_settings_edit()

    assert controller.settings is original


# --- pitch_result_changed: fires every cycle, unaffected by the state machine

def test_in_tune_result_reaches_pitch_result_changed_with_near_zero_cents(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)
    controller.set_target(_guitar_string(1), 0)
    received = []
    controller.pitch_result_changed.connect(
        lambda result, cents, level: received.append((result, cents, level))
    )

    target_hz = expected_frequency_hz(_guitar_string(1), 0)
    _pluck(capture, target_hz)

    assert len(received) == 1
    result, cents, level = received[0]
    assert result is not None
    assert cents == pytest.approx(0.0, abs=1.0)
    assert level == AUDIBLE_LEVEL


def test_no_pitch_result_still_reports_level_with_none_cents(capture, clock, qtbot):
    """A None PitchResult (buffer too short, or nothing in the search band)
    must still carry the level reading through - level diagnostics work
    independently of whether a pitch was matched."""
    controller = _controller(capture, clock, qtbot)
    controller.set_target(_guitar_string(1), 0)
    received = []
    controller.pitch_result_changed.connect(
        lambda result, cents, level: received.append((result, cents, level))
    )

    _pluck(capture, target_hz=None)

    assert received == [(None, None, AUDIBLE_LEVEL)]


def test_pitch_result_changed_fires_every_cycle_even_mid_settle(capture, clock, qtbot):
    """reading_edit must keep updating live even while the state machine is
    still waiting out SETTLE_DELAY_SECONDS - only the SPOKEN announcement is
    gated, never this per-cycle signal."""
    controller = _controller(capture, clock, qtbot)
    controller.set_target(_guitar_string(1), 0)
    received = []
    controller.pitch_result_changed.connect(lambda *args: received.append(args))
    target_hz = expected_frequency_hz(_guitar_string(1), 0)

    _pluck(capture, target_hz)  # onset, not yet settled
    clock.advance(SETTLE_DELAY_SECONDS / 2)
    _pluck(capture, target_hz)  # still not settled

    assert len(received) == 2


def test_a_result_below_threshold_is_discarded_before_cents_are_computed(capture, clock, qtbot):
    """FOURTH live-testing report's regression test: a below-threshold
    peak_level used to still surface a computed cents figure alongside "no
    signal" (e.g. reading_edit showing "no signal - E: 104 cents flat").
    A result arriving below threshold must be treated as no result at all -
    both PitchResult and cents come through as None, regardless of what the
    detector itself returned."""
    controller = _controller(capture, clock, qtbot)
    controller.set_target(_guitar_string(1), 0)
    received = []
    controller.pitch_result_changed.connect(
        lambda result, cents, level: received.append((result, cents, level))
    )
    target_hz = expected_frequency_hz(_guitar_string(1), 0)

    _pluck(capture, target_hz, level=BELOW_THRESHOLD_LEVEL)

    assert received == [(None, None, BELOW_THRESHOLD_LEVEL)]


# --- WAITING/REPORTING accessible announcement ------------------------------

def test_a_quiet_signal_below_threshold_never_reports(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)
    controller.set_target(_guitar_string(1), 0)
    announcements = []
    controller.announcement_requested.connect(announcements.append)
    target_hz = expected_frequency_hz(_guitar_string(1), 0)

    for _ in range(5):
        _pluck(capture, target_hz, level=BELOW_THRESHOLD_LEVEL)
        clock.advance(SETTLE_DELAY_SECONDS)

    assert announcements == []


def test_pure_silence_never_announces(capture, clock, qtbot):
    """No note played, nothing spoken - unlike the old time-throttle design,
    where the very first result (even silence) always announced
    immediately."""
    controller = _controller(capture, clock, qtbot)
    controller.set_target(_guitar_string(1), 0)
    announcements = []
    controller.announcement_requested.connect(announcements.append)

    for _ in range(5):
        _pluck(capture, target_hz=None, level=QUIET_LEVEL)
        clock.advance(SETTLE_DELAY_SECONDS)

    assert announcements == []


def test_a_pluck_does_not_announce_before_the_settle_delay_elapses(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)
    controller.set_target(_guitar_string(1), 0)
    announcements = []
    controller.announcement_requested.connect(announcements.append)
    target_hz = expected_frequency_hz(_guitar_string(1), 0)

    _pluck(capture, target_hz)  # onset detected
    clock.advance(SETTLE_DELAY_SECONDS * 0.5)
    _pluck(capture, target_hz)  # still settling

    assert announcements == []


def test_a_pluck_announces_exactly_once_after_settling(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)
    controller.set_target(_guitar_string(1), 0)
    announcements = []
    controller.announcement_requested.connect(announcements.append)
    target_hz = expected_frequency_hz(_guitar_string(1), 0)

    _settle(capture, clock, target_hz)

    assert announcements == ["signal 50 percent. E. in tune"]


def test_a_cycle_with_no_pitch_lock_does_not_reset_the_settle_streak(capture, clock, qtbot):
    """FIFTH live-testing report's regression test: real playing was
    "inconsistent" - a loud, clean first pluck usually reported, but a
    second pluck of the same volume often got no response. Root cause: a
    single detection cycle's YIN pass can genuinely miss the pitch (result/
    cents come back None) even while the note is unambiguously still
    sounding well above the volume threshold - that must not restart the
    settle timer, or a real sustained pluck can go unreported."""
    controller = _controller(capture, clock, qtbot)
    controller.set_target(_guitar_string(1), 0)
    announcements = []
    controller.announcement_requested.connect(announcements.append)
    target_hz = expected_frequency_hz(_guitar_string(1), 0)

    _pluck(capture, target_hz)  # onset
    clock.advance(SETTLE_DELAY_SECONDS / 2)
    _pluck(capture, target_hz=None, level=AUDIBLE_LEVEL)  # loud, but no pitch lock this cycle
    clock.advance(SETTLE_DELAY_SECONDS / 2)
    _pluck(capture, target_hz)  # settled - reports, unaffected by the missed cycle

    assert announcements == ["signal 50 percent. E. in tune"]


def test_settle_delay_elapsing_without_a_pitch_lock_waits_for_one_rather_than_reporting_nothing(
    capture, clock, qtbot
):
    controller = _controller(capture, clock, qtbot)
    controller.set_target(_guitar_string(1), 0)
    announcements = []
    controller.announcement_requested.connect(announcements.append)
    target_hz = expected_frequency_hz(_guitar_string(1), 0)

    _pluck(capture, target_hz)  # onset
    clock.advance(SETTLE_DELAY_SECONDS)
    _pluck(capture, target_hz=None, level=AUDIBLE_LEVEL)  # settle delay elapsed, but no lock yet
    assert announcements == []

    _pluck(capture, target_hz)  # a later cycle with a lock, same clock time - reports now
    assert announcements == ["signal 50 percent. E. in tune"]


def test_a_sustained_pluck_does_not_re_announce_before_the_hold_expires(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)
    controller.set_target(_guitar_string(1), 0)
    announcements = []
    controller.announcement_requested.connect(announcements.append)
    target_hz = expected_frequency_hz(_guitar_string(1), 0)

    _settle(capture, clock, target_hz)  # first (only, so far) report
    for _ in range(3):
        clock.advance(SETTLE_DELAY_SECONDS)  # 3 * 0.35s stays under REPORT_HOLD_SECONDS (1.5s)
        _pluck(capture, target_hz)  # still ringing, same pluck, still holding

    assert announcements == ["signal 50 percent. E. in tune"]


def test_reporting_reverts_to_waiting_after_the_hold_and_announces_it(capture, clock, qtbot):
    """The user's own requested design: "says something like 5 cents sharp,
    then after a second or two, reverts to waiting" - the revert itself is
    also pushed, not just displayed, so it reaches the user regardless of
    where dialog focus currently is."""
    controller = _controller(capture, clock, qtbot)
    controller.set_target(_guitar_string(1), 0)
    announcements = []
    controller.announcement_requested.connect(announcements.append)
    target_hz = expected_frequency_hz(_guitar_string(1), 0)

    _settle(capture, clock, target_hz)  # first report
    clock.advance(REPORT_HOLD_SECONDS)
    _pluck(capture, target_hz=None, level=QUIET_LEVEL)  # first cycle after the hold expires

    assert announcements == ["signal 50 percent. E. in tune", "Waiting."]


def test_a_sustained_pluck_cycles_report_waiting_report_while_it_keeps_ringing(capture, clock, qtbot):
    """A held note doesn't just report once ever - once the hold reverts to
    WAITING, a still-ringing note settles and reports again, cycling for as
    long as it stays above threshold."""
    controller = _controller(capture, clock, qtbot)
    controller.set_target(_guitar_string(1), 0)
    announcements = []
    controller.announcement_requested.connect(announcements.append)
    target_hz = expected_frequency_hz(_guitar_string(1), 0)

    _settle(capture, clock, target_hz)  # first report
    clock.advance(REPORT_HOLD_SECONDS)
    _pluck(capture, target_hz)  # reverts to Waiting (this cycle only reverts - see
    # _advance_state's docstring: a REPORTING cycle either checks the hold
    # or returns, it never also starts tracking a new onset in the same call)
    _settle(capture, clock, target_hz)  # still ringing - registers onset, then settles again

    assert announcements == [
        "signal 50 percent. E. in tune",
        "Waiting.",
        "signal 50 percent. E. in tune",
    ]


def test_silence_then_a_new_pluck_announces_again(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)
    controller.set_target(_guitar_string(1), 0)
    announcements = []
    controller.announcement_requested.connect(announcements.append)
    target_hz = expected_frequency_hz(_guitar_string(1), 0)

    _settle(capture, clock, target_hz)  # first report
    clock.advance(REPORT_HOLD_SECONDS)
    _pluck(capture, target_hz=None, level=QUIET_LEVEL)  # reverts to Waiting (silence)

    clock.advance(0.1)
    _settle(capture, clock, target_hz)  # second pluck

    assert announcements == [
        "signal 50 percent. E. in tune",
        "Waiting.",
        "signal 50 percent. E. in tune",
    ]


def test_switching_target_mid_settle_discards_the_in_flight_state(capture, clock, qtbot):
    """set_target resets state - a pluck ringing against the OLD string
    shouldn't get reported against a newly-selected one."""
    controller = _controller(capture, clock, qtbot)
    controller.set_target(_guitar_string(1), 0)
    announcements = []
    controller.announcement_requested.connect(announcements.append)
    string1_hz = expected_frequency_hz(_guitar_string(1), 0)

    _pluck(capture, string1_hz)  # onset on string 1
    clock.advance(SETTLE_DELAY_SECONDS * 0.5)

    controller.set_target(_guitar_string(2), 0)  # switch before it settles
    clock.advance(SETTLE_DELAY_SECONDS * 0.6)  # would have settled on string 1 by now
    string2_hz = expected_frequency_hz(_guitar_string(2), 0)
    _pluck(capture, string2_hz)  # string 2's own onset just starting

    assert announcements == []


def test_start_listening_resets_state(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)
    controller.set_target(_guitar_string(1), 0)
    announcements = []
    controller.announcement_requested.connect(announcements.append)
    target_hz = expected_frequency_hz(_guitar_string(1), 0)

    _pluck(capture, target_hz)  # onset in flight
    controller.start_listening("My Microphone")  # reopen mid-onset
    clock.advance(SETTLE_DELAY_SECONDS)
    _pluck(capture, target_hz)  # this is the FIRST cycle since reopening

    assert announcements == []


# --- configurable signal threshold ------------------------------------------

def test_set_signal_threshold_raising_it_prevents_a_previously_reportable_level(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)
    controller.set_target(_guitar_string(1), 0)
    controller.set_signal_threshold(60)  # 60% - above AUDIBLE_LEVEL (50%)
    announcements = []
    controller.announcement_requested.connect(announcements.append)
    target_hz = expected_frequency_hz(_guitar_string(1), 0)

    for _ in range(5):
        _pluck(capture, target_hz, level=AUDIBLE_LEVEL)
        clock.advance(SETTLE_DELAY_SECONDS)

    assert announcements == []


def test_set_signal_threshold_lowering_it_allows_a_previously_too_quiet_level(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)
    controller.set_target(_guitar_string(1), 0)
    controller.set_signal_threshold(1)  # 1% - below BELOW_THRESHOLD_LEVEL (1%)
    announcements = []
    controller.announcement_requested.connect(announcements.append)
    target_hz = expected_frequency_hz(_guitar_string(1), 0)

    _settle(capture, clock, target_hz, level=BELOW_THRESHOLD_LEVEL)

    assert announcements == ["signal 1 percent. E. in tune"]


def test_set_signal_threshold_mid_settle_discards_the_in_flight_state(capture, clock, qtbot):
    controller = _controller(capture, clock, qtbot)
    controller.set_target(_guitar_string(1), 0)
    announcements = []
    controller.announcement_requested.connect(announcements.append)
    target_hz = expected_frequency_hz(_guitar_string(1), 0)

    _pluck(capture, target_hz)  # onset in flight
    clock.advance(SETTLE_DELAY_SECONDS * 0.5)

    controller.set_signal_threshold(10)  # changed before it settles

    clock.advance(SETTLE_DELAY_SECONDS * 0.6)  # would have settled by now, pre-reset
    _pluck(capture, target_hz)  # this is the FIRST cycle since the threshold change

    assert announcements == []


# --- confidence gate + attack (sharp-rise) gate, SIXTH report --------------

def test_a_low_confidence_result_never_reports_even_if_sustained(capture, clock, qtbot):
    """A low-confidence detection (e.g. non-tonal background noise that
    happens to cross the volume threshold) is treated exactly like no
    result at all - never contributes to pitch_result_changed's cents, and
    never settles/reports, no matter how long it's sustained."""
    controller = _controller(capture, clock, qtbot)
    controller.set_target(_guitar_string(1), 0)
    announcements = []
    controller.announcement_requested.connect(announcements.append)
    received = []
    controller.pitch_result_changed.connect(
        lambda result, cents, level: received.append((result, cents, level))
    )
    target_hz = expected_frequency_hz(_guitar_string(1), 0)
    low_confidence = MIN_CONFIDENCE - 0.1

    for _ in range(5):
        _pluck(capture, target_hz, confidence=low_confidence)
        clock.advance(SETTLE_DELAY_SECONDS)

    assert announcements == []
    assert all(result is None and cents is None for result, cents, _ in received)


def test_a_gradual_rise_never_reports(capture, clock, qtbot):
    """SIXTH live-testing report's core regression test for the attack
    gate: a source that creeps up smoothly (a fan spinning up, a voice
    getting louder) rather than jumping sharply in a single ~0.2s cycle
    must never validate as an attack, no matter how high it eventually
    climbs above threshold or how long it holds there."""
    controller = _controller(capture, clock, qtbot)
    controller.set_target(_guitar_string(1), 0)
    announcements = []
    controller.announcement_requested.connect(announcements.append)
    target_hz = expected_frequency_hz(_guitar_string(1), 0)
    min_rise = NO_SIGNAL_LEVEL_THRESHOLD * MIN_ATTACK_RISE_FRACTION
    step = min_rise / 2  # comfortably under the per-cycle rise requirement

    level = 0.0
    for _ in range(20):
        level += step
        _pluck(capture, target_hz, level=level)
        clock.advance(SETTLE_DELAY_SECONDS)
    # Comfortably above the default 2% threshold by now and holding steady -
    # still never validated, since no single cycle ever jumped sharply.
    for _ in range(5):
        _pluck(capture, target_hz, level=level)
        clock.advance(SETTLE_DELAY_SECONDS)

    assert announcements == []


def test_switching_target_does_not_require_a_fresh_attack_for_a_still_sounding_note(
    capture, clock, qtbot
):
    """_reset_state() (set_target/set_signal_threshold/start_listening's
    shared REPORT/settle-timing reset) deliberately does not clear
    _attack_validated/_previous_peak_level - those describe the real audio
    signal's own history, not the selected target. Switching strings while
    a note is still ringing at a steady level (no fresh sharp rise to
    offer) must not block a report against the new target."""
    controller = _controller(capture, clock, qtbot)
    controller.set_target(_guitar_string(1), 0)
    announcements = []
    controller.announcement_requested.connect(announcements.append)
    string1_hz = expected_frequency_hz(_guitar_string(1), 0)

    _settle(capture, clock, string1_hz)  # first report, on string 1 (E)
    clock.advance(REPORT_HOLD_SECONDS)

    controller.set_target(_guitar_string(2), 0)  # switch strings mid-ring, steady level
    string2_hz = expected_frequency_hz(_guitar_string(2), 0)
    clock.advance(SETTLE_DELAY_SECONDS)
    _pluck(capture, string2_hz)  # steady level, zero rise - onset via retained attack_validated
    clock.advance(SETTLE_DELAY_SECONDS)
    _pluck(capture, string2_hz)  # settles - reports against the NEW target

    assert announcements == [
        "signal 50 percent. E. in tune",
        "signal 50 percent. B. in tune",
    ]
