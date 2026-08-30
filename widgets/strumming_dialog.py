# widgets/strumming_dialog.py
from typing import List

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from models.music_data import MusicData
from models.strum_pattern import StrumPattern
from widgets.list_focus_helper import focus_list_and_reannounce_current_row


class StrummingDialog(QDialog):
    """Tools > Strumming Patterns... - a read-only view of a UG import's
    decoded strumming pattern(s). The strum audio is unusable for working
    out a pattern by ear (the user's own report), so the pattern is made
    legible here instead: a flat list, one row per slot, each row stating
    both the time position and the stroke ("Bar 1, 1: down", "Bar 1, 1 e:
    pause"). A flat QListWidget, not a two-row table - the app's no-tables
    accessibility rule.

    The looped demo plays at the score's current playback tempo (not the
    pattern's own imported bpm): the Tempo spin box shows and edits that
    tempo, with the same S / F / D keys the main window uses (slower /
    faster / reset). "Include metronome click" adds a click on each beat
    under the demo.

    Pure view (docs/dialog_widget_patterns.md conventions): it emits
    play_pattern_requested / stop_requested / tempo_changed and MainWindow
    drives the synth and the score's playback tempo. Looping is handled
    here with a QTimer that re-emits play_pattern_requested once per
    pattern length, until Stop is pressed or the dialog closes.
    """

    play_pattern_requested = Signal(int)  # pattern index
    stop_requested = Signal()
    tempo_changed = Signal(int)  # new tempo, BPM (display units)

    def __init__(
        self,
        parent=None,
        patterns: List[StrumPattern] = None,
        current_tempo_bpm: float = 120.0,
        default_tempo_bpm: float = 120.0,
    ):
        super().__init__(parent)
        self.setWindowTitle("Strumming Patterns")
        self._patterns = list(patterns or [])
        self._default_tempo_bpm = int(round(default_tempo_bpm))

        layout = QVBoxLayout(self)

        self.pattern_combo = QComboBox(self)
        for pattern in self._patterns:
            self.pattern_combo.addItem(self._combo_label(pattern))
        combo_label = QLabel("&Pattern:", self)
        combo_label.setBuddy(self.pattern_combo)
        # Hidden, not omitted, when there's only one - keeps the layout and
        # tab order stable and the code path uniform.
        show_combo = len(self._patterns) > 1
        combo_label.setVisible(show_combo)
        self.pattern_combo.setVisible(show_combo)
        layout.addWidget(combo_label)
        layout.addWidget(self.pattern_combo)

        list_label = QLabel("&Slots:", self)
        self.slot_list = QListWidget(self)
        list_label.setBuddy(self.slot_list)
        layout.addWidget(list_label)
        layout.addWidget(self.slot_list)

        tempo_row = QHBoxLayout()
        tempo_label = QLabel("&Tempo (BPM):", self)
        self.tempo_spin = QSpinBox(self)
        self.tempo_spin.setRange(MusicData.MIN_TEMPO_BPM, MusicData.MAX_TEMPO_BPM)
        self.tempo_spin.setKeyboardTracking(False)
        self.tempo_spin.setValue(
            max(MusicData.MIN_TEMPO_BPM,
                min(MusicData.MAX_TEMPO_BPM, int(round(current_tempo_bpm))))
        )
        tempo_label.setBuddy(self.tempo_spin)
        self.tempo_spin.valueChanged.connect(self._on_tempo_spin_changed)
        tempo_row.addWidget(tempo_label)
        tempo_row.addWidget(self.tempo_spin)
        tempo_row.addStretch(1)
        layout.addLayout(tempo_row)

        self.click_checkbox = QCheckBox("Include metronome &click", self)
        layout.addWidget(self.click_checkbox)

        self.play_button = QPushButton("&Play pattern", self)
        self.play_button.setAutoDefault(False)
        self.play_button.clicked.connect(self._toggle_play)
        button_row = QHBoxLayout()
        button_row.addWidget(self.play_button)
        layout.addLayout(button_row)

        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        close_box.rejected.connect(self.reject)
        layout.addWidget(close_box)

        # The main window's own tempo keys, replicated dialog-wide so they
        # work regardless of which control has focus. They drive the spin
        # box, whose valueChanged fans out to tempo_changed.
        for key, handler in (
            (Qt.Key.Key_S, lambda: self._nudge_tempo(-10)),
            (Qt.Key.Key_F, lambda: self._nudge_tempo(10)),
            (Qt.Key.Key_D, lambda: self.tempo_spin.setValue(self._default_tempo_bpm)),
        ):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(handler)

        self._loop_timer = QTimer(self)
        self._loop_timer.timeout.connect(self._fire_loop)
        self._playing = False

        self.pattern_combo.currentIndexChanged.connect(self._populate_slots)
        self._populate_slots()

    @staticmethod
    def _combo_label(pattern: StrumPattern) -> str:
        name = pattern.name or "Unnamed pattern"
        bpm = f"{pattern.bpm} bpm" if pattern.bpm else "tempo unknown"
        return f"{name}: {bpm}, {pattern.subdivision_name()}, {pattern.bar_count()} bars"

    def current_pattern_index(self) -> int:
        return max(0, self.pattern_combo.currentIndex())

    def _current_pattern(self) -> StrumPattern:
        return self._patterns[self.current_pattern_index()]

    def include_click(self) -> bool:
        return self.click_checkbox.isChecked()

    def _nudge_tempo(self, delta: int) -> None:
        self.tempo_spin.setValue(self.tempo_spin.value() + delta)

    def _on_tempo_spin_changed(self, value: int) -> None:
        self.tempo_changed.emit(value)
        # Keep the loop cadence in step with the new tempo without making
        # the user press Stop/Play again.
        if self._playing:
            self._loop_timer.start(self._loop_interval_ms())

    def _populate_slots(self, *_):
        self._stop()
        self.slot_list.clear()
        if not self._patterns:
            return
        self.slot_list.addItems(self._current_pattern().slot_rows())
        if self.slot_list.count():
            self.slot_list.setCurrentRow(0)

    def _toggle_play(self):
        if self._playing:
            self._stop()
        else:
            self._start()

    def _start(self):
        if not self._patterns:
            return
        self._playing = True
        self.play_button.setText("&Stop")
        self._fire_loop()
        self._loop_timer.start(self._loop_interval_ms())

    def _loop_interval_ms(self) -> int:
        """Re-fire once per full pattern, timed at the chosen tempo so the
        loop stays in step with the demo audio (which MainWindow also plays
        at this tempo). UG tempo is always quarter-note BPM, so the spin
        value doubles as the quarter BPM here."""
        pattern = self._current_pattern()
        slot_ms = pattern.slot_ms_at_bpm(self.tempo_spin.value())
        return max(200, int(slot_ms * max(1, len(pattern.codes))))

    def _stop(self):
        if not self._playing:
            return
        self._playing = False
        self._loop_timer.stop()
        self.play_button.setText("&Play pattern")
        self.stop_requested.emit()

    def _fire_loop(self):
        self.play_pattern_requested.emit(self.current_pattern_index())

    def reject(self):
        self._stop()
        super().reject()

    def closeEvent(self, event):
        self._stop()
        super().closeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, lambda: focus_list_and_reannounce_current_row(self.slot_list))
