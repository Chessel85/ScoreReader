# widgets/voice_control_dialog.py
from typing import List, Optional

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
)

from models.voice_control_settings import DEFAULT_CONFIDENCE_THRESHOLD, VoiceControlSettings
from widgets.range_spin_box import RangeSpinBox

# Shown as the device combo's first entry when no device is selected, or
# when nothing is enumerated - never a real device description, so it can
# never collide with one. None (the default microphone) resolves to this.
NO_DEVICE = "(Default microphone)"


class VoiceControlDialog(QDialog):
    """Options > Voice Control Settings... (Ref 19) - which microphone to
    listen on for hands-free voice commands, and how confident a
    recognition result must be before it's acted on.

    Pure view, like every other dialog in this app: never touches
    VoiceControlController/SynthEngine itself, only emits signals -
    main_window.py's _show_voice_control_dialog wires those and performs
    commit_settings_edit/cancel_settings_edit itself once exec() returns,
    the same shape _show_live_midi_input_dialog already has.

    Unlike LiveMidiInputDialog, there is nothing to live-preview here (a
    confidence threshold has no audible effect until a command is actually
    spoken) - test_requested instead opens the separate practice/test
    dialog (widgets/voice_control_test_dialog.py) with whatever device/
    threshold is CURRENTLY SET IN THIS DIALOG (not yet committed), so the
    user can try a setting before deciding to keep it.

    Same focus-on-show reasoning as every other dialog in this app:
    setFocus() before the native window exists never reaches NVDA, so it's
    deferred to showEvent, on the first widget in tab order (enabled_checkbox)."""

    test_requested = Signal(str, float)  # device_name ("" for default), confidence_threshold
    refresh_requested = Signal()

    def __init__(
        self,
        parent=None,
        devices: Optional[List[str]] = None,
        settings: Optional[VoiceControlSettings] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Voice Control Settings")
        settings = settings or VoiceControlSettings()

        self.enabled_checkbox = QCheckBox("&Enable Voice Control", self)
        self.enabled_checkbox.setChecked(settings.enabled)

        self.device_combo = QComboBox(self)
        self.set_devices(devices or [], selected=settings.device_name)

        self.refresh_button = QPushButton("&Refresh", self)
        self.refresh_button.clicked.connect(self.refresh_requested)

        device_row = QHBoxLayout()
        device_row.addWidget(self.device_combo, stretch=1)
        device_row.addWidget(self.refresh_button)

        # reset_value matches DEFAULT_CONFIDENCE_THRESHOLD - the user's own
        # quick "somewhere reasonable" reference point.
        self.confidence_spin = RangeSpinBox(self, reset_value=int(round(DEFAULT_CONFIDENCE_THRESHOLD)))
        self.confidence_spin.setRange(0, 100)
        self.confidence_spin.setSuffix("%")
        self.confidence_spin.setValue(int(round(settings.confidence_threshold)))
        self.confidence_spin.setKeyboardTracking(False)

        form = QFormLayout()
        form.addRow("&Device:", device_row)
        form.addRow("&Confidence Threshold:", self.confidence_spin)

        self.test_button = QPushButton("&Test...", self)
        self.test_button.clicked.connect(self._on_test_clicked)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.enabled_checkbox)
        layout.addLayout(form)
        layout.addWidget(self.test_button)
        layout.addWidget(buttons)

    def set_devices(self, devices: List[str], selected: Optional[str] = None) -> None:
        """Repopulates the device combo - called at construction and from
        refresh_requested's handler (device list re-enumerated fresh, since
        it can change while the dialog is open). Preserves `selected` (the
        settings' own device_name) if it's still present in the new list,
        even across a refresh. Mirrors LiveMidiInputDialog.set_devices."""
        if selected is None:
            item = self.device_combo.currentData()
            selected = item if isinstance(item, str) else None
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        self.device_combo.addItem(NO_DEVICE, None)
        for name in devices:
            self.device_combo.addItem(name, name)
        index = self.device_combo.findData(selected) if selected else -1
        self.device_combo.setCurrentIndex(index if index >= 0 else 0)
        self.device_combo.blockSignals(False)

    def _on_test_clicked(self) -> None:
        device_name = self.device_combo.currentData()
        self.test_requested.emit(device_name or "", float(self.confidence_spin.value()))

    def result_settings(self) -> VoiceControlSettings:
        """Read after exec() returns Accepted."""
        return VoiceControlSettings(
            enabled=self.enabled_checkbox.isChecked(),
            device_name=self.device_combo.currentData(),
            confidence_threshold=float(self.confidence_spin.value()),
        )

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.enabled_checkbox.setFocus)
