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
from models.score_config_data import PercussionItemKey, ScoreConfig, StaffKey, VoiceKey

__all__ = [
    "ScoreConfig", "StaffKey", "VoiceKey", "PercussionItemKey",
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


def _encode_percussion_item_key(key: PercussionItemKey) -> str:
    part_id, source_key = key
    return f"{part_id}|{source_key}"


def _decode_percussion_item_key(encoded: str) -> PercussionItemKey:
    part_id, source_key = encoded.split("|")
    return (part_id, int(source_key))


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
            parts_muted=set(data.get("parts_muted", [])),
            staves_muted={_decode_staff_key(k) for k in data.get("staves_muted", [])},
            voices_muted={_decode_voice_key(k) for k in data.get("voices_muted", [])},
            parts_soloed=set(data.get("parts_soloed", [])),
            staves_soloed={_decode_staff_key(k) for k in data.get("staves_soloed", [])},
            voices_soloed={_decode_voice_key(k) for k in data.get("voices_soloed", [])},
            metronome_enabled=data.get("metronome_enabled", False),
            position_announcer_enabled=data.get("position_announcer_enabled", False),
            voice_display_attributes={
                _decode_voice_key(k): set(v)
                for k, v in data.get("voice_display_attributes", {}).items()
            },
            attribute_order=list(data.get("attribute_order", [])),
            mixer=MixerSettings.from_dict(data.get("mixer")),
            part_name_overrides={
                str(k): str(v) for k, v in (data.get("part_name_overrides") or {}).items()
            },
            part_program_overrides={
                str(k): int(v) for k, v in (data.get("part_program_overrides") or {}).items()
            },
            key_signature_override_fifths=data.get("key_signature_override_fifths"),
            key_signature_override_mode=data.get("key_signature_override_mode"),
            playback_tempo_bpm=data.get("playback_tempo_bpm"),
            percussion_item_overrides={
                _decode_percussion_item_key(k): int(v)
                for k, v in (data.get("percussion_item_overrides") or {}).items()
            },
            percussion_item_name_overrides={
                _decode_percussion_item_key(k): str(v)
                for k, v in (data.get("percussion_item_name_overrides") or {}).items()
            },
            percussion_auto_correct_enabled=data.get("percussion_auto_correct_enabled", False),
            last_position_index=int(data.get("last_position_index", 0)),
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
        "parts_muted": sorted(config.parts_muted),
        "staves_muted": [_encode_staff_key(k) for k in sorted(config.staves_muted)],
        "voices_muted": [_encode_voice_key(k) for k in sorted(config.voices_muted)],
        "parts_soloed": sorted(config.parts_soloed),
        "staves_soloed": [_encode_staff_key(k) for k in sorted(config.staves_soloed)],
        "voices_soloed": [_encode_voice_key(k) for k in sorted(config.voices_soloed)],
        "metronome_enabled": config.metronome_enabled,
        "position_announcer_enabled": config.position_announcer_enabled,
        "voice_display_attributes": {
            _encode_voice_key(k): sorted(v)
            for k, v in config.voice_display_attributes.items()
        },
        "attribute_order": list(config.attribute_order),
        "mixer": config.mixer.to_dict(),
        "part_name_overrides": dict(config.part_name_overrides),
        "part_program_overrides": dict(config.part_program_overrides),
        "key_signature_override_fifths": config.key_signature_override_fifths,
        "key_signature_override_mode": config.key_signature_override_mode,
        "playback_tempo_bpm": config.playback_tempo_bpm,
        "percussion_item_overrides": {
            _encode_percussion_item_key(k): v for k, v in config.percussion_item_overrides.items()
        },
        "percussion_item_name_overrides": {
            _encode_percussion_item_key(k): v for k, v in config.percussion_item_name_overrides.items()
        },
        "percussion_auto_correct_enabled": config.percussion_auto_correct_enabled,
        "last_position_index": config.last_position_index,
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
