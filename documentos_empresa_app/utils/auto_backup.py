from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from documentos_empresa_app.utils.common import APP_NAME
from documentos_empresa_app.utils.helpers import load_config, save_config


AUTO_BACKUP_CONFIG_KEY = "auto_backup"
DEFAULT_AUTO_BACKUP_INTERVAL_DAYS = 1
DEFAULT_AUTO_BACKUP_KEEP_LAST = 10
MIN_AUTO_BACKUP_INTERVAL_DAYS = 1
MAX_AUTO_BACKUP_INTERVAL_DAYS = 365
MIN_AUTO_BACKUP_KEEP_LAST = 1
MAX_AUTO_BACKUP_KEEP_LAST = 999


def get_default_auto_backup_directory() -> Path:
    base_dir = Path.home()
    for documents_dirname in ("Documents", "Documentos"):
        documents_dir = Path.home() / documents_dirname
        if documents_dir.exists():
            base_dir = documents_dir
            break
    return base_dir / APP_NAME / "backups"


def normalize_auto_backup_settings(
    raw_settings: dict | None,
    *,
    default_directory: str | Path | None = None,
) -> dict:
    settings = raw_settings if isinstance(raw_settings, dict) else {}
    directory = str(settings.get("directory") or default_directory or get_default_auto_backup_directory()).strip()
    return {
        "enabled": bool(settings.get("enabled")),
        "directory": str(Path(directory).expanduser()),
        "interval_days": _coerce_int(
            settings.get("interval_days"),
            DEFAULT_AUTO_BACKUP_INTERVAL_DAYS,
            MIN_AUTO_BACKUP_INTERVAL_DAYS,
            MAX_AUTO_BACKUP_INTERVAL_DAYS,
        ),
        "keep_last": _coerce_int(
            settings.get("keep_last"),
            DEFAULT_AUTO_BACKUP_KEEP_LAST,
            MIN_AUTO_BACKUP_KEEP_LAST,
            MAX_AUTO_BACKUP_KEEP_LAST,
        ),
        "last_backup_at": _normalize_timestamp(settings.get("last_backup_at")),
        "last_backup_path": str(settings.get("last_backup_path") or "").strip(),
    }


def load_auto_backup_settings() -> dict:
    config = load_config()
    return normalize_auto_backup_settings(config.get(AUTO_BACKUP_CONFIG_KEY))


def save_auto_backup_settings(settings: dict) -> dict:
    normalized = normalize_auto_backup_settings(settings)
    config = load_config()
    config[AUTO_BACKUP_CONFIG_KEY] = normalized
    save_config(config)
    return normalized


def should_run_auto_backup(settings: dict, *, now: datetime | None = None) -> bool:
    normalized = normalize_auto_backup_settings(settings)
    if not normalized["enabled"]:
        return False

    current_time = now or datetime.now()
    last_backup_at = parse_auto_backup_timestamp(normalized.get("last_backup_at"))
    if last_backup_at is None:
        return True

    next_backup_at = last_backup_at + timedelta(days=normalized["interval_days"])
    return current_time >= next_backup_at


def mark_auto_backup_created(result: dict, *, when: datetime | None = None) -> dict:
    settings = load_auto_backup_settings()
    settings["last_backup_at"] = (when or datetime.now()).isoformat(timespec="seconds")
    settings["last_backup_path"] = str(result.get("path") or "")
    return save_auto_backup_settings(settings)


def parse_auto_backup_timestamp(raw_value: object) -> datetime | None:
    normalized = _normalize_timestamp(raw_value)
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _coerce_int(raw_value: object, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = default
    return min(max(value, minimum), maximum)


def _normalize_timestamp(raw_value: object) -> str | None:
    normalized = str(raw_value or "").strip()
    return normalized or None
