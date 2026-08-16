# workers/ug_import_worker.py
import traceback

from PySide6.QtCore import QThread, Signal

from parsers.ug_reader import UgReader


class UgImportThread(QThread):
    """Runs UgReader.load() off the UI thread - the URL counterpart of
    ScoreLoadThread. A network fetch plus JSON parse is no faster than a
    local file load's ~460ms music21 pass, and can be much slower (or hang)
    on a bad connection, so this stays off the UI thread for the same
    reason: silence with no cue is worse than a frozen window for a
    screen-reader-first app.

    Same loaded/failed Signal contract as ScoreLoadThread, so
    ScoreSession.import_from_url can share _on_loaded/_on_thread_finished
    and main_window.py's _on_score_loaded/_on_score_load_failed wiring
    needs no changes at all.
    """

    loaded = Signal(object)
    failed = Signal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            data = UgReader(self.url).load()
        except Exception:
            self.failed.emit(traceback.format_exc())
            return
        self.loaded.emit(data)
