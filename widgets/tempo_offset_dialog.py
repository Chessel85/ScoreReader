# widgets/tempo_offset_dialog.py
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout


class TempoOffsetDialog(QDialog):
    """Options > Tempo Offset... (E3, Ref 12 AC5) - a TEMPO OFFSET dialog,
    not an absolute-tempo one: the score's own tempo (A9) is always the
    default, and this sets how far playback should run from it, the same
    delta the F/S/D keys (E2) already adjust in 10bpm steps. Accepts decimal
    values; an offset that would push playback outside the hard 30-300bpm
    boundary is CLAMPED by MusicData.set_playback_tempo_offset() on accept,
    not rejected here - matches Ref 12 AC2's "boundaries are enforced"
    rather than a validation error.

    Same shape as GotoMeasureDialog (C8): label + validated QLineEdit +
    OK/Cancel, focus deferred to showEvent for the same NVDA reason."""

    def __init__(self, parent=None, current_offset: float = 0.0, beat_unit_name: str = "quarter"):
        super().__init__(parent)
        self.setWindowTitle("Tempo Offset")

        self.offset_edit = QLineEdit(self)
        validator = QDoubleValidator(-1000.0, 1000.0, 2, self)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.offset_edit.setValidator(validator)
        self.offset_edit.setText(self._format(current_offset))
        self.offset_edit.selectAll()

        # beat_unit_name (e.g. "eighth" for a score marked eighth=96) names
        # the SAME units MusicData.playback_tempo_offset is stored in and
        # the status bar displays (E1 fix) - spelling it out here directly
        # answers the reported confusion where an offset entered/read here
        # didn't match what F/S/D and the status bar showed.
        label = QLabel(
            f"Tempo offset in {beat_unit_name} notes per minute, from the score's own tempo:", self
        )
        label.setBuddy(self.offset_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(label)
        layout.addWidget(self.offset_edit)
        layout.addWidget(buttons)

    @staticmethod
    def _format(value: float) -> str:
        return str(int(value)) if float(value).is_integer() else str(value)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.offset_edit.setFocus)

    def tempo_offset(self) -> Optional[float]:
        """The typed value, or None if the field was left empty."""
        text = self.offset_edit.text().strip()
        return float(text) if text else None
