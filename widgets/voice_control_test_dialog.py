# widgets/voice_control_test_dialog.py
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QDialog,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)

from audio.voice_recognition import UNKNOWN_TOKEN, VoiceRecognitionManager


class VoiceControlTestDialog(QDialog):
    """Options > Voice Control Settings... > Test... (Ref 19) - lets the
    user practice speaking commands and check their microphone/threshold
    setup without triggering any real navigation or playback.

    Owns its OWN VoiceRecognitionManager instance, entirely separate from
    VoiceControlController's real one - main_window.py's
    _show_voice_control_test_dialog pauses the real listening session for
    the duration this dialog is open (two worker processes competing for
    the same microphone is untested and best avoided). This dialog's
    recognition results are NEVER dispatched into
    NavigationController/PlaybackController - set_diagnostic_callback (not
    set_callback) is used specifically because it reports every attempt,
    accepted or not, which is what a practice/calibration dialog needs to
    show.

    Threading: mirrors VoiceControlController's own private-signal +
    QueuedConnection pattern - the manager's callback fires on its own
    background thread, and _raw_diagnostic/_handle_diagnostic marshal it
    onto the Qt main thread before touching any widget.
    """

    _raw_diagnostic = Signal(str, float, bool)

    def __init__(
        self,
        parent=None,
        device_name: str = "",
        confidence_threshold: float = 70.0,
        voice_manager: Optional[VoiceRecognitionManager] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Voice Control Test")
        self._device_name: Optional[str] = device_name or None
        self._confidence_threshold = confidence_threshold
        self._manager = voice_manager if voice_manager is not None else VoiceRecognitionManager()
        self._manager.set_diagnostic_callback(self._on_raw_diagnostic)
        self._raw_diagnostic.connect(self._handle_diagnostic, Qt.ConnectionType.QueuedConnection)
        self._running = False

        self.hint_label = QLabel(
            "Try saying, for example, \"stop\" or \"next bar\". "
            "The full list of commands is in the User Guide. "
            f"Confidence threshold for this test: {confidence_threshold:.0f}%.",
            self,
        )
        self.hint_label.setWordWrap(True)

        self.status_label = QLabel(
            "Press Start Test, then speak one of the voice commands.", self
        )

        self.start_button = QPushButton("&Start Test", self)
        self.start_button.clicked.connect(self._toggle_listening)

        self.results_list = QListWidget(self)
        self.results_list.setAccessibleName("Recognition results")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.hint_label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.start_button)
        layout.addWidget(self.results_list)
        layout.addWidget(buttons)

    def _toggle_listening(self) -> None:
        if self._running:
            self._stop_test_session()
            return
        started = self._manager.start(self._device_name, self._confidence_threshold)
        self._running = started
        if started:
            self.status_label.setText("Listening - speak a voice command.")
            self.start_button.setText("St&op Test")
        else:
            self.status_label.setText(
                "Could not start voice recognition. See the console for details."
            )

    def _stop_test_session(self) -> None:
        """The one teardown path - called from Stop, and from reject/
        closeEvent, so the background recognizer thread never outlives this
        dialog regardless of how it closes."""
        if self._running:
            self._manager.stop()
            self._running = False
        self.status_label.setText("Press Start Test, then speak one of the voice commands.")
        self.start_button.setText("&Start Test")

    def _on_raw_diagnostic(self, heard_text: str, confidence: float, accepted: bool) -> None:
        """VoiceRecognitionManager's own background thread. Does nothing but
        emit - see class docstring."""
        self._raw_diagnostic.emit(heard_text, confidence, accepted)

    def _handle_diagnostic(self, heard_text: str, confidence: float, accepted: bool) -> None:
        """Qt main thread only. Never dispatches into any controller - this
        dialog is feedback-only (see class docstring).

        Silence is dropped rather than listed - audio/voice_recognition.py
        reports it as heard_text="(silence)" (see its own _handle_final_
        result), and listing one row per silent gap made the results list
        hard to navigate for no useful information (reported).

        Vosk's own catch-all UNKNOWN_TOKEN ("[unk]") means "something was
        said that isn't in the vocabulary" - shown with a plain-language
        message instead of the raw "[unk]" token, which read as unclear
        jargon in testing (reported)."""
        if heard_text == "(silence)":
            return
        if heard_text == UNKNOWN_TOKEN:
            self.results_list.addItem("Word not in dictionary - rejected")
            self.results_list.scrollToBottom()
            return
        verdict = "accepted" if accepted else "rejected"
        self.results_list.addItem(f"Heard: '{heard_text}' - confidence {confidence:.0f}% ({verdict})")
        self.results_list.scrollToBottom()

    def reject(self):
        self._stop_test_session()
        super().reject()

    def closeEvent(self, event):
        self._stop_test_session()
        super().closeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.start_button.setFocus)
