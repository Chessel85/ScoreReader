# widgets/status_bar_widget.py
from typing import List

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QLabel, QStatusBar


class _StatusField(QLabel):
    """One focusable, individually screen-reader-announced field within the
    status bar (C6). A plain QLabel is not a tab stop - this adds a focus
    policy, a visible focus indicator, and keeps setAccessibleName in sync
    with the label text so NVDA announces the field's content when it
    receives focus, not a generic "label".

    Tab/Backtab are intercepted via event() rather than keyPressEvent - Qt's
    own focus-chain handling claims the Tab key before a plain QWidget's
    keyPressEvent would ever see it - and handed straight to the owning
    StatusBarWidget as "move to field N" using this field's own known index,
    so cycling works the same way whether or not this field currently holds
    real OS/window focus (C7: only F6/Shift+F6 leave the status bar pane).
    """

    def __init__(self, status_bar: "StatusBarWidget", index: int, parent=None):
        super().__init__(parent)
        self._status_bar = status_bar
        self.index = index
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMargin(4)

    def setText(self, text: str):
        super().setText(text)
        self.setAccessibleName(text)

    def event(self, event):
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Tab:
                self._status_bar.focus_field((self.index + 1) % self._status_bar.FIELD_COUNT)
                return True
            if key == Qt.Key.Key_Backtab:
                self._status_bar.focus_field((self.index - 1) % self._status_bar.FIELD_COUNT)
                return True
        return super().event(event)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.setStyleSheet("border: 1px solid palette(highlight);")

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.setStyleSheet("")


class StatusBarWidget(QStatusBar):
    """C6/C7/E2/E5/E8/Ref 28/29: measure/beat position, key signature, time
    signature, playback tempo, playback status (Playing/Paused/Stopped),
    metronome on/off, position announcer on/off and the current Preview
    length, each its own focusable field. Tab/Shift+Tab cycle only among
    these eight fields and wrap, rather than leaving the pane the way every
    region widget's Tab does - F6/Shift+F6 (C7) have sole ownership of
    leaving the status bar.

    Using the real QStatusBar (via QMainWindow.setStatusBar) is what makes
    NVDA's "report status bar" command (NVDA+End) work through Qt's native
    accessibility role - no extra plumbing needed here for that.
    """

    # Named indices so callers updating one field don't hardcode a number.
    # This order is also the Tab order the user experiences.
    POSITION_FIELD = 0
    KEY_FIELD = 1
    TIME_FIELD = 2
    TEMPO_FIELD = 3
    PLAYBACK_FIELD = 4
    METRONOME_FIELD = 5
    POSITION_ANNOUNCER_FIELD = 6
    PREVIEW_LENGTH_FIELD = 7
    FIELD_COUNT = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fields = [_StatusField(self, i, self) for i in range(self.FIELD_COUNT)]
        for field in self._fields:
            self.addWidget(field)
        self.set_fields([
            "Measure - beat -", "Key: -", "Time: -", "Playback tempo: -",
            "Playback: Stopped", "Metronome: Off", "Position Announcer: Off",
            "Preview length: 2 bars",
        ])

    def set_fields(self, texts: List[str]) -> None:
        for field, text in zip(self._fields, texts):
            field.setText(text)

    def set_field(self, index: int, text: str) -> None:
        """Updates a single field without touching the others - used when
        only playback status changes (E6 phrase audition, pause/resume)."""
        self._fields[index].setText(text)

    def first_field(self) -> _StatusField:
        return self._fields[0]

    def focus_field(self, index: int) -> None:
        self._fields[index].setFocus(Qt.FocusReason.TabFocusReason)
