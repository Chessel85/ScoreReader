# widgets/key_signature_dialog.py
from typing import Optional, Tuple

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QVBoxLayout

from models.key_signatures import key_override_options


class KeySignatureDialog(QDialog):
    """Edit > Key Signature... (S6) - a single whole-piece key signature
    override, saved per file. MIDI files often lack correct - or any - key
    metadata, which drives MidiTimelineBuilder's sharp/flat enharmonic
    spelling choice; this lets the user state the real key.

    Originally lived as a second control inside widgets/instrument_dialog.py
    (S5's per-part rename/reprogram dialog) - reverted to its own dialog:
    the user found renaming a part and overriding the score's key too
    different a pair of actions to share one dialog, even though both are
    "override what the file declared, save it per file".

    One control, one combo: picking e.g. "G major" sets both the fifths (1)
    and the major/minor display mode together - simpler than two separate
    fifths/mode controls, and it's also what fixes FIFTHS_MAP's ambiguous
    "C major / A minor"-style label the user found weak. Non-editable
    combo, deliberately unlike widgets/instrument_dialog.py's instrument
    picker - with only 31 entries, Qt's native keyboard-search (press a
    letter, jump/cycle - confirmed working well by the user on the
    instrument combo) is sufficient on its own, and a plain combo needs
    none of the free-text-resolution handling the instrument field needs.

    Pure view like every other dialog here: main_window.py's
    _show_key_signature_dialog reads self.key_override() after exec() and
    applies it through MusicData.apply_key_signature_override - this class
    never touches MusicData."""

    def __init__(
        self,
        parent=None,
        current_key: Tuple[Optional[int], Optional[str]] = (None, None),
    ):
        super().__init__(parent)
        self.setWindowTitle("Key Signature")

        self.key_combo = QComboBox(self)
        selected_index = 0
        for i, (label, fifths, mode) in enumerate(key_override_options()):
            self.key_combo.addItem(label, (fifths, mode))
            if (fifths, mode) == current_key:
                selected_index = i
        self.key_combo.setCurrentIndex(selected_index)

        form = QFormLayout()
        form.addRow("&Key signature:", self.key_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def key_override(self) -> Tuple[Optional[int], Optional[str]]:
        """(fifths, mode) for the selected key entry, or (None, None) for
        "use the file's own key" - always a valid preset pair, since the
        combo is non-editable (no partial-text state to resolve)."""
        return self.key_combo.currentData()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.key_combo.setFocus)
