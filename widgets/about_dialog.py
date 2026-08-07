# widgets/about_dialog.py
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from version import __version__


class _FocusableLabel(QLabel):
    """A QLabel that's also a tab stop, so NVDA users can move through the
    About text piece by piece with Tab instead of relying on a single
    wall-of-text label read all at once. Same focus-visible pattern as
    StatusBarWidget's _StatusField."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setWordWrap(True)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.setStyleSheet("border: 1px solid palette(highlight);")

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.setStyleSheet("")


class AboutDialog(QDialog):
    """Help > About Recall Score... (C8). A real QDialog rather than a bare
    QMessageBox.about() call, since there's room planned for links and
    richer formatted text later - QLabel already supports rich text and
    setOpenExternalLinks(True) whenever that's needed, without changing the
    mechanism used to show this dialog.

    The text is split into separate labels (name / version / description)
    rather than one multi-line QLabel so each is its own Tab stop."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About Recall Score")

        name_label = _FocusableLabel("Recall Score", self)
        version_label = _FocusableLabel(f"Version {__version__}", self)
        description_label = _FocusableLabel(
            "A screen-reader-first music score and guitar-tab viewer/editor "
            "for visually impaired musicians.",
            self,
        )

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, self)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(name_label)
        layout.addWidget(version_label)
        layout.addWidget(description_label)
        layout.addWidget(buttons)
