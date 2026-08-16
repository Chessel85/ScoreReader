# workers/score_load_worker.py
import traceback

from PySide6.QtCore import QThread, Signal

from parsers.gp_reader import GpReader
from parsers.midi_reader import MidiReader
from parsers.musicXML_reader import MusicXMLReader


class ScoreLoadThread(QThread):
    """Runs MusicXMLReader.load() off the UI thread.

    A synchronous load blocks on several ElementTree passes plus
    music21.converter.parse (~460ms) - for a screen-reader-first app that is
    silence with no cue, not just a frozen window. loaded/failed are
    Qt-queued back onto whichever thread owns this QThread's parent.
    """

    loaded = Signal(object)
    failed = Signal(str)

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path

    def run(self):
        try:
            if self.file_path.lower().endswith((".mid", ".midi")):
                data = MidiReader(self.file_path).load()
            elif self.file_path.lower().endswith(".gp"):
                data = GpReader(self.file_path).load()
            else:
                data = MusicXMLReader(self.file_path).load()
        except Exception:
            self.failed.emit(traceback.format_exc())
            return
        self.loaded.emit(data)
