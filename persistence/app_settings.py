# persistence/app_settings.py
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QStandardPaths


@dataclass
class AppSettings:
    """App-wide preferences that are the same regardless of which score is
    loaded - today just the UK/US terminology dialect (F4/D-6). Deliberately
    separate from ScoreConfig (persistence/score_config.py), which is
    per-file. uk_terms=None means no preference has been saved yet, so the
    caller should fall back to its own default (OS-locale detection)."""

    uk_terms: Optional[bool] = None


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
        return AppSettings(uk_terms=data.get("uk_terms"))
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
