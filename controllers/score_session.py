# controllers/score_session.py
from typing import Optional, Union

from PySide6.QtCore import QObject, Signal

from models.music_data import MusicData
from workers.score_load_worker import ScoreLoadThread
from workers.ug_import_worker import UgImportThread


class ScoreSession(QObject):
    """What is currently loaded: the score, the synth, and the dialect.

    Every controller reads `session.music_data` per call rather than caching
    it, because MusicData is REPLACED wholesale on each load rather than
    mutated. Caching it would leave a controller silently driving the
    previous score - a bug class that would otherwise grow with every
    controller added.

    Owns the load thread too, so "start a load" and "what is loaded" stay in
    one place. Loading is off the UI thread because a synchronous load blocks
    on several ElementTree passes plus music21 (~460ms), which for a
    screen-reader-first app is silence with no cue.
    """

    score_loaded = Signal(object)  # MusicData
    load_failed = Signal(str)

    def __init__(self, synth, uk_terms: bool, parent=None):
        super().__init__(parent)
        self.synth = synth
        self.uk_terms = uk_terms
        self.music_data: Optional[MusicData] = None
        self._load_thread: Optional[Union[ScoreLoadThread, UgImportThread]] = None

    @property
    def load_thread(self) -> Optional[Union[ScoreLoadThread, UgImportThread]]:
        return self._load_thread

    def is_loading(self) -> bool:
        return self._load_thread is not None

    def load(self, file_path: str) -> None:
        """Start loading `file_path`. A no-op while a load is already in
        flight - see Ref 25/NFR-06 (I1) for the accessible error reporting
        this and _on_failed still lack."""
        if self._load_thread is not None:
            return
        self._load_thread = ScoreLoadThread(file_path, self)
        self._load_thread.loaded.connect(self._on_loaded)
        self._load_thread.failed.connect(self.load_failed.emit)
        self._load_thread.finished.connect(self._on_thread_finished)
        self._load_thread.start()

    def import_from_url(self, url: str) -> None:
        """Start importing an Ultimate Guitar tab from `url` - the URL
        counterpart of load() above, same single-slot in-flight guard (a
        file load and a URL import can't run concurrently either) and the
        same loaded/failed signal wiring, so _on_loaded/_on_thread_finished
        are shared unchanged."""
        if self._load_thread is not None:
            return
        self._load_thread = UgImportThread(url, self)
        self._load_thread.loaded.connect(self._on_loaded)
        self._load_thread.failed.connect(self.load_failed.emit)
        self._load_thread.finished.connect(self._on_thread_finished)
        self._load_thread.start()

    def wait_for_load(self) -> None:
        if self._load_thread is not None:
            self._load_thread.wait()

    def set_uk_terms(self, uk_terms: bool) -> None:
        """The dialect is a GLOBAL preference, but MusicData carries its own
        copy for rendering - so it is applied both here and to each score as
        it loads."""
        self.uk_terms = uk_terms
        if self.music_data is not None:
            self.music_data.uk_terms = uk_terms

    def _on_loaded(self, music_data: MusicData) -> None:
        self.music_data = music_data
        # MusicData is wholly replaced on every load, so the global dialect
        # must be reapplied or it silently resets to MusicData's own
        # construction default on every open.
        music_data.uk_terms = self.uk_terms
        self.score_loaded.emit(music_data)

    def _on_thread_finished(self) -> None:
        # deleteLater, not merely dropping the Python reference: the thread
        # is parented to this session, so the C++ object outlives it and one
        # would otherwise accumulate per file opened for the life of the
        # process. Safe from the finished signal (the standard Qt idiom) -
        # run() has already returned by the time it fires, and the parsed
        # score is a local inside it, so nothing large is being held.
        self._load_thread.deleteLater()
        self._load_thread = None
