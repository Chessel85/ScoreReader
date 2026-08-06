# widgets/about_dialog.py
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from version import __version__


class AboutDialog(QDialog):
    """Help > About Recall Score... (C8). A real QDialog rather than a bare
    QMessageBox.about() call, since there's room planned for links and
    richer formatted text later - QLabel already supports rich text and
    setOpenExternalLinks(True) whenever that's needed, without changing the
    mechanism used to show this dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About Recall Score")

        text = QLabel(
            f"Recall Score\n"
            f"Version {__version__}\n\n"
            "A screen-reader-first music score and guitar-tab viewer/editor "
            "for visually impaired musicians.",
            self,
        )
        text.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, self)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(text)
        layout.addWidget(buttons)
