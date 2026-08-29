# widgets/mixer_dialog.py
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from widgets.list_focus_helper import focus_list_and_reannounce_current_row
from widgets.range_spin_box import RangeSpinBox


class MixerDialog(QDialog):
    """Edit > Mixer... (Ctrl+Shift+X, wishlist #4) - volume/pan per
    instrument plus the click, position announcer and performance-cue
    channels.

    Pure view, like every other dialog in this app: it never touches
    MusicData/PlaybackController/SynthEngine itself, only emits signals -
    MainWindow._show_mixer_dialog wires those to
    controllers/playback_controller.py's set_mixer_volume/set_mixer_pan
    (the live-preview push) and audition_phrase (Alt+W / the Preview
    button), and performs commit_mixer_edit/cancel_mixer_edit itself once
    exec() returns.

    Same focus-on-show reasoning as every other dialog: setFocus() before
    the native window exists never reaches NVDA, so it's deferred to
    showEvent (AttributeOrderDialog/GotoMeasureDialog/TempoOffsetDialog all
    do this)."""

    volume_changed = Signal(str, int)  # key, percent
    pan_changed = Signal(str, int)     # key, percent
    preview_requested = Signal()

    def __init__(self, parent=None, rows: Optional[List[Tuple[str, str, int, int]]] = None):
        super().__init__(parent)
        self.setWindowTitle("Mixer")

        # key -> (volume_percent, pan_percent), so switching the selected
        # row can restore its own values into the spin boxes.
        self._values = {key: (volume, pan) for key, _, volume, pan in (rows or [])}

        self.row_list = QListWidget(self)
        for key, label, _, _ in (rows or []):
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.row_list.addItem(item)
        self.row_list.currentRowChanged.connect(self._on_row_changed)

        # reset_value=50, not 100: the user's own preference - Insert is a
        # quick "put it somewhere reasonable" key while editing, not a claim
        # that 50% is the engine's true default (begin_mixer_edit's initial
        # per-row display value is still the real default, 100%, for a row
        # with no override).
        self.volume_spin = RangeSpinBox(self, reset_value=50)
        self.volume_spin.setRange(0, 100)
        self.volume_spin.setSuffix("%")
        # False: valueChanged fires on Enter/focus-out/arrow-step/wheel-step,
        # not on every partial keystroke while typing - so a live preview
        # reflects a deliberately-finished value ("100"), not "1" of "100"
        # mid-type.
        self.volume_spin.setKeyboardTracking(False)
        self.volume_spin.valueChanged.connect(self._on_volume_changed)

        self.pan_spin = RangeSpinBox(self, reset_value=0)
        self.pan_spin.setRange(-100, 100)
        self.pan_spin.setSuffix("%")
        self.pan_spin.setKeyboardTracking(False)
        self.pan_spin.valueChanged.connect(self._on_pan_changed)

        form = QFormLayout()
        form.addRow("&Volume:", self.volume_spin)
        form.addRow("&Pan:", self.pan_spin)

        # "Preview Alt+&W" - the visible label spells the shortcut out
        # directly (user-requested), and the & on the W still gives a
        # working Alt+W mnemonic, since it's a real letter in that text.
        # An earlier version used "&Preview" (Alt+P), which collided with
        # the Pan field's own "&Pan:" mnemonic (also Alt+P) - reported bug,
        # live-tested: Alt+P didn't reliably reach the Preview button.
        #
        # Deliberately NO tooltip/setToolTip text here - reported bug,
        # live-tested: a tooltip explaining what the button does ("Play the
        # current bar and the next bar") got read out by NVDA right after
        # the button's own name, on top of the label already spelling out
        # what it is. The label alone is the whole accessible name.
        self.preview_button = QPushButton("Preview Alt+&W", self)
        self.preview_button.clicked.connect(self.preview_requested)

        button_row = QHBoxLayout()
        button_row.addWidget(self.preview_button)
        button_row.addStretch()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        controls = QWidget(self)
        controls_layout = QVBoxLayout(controls)
        controls_layout.addLayout(form)
        controls_layout.addLayout(button_row)

        top_row = QHBoxLayout()
        top_row.addWidget(self.row_list)
        top_row.addWidget(controls)

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addWidget(buttons)

        if self.row_list.count() > 0:
            self.row_list.setCurrentRow(0)
        else:
            self.volume_spin.setEnabled(False)
            self.pan_spin.setEnabled(False)
            self.preview_button.setEnabled(False)

    def _current_key(self) -> Optional[str]:
        item = self.row_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _on_row_changed(self, row: int) -> None:
        key = self._current_key()
        if key is None:
            return
        volume, pan = self._values.get(key, (100, 0))
        # Reflecting the newly-selected row's own values must not itself
        # emit volume_changed/pan_changed - that would misreport "the user
        # changed this row's value" for a row they only just arrived at.
        self.volume_spin.blockSignals(True)
        self.volume_spin.setValue(volume)
        self.volume_spin.blockSignals(False)
        self.pan_spin.blockSignals(True)
        self.pan_spin.setValue(pan)
        self.pan_spin.blockSignals(False)

    def _on_volume_changed(self, value: int) -> None:
        key = self._current_key()
        if key is None:
            return
        _, pan = self._values.get(key, (100, 0))
        self._values[key] = (value, pan)
        self.volume_changed.emit(key, value)

    def _on_pan_changed(self, value: int) -> None:
        key = self._current_key()
        if key is None:
            return
        volume, _ = self._values.get(key, (100, 0))
        self._values[key] = (volume, value)
        self.pan_changed.emit(key, value)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, lambda: focus_list_and_reannounce_current_row(self.row_list))
