# persistence/score_config.py
"""Reading and writing a ScoreConfig (Ref 27) to its per-score .rsc file.

The ScoreConfig shape itself lives in models/score_config_data.py: this
module imports Qt for QStandardPaths, and MusicData imports ScoreConfig, so
keeping the dataclass here dragged Qt into every models/ import. It is
re-exported below so either import path works. The JSON key codecs stay
here - how a tuple key is spelled in a file is serialisation, not shape.
"""
import json
import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QStandardPaths

from models.mixer_settings import MixerSettings
from models.score_config_data import ScoreConfig, StaffKey, VoiceKey

__all__ = [
    "ScoreConfig", "StaffKey", "VoiceKey",
    "config_dir", "path_for", "load_for", "save", "delete_for",
]


def _encode_voice_key(key: VoiceKey) -> str:
    part_id, staff, voice = key
    return f"{part_id}|{staff}|{voice}"


def _decode_voice_key(encoded: str) -> VoiceKey:
    part_id, staff, voice = encoded.split("|")
    return (part_id, int(staff), int(voice))


def _encode_staff_key(key: StaffKey) -> str:
    part_id, staff = key
    return f"{part_id}|{staff}"


def _decode_staff_key(encoded: str) -> StaffKey:
    part_id, staff = encoded.split("|")
    return (part_id, int(staff))


def config_dir() -> Path:
    app_data_dir = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppLocalDataLocation
    )
    return Path(app_data_dir) / "scores"


def path_for(file_path: str) -> Path:
    """Keyed by the music file's basename+extension only, never its folder,
    so moving the file keeps its config. Two different files sharing a name
    will collide - accepted, given loading is best-effort anyway."""
    return config_dir() / f"{os.path.basename(file_path)}.rsc"


def load_for(file_path: str) -> Optional[ScoreConfig]:
    path = path_for(file_path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return ScoreConfig(
            schema_version=data.get("schema_version", 1),
            parts_off=set(data.get("parts_off", [])),
            staves_off={_decode_staff_key(k) for k in data.get("staves_off", [])},
            voices_off={_decode_voice_key(k) for k in data.get("voices_off", [])},
            metronome_enabled=data.get("metronome_enabled", False),
            position_announcer_enabled=data.get("position_announcer_enabled", False),
            voice_display_attributes={
                _decode_voice_key(k): set(v)
                for k, v in data.get("voice_display_attributes", {}).items()
            },
            attribute_order=list(data.get("attribute_order", [])),
            mixer=MixerSettings.from_dict(data.get("mixer")),
        )
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError, ValueError) as e:
        print(f"[ERROR] Failed to load score config from {path}: {e}")
        return None


def save(file_path: str, config: ScoreConfig) -> None:
    path = path_for(file_path)
    data = {
        "schema_version": config.schema_version,
        "parts_off": sorted(config.parts_off),
        "staves_off": [_encode_staff_key(k) for k in sorted(config.staves_off)],
        "voices_off": [_encode_voice_key(k) for k in sorted(config.voices_off)],
        "metronome_enabled": config.metronome_enabled,
        "position_announcer_enabled": config.position_announcer_enabled,
        "voice_display_attributes": {
            _encode_voice_key(k): sorted(v)
            for k, v in config.voice_display_attributes.items()
        },
        "attribute_order": list(config.attribute_order),
        "mixer": config.mixer.to_dict(),
    }
    try:
        os.makedirs(path.parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError as e:
        print(f"[ERROR] Failed to save score config to {path}: {e}")


def delete_for(file_path: str) -> None:
    path = path_for(file_path)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError as e:
        print(f"[ERROR] Failed to delete score config at {path}: {e}")
