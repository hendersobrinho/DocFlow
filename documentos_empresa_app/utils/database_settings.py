from __future__ import annotations

import os

from psycopg.conninfo import make_conninfo

from documentos_empresa_app.utils.helpers import load_config, save_config
from documentos_empresa_app.utils.secret_protection import protect_secret, unprotect_secret

# Quando definida, tem prioridade sobre a conexao salva na configuracao local - util para
# servidores/instalacoes gerenciadas. Aceita URL (postgresql://usuario:senha@host:5432/banco)
# ou o formato chave=valor do libpq ("host=... dbname=...").
DATABASE_URL_ENV_VAR = "DOCFLOW_DATABASE_URL"
DATABASE_CONFIG_KEY = "database"

SSL_MODES = ("prefer", "disable", "require")
DEFAULT_DATABASE_SETTINGS = {
    "host": "localhost",
    "port": 5432,
    "dbname": "docflow",
    "user": "",
    "password": "",
    "sslmode": "prefer",
}


def get_database_url_from_env() -> str | None:
    value = str(os.environ.get(DATABASE_URL_ENV_VAR) or "").strip()
    return value or None


def normalize_database_settings(raw: dict | None) -> dict:
    raw = raw or {}
    settings = dict(DEFAULT_DATABASE_SETTINGS)
    for key in ("host", "dbname", "user", "password"):
        settings[key] = str(raw.get(key) or "").strip()
    try:
        settings["port"] = int(raw.get("port") or DEFAULT_DATABASE_SETTINGS["port"])
    except (TypeError, ValueError):
        settings["port"] = DEFAULT_DATABASE_SETTINGS["port"]
    sslmode = str(raw.get("sslmode") or "").strip()
    settings["sslmode"] = sslmode if sslmode in SSL_MODES else DEFAULT_DATABASE_SETTINGS["sslmode"]
    return settings


def load_database_settings() -> dict:
    stored = load_config().get(DATABASE_CONFIG_KEY)
    if not isinstance(stored, dict):
        return dict(DEFAULT_DATABASE_SETTINGS)
    settings = dict(stored)
    settings["password"] = unprotect_secret(stored.get("password")) or ""
    return normalize_database_settings(settings)


def save_database_settings(settings: dict) -> dict:
    normalized = normalize_database_settings(settings)
    stored = dict(normalized)
    # A senha do banco fica protegida como as chaves de API (DPAPI no Windows).
    stored["password"] = protect_secret(normalized["password"]) if normalized["password"] else None
    config = load_config()
    config[DATABASE_CONFIG_KEY] = stored
    save_config(config)
    return normalized


def has_saved_database_settings() -> bool:
    stored = load_config().get(DATABASE_CONFIG_KEY)
    return isinstance(stored, dict) and bool(str(stored.get("dbname") or "").strip())


def load_legacy_sqlite_path() -> str | None:
    """Caminho do banco SQLite usado antes da migracao para o PostgreSQL, se houver -
    usado so para orientar o usuario a importar os dados antigos."""
    value = str(load_config().get("db_path") or "").strip()
    return value or None


def build_conninfo(settings: dict) -> str:
    normalized = normalize_database_settings(settings)
    params = {
        "host": normalized["host"] or None,
        "port": normalized["port"],
        "dbname": normalized["dbname"],
        "user": normalized["user"] or None,
        "password": normalized["password"] or None,
        "sslmode": normalized["sslmode"],
    }
    return make_conninfo(**{key: value for key, value in params.items() if value is not None})


def resolve_database_conninfo() -> str | None:
    env_url = get_database_url_from_env()
    if env_url:
        return env_url
    if not has_saved_database_settings():
        return None
    return build_conninfo(load_database_settings())
