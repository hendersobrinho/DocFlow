from __future__ import annotations

import os
from pathlib import Path
import sys


APP_NAME = "G-docs"
LEGACY_CONFIG_DIR = Path.home() / ".documentos_empresa_app"


def get_default_config_dir() -> Path:
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / APP_NAME
        return Path.home() / "AppData" / "Roaming" / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path.home() / ".g_docs"


CONFIG_DIR = get_default_config_dir()
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_DB_NAME = "g_docs.db"
DOCUMENT_DELIVERY_OPTIONS = (
    "WhatsApp",
    "Email",
    "Onvio",
)
DOCUMENT_DELIVERY_OPTION_BY_KEY = {
    "whatsapp": "WhatsApp",
    "email": "Email",
    "onvio": "Onvio",
}
STATUS_OPTIONS = ("", "Recebido", "Pendente", "Encerrado")
STATUS_COLORS = {
    "": "#FFFFFF",
    "Recebido": "#D9F2D9",
    "Pendente": "#FAD4D4",
    "Encerrado": "#E2E2E2",
}
MONTH_NAMES = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Marco",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}


class ValidationError(Exception):
    """Erro de validacao de negocio."""


def _coerce_delivery_method_items(raw_methods: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if raw_methods is None:
        return []
    if isinstance(raw_methods, str):
        return [item.strip() for item in raw_methods.split(",")]
    return [str(item).strip() for item in raw_methods]


def parse_delivery_methods(
    raw_methods: str | list[str] | tuple[str, ...] | None,
    known_options: str | list[str] | tuple[str, ...] | None = None,
) -> list[str]:
    items = _coerce_delivery_method_items(raw_methods)
    canonical_by_key = dict(DOCUMENT_DELIVERY_OPTION_BY_KEY)
    for option in _coerce_delivery_method_items(known_options):
        if option:
            canonical_by_key[option.casefold()] = option

    normalized_items: list[str] = []
    seen_keys: set[str] = set()
    for item in items:
        if not item:
            continue
        canonical = canonical_by_key.get(item.casefold(), item)
        item_key = canonical.casefold()
        if item_key in seen_keys:
            continue
        seen_keys.add(item_key)
        normalized_items.append(canonical)
    return normalized_items


def normalize_delivery_methods(
    raw_methods: str | list[str] | tuple[str, ...] | None,
    known_options: str | list[str] | tuple[str, ...] | None = None,
) -> str | None:
    normalized_items = parse_delivery_methods(raw_methods, known_options=known_options)
    return ", ".join(normalized_items) if normalized_items else None


def month_key(year: int, month: int) -> int:
    return year * 100 + month


def format_period_label(year: int, month: int) -> str:
    return f"{month:02d}/{year} - {MONTH_NAMES.get(month, str(month))}"


def count_months_between(start_year: int, start_month: int, end_year: int, end_month: int) -> int:
    return (end_year - start_year) * 12 + (end_month - start_month) + 1
