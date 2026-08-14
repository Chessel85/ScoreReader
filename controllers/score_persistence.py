# controllers/score_persistence.py
import os

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from persistence import score_config


class ScorePersistenceController:
    """Ref 27: the per-score .rsc file - saving the current score's state,
    restoring it on load, and the two Edit-menu escape hatches.

    Users are meant to stay unaware .rsc files exist at all; "Open Local
    Folder" and "Clear Preferences" are a deliberate minimal escape hatch,
    not a settings UI.
    """

    def __init__(self, session, region_2, clear_action=None):
        self.session = session
        # Region 2's model is the only place a part/stave/voice's OWN toggle
        # (independent of its descendants) lives - see save_current.
        self.region_2 = region_2
        self.clear_action = clear_action

    @property
    def music_data(self):
        return self.session.music_data

    def _has_file(self) -> bool:
        return self.music_data is not None and bool(self.music_data.file_path)

    def load_for_current(self):
        """The saved config for the loaded score, or None."""
        if not self._has_file():
            return None
        return score_config.load_for(self.music_data.file_path)

    def save_current(self) -> None:
        """Writes this score's toggles, shown attributes, attribute order and
        metronome state to its .rsc. Called when swapping files and on
        shutdown - the two points the user asked for, not on every toggle.

        export_config()'s own voices_off is a best-effort derivation for
        standalone use; it is overwritten here with Region 2's per-node
        state, which is lossless where the derived version is not. See
        ScoreConfig's docstring."""
        if not self._has_file():
            return
        config = self.music_data.export_config()
        config.parts_off, config.staves_off, config.voices_off = (
            self.region_2.model_manager.get_off_node_keys()
        )
        score_config.save(self.music_data.file_path, config)

    def open_config_folder(self) -> None:
        folder = score_config.config_dir()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def clear_action_text(self) -> str:
        if not self._has_file():
            return "&Clear Preferences"
        return f"&Clear Preferences for {os.path.basename(self.music_data.file_path)}"

    def refresh_clear_action(self) -> None:
        if self.clear_action is None:
            return
        self.clear_action.setText(self.clear_action_text())
        self.clear_action.setEnabled(self._has_file())

    def clear_current(self) -> None:
        if not self._has_file():
            return
        score_config.delete_for(self.music_data.file_path)
