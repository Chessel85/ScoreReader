# widgets/goto_measure_dialog.py
from typing import Optional

from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout


class GotoMeasureDialog(QDialog):
    """Navigation > Go to Measure... (C8) - a menu-driven alternative to
    typing a bar number directly into the Note region (C4, Ref 6), for
    anyone who prefers a dialog. Reuses the same
    MusicData.jump_to_measure() the typed-digits path uses, just triggered
    from here instead of Enter."""

    def __init__(self, parent=None, current_measure: Optional[int] = None):
        super().__init__(parent)
        self.setWindowTitle("Go to Measure")

        self.measure_edit = QLineEdit(self)
        # Whole measure numbers only - this jumps to a measure, not a
        # measure+beat position, so "4.3" must never be read as "measure 4
        # beat 3". QIntValidator already rejects '.' outright.
        self.measure_edit.setValidator(QIntValidator(0, 9999, self))
        if current_measure is not None:
            self.measure_edit.setText(str(current_measure))
            self.measure_edit.selectAll()

        label = QLabel("Measure number (whole numbers only, no beat position):", self)
        label.setBuddy(self.measure_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(label)
        layout.addWidget(self.measure_edit)
        layout.addWidget(buttons)

        self.measure_edit.setFocus()

    def measure_number(self) -> Optional[int]:
        """The typed value, or None if the field was left empty."""
        text = self.measure_edit.text().strip()
        return int(text) if text else None
