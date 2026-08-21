# widgets/range_spin_box.py
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSpinBox


class RangeSpinBox(QSpinBox):
    """A QSpinBox where Home jumps to the maximum, End to the minimum, and
    Insert resets to reset_value (e.g. pan's centre, 0%, or the user's
    preferred volume reset point, 50%) - a plain QSpinBox only uses Home/End
    to move the text cursor within the typed digits, giving no
    single-keystroke way to reach an extreme (e.g. full left/full right
    pan) or back to a known reference point.

    Home->maximum/End->minimum (not the other way round) per the user's own
    request: for Pan, Home is +100% (right) and End is -100% (left); for
    Volume, Home is 100% (loudest this dialog allows) and End is 0% (mute) -
    both are "Home = highest number this control has", not "Home = the
    quiet/left end".

    Extracted from widgets/mixer_dialog.py (originally private, _RangeSpinBox)
    so widgets/live_midi_input_dialog.py can share it without reaching into
    another widget module's internals - no MixerDialog-specific coupling."""

    def __init__(self, parent=None, reset_value: int = 0):
        super().__init__(parent)
        self._reset_value = reset_value

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Home:
            self.setValue(self.maximum())
            return
        if event.key() == Qt.Key.Key_End:
            self.setValue(self.minimum())
            return
        if event.key() == Qt.Key.Key_Insert:
            self.setValue(self._reset_value)
            return
        super().keyPressEvent(event)
