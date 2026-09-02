# widgets/play_settings_dialog.py
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from models.music_data import MusicData
from models.play_settings import (
    LOOP_REPEAT_MODES,
    MAX_LEAD_IN_BARS,
    MAX_LEAD_IN_BEATS,
    MAX_LOOP_LENGTH_BARS,
    MIN_LOOP_LENGTH_BARS,
    PlaySettings,
)

# Combo labels, index-aligned to models.play_settings.LOOP_REPEAT_MODES.
_LOOP_REPEAT_LABELS = (
    "Repeat the first play-through",
    "Repeat the second play-through",
    "Alternate the first and second play-throughs",
)
from models.vocabulary import bar_word


class PlaySettingsDialog(QDialog):
    """Playback > Play Settings... (Ctrl+Shift+V, also Ctrl+T) - the single
    settings dialog for the one play transport: the absolute playback tempo
    for this piece, the lead-in count-in before Space starts, and whether
    Space loops a fixed window.

    Replaces the old Preview Settings / Tempo Offset dialogs. A pure view,
    like MixerDialog: it edits a working copy and hands it back from
    play_settings() / tempo_display_bpm(); MainWindow decides what to do
    with them on OK. Every control has a QLabel with setBuddy so a screen
    reader announces what it is, and focus is deferred to showEvent for the
    same NVDA reason.

    Bar/measure wording goes through vocabulary.bar_word, never a hardcoded
    literal.
    """

    def __init__(
        self,
        parent=None,
        play_settings: PlaySettings = None,
        current_tempo_display_bpm: float = 120.0,
        uk_terms: bool = True,
        score_has_repeats: bool = False,
    ):
        super().__init__(parent)
        self.setWindowTitle("Play Settings")
        settings = play_settings.copy() if play_settings is not None else PlaySettings()
        bar = bar_word(uk_terms)
        # "Repeat handling while looping" only bites when the score actually
        # carries repeat barlines; the combo is disabled otherwise (as it is
        # with looping off).
        self._score_has_repeats = bool(score_has_repeats)

        layout = QVBoxLayout(self)

        self.tempo_spin = QSpinBox(self)
        self.tempo_spin.setRange(MusicData.MIN_TEMPO_BPM, MusicData.MAX_TEMPO_BPM)
        self.tempo_spin.setValue(
            max(
                MusicData.MIN_TEMPO_BPM,
                min(MusicData.MAX_TEMPO_BPM, int(round(current_tempo_display_bpm))),
            )
        )
        self._add_row(layout, "Playback tempo (beats per minute):", self.tempo_spin)

        self.lead_in_check = QCheckBox("Play a &lead-in metronome click", self)
        self.lead_in_check.setChecked(settings.lead_in_enabled)
        layout.addWidget(self.lead_in_check)

        self.lead_in_bars_spin = QSpinBox(self)
        self.lead_in_bars_spin.setRange(0, MAX_LEAD_IN_BARS)
        self.lead_in_bars_spin.setValue(settings.lead_in_bars)
        self._add_row(layout, f"Lead-in {bar}s:", self.lead_in_bars_spin)

        self.lead_in_beats_spin = QSpinBox(self)
        self.lead_in_beats_spin.setRange(0, MAX_LEAD_IN_BEATS)
        self.lead_in_beats_spin.setValue(settings.lead_in_beats)
        self._add_row(layout, "Extra lead-in beats:", self.lead_in_beats_spin)

        self.loop_check = QCheckBox("&Repeat (loop) until stopped", self)
        self.loop_check.setChecked(settings.loop_enabled)
        layout.addWidget(self.loop_check)

        self.loop_length_spin = QSpinBox(self)
        self.loop_length_spin.setRange(MIN_LOOP_LENGTH_BARS, MAX_LOOP_LENGTH_BARS)
        self.loop_length_spin.setValue(settings.loop_length_bars)
        self._add_row(layout, f"Loop length in {bar}s:", self.loop_length_spin)

        self.loop_repeat_combo = QComboBox(self)
        self.loop_repeat_combo.addItems(_LOOP_REPEAT_LABELS)
        try:
            mode_index = LOOP_REPEAT_MODES.index(settings.loop_repeat_mode)
        except ValueError:
            mode_index = 0
        self.loop_repeat_combo.setCurrentIndex(mode_index)
        self._add_row(layout, "Repeat handling while looping:", self.loop_repeat_combo)

        self.loop_lead_in_check = QCheckBox("Play the lead-in a&gain on every repeat", self)
        self.loop_lead_in_check.setChecked(settings.loop_lead_in)
        layout.addWidget(self.loop_lead_in_check)

        self.lead_in_check.toggled.connect(self._update_enabled_states)
        self.loop_check.toggled.connect(self._update_enabled_states)
        self._update_enabled_states()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_row(self, layout: QVBoxLayout, text: str, widget) -> None:
        label = QLabel(text, self)
        label.setBuddy(widget)
        layout.addWidget(label)
        layout.addWidget(widget)

    def _update_enabled_states(self, *_args) -> None:
        lead_in = self.lead_in_check.isChecked()
        looping = self.loop_check.isChecked()
        self.lead_in_bars_spin.setEnabled(lead_in)
        self.lead_in_beats_spin.setEnabled(lead_in)
        self.loop_length_spin.setEnabled(looping)
        self.loop_repeat_combo.setEnabled(looping and self._score_has_repeats)
        # "Play the lead-in again on every repeat" only means something when
        # there is both a loop to repeat and a lead-in to replay.
        self.loop_lead_in_check.setEnabled(looping and lead_in)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.tempo_spin.setFocus)

    def play_settings(self) -> PlaySettings:
        """The edited lead-in/looping settings. Clamping is PlaySettings'
        own job, so a value typed straight into a spin box is bounded the
        same way a hand-edited settings file is."""
        return PlaySettings(
            lead_in_enabled=self.lead_in_check.isChecked(),
            lead_in_bars=self.lead_in_bars_spin.value(),
            lead_in_beats=self.lead_in_beats_spin.value(),
            loop_enabled=self.loop_check.isChecked(),
            loop_length_bars=self.loop_length_spin.value(),
            loop_lead_in=self.loop_lead_in_check.isChecked(),
            loop_repeat_mode=LOOP_REPEAT_MODES[self.loop_repeat_combo.currentIndex()],
        )

    def tempo_display_bpm(self) -> int:
        """The absolute playback tempo, in time-signature-denominator beats
        per minute."""
        return self.tempo_spin.value()
