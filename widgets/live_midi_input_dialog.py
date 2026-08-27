# widgets/live_midi_input_dialog.py
from typing import List, Optional

from PySide6.QtCore import QStringListModel, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QCompleter,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
)

from models.gm_instruments import GM_INSTRUMENT_NAMES, GM_PROGRAM_BY_NAME, gm_instrument_name
from models.live_midi_input_settings import LiveMidiInputSettings
from widgets.range_spin_box import RangeSpinBox

# Shown as the device combo's first entry when no device is selected, or
# when nothing is plugged in - never a real port name, so it can never
# collide with one.
NO_DEVICE = "(No device)"

# Transient sole entry while the port list is enumerated off the main
# thread (P1). set_devices() replaces it when the worker signals back.
SCANNING_DEVICES = "Scanning for devices…"


class LiveMidiInputDialog(QDialog):
    """Options > Live MIDI Input Settings... (Ctrl+Shift+L) - which MIDI
    device to play through Recall Score's own synth, what instrument it
    sounds as, and its volume/pan.

    Pure view, like every other dialog in this app: never touches
    LiveMidiInputController/SynthEngine itself, only emits signals -
    main_window.py's _show_live_midi_input_dialog wires those to
    controllers/live_midi_input_controller.py's preview_instrument/
    preview_volume/preview_pan (the live-preview push, mirroring
    MixerDialog's volume_changed/pan_changed) and performs
    commit_settings_edit/cancel_settings_edit itself once exec() returns.

    Device selection has NO live-preview signal, unlike instrument/volume/
    pan - there is nothing to preview about a port choice until a note is
    actually played through it, and reconnecting is a heavier operation
    than a CC tweak (see LiveMidiInputController.commit_settings_edit). It
    is read only via result_settings() after OK. Ports can be hot-plugged,
    and Qt has no native hotplug notification, so a Refresh button
    re-enumerates on demand rather than the combo silently going stale.

    Same focus-on-show reasoning as every other dialog: setFocus() before
    the native window exists never reaches NVDA, so it's deferred to
    showEvent."""

    instrument_changed = Signal(int)  # 1-indexed gm_program
    volume_changed = Signal(int)      # percent
    pan_changed = Signal(int)         # percent
    refresh_requested = Signal()

    def __init__(
        self,
        parent=None,
        devices: Optional[List[str]] = None,
        settings: Optional[LiveMidiInputSettings] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Live MIDI Input Settings")
        settings = settings or LiveMidiInputSettings()
        # The last-resolved GM program, used as result_settings()'s fallback
        # if the combo is left showing unresolved typed text at OK-time
        # (mirrors InstrumentDialog's "ignore an unresolved edit" handling,
        # but that dialog can fall back to its own _part_values; this one
        # has no such secondary store, so the last real resolution is kept
        # here instead).
        self._gm_program = settings.gm_program

        self.enabled_checkbox = QCheckBox("&Enable Live MIDI Input", self)
        self.enabled_checkbox.setChecked(settings.enabled)

        self.device_combo = QComboBox(self)
        self.set_devices(devices or [], selected=settings.device_name)

        self.refresh_button = QPushButton("&Refresh", self)
        self.refresh_button.clicked.connect(self.refresh_requested)

        device_row = QHBoxLayout()
        device_row.addWidget(self.device_combo, stretch=1)
        device_row.addWidget(self.refresh_button)

        self.instrument_combo = QComboBox(self)
        self.instrument_combo.setEditable(True)
        self.instrument_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.instrument_combo.addItems(GM_INSTRUMENT_NAMES)
        completer = QCompleter(self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setModel(QStringListModel(GM_INSTRUMENT_NAMES, self))
        self.instrument_combo.setCompleter(completer)
        self.instrument_combo.setCurrentText(gm_instrument_name(settings.gm_program))
        self.instrument_combo.currentTextChanged.connect(self._on_instrument_text_changed)

        # reset_value=50 for volume (the user's own quick "somewhere
        # reasonable" reference point, not a claim 50% is the true default -
        # same reasoning MixerDialog's volume_spin already has), 0 (centre)
        # for pan.
        self.volume_spin = RangeSpinBox(self, reset_value=50)
        self.volume_spin.setRange(0, 100)
        self.volume_spin.setSuffix("%")
        self.volume_spin.setValue(settings.volume_percent)
        self.volume_spin.setKeyboardTracking(False)
        self.volume_spin.valueChanged.connect(self.volume_changed)

        self.pan_spin = RangeSpinBox(self, reset_value=0)
        self.pan_spin.setRange(-100, 100)
        self.pan_spin.setSuffix("%")
        self.pan_spin.setValue(settings.pan_percent)
        self.pan_spin.setKeyboardTracking(False)
        self.pan_spin.valueChanged.connect(self.pan_changed)

        form = QFormLayout()
        form.addRow("&Device:", device_row)
        form.addRow("&Instrument:", self.instrument_combo)
        form.addRow("&Volume:", self.volume_spin)
        form.addRow("Pa&n:", self.pan_spin)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.enabled_checkbox)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def set_devices(self, devices: List[str], selected: Optional[str] = None) -> None:
        """Repopulates the device combo - called at construction and from
        refresh_requested's handler (device list re-enumerated fresh, since
        it can change while the dialog is open). Preserves `selected` (the
        settings' own device_name) if it's still present in the new list,
        even across a refresh."""
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

    def set_devices_scanning(self) -> None:
        """Show a single "Scanning…" entry while the real port list is being
        enumerated off the main thread (see main_window._scan_devices_async).
        set_devices() replaces this when the worker signals back."""
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        self.device_combo.addItem(SCANNING_DEVICES, None)
        self.device_combo.setCurrentIndex(0)
        self.device_combo.blockSignals(False)

    def _on_instrument_text_changed(self, text: str) -> None:
        """Only previews when the typed/selected text resolves to a real GM
        instrument name - an unresolved partial search (still being typed)
        is not previewed, the same "ignore an unresolved edit" reasoning
        InstrumentDialog._commit_current_row already has."""
        program = GM_PROGRAM_BY_NAME.get(text)
        if program is not None:
            self._gm_program = program
            self.instrument_changed.emit(program)

    def result_settings(self) -> LiveMidiInputSettings:
        """Read after exec() returns Accepted."""
        device_name = self.device_combo.currentData()
        program = GM_PROGRAM_BY_NAME.get(self.instrument_combo.currentText(), self._gm_program)
        return LiveMidiInputSettings(
            enabled=self.enabled_checkbox.isChecked(),
            device_name=device_name,
            gm_program=program,
            volume_percent=self.volume_spin.value(),
            pan_percent=self.pan_spin.value(),
        )

    def showEvent(self, event):
        super().showEvent(event)
        # enabled_checkbox, not device_combo - it's the FIRST widget in tab
        # order (the first one added to the layout). Reported bug, live-
        # tested by the user (blind, screen-reader-only): starting focus on
        # device_combo instead meant forward-Tabbing from the open dialog
        # went straight past every control to OK without ever passing
        # through the checkbox, since it sits BEFORE device_combo in the
        # chain - there was no way to discover it without already knowing
        # to Shift+Tab backward first. Starting on the first widget is what
        # every other dialog in this app already does (MixerDialog/
        # InstrumentDialog focus their own first widget, row_list) - this
        # one just named the wrong widget.
        QTimer.singleShot(0, self.enabled_checkbox.setFocus)
