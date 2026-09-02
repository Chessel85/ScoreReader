# widgets/ultimate_guitar_import_dialog.py
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from parsers.ug_source import validate_url_shape


class UltimateGuitarImportDialog(QDialog):
    """File > Import from Ultimate Guitar... - paste a UG tab-page URL and
    import its chords, lyrics and tablature. Modeled on
    widgets/key_signature_dialog.py's shape (single control, QFormLayout,
    one result-accessor, showEvent focus grab) but with a QLineEdit instead
    of a combo box, since a URL is free-text, not a pick from a fixed list.

    Only does the cheap, synchronous URL-shape check on Accept (right host,
    starts with /tab/) - shown inline rather than closing the dialog. The
    real check (does the page actually have Chords/Tab data) can only happen
    after a network fetch, so it happens later, off the UI thread, and
    surfaces through the existing load_failed path if it fails - this
    dialog itself never touches the network.

    Pure view like every other dialog here: main_window.py's
    _show_ultimate_guitar_import_dialog reads self.url() after exec() and
    starts the import through ScoreSession.import_from_url - this class
    never touches MusicData or the network."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import from Ultimate Guitar")

        self.url_edit = QLineEdit(self)
        self.url_edit.setMinimumWidth(400)
        self.url_edit.setPlaceholderText("https://tabs.ultimate-guitar.com/tab/...")

        self.error_label = QLabel(self)
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)

        form = QFormLayout()
        form.addRow("&Ultimate Guitar URL:", self.url_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addWidget(buttons)

    def _on_accept(self):
        url = self.url_edit.text().strip()
        try:
            validate_url_shape(url)
        except ValueError as e:
            self.error_label.setText(str(e))
            self.error_label.setVisible(True)
            return
        self.accept()

    def url(self) -> str:
        """The pasted URL, only meaningful after exec() returns Accepted -
        already passed the cheap synchronous shape check by that point."""
        return self.url_edit.text().strip()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.url_edit.setFocus)
