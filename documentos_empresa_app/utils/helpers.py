from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import quote

from documentos_empresa_app.utils.common import (
    APP_NAME,
    CONFIG_DIR,
    CONFIG_FILE,
    LEGACY_CONFIG_DIRS,
    ValidationError,
)


def ensure_config_dir() -> None:
    migrate_legacy_config_dir()
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _harden_config_directory_permissions()
    _harden_config_file_permissions(CONFIG_FILE)


def migrate_legacy_config_dir() -> None:
    if CONFIG_DIR.exists():
        return

    for legacy_config_dir in LEGACY_CONFIG_DIRS:
        if CONFIG_DIR == legacy_config_dir or not legacy_config_dir.exists():
            continue
        _migrate_config_dir(legacy_config_dir)
        return


def _migrate_config_dir(legacy_config_dir: Path) -> None:
    CONFIG_DIR.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(legacy_config_dir), str(CONFIG_DIR))
    except OSError:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        legacy_config_file = legacy_config_dir / "config.json"
        if legacy_config_file.exists() and not CONFIG_FILE.exists():
            shutil.copy2(legacy_config_file, CONFIG_FILE)
            _harden_config_file_permissions(CONFIG_FILE)
        return

    _rewrite_migrated_config_paths(CONFIG_FILE, legacy_config_dir, CONFIG_DIR)


def _rewrite_migrated_config_paths(config_file: Path, old_root: Path, new_root: Path) -> None:
    if not config_file.exists():
        return
    try:
        config = json.loads(config_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return

    db_path = config.get("db_path")
    if not db_path:
        return

    try:
        resolved_path = Path(db_path).expanduser()
        if resolved_path.is_relative_to(old_root):
            config["db_path"] = str(new_root / resolved_path.relative_to(old_root))
            config_file.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
            _harden_config_file_permissions(config_file)
    except OSError:
        return


def load_config() -> dict:
    ensure_config_dir()
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_config(config: dict) -> None:
    ensure_config_dir()
    CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    _harden_config_file_permissions(CONFIG_FILE)


def resolve_anthropic_api_key() -> str | None:
    env_key = os.environ.get("ANTHROPIC_API_KEY")
    if env_key:
        return env_key
    stored = str(load_config().get("anthropic_api_key") or "").strip()
    return stored or None


def load_document_agent_inbox_folder() -> str | None:
    stored = str(load_config().get("document_agent_inbox_folder") or "").strip()
    return stored or None


def save_document_agent_inbox_folder(folder: str | None) -> None:
    config = load_config()
    normalized = str(folder or "").strip()
    if normalized:
        config["document_agent_inbox_folder"] = normalized
    else:
        config.pop("document_agent_inbox_folder", None)
    save_config(config)


def load_login_preferences() -> dict:
    config = load_config()
    stored = config.get("login_preferences")
    if not isinstance(stored, dict):
        return {
            "username": "",
            "remember_credential": False,
            "remembered_token": None,
        }

    username = str(stored.get("username") or "").strip()
    remembered_token = str(stored.get("remembered_token") or "").strip() or None
    remember_credential = bool(stored.get("remember_credential") and remembered_token)
    return {
        "username": username,
        "remember_credential": remember_credential,
        "remembered_token": remembered_token,
    }


def save_login_preferences(
    username: str | None,
    *,
    remember_credential: bool,
    remembered_token: str | None,
) -> None:
    config = load_config()
    normalized_username = str(username or "").strip()
    normalized_token = str(remembered_token or "").strip() or None

    if normalized_username or normalized_token or remember_credential:
        config["login_preferences"] = {
            "username": normalized_username,
            "remember_credential": bool(remember_credential and normalized_token),
            "remembered_token": normalized_token if remember_credential else None,
        }
    else:
        config.pop("login_preferences", None)
    save_config(config)


def _harden_config_directory_permissions() -> None:
    if os.name == "nt":
        return
    try:
        os.chmod(CONFIG_DIR, 0o700)
    except OSError:
        return


def _harden_config_file_permissions(file_path: Path) -> None:
    if os.name == "nt" or not file_path.exists():
        return
    try:
        os.chmod(file_path, 0o600)
    except OSError:
        return


def open_directory_in_file_manager(directory: str | Path) -> None:
    path = Path(directory).expanduser()
    if not path.exists() or not path.is_dir():
        raise ValidationError("A pasta vinculada nao foi encontrada no computador.")

    try:
        if sys.platform.startswith("win") and hasattr(os, "startfile"):
            os.startfile(str(path))
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
            return
        subprocess.Popen(["xdg-open", str(path)])
    except OSError as exc:
        raise ValidationError("Nao foi possivel abrir a pasta vinculada.") from exc


def get_default_email_handler() -> str:
    if sys.platform.startswith("win"):
        return "Cliente de email padrao do Windows"
    if sys.platform == "darwin":
        return "Cliente de email padrao do macOS"

    for command in (
        ["xdg-mime", "query", "default", "x-scheme-handler/mailto"],
        ["gio", "mime", "x-scheme-handler/mailto"],
    ):
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True)
        except (OSError, subprocess.CalledProcessError):
            continue
        output = result.stdout.strip()
        if not output:
            continue
        if "Default application for" in output:
            marker = "Default application for “x-scheme-handler/mailto”:"
            if marker in output:
                return output.split(marker, 1)[1].strip()
        return output.splitlines()[0].strip()
    return "Cliente de email padrao do sistema"


def open_email_draft(to_address: str, subject: str, body: str) -> str:
    to_value = str(to_address or "").strip()
    if not to_value:
        raise ValidationError("Nao foi informado um destinatario de email.")

    handler_name = get_default_email_handler()
    mailto_url = f'mailto:{quote(to_value)}?subject={quote(subject)}&body={quote(body)}'

    try:
        if sys.platform.startswith("win") and hasattr(os, "startfile"):
            os.startfile(mailto_url)
            return handler_name

        if sys.platform == "darwin":
            subprocess.Popen(["open", mailto_url])
            return handler_name

        linux_attempts = [
            ["xdg-email", "--utf8", "--subject", subject, "--body", body, to_value],
            ["gio", "open", mailto_url],
            ["xdg-open", mailto_url],
        ]
        for command in linux_attempts:
            try:
                subprocess.Popen(command)
                return handler_name
            except OSError:
                continue
    except OSError as exc:
        raise ValidationError("Nao foi possivel abrir o cliente de email do sistema.") from exc

    raise ValidationError("Nao foi possivel localizar um cliente de email compativel neste computador.")


def get_install_root_directory() -> Path:
    app_reference = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve()
    anchor = app_reference.anchor or Path.cwd().anchor or os.sep
    return Path(anchor)


def is_database_path_usable(db_path: str | Path) -> bool:
    path = Path(db_path)
    if path.exists():
        return path.is_file() and os.access(path, os.R_OK | os.W_OK)

    parent = path.parent
    return parent.exists() and parent.is_dir() and os.access(parent, os.W_OK)
