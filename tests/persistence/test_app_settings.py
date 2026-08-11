# tests/persistence/test_app_settings.py
"""settings_path() is redirected into a per-test tmp_path by conftest's
autouse _isolate_persistence fixture, so these never touch the real
developer machine's %LOCALAPPDATA%."""
from persistence import app_settings
from persistence.app_settings import AppSettings


def test_load_with_no_saved_file_returns_defaults():
    settings = app_settings.load()
    assert settings.uk_terms is None


def test_save_then_load_round_trips():
    app_settings.save(AppSettings(uk_terms=True))
    assert app_settings.load().uk_terms is True

    app_settings.save(AppSettings(uk_terms=False))
    assert app_settings.load().uk_terms is False


def test_load_with_corrupt_file_falls_back_to_defaults():
    path = app_settings.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not valid json{{{", encoding="utf-8")

    settings = app_settings.load()
    assert settings.uk_terms is None
