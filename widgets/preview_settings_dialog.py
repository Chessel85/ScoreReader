# widgets/preview_settings_dialog.py
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from models.preview_settings import (
    MAX_LEAD_IN_BARS,
    MAX_LEAD_IN_BEATS,
    MAX_PREVIEW_BARS,
    MIN_PREVIEW_BARS,
    PreviewSettings,
)
from models.vocabulary import bar_word


class PreviewSettingsDialog(QDialog):
    """Playback > Preview Settings... - how Preview behaves: the count-in
    before it starts, how many bars it runs for, and whether it repeats.

    Reported from real practice use: Preview sounded the instant Enter was
    pressed, leaving no time to get hands back onto the guitar.

    A pure view, like MixerDialog: it edits a working copy and hands it back
    from preview_settings(); MainWindow decides what to do with it on OK.
    Same accessibility conventions as TempoOffsetDialog - every control has
    a QLabel with setBuddy so a screen reader announces what it is, and
    focus is deferred to showEvent for the same NVDA reason.

    Bar/measure wording goes through vocabulary.bar_word (F4/D-6), never a
    hardcoded literal - dialect is the user's choice everywhere else in the
    app too.
    """

    def __init__(self, parent=None, settings: PreviewSettings = None, uk_terms: bool = True):
        super().__init__(parent)
        self.setWindowTitle("Preview Settings")
        settings = settings.copy() if settings is not None else PreviewSettings()
        bar = bar_word(uk_terms)

        layout = QVBoxLayout(self)

        self.lead_in_bars_spin = QSpinBox(self)
        self.lead_in_bars_spin.setRange(0, MAX_LEAD_IN_BARS)
        self.lead_in_bars_spin.setValue(settings.lead_in_bars)
        self._add_row(layout, f"Lead-in {bar}s before the preview starts:", self.lead_in_bars_spin)

        self.lead_in_beats_spin = QSpinBox(self)
        self.lead_in_beats_spin.setRange(0, MAX_LEAD_IN_BEATS)
        self.lead_in_beats_spin.setValue(settings.lead_in_beats)
        self._add_row(layout, "Extra lead-in beats:", self.lead_in_beats_spin)

        self.lead_in_click_check = QCheckBox("Play the metronome &click during the lead-in", self)
        self.lead_in_click_check.setChecked(settings.lead_in_click)
        layout.addWidget(self.lead_in_click_check)

        self.preview_bars_spin = QSpinBox(self)
        self.preview_bars_spin.setRange(MIN_PREVIEW_BARS, MAX_PREVIEW_BARS)
        self.preview_bars_spin.setValue(settings.preview_bars)
        self._add_row(layout, f"Preview length in {bar}s:", self.preview_bars_spin)

        self.loop_check = QCheckBox("&Repeat the preview until stopped", self)
        self.loop_check.setChecked(settings.loop)
        layout.addWidget(self.loop_check)

        self.loop_lead_in_check = QCheckBox("Play the lead-in &again on every repeat", self)
        self.loop_lead_in_check.setChecked(settings.loop_includes_lead_in)
        layout.addWidget(self.loop_lead_in_check)

        # Meaningless with looping off, so it follows the loop checkbox
        # rather than silently doing nothing.
        self.loop_check.toggled.connect(self.loop_lead_in_check.setEnabled)
        self.loop_lead_in_check.setEnabled(self.loop_check.isChecked())

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

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.lead_in_bars_spin.setFocus)

    def preview_settings(self) -> PreviewSettings:
        """The edited settings. Clamping is PreviewSettings' own job, so a
        value typed straight into a spin box is bounded the same way a
        hand-edited settings file is."""
        return PreviewSettings(
            lead_in_bars=self.lead_in_bars_spin.value(),
            lead_in_beats=self.lead_in_beats_spin.value(),
            lead_in_click=self.lead_in_click_check.isChecked(),
            preview_bars=self.preview_bars_spin.value(),
            loop=self.loop_check.isChecked(),
            loop_includes_lead_in=self.loop_lead_in_check.isChecked(),
        )
