# widgets/tuner_dialog.py
from typing import List, Optional

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QAccessible, QAccessibleAnnouncementEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from audio.pitch_detector import PitchResult
from models.tuner_instruments import (
    A4_FREQUENCY_HZ,
    A4_REFERENCE_MAX_HZ,
    A4_REFERENCE_MIN_HZ,
    REFERENCE_OFFSET_MAX_SEMITONES,
    REFERENCE_OFFSET_MIN_SEMITONES,
    SIGNAL_THRESHOLD_MAX_PERCENT,
    SIGNAL_THRESHOLD_MIN_PERCENT,
    TUNER_INSTRUMENT_NAMES,
    TunerString,
    cents_description,
    level_description,
    tuner_instrument_by_name,
)
from models.tuner_settings import TunerSettings
from widgets.range_spin_box import RangeSpinBox

# Shown as the device combo's first entry - never a real device name, so it
# can never collide with one. Selecting it means "system default input
# device" (TunerCapture.open(None)).
SYSTEM_DEFAULT_DEVICE = "(System Default)"


class TunerDialog(QDialog):
    """Tools > Tuner - pick an instrument/string/reference-pitch offset and
    a microphone; the dialog listens continuously for as long as it's open
    (starts on showEvent, stops in done() - see that method for why not
    closeEvent alone) and speaks throttled cents feedback via
    controllers/tuner_controller.py's QAccessibleAnnouncementEvent path.
    There is no explicit Start/Stop Listening control (the tuner plan's own
    UI simplification) - a physical clip-on tuner behaves the same way once
    switched on.

    Pure view, like every other dialog in this app: never touches
    TunerController/TunerCapture itself, only emits signals -
    main_window.py's _show_tuner_dialog wires those to the controller and
    performs commit/cancel itself once exec() returns. The ONE exception is
    announce() below: it performs the actual QAccessible.updateAccessibility()
    call (controllers/tuner_controller.py only decides WHEN/WHAT to announce
    and emits announcement_requested(str) - this dialog is the real widget
    behind the event, since a plain QObject controller has no accessibility
    interface for Qt's platform bridge to resolve; see that module's own
    GOTCHA for the live-tested bug this was).

    reading_edit (a read-only QLineEdit, not a QLabel) exists alongside the
    spoken announcement, not instead of it - added after a second live-
    testing report: the announcement mechanism turned out to be silently
    broken (see above), and there was no way for the user to independently
    confirm what the app was actually detecting without it. Being a real
    edit control in the tab order means NVDA reads its content the moment
    focus lands on it, which doesn't depend on whether announcement events
    are reaching the screen reader at all - a genuinely independent check.

    Unlike widgets/live_midi_input_dialog.py's device combo (deliberately
    NOT live-previewed - reconnecting a MIDI port is heavier than a CC
    tweak, and nothing sounds until a note is actually played through it),
    THIS dialog's whole purpose while open is listening, so device_changed
    fires immediately on selection and is wired to actually reopen capture -
    there's nothing to defer it for.

    Same focus-on-show reasoning as every other dialog: setFocus() before
    the native window exists never reaches NVDA, so it's deferred to
    showEvent."""

    target_changed = Signal(object, int, int)  # TunerString, reference_offset_semitones, a4_hz
    threshold_changed = Signal(int)       # signal_threshold_percent
    device_changed = Signal(object)       # str device name, or None for system default
    refresh_requested = Signal()
    listening_requested = Signal(object)  # str device name, or None - emitted once, on show
    listening_stopped = Signal()          # emitted once, from done() - see its docstring

    def __init__(
        self,
        parent=None,
        devices: Optional[List[str]] = None,
        settings: Optional[TunerSettings] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Tuner")
        settings = settings or TunerSettings()

        self.instrument_combo = QComboBox(self)
        self.instrument_combo.addItems(TUNER_INSTRUMENT_NAMES)
        instrument_index = self.instrument_combo.findText(settings.instrument)
        self.instrument_combo.setCurrentIndex(instrument_index if instrument_index >= 0 else 0)
        self.instrument_combo.currentTextChanged.connect(self._on_instrument_changed)

        self.string_combo = QComboBox(self)
        self._populate_strings(settings.last_string_index)
        self.string_combo.currentIndexChanged.connect(self._on_target_control_changed)

        self.offset_spin = RangeSpinBox(self, reset_value=0)
        self.offset_spin.setRange(REFERENCE_OFFSET_MIN_SEMITONES, REFERENCE_OFFSET_MAX_SEMITONES)
        self.offset_spin.setSuffix(" semitones")
        self.offset_spin.setValue(settings.reference_offset_semitones)
        self.offset_spin.setKeyboardTracking(False)
        self.offset_spin.valueChanged.connect(self._on_target_control_changed)

        # A different axis from offset_spin above - this shifts the whole
        # pitch STANDARD (e.g. Baroque 415Hz, orchestral 442Hz), not an
        # individual string away from its own standard pitch. reset_value
        # is the standard 440Hz concert pitch, not 0 - there's no
        # meaningful "zero" for a Hz value the way there is for an offset.
        self.a4_spin = RangeSpinBox(self, reset_value=int(A4_FREQUENCY_HZ))
        self.a4_spin.setRange(A4_REFERENCE_MIN_HZ, A4_REFERENCE_MAX_HZ)
        self.a4_spin.setSuffix(" Hz")
        self.a4_spin.setValue(settings.a4_reference_hz)
        self.a4_spin.setKeyboardTracking(False)
        self.a4_spin.valueChanged.connect(self._on_target_control_changed)

        # How loud a pluck must be before a reading is trusted at all - see
        # models/tuner_settings.TunerSettings.signal_threshold_percent's own
        # docstring for the live-tested bug this fixes (a below-threshold
        # "no signal" reading could still show a stray cents figure) and the
        # live-tested report behind adding it (a fixed threshold either
        # missed the user's own real, quiet plucks or was never crossed at
        # all, so no announcement ever fired). A separate signal from
        # target_changed, not folded into it - this isn't part of "what
        # note/pitch standard to compare against", it's a sensitivity knob.
        self.threshold_spin = RangeSpinBox(self, reset_value=settings.signal_threshold_percent)
        self.threshold_spin.setRange(SIGNAL_THRESHOLD_MIN_PERCENT, SIGNAL_THRESHOLD_MAX_PERCENT)
        self.threshold_spin.setSuffix(" %")
        self.threshold_spin.setValue(settings.signal_threshold_percent)
        self.threshold_spin.setKeyboardTracking(False)
        self.threshold_spin.valueChanged.connect(self._on_threshold_changed)

        self.device_combo = QComboBox(self)
        self.set_devices(devices or [], selected=settings.input_device)
        self.device_combo.currentIndexChanged.connect(self._on_device_changed)

        self.refresh_button = QPushButton("&Refresh", self)
        self.refresh_button.clicked.connect(self.refresh_requested)

        device_row = QHBoxLayout()
        device_row.addWidget(self.device_combo, stretch=1)
        device_row.addWidget(self.refresh_button)

        # An explicit QLabel + setBuddy, not QFormLayout.addRow("&Device:",
        # device_row) - live-tested (a screenshot of the running dialog):
        # QFormLayout's addRow(str, QLayout) overload does NOT parse the
        # "&" mnemonic the way its addRow(str, QWidget) overload does for
        # every other row here, so it rendered the literal "&Device:" text
        # instead of an underlined "D". Constructing the QLabel directly
        # sidesteps whichever overload is used.
        device_label = QLabel("&Device:", self)
        device_label.setBuddy(self.device_combo)

        # Read-only and genuinely focusable/tab-reachable (unlike a QLabel,
        # which NVDA won't announce on its own when its text changes while
        # unfocused) - see the class docstring for why this exists alongside
        # the spoken announcement rather than replacing it.
        self.reading_edit = QLineEdit(self)
        self.reading_edit.setReadOnly(True)
        reading_label = QLabel("Current &Reading:", self)
        reading_label.setBuddy(self.reading_edit)
        # Same wording the spoken/pushed "Waiting." announcement uses (see
        # controllers/tuner_controller.py) - initialised through
        # update_pitch_display itself rather than a separate hardcoded
        # string, so the two can't drift apart.
        self.update_pitch_display(None, None, 0.0)

        form = QFormLayout()
        form.addRow("&Instrument:", self.instrument_combo)
        form.addRow("&String:", self.string_combo)
        form.addRow("Reference &Pitch Offset:", self.offset_spin)
        form.addRow("Reference Pitch (&A4):", self.a4_spin)
        form.addRow("Signal &Threshold:", self.threshold_spin)
        form.addRow(device_label, device_row)
        form.addRow(reading_label, self.reading_edit)

        # Live-tested (FIFTH/sixth reports, controllers/tuner_controller.py):
        # a Realtek microphone's own "signal enhancements" (acoustic echo
        # cancellation/noise suppression/beamforming, set through the
        # vendor's own audio console app, not anything Windows itself
        # exposes for a third-party app to detect programmatically - see the
        # design discussion this came out of) mangled the captured audio
        # badly enough that pitch detection never locked reliably. No
        # reliable way to detect that setting from here, so this is a plain
        # static reminder rather than a live check.
        enhancements_note = QLabel(
            "For good results ensure that all microphone enhancements and effects are off.", self
        )
        enhancements_note.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(enhancements_note)
        layout.addWidget(buttons)

        # Deliberately NOT self._emit_target_changed() here: at this point
        # in __init__, the caller (main_window.py's _show_tuner_dialog)
        # hasn't connected target_changed to anything yet - that connection
        # happens on the lines immediately after TunerDialog(...) returns.
        # An emission from inside __init__ would fire into the void. Live-
        # tested bug this used to cause: the controller's target stayed
        # unset until the user changed a control by hand, and with no
        # target it gave no feedback at all, indistinguishable from the mic
        # not working. _show_tuner_dialog now seeds the initial target
        # itself, explicitly, once the connection actually exists.

    # --- instrument/string population --------------------------------------

    def _populate_strings(self, preferred_index: int) -> None:
        instrument = tuner_instrument_by_name(self.instrument_combo.currentText())
        self.string_combo.blockSignals(True)
        self.string_combo.clear()
        for tuner_string in instrument.strings:
            self.string_combo.addItem(tuner_string.label, tuner_string)
        index = preferred_index if 0 <= preferred_index < len(instrument.strings) else 0
        self.string_combo.setCurrentIndex(index)
        self.string_combo.blockSignals(False)

    def _on_instrument_changed(self, _text: str) -> None:
        self._populate_strings(preferred_index=0)
        self._emit_target_changed()

    def _on_target_control_changed(self, *_args) -> None:
        self._emit_target_changed()

    def _emit_target_changed(self) -> None:
        tuner_string = self.string_combo.currentData()
        if tuner_string is None:
            return
        self.target_changed.emit(tuner_string, self.offset_spin.value(), self.a4_spin.value())

    def _on_threshold_changed(self, _value: int) -> None:
        self.threshold_changed.emit(self.threshold_spin.value())

    def current_string(self) -> Optional[TunerString]:
        return self.string_combo.currentData()

    def current_offset(self) -> int:
        return self.offset_spin.value()

    def current_a4_hz(self) -> int:
        return self.a4_spin.value()

    def current_threshold_percent(self) -> int:
        return self.threshold_spin.value()

    def current_device(self) -> Optional[str]:
        item = self.device_combo.currentData()
        return item if isinstance(item, str) else None

    # --- device list ---------------------------------------------------------

    def set_devices(self, devices: List[str], selected: Optional[str] = None) -> None:
        """Repopulates the device combo - called at construction and from
        refresh_requested's handler (device list re-enumerated fresh, since
        it can change while the dialog is open). Preserves `selected` (the
        settings' own input_device) if it's still present in the new list,
        even across a refresh - mirrors
        widgets/live_midi_input_dialog.py's set_devices."""
        if selected is None:
            item = self.device_combo.currentData()
            selected = item if isinstance(item, str) else None
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        self.device_combo.addItem(SYSTEM_DEFAULT_DEVICE, None)
        for name in devices:
            self.device_combo.addItem(name, name)
        index = self.device_combo.findData(selected) if selected else -1
        self.device_combo.setCurrentIndex(index if index >= 0 else 0)
        self.device_combo.blockSignals(False)

    def _on_device_changed(self, _index: int) -> None:
        self.device_changed.emit(self.current_device())

    # --- live status (driven by TunerController.pitch_result_changed) ------

    def update_pitch_display(
        self, result: Optional[PitchResult], cents: Optional[float], peak_level: float
    ) -> None:
        """peak_level is always shown, regardless of whether a pitch was
        confidently matched - see controllers/tuner_controller.py's module
        docstring for why: without it, reading_edit couldn't tell "nothing
        reaching the mic" apart from "something reaching the mic but no
        clear pitch yet" either. Plain setText(), not setPlainText() or
        similar - QLineEdit, not a multi-line control, matching the single-
        line status this dialog reports.

        level_description is passed THIS dialog's own current threshold
        control (not its module default) so the displayed "no signal"
        boundary always matches what the controller actually gates a
        reading on - the two can't drift apart, the same reasoning
        cents_description/level_description are already shared functions
        for in the first place. cents is expected to already be None
        whenever peak_level is below that threshold (the controller's own
        job, not this method's)."""
        threshold = self.current_threshold_percent() / 100.0
        level_text = level_description(peak_level, threshold)
        if result is None or cents is None:
            self.reading_edit.setText(f"{level_text} - waiting")
            return
        tuner_string = self.current_string()
        note_label = tuner_string.note_name if tuner_string is not None else "?"
        self.reading_edit.setText(f"{level_text} - {note_label}: {cents_description(cents)}")

    def announce(self, message: str) -> None:
        """Performs the actual QAccessible.updateAccessibility() call, using
        THIS DIALOG (a real widget) as the event's target - see the class
        docstring's opening paragraph for why this can't live in the
        controller. main_window.py's _show_tuner_dialog connects
        TunerController.announcement_requested to this method."""
        event = QAccessibleAnnouncementEvent(self, message)
        event.setPoliteness(QAccessible.AnnouncementPoliteness.Assertive)
        QAccessible.updateAccessibility(event)

    # --- result ---------------------------------------------------------

    def result_settings(self) -> TunerSettings:
        """Read after exec() returns Accepted."""
        return TunerSettings(
            instrument=self.instrument_combo.currentText(),
            last_string_index=self.string_combo.currentIndex(),
            reference_offset_semitones=self.offset_spin.value(),
            a4_reference_hz=self.a4_spin.value(),
            signal_threshold_percent=self.threshold_spin.value(),
            input_device=self.current_device(),
        )

    # --- lifecycle -----------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.instrument_combo.setFocus)
        # Deferred alongside focus, for the same reason: starting the real
        # audio stream from inside showEvent itself (before the native
        # window is fully up) is avoidable jank a 0ms singleShot sidesteps,
        # matching how focus itself is handled on this exact line.
        QTimer.singleShot(0, lambda: self.listening_requested.emit(self.current_device()))

    def done(self, result):
        """Overridden rather than closeEvent: closeEvent only fires for a
        window-system close (the title bar X), not for accept()/reject()
        triggered by the OK/Cancel buttons or Escape - done() is the one
        method all of those funnel through, so it's the only reliable place
        to guarantee listening_stopped fires exactly once regardless of how
        the dialog closed."""
        self.listening_stopped.emit()
        super().done(result)
