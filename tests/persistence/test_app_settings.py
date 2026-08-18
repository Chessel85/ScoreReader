# tests/persistence/test_app_settings.py
"""settings_path() is redirected into a per-test tmp_path by conftest's
autouse _isolate_persistence fixture, so these never touch the real
developer machine's %LOCALAPPDATA%."""
from models.preview_settings import PreviewSettings
from persistence import app_settings
from persistence.app_settings import AppSettings


def test_load_with_no_saved_file_returns_defaults():
    settings = app_settings.load()
    assert settings.uk_terms is None
    assert settings.recent_files == []


def test_add_recent_file_puts_newest_first():
    app_settings.add_recent_file("a.xml")
    app_settings.add_recent_file("b.xml")
    assert app_settings.load().recent_files == ["b.xml", "a.xml"]


def test_add_recent_file_moves_an_existing_entry_to_the_front_without_duplicating():
    app_settings.add_recent_file("a.xml")
    app_settings.add_recent_file("b.xml")
    app_settings.add_recent_file("a.xml")
    assert app_settings.load().recent_files == ["a.xml", "b.xml"]


def test_add_recent_file_caps_at_max_recent_files():
    for i in range(app_settings.MAX_RECENT_FILES + 3):
        app_settings.add_recent_file(f"{i}.xml")
    recents = app_settings.load().recent_files
    assert len(recents) == app_settings.MAX_RECENT_FILES
    # Most recently added first, oldest ones fallen off the end.
    assert recents[0] == f"{app_settings.MAX_RECENT_FILES + 2}.xml"


def test_add_recent_file_preserves_uk_terms():
    app_settings.save(AppSettings(uk_terms=True))
    app_settings.add_recent_file("a.xml")
    settings = app_settings.load()
    assert settings.uk_terms is True
    assert settings.recent_files == ["a.xml"]


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


# --- Preview settings (global, not per score) ----------------------------

def test_preview_settings_default_when_nothing_has_been_saved():
    assert app_settings.load().preview == PreviewSettings()


def test_set_preview_settings_round_trips():
    app_settings.set_preview_settings(
        PreviewSettings(lead_in_bars=2, lead_in_click=False, preview_bars=4, loop=True)
    )

    saved = app_settings.load().preview
    assert saved.lead_in_bars == 2
    assert saved.lead_in_click is False
    assert saved.preview_bars == 4
    assert saved.loop is True


def test_set_preview_settings_leaves_the_other_preferences_alone():
    """Load-mutate-save, for the same reason add_recent_file has to be: a
    fresh AppSettings literal here would wipe the dialect and the recent
    files list."""
    app_settings.save(AppSettings(uk_terms=True, recent_files=["a.xml"]))

    app_settings.set_preview_settings(PreviewSettings(loop=True))

    settings = app_settings.load()
    assert settings.uk_terms is True
    assert settings.recent_files == ["a.xml"]
    assert settings.preview.loop is True


def test_saving_other_preferences_leaves_preview_settings_alone():
    app_settings.set_preview_settings(PreviewSettings(preview_bars=8))

    app_settings.add_recent_file("b.xml")

    assert app_settings.load().preview.preview_bars == 8
