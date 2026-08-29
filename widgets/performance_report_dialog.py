# widgets/performance_report_dialog.py
from typing import List

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QListWidget, QVBoxLayout

from widgets.list_focus_helper import focus_list_and_reannounce_current_row


class PerformanceReportDialog(QDialog):
    """Ref 29: Edit > Performance Report... - a read-only, whole-score
    overview (title/composer/tempo/key/time-sig, instrument note counts,
    anacrusis, bar count, repeat/ending/hairpin summary), built once from
    MusicData.get_performance_report_lines() and just displayed - no
    in-dialog interaction, unlike AttributeOrderDialog's live-signal
    pattern, and deliberately no jump-to-location navigation (explicit
    scope cut for this iteration - Region 5's own Ctrl+Home/Ctrl+End is the
    only jump feature this version has).

    A flat QListWidget (one item per line), not a QTextEdit, for the same
    "NVDA reads a whole row in one keystroke" reasoning Region 2/5 already
    use - a rich/nested tree control is explicitly out of scope for now.
    """

    def __init__(self, parent=None, lines: List[str] = None):
        super().__init__(parent)
        self.setWindowTitle("Performance Report")

        label = QLabel("Performance report:", self)
        self.report_list = QListWidget(self)
        label.setBuddy(self.report_list)
        self.report_list.addItems(lines or [])

        close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        close_buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(label)
        layout.addWidget(self.report_list)
        layout.addWidget(close_buttons)

    def showEvent(self, event):
        """Same deferred-focus idiom as GotoMeasureDialog/AttributeOrderDialog
        - setFocus() before the native window exists never reaches NVDA."""
        super().showEvent(event)
        QTimer.singleShot(0, lambda: focus_list_and_reannounce_current_row(self.report_list))
