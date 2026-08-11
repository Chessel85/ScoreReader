# persistence/score_config.py
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from PySide6.QtCore import QStandardPaths

VoiceKey = Tuple[str, int, int]


@dataclass
class ScoreConfig:
    """Per-file config (Ref 27): which part/staff/voice combinations are
    switched off, which optional attributes are shown against notes in each
    voice, the order those attributes render in, and whether the metronome
    was on - everything MainWindow needs to restore a score to how the user
    last left it. Deliberately excludes language (persistence/app_settings.py
    - a global preference, not a per-file one).

    voices_off (not an on-list) and voice_display_attributes/attribute_order
    filtered against the freshly-loaded score's own known voices/attribute
    keys are what make loading best-effort: a saved entry that no longer
    corresponds to anything in the current score is simply dropped rather
    than rejecting the whole config (see MusicData.apply_config)."""

    schema_version: int = 1
    voices_off: Set[VoiceKey] = field(default_factory=set)
    metronome_enabled: bool = False
    voice_display_attributes: Dict[VoiceKey, Set[str]] = field(default_factory=dict)
    attribute_order: List[str] = field(default_factory=list)


def _encode_voice_key(key: VoiceKey) -> str:
    part_id, staff, voice = key
    return f"{part_id}|{staff}|{voice}"


def _decode_voice_key(encoded: str) -> VoiceKey:
    part_id, staff, voice = encoded.split("|")
    return (part_id, int(staff), int(voice))


def config_dir() -> Path:
    app_data_dir = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppLocalDataLocation
    )
    return Path(app_data_dir) / "scores"


def path_for(file_path: str) -> Path:
    """Keyed purely by the music file's own basename+extension, never by
    its location - the user is free to move the file around and the same
    config is found again by name alone (a deliberate choice; two
    different files sharing a name will collide, and that's accepted as a
    consequence of best-effort loading rather than solved here)."""
    return config_dir() / f"{os.path.basename(file_path)}.rsc"


def load_for(file_path: str) -> Optional[ScoreConfig]:
    path = path_for(file_path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return ScoreConfig(
            schema_version=data.get("schema_version", 1),
            voices_off={_decode_voice_key(k) for k in data.get("voices_off", [])},
            metronome_enabled=data.get("metronome_enabled", False),
            voice_display_attributes={
                _decode_voice_key(k): set(v)
                for k, v in data.get("voice_display_attributes", {}).items()
            },
            attribute_order=list(data.get("attribute_order", [])),
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
        "voices_off": [_encode_voice_key(k) for k in sorted(config.voices_off)],
        "metronome_enabled": config.metronome_enabled,
        "voice_display_attributes": {
            _encode_voice_key(k): sorted(v)
            for k, v in config.voice_display_attributes.items()
        },
        "attribute_order": list(config.attribute_order),
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
