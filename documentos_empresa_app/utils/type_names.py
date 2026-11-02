from __future__ import annotations

import re
import unicodedata


CANONICAL_TYPE_NAME_BY_KEY = {
    "extratos cc": "Extratos CC",
    "extrato cc": "Extratos CC",
    "extratos c c": "Extratos CC",
    "extrato c c": "Extratos CC",
    "extratos aplicacao": "Extratos aplicacao",
    "extrato aplicacao": "Extratos aplicacao",
    "extratos aplicacoes": "Extratos aplicacao",
    "extrato aplicacoes": "Extratos aplicacao",
    "contratos": "Contratos",
    "contrato": "Contratos",
    "comprovantes": "Comprovantes",
    "comprovante": "Comprovantes",
    "outros": "Outros",
    "outro": "Outros",
    "informe de rendimentos": "Informe de Rendimentos",
    "informe de rendimento": "Informe de Rendimentos",
    "informes de rendimentos": "Informe de Rendimentos",
    "informe rendimentos": "Informe de Rendimentos",
    "crm": "CRM",
    "cro": "CRO",
}


def normalize_type_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value).strip())
    normalized = "".join(character for character in normalized if not unicodedata.combining(character))
    normalized = re.sub(r"[^a-zA-Z0-9]+", " ", normalized).strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def canonicalize_tipo_name(nome_tipo: str) -> str:
    normalized = str(nome_tipo).strip()
    if not normalized:
        return normalized
    key = normalize_type_key(normalized)
    return CANONICAL_TYPE_NAME_BY_KEY.get(key, normalized)

