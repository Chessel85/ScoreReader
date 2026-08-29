# widgets/tuner_settings_dialog.py
from typing import List, Optional

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from models.tuner_instruments import (
    A4_FREQUENCY_HZ,
    A4_REFERENCE_MAX_HZ,
    A4_REFERENCE_MIN_HZ,
    SIGNAL_THRESHOLD_MAX_PERCENT,
    SIGNAL_THRESHOLD_MIN_PERCENT,
)
from models.tuner_settings import TunerSettings
from widgets.range_spin_box import RangeSpinBox

# Shown as the device combo's first entry - never a real device name, so it
# can never collide with one. Selecting it means "system default input
# device" (TunerCapture.open(None)).
SYSTEM_DEFAULT_DEVICE = "(System Default)"


class TunerSettingsDialog(QDialog):
    """Tools > Tuner's Settings button - the set-once values split out of
    the main TunerDialog (widgets/tuner_dialog.py) once that dialog stopped
    needing an Instrument/String picker: reference pitch (A4), signal
    sensitivity threshold, and input device. Mirrors
    widgets/live_midi_input_dialog.py's OK/Cancel + live-preview-then-
    commit/cancel shape, with one difference: UNLIKE that dialog's device
    combo (deliberately not live-previewed there, since nothing sounds
    until a note is played through a newly-connected MIDI port), THIS
    dialog's device_changed fires immediately on selection - the outer
    TunerDialog is still actively listening the whole time this dialog is
    open, so there is no reason to defer reopening capture with the new
    device.

    Pure view, like every other dialog in this app: never touches
    TunerController itself, only emits signals - main_window.py's
    _show_tuner_dialog wires those to the controller's live-preview setters
    and performs commit_settings_edit/cancel_settings_edit itself once
    exec() returns.

    Same focus-on-show reasoning as every other dialog: setFocus() before
    the native window exists never reaches NVDA, so it's deferred to
    showEvent."""

    a4_changed = Signal(int)         # a4_reference_hz, live preview
    threshold_changed = Signal(int)  # signal_threshold_percent, live preview
    device_changed = Signal(object)  # str device name, or None for system default - live
    refresh_requested = Signal()

    def __init__(
        self,
        parent=None,
        devices: Optional[List[str]] = None,
        settings: Optional[TunerSettings] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Tuner Settings")
        settings = settings or TunerSettings()

        # A different axis from the old per-string reference offset (now
        # removed entirely) - this shifts the whole pitch STANDARD (e.g.
        # Baroque 415Hz, orchestral 442Hz), not any individual note.
        # reset_value is the standard 440Hz concert pitch, not 0 - there's
        # no meaningful "zero" for a Hz value the way there is for an
        # offset.
        self.a4_spin = RangeSpinBox(self, reset_value=int(A4_FREQUENCY_HZ))
        self.a4_spin.setRange(A4_REFERENCE_MIN_HZ, A4_REFERENCE_MAX_HZ)
        self.a4_spin.setSuffix(" Hz")
        self.a4_spin.setValue(settings.a4_reference_hz)
        self.a4_spin.setKeyboardTracking(False)
        self.a4_spin.valueChanged.connect(self.a4_changed)

        # How loud a pluck must be before a reading is trusted at all - see
        # models/tuner_settings.TunerSettings.signal_threshold_percent's own
        # docstring for the live-tested bug this fixes (a below-threshold
        # "no signal" reading could still show a stray cents figure) and the
        # live-tested report behind adding it (a fixed threshold either
        # missed the user's own real, quiet plucks or was never crossed at
        # all, so no announcement ever fired).
        self.threshold_spin = RangeSpinBox(self, reset_value=settings.signal_threshold_percent)
        self.threshold_spin.setRange(SIGNAL_THRESHOLD_MIN_PERCENT, SIGNAL_THRESHOLD_MAX_PERCENT)
        self.threshold_spin.setSuffix(" %")
        self.threshold_spin.setValue(settings.signal_threshold_percent)
        self.threshold_spin.setKeyboardTracking(False)
        self.threshold_spin.valueChanged.connect(self.threshold_changed)

        self.device_combo = QComboBox(self)
        self.set_devices(devices or [], selected=settings.input_device)
        self.device_combo.currentIndexChanged.connect(self._on_device_changed)

        self.refresh_button = QPushButton("&Refresh", self)
        self.refresh_button.clicked.connect(self.refresh_requested)

        device_row = QHBoxLayout()
        device_row.addWidget(self.device_combo, stretch=1)
        device_row.addWidget(self.refresh_button)

        # An explicit QLabel + setBuddy, not QFormLayout.addRow("&Device:",
        # device_row) - live-tested (the old tuner_dialog.py this was moved
        # from): QFormLayout's addRow(str, QLayout) overload does NOT parse
        # the "&" mnemonic the way its addRow(str, QWidget) overload does
        # for every other row here, so it rendered the literal "&Device:"
        # text instead of an underlined "D". Constructing the QLabel
        # directly sidesteps whichever overload is used.
        device_label = QLabel("&Device:", self)
        device_label.setBuddy(self.device_combo)

        form = QFormLayout()
        form.addRow("Reference Pitch (&A4):", self.a4_spin)
        form.addRow("Signal &Threshold:", self.threshold_spin)
        form.addRow(device_label, device_row)

        # Live-tested (moved from the old tuner_dialog.py): a Realtek
        # microphone's own "signal enhancements" (acoustic echo
        # cancellation/noise suppression/beamforming, set through the
        # vendor's own audio console app, not anything Windows itself
        # exposes for a third-party app to detect programmatically) mangled
        # the captured audio badly enough that pitch detection never locked
        # reliably. No reliable way to detect that setting from here, so
        # this is a plain static reminder rather than a live check.
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

    # --- result ---------------------------------------------------------

    def result_settings(self) -> TunerSettings:
        """Read after exec() returns Accepted."""
        return TunerSettings(
            a4_reference_hz=self.a4_spin.value(),
            signal_threshold_percent=self.threshold_spin.value(),
            input_device=self.current_device(),
        )

    # --- lifecycle -----------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.a4_spin.setFocus)
