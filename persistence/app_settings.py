# persistence/app_settings.py
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QStandardPaths

# File > Recent Files - most-recent-first, capped at this many entries.
MAX_RECENT_FILES = 8


@dataclass
class AppSettings:
    """App-wide preferences that are the same regardless of which score is
    loaded - today the UK/US terminology dialect (F4/D-6) and the Recent
    Files list. Deliberately separate from ScoreConfig
    (persistence/score_config.py), which is per-file. uk_terms=None means
    no preference has been saved yet, so the caller should fall back to its
    own default (OS-locale detection)."""

    uk_terms: Optional[bool] = None
    recent_files: List[str] = field(default_factory=list)


def settings_path() -> Path:
    app_data_dir = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppLocalDataLocation
    )
    return Path(app_data_dir) / "settings.json"


def load() -> AppSettings:
    path = settings_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return AppSettings(
            uk_terms=data.get("uk_terms"),
            recent_files=data.get("recent_files", []),
        )
    except FileNotFoundError:
        return AppSettings()
    except (OSError, json.JSONDecodeError) as e:
        print(f"[ERROR] Failed to load app settings from {path}: {e}")
        return AppSettings()


def save(settings: AppSettings) -> None:
    path = settings_path()
    try:
        os.makedirs(path.parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(settings), f, indent=2)
    except OSError as e:
        print(f"[ERROR] Failed to save app settings to {path}: {e}")


def add_recent_file(file_path: str) -> None:
    """Records file_path as the most-recently-opened file - most-recent
    first, no duplicates, capped at MAX_RECENT_FILES. Loads and saves the
    whole settings file itself (load-mutate-save) rather than taking an
    AppSettings in, so callers don't need to worry about clobbering
    uk_terms or vice versa - the same reason set_uk_terms in main_window.py
    must load-mutate-save too, not construct a fresh AppSettings."""
    settings = load()
    recents = [p for p in settings.recent_files if p != file_path]
    recents.insert(0, file_path)
    settings.recent_files = recents[:MAX_RECENT_FILES]
    save(settings)
