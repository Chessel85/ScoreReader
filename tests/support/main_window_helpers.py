# tests/support/main_window_helpers.py
"""Shared helpers for the split-up MainWindow test modules.

These used to be module-level functions in the single tests/test_main_window.py
(4,457 lines). That file was split by feature area (S10 of code_review_26th.md);
the handful of helpers every split module needs live here so there is one copy.
"""
from PySide6.QtWidgets import QApplication, QDialog

from models.play_settings import PlaySettings


def no_lead_in(window, **overrides):
    """Play settings with no count-in and no looping.

    The shipped default is a one-bar lead-in (models/play_settings.py),
    which is right for practice but means Space no longer sounds anything
    until the count-in finishes. Tests asserting what playback PLAYS opt
    out of it; the lead-in has its own tests.
    """
    overrides.setdefault("lead_in_enabled", False)
    overrides.setdefault("loop_enabled", False)
    settings = PlaySettings(lead_in_bars=0, lead_in_beats=0, **overrides)
    window.playback.set_play_settings(settings)
    return settings


def load_and_wait(window, qtbot, file_path: str):
    """load_score_from_file (R1) runs on a background QThread - block until
    it signals completion so assertions run against the loaded state.

    _on_score_loaded (sets _music_data) is queued to the main thread before
    the thread's finished signal (emitted after run() returns), so waiting
    for _load_thread to clear back to None is sufficient.
    """
    window.load_score_from_file(file_path)
    qtbot.waitUntil(lambda: window._load_thread is None, timeout=5000)


def _show(window, qtbot):
    """F6 pane cycling (C7) moves real Qt keyboard focus between widgets,
    which needs a shown, exposed window to behave correctly - unlike every
    other test in this file, which only exercises keyPressEvent handlers
    directly and never needed real focus tracking (see the docstring on
    test_four_distinct_regions_are_tab_focusable)."""
    window.show()
    qtbot.waitExposed(window)


def _focus(widget):
    """setFocus() alone only schedules a focusChanged signal - process
    events so MainWindow._on_focus_changed (which _last_focused_region
    tracking relies on) has actually run before the next assertion."""
    widget.setFocus()
    QApplication.processEvents()


# --- Ultimate Guitar import fakes -------------------------------------------
# Shared by test_main_window_ug_import.py plus the Recent Files and Reorder
# Parts tests (both need a loaded UG score), which live in other split modules.

def _fake_ug_import_dialog(monkeypatch, window, *, url: str, accept: bool = True):
    """Same convention as _fake_key_signature_dialog/_fake_instrument_dialog
    (CLAUDE.md: dialog construction stays in MainWindow, so tests
    monkeypatch main_window.<DialogClass>)."""
    from widgets.ultimate_guitar_import_dialog import UltimateGuitarImportDialog

    dialog = UltimateGuitarImportDialog(window)
    dialog.url_edit.setText(url)

    def fake_exec():
        return QDialog.DialogCode.Accepted if accept else QDialog.DialogCode.Rejected

    monkeypatch.setattr(dialog, "exec", fake_exec)
    monkeypatch.setattr("main_window.UltimateGuitarImportDialog", lambda parent: dialog)
    return dialog


def _fake_ug_source(content: str, strum_codes=None, *, capo=None):
    from parsers.ug_source import UgSource
    from models.strum_pattern import StrumPattern

    patterns = []
    if strum_codes:
        patterns.append(
            StrumPattern(
                name="", bpm=115, denominator=16, is_triplet=True, codes=list(strum_codes)
            )
        )
    return UgSource(
        song_name="Test Song",
        artist_name="Test Artist",
        tonality="C",
        tuning="E A D G B E",
        difficulty="novice",
        content=content,
        tab_id=1,
        source_url="https://tabs.ultimate-guitar.com/tab/test/test-chords-1",
        strum_patterns=patterns,
        capo=capo,
    )


def _load_ug_import(window, qtbot, monkeypatch, content: str, strum_codes=None, *, capo=None):
    monkeypatch.setattr(
        "parsers.ug_reader.read_ug_source",
        lambda url: _fake_ug_source(content, strum_codes, capo=capo),
    )
    _fake_ug_import_dialog(
        monkeypatch, window, url="https://tabs.ultimate-guitar.com/tab/test/test-chords-1"
    )
    window.open_ultimate_guitar_import_dialog()
    qtbot.waitUntil(lambda: window._load_thread is None, timeout=5000)
