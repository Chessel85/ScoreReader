# widgets/tuner_dialog.py
from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from widgets import accessible_announcer


class TunerDialog(QDialog):
    """Tools > Tuner - a generic chromatic tuner. Auto-detects whatever note
    is currently sounding (controllers/tuner_controller.py's tracking/
    acquisition search-band state machine) and speaks/displays the nearest
    note and its cents deviation - there is no Instrument/String picker to
    maintain any more (see that controller's module docstring for why this
    redesign removed them). The dialog listens continuously for as long as
    it's open (starts on showEvent, stops in done() - see that method for
    why not closeEvent alone) and speaks throttled cents feedback via
    controllers/tuner_controller.py's QAccessibleAnnouncementEvent path.
    There is no explicit Start/Stop Listening control (matching a physical
    clip-on tuner, which behaves the same way once switched on).

    Reference pitch (A4), signal sensitivity threshold, and input device are
    set-once values, not something touched mid-pluck - they live in the
    nested Settings dialog (widgets/tuner_settings_dialog.py), reached via
    the Settings button below. This dialog itself has no editable state of
    its own left, so its own OK/Cancel became a single Close button.

    Pure view, like every other dialog in this app: never touches
    TunerController/TunerCapture itself, only emits signals -
    main_window.py's _show_tuner_dialog wires those to the controller. The
    ONE exception is announce() below: it performs the actual
    QAccessible.updateAccessibility() call (controllers/tuner_controller.py
    only decides WHEN/WHAT to announce and emits announcement_requested(str)
    - this dialog is the real widget behind the event, since a plain
    QObject controller has no accessibility interface for Qt's platform
    bridge to resolve; see that module's own GOTCHA for the live-tested bug
    this was).

    reading_edit (a read-only QLineEdit, not a QLabel) exists alongside the
    spoken announcement, not instead of it - added after a live-testing
    report: the announcement mechanism turned out to be silently broken
    (see controllers/tuner_controller.py), and there was no way for the
    user to independently confirm what the app was actually detecting
    without it. Being a real edit control in the tab order means NVDA reads
    its content the moment focus lands on it, which doesn't depend on
    whether announcement events are reaching the screen reader at all - a
    genuinely independent check.

    Same focus-on-show reasoning as every other dialog: setFocus() before
    the native window exists never reaches NVDA, so it's deferred to
    showEvent."""

    settings_requested = Signal()
    listening_requested = Signal()  # emitted once, on show
    listening_stopped = Signal()    # emitted once, from done() - see its docstring

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tuner")

        # Read-only and genuinely focusable/tab-reachable (unlike a QLabel,
        # which NVDA won't announce on its own when its text changes while
        # unfocused) - see the class docstring for why this exists alongside
        # the spoken announcement rather than replacing it.
        self.reading_edit = QLineEdit(self)
        self.reading_edit.setReadOnly(True)
        reading_label = QLabel("Current &Reading:", self)
        reading_label.setBuddy(self.reading_edit)
        # Same wording the spoken/pushed "Waiting." announcement uses (see
        # controllers/tuner_controller.py) - initialised through
        # update_pitch_display itself rather than a separate hardcoded
        # string, so the two can't drift apart.
        self.update_pitch_display("no signal - waiting")

        self.settings_button = QPushButton("&Settings…", self)
        self.settings_button.clicked.connect(self.settings_requested)

        # Close is a RejectRole button, so QDialogButtonBox emits `rejected`
        # when it's clicked - routed to accept() anyway, since there is no
        # OK/Cancel distinction left for this dialog to make (see class
        # docstring): closing it always just closes it.
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(reading_label)
        layout.addWidget(self.reading_edit)
        layout.addWidget(self.settings_button)
        layout.addWidget(buttons)

    # --- live status (driven by TunerController.pitch_result_changed) ------

    def update_pitch_display(self, status_text: str) -> None:
        """status_text arrives fully composed by
        controllers/tuner_controller.py's _status_text - this dialog no
        longer holds any state (threshold, target) needed to reconstruct it
        itself. Plain setText(), not setPlainText() or similar - QLineEdit,
        not a multi-line control, matching the single-line status this
        dialog reports."""
        self.reading_edit.setText(status_text)

    def announce(self, message: str) -> None:
        """Posts the announcement with THIS DIALOG (a real widget) as the
        event's target - see the class docstring's opening paragraph for why
        this can't live in the controller. main_window.py's
        _show_tuner_dialog connects TunerController.announcement_requested to
        this method."""
        accessible_announcer.announce(self, message)

    # --- lifecycle -----------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.reading_edit.setFocus)
        # Deferred alongside focus, for the same reason: starting the real
        # audio stream from inside showEvent itself (before the native
        # window is fully up) is avoidable jank a 0ms singleShot sidesteps,
        # matching how focus itself is handled on this exact line.
        QTimer.singleShot(0, self.listening_requested.emit)

    def done(self, result):
        """Overridden rather than closeEvent: closeEvent only fires for a
        window-system close (the title bar X), not for accept()/reject()
        triggered by the Close button or Escape - done() is the one method
        all of those funnel through, so it's the only reliable place to
        guarantee listening_stopped fires exactly once regardless of how
        the dialog closed."""
        self.listening_stopped.emit()
        super().done(result)
