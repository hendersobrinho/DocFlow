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
from documentos_empresa_app.utils.secret_protection import protect_secret, unprotect_secret


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


# Chaves que versoes anteriores gravavam para recursos que foram removidos: o agente de IA
# (provedor, API keys, modelo, limiar de confianca, prompt customizado) e o agente
# organizador de documentos (pasta de entrada, caixa de email IMAP com a senha e o registro
# de remetentes dos anexos). purge_removed_feature_settings apaga esses valores para nao
# deixar credenciais esquecidas no config.json.
REMOVED_FEATURE_CONFIG_KEYS = (
    "anthropic_api_key",
    "openai_api_key",
    "agente_provider",
    "agente_modelo_anthropic",
    "agente_modelo_openai",
    "agente_confianca_minima",
    "agente_system_prompt_customizado",
    "document_agent_inbox_folder",
    "email_ingestion_imap",
    "email_ingestion_senders",
)


def purge_removed_feature_settings() -> None:
    config = load_config()
    if not any(key in config for key in REMOVED_FEATURE_CONFIG_KEYS):
        return
    for key in REMOVED_FEATURE_CONFIG_KEYS:
        config.pop(key, None)
    save_config(config)


def load_backup_encryption_password() -> str | None:
    stored = str(unprotect_secret(load_config().get("backup_encryption_password")) or "").strip()
    return stored or None


def save_backup_encryption_password(password: str | None) -> None:
    config = load_config()
    normalized = str(password or "").strip()
    if normalized:
        config["backup_encryption_password"] = protect_secret(normalized)
    else:
        config.pop("backup_encryption_password", None)
    save_config(config)


def load_mailing_campaign() -> dict:
    stored = load_config().get("mala_direta_campanha")
    return dict(stored) if isinstance(stored, dict) else {}


def save_mailing_campaign(campaign: dict) -> None:
    config = load_config()
    config["mala_direta_campanha"] = campaign
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
    remembered_token = str(unprotect_secret(stored.get("remembered_token")) or "").strip() or None
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
            "remembered_token": protect_secret(normalized_token) if remember_credential else None,
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


def open_file_in_default_app(file_path: str | Path) -> None:
    path = Path(file_path).expanduser()
    if not path.exists() or not path.is_file():
        raise ValidationError("O arquivo nao foi encontrado no computador.")

    try:
        if sys.platform.startswith("win") and hasattr(os, "startfile"):
            os.startfile(str(path))
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
            return
        subprocess.Popen(["xdg-open", str(path)])
    except OSError as exc:
        raise ValidationError("Nao foi possivel abrir o arquivo.") from exc


def get_documents_directory() -> Path:
    """Pasta Documentos do usuario (ou a pasta pessoal, se nao existir) - ponto de partida
    para salvar relatorios, em vez da pasta de onde o programa foi aberto."""
    home = Path.home()
    for name in ("Documents", "Documentos"):
        candidate = home / name
        if candidate.is_dir():
            return candidate
    return home


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


def open_bcc_email_draft(bcc_addresses: list[str], subject: str, body: str) -> str:
    """Abre um rascunho no cliente de email padrao com todos os enderecos em BCC -
    nenhum destinatario ve o email dos outros, e o envio em si fica por conta do
    usuario dentro do proprio cliente de email (nada e enviado por aqui)."""
    addresses = [str(address or "").strip() for address in bcc_addresses if str(address or "").strip()]
    if not addresses:
        raise ValidationError("Nao ha destinatarios para o rascunho de email.")

    handler_name = get_default_email_handler()
    bcc_value = ",".join(addresses)
    mailto_url = f'mailto:?bcc={quote(bcc_value)}&subject={quote(subject)}&body={quote(body)}'

    try:
        if sys.platform.startswith("win") and hasattr(os, "startfile"):
            os.startfile(mailto_url)
            return handler_name

        if sys.platform == "darwin":
            subprocess.Popen(["open", mailto_url])
            return handler_name

        linux_attempts = [
            ["xdg-email", "--utf8", "--bcc", bcc_value, "--subject", subject, "--body", body],
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
