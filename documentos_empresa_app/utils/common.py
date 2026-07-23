from __future__ import annotations

import os
from pathlib import Path
import sys


APP_NAME = "DocFLow"
LEGACY_CONFIG_DIRS = (
    Path.home() / ".g_docs",
    Path.home() / ".documentos_empresa_app",
)
LEGACY_CONFIG_DIR = LEGACY_CONFIG_DIRS[-1]


def get_default_config_dir() -> Path:
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / APP_NAME
        return Path.home() / "AppData" / "Roaming" / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path.home() / ".docflow"


CONFIG_DIR = get_default_config_dir()
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_DB_NAME = "docflow.db"
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
MAX_COMPANY_OBSERVATION_LENGTH = 255
TYPE_OCCURRENCE_MENSAL = "mensal"
TYPE_OCCURRENCE_TRIMESTRAL = "trimestral"
TYPE_OCCURRENCE_ANUAL_JANEIRO = "anual_janeiro"
TYPE_OCCURRENCE_LABELS = {
    TYPE_OCCURRENCE_MENSAL: "Mensal",
    TYPE_OCCURRENCE_TRIMESTRAL: "Trimestral",
    TYPE_OCCURRENCE_ANUAL_JANEIRO: "Anual em janeiro",
}
TYPE_OCCURRENCE_CHOICES = (
    (TYPE_OCCURRENCE_MENSAL, TYPE_OCCURRENCE_LABELS[TYPE_OCCURRENCE_MENSAL]),
    (TYPE_OCCURRENCE_TRIMESTRAL, TYPE_OCCURRENCE_LABELS[TYPE_OCCURRENCE_TRIMESTRAL]),
    (TYPE_OCCURRENCE_ANUAL_JANEIRO, TYPE_OCCURRENCE_LABELS[TYPE_OCCURRENCE_ANUAL_JANEIRO]),
)
TYPE_OCCURRENCE_ALLOWED_MONTHS = {
    TYPE_OCCURRENCE_MENSAL: frozenset(range(1, 13)),
    TYPE_OCCURRENCE_TRIMESTRAL: frozenset({1, 4, 7, 10}),
    TYPE_OCCURRENCE_ANUAL_JANEIRO: frozenset({1}),
}
AUTO_STATUS_NAO_COBRAR = "Nao cobrar"
STATUS_OPTIONS = ("", "Recebido", "Pendente", AUTO_STATUS_NAO_COBRAR, "Encerrado")
STATUS_COLORS = {
    "": "#FFFFFF",
    "Recebido": "#D9F2D9",
    "Pendente": "#FAD4D4",
    "Encerrado": "#E2E2E2",
    AUTO_STATUS_NAO_COBRAR: "#F6EFC7",
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


def normalize_type_occurrence_rule(raw_rule: str | None) -> str:
    normalized = str(raw_rule or "").strip().casefold().replace("-", "_").replace(" ", "_")
    alias_map = {
        "": TYPE_OCCURRENCE_MENSAL,
        "mensal": TYPE_OCCURRENCE_MENSAL,
        "padrao": TYPE_OCCURRENCE_MENSAL,
        "normal": TYPE_OCCURRENCE_MENSAL,
        "trimestral": TYPE_OCCURRENCE_TRIMESTRAL,
        "anual": TYPE_OCCURRENCE_ANUAL_JANEIRO,
        "anual_janeiro": TYPE_OCCURRENCE_ANUAL_JANEIRO,
        "janeiro": TYPE_OCCURRENCE_ANUAL_JANEIRO,
    }
    if normalized not in alias_map:
        raise ValidationError("Regra de ocorrencia invalida para o tipo de documento.")
    return alias_map[normalized]


def get_type_occurrence_label(raw_rule: str | None) -> str:
    rule = normalize_type_occurrence_rule(raw_rule)
    return TYPE_OCCURRENCE_LABELS[rule]


def is_chargeable_period(raw_rule: str | None, month: int) -> bool:
    rule = normalize_type_occurrence_rule(raw_rule)
    return month in TYPE_OCCURRENCE_ALLOWED_MONTHS[rule]


def build_chargeable_closure_key_map(
    closure_rows: list[dict],
    occurrence_by_document: dict[int, str | None],
) -> dict[int, int]:
    closure_keys: dict[int, int] = {}
    for row in closure_rows:
        occurrence_rule = normalize_type_occurrence_rule(
            occurrence_by_document.get(row["documento_empresa_id"], TYPE_OCCURRENCE_MENSAL)
        )
        if not is_chargeable_period(occurrence_rule, row["mes"]):
            continue

        current_key = month_key(row["ano"], row["mes"])
        previous_key = closure_keys.get(row["documento_empresa_id"])
        if previous_key is None or current_key < previous_key:
            closure_keys[row["documento_empresa_id"]] = current_key
    return closure_keys


def month_key(year: int, month: int) -> int:
    return year * 100 + month


def format_period_label(year: int, month: int) -> str:
    return f"{month:02d}/{year} - {MONTH_NAMES.get(month, str(month))}"


def count_months_between(start_year: int, start_month: int, end_year: int, end_month: int) -> int:
    return (end_year - start_year) * 12 + (end_month - start_month) + 1
