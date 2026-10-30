from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Callable

from documentos_empresa_app.utils.common import (
    TYPE_OCCURRENCE_ALLOWED_MONTHS,
    is_chargeable_period,
    normalize_type_occurrence_rule,
)

# ── Text normalization ─────────────────────────────────────────────────────────

def normalize(text: str) -> str:
    nfkd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn").lower()


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", normalize(text))


def contains_any(text: str, tokens: list[str]) -> bool:
    norm = normalize(text)
    return any(normalize(t) in norm for t in tokens)


def split_aliases(raw: str | list[str] | tuple[str, ...] | None, fallback: list[str]) -> list[str]:
    if raw is None:
        return list(fallback)
    if isinstance(raw, (list, tuple)):
        aliases = [str(item).strip() for item in raw if str(item).strip()]
    else:
        aliases = [
            part.strip()
            for part in re.split(r"[;\n,]+", str(raw))
            if part.strip()
        ]
    return aliases or list(fallback)


def split_lines(raw: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(item).strip() for item in raw if str(item).strip()]
    return [line.strip() for line in str(raw).splitlines() if line.strip()]


def normalize_file_check_options(options: dict | None = None) -> dict:
    merged = dict(DEFAULT_FILE_CHECK_OPTIONS)
    if options:
        merged.update({k: v for k, v in options.items() if v is not None})

    if merged.get("layout_mode") not in {
        LAYOUT_AUTO, LAYOUT_YEAR_DIRECT, LAYOUT_MONTH_FIRST, LAYOUT_DOCUMENT_FIRST,
    }:
        merged["layout_mode"] = LAYOUT_AUTO
    if merged.get("period_source") not in {
        PERIOD_SOURCE_FILENAME_OR_FOLDER, PERIOD_SOURCE_FILENAME_ONLY,
    }:
        merged["period_source"] = PERIOD_SOURCE_FILENAME_OR_FOLDER

    merged["allow_generic_documents"] = bool(merged.get("allow_generic_documents", True))
    merged["require_registered_terms"] = bool(merged.get("require_registered_terms", True))
    merged["bank_folder_aliases"] = "; ".join(
        split_aliases(merged.get("bank_folder_aliases"), EXTRATOS_FOLDER_TOKENS)
    )
    merged["cc_folder_aliases"] = "; ".join(
        split_aliases(merged.get("cc_folder_aliases"), CC_FOLDER_TOKENS)
    )
    merged["aplicacao_folder_aliases"] = "; ".join(
        split_aliases(merged.get("aplicacao_folder_aliases"), APLICACAO_FOLDER_TOKENS)
    )
    merged["filename_templates"] = str(
        merged.get("filename_templates", DEFAULT_FILE_CHECK_OPTIONS["filename_templates"])
    ).strip()
    merged["require_template_match"] = bool(merged.get("require_template_match", False))
    merged["required_filename_terms"] = "; ".join(
        split_aliases(merged.get("required_filename_terms"), [])
    )
    merged["forbidden_filename_terms"] = "; ".join(
        split_aliases(merged.get("forbidden_filename_terms"), [])
    )
    return merged


# ── Result constants ───────────────────────────────────────────────────────────

RESULT_ALTA_CONFIANCA = "alta_confianca"
RESULT_REVISAR = "revisar"
RESULT_NAO_ENCONTRADO = "nao_encontrado"
RESULT_ERRO = "erro"

SCORE_HIGH = 90
SCORE_REVIEW = 60

# ── Temporal classification constants ─────────────────────────────────────────

TEMPORAL_ATUAL = "competencia_atual"
TEMPORAL_ANTERIOR_PENDENTE = "competencia_anterior_pendente"
TEMPORAL_ANTERIOR_RECEBIDA = "competencia_anterior_ja_recebida"
TEMPORAL_FUTURA = "competencia_futura"
TEMPORAL_DIFERENTE = "competencia_diferente"
TEMPORAL_NAO_IDENTIFICADA = "competencia_nao_identificada"

# ── Verification mode constants ────────────────────────────────────────────────

MODE_CURRENT_ONLY = "somente_atual"
MODE_PENDING_HISTORY = "pendentes_ate_atual"

# ── Folder/rule configuration constants ───────────────────────────────────────

LAYOUT_AUTO = "auto"
LAYOUT_YEAR_DIRECT = "ano_direto"
LAYOUT_MONTH_FIRST = "competencia_primeiro"
LAYOUT_DOCUMENT_FIRST = "documento_primeiro"

PERIOD_SOURCE_FILENAME_OR_FOLDER = "nome_ou_pasta"
PERIOD_SOURCE_FILENAME_ONLY = "somente_nome"

# ── Bank aliases ───────────────────────────────────────────────────────────────

BANK_ALIASES: dict[str, list[str]] = {
    "banco do brasil": ["banco do brasil", "bb", "brasil"],
    "caixa": ["caixa", "cef"],
    "itau": ["itau", "itau"],
    "bradesco": ["bradesco"],
    "santander": ["santander", "santarder"],
    "sicredi": ["sicredi"],
    "sicoob": ["sicoob"],
    "banestes": ["banestes"],
    "nubank": ["nubank", "nu"],
    "inter": ["inter"],
    "c6": ["c6"],
    "safra": ["safra"],
}

# ── Document-type tokens (for nome_documento / nome_tipo matching) ─────────────

EXTRATO_BASE_TOKENS = ["extrato", "bancario", "banco"]

CC_DOCUMENT_TOKENS = ["conta corrente", "cc", "c/c", "c.c", "corrente"]
APLICACAO_DOCUMENT_TOKENS = [
    "aplicacao", "aplicacoes", "investimento", "investimentos",
    "poupanca", "rendimento", "resgate", "cdb",
]

# ── Folder-name tokens ─────────────────────────────────────────────────────────

EXTRATOS_FOLDER_TOKENS = [
    "extratos bancarios", "extrato bancario", "extrato banco", "bancos",
]

CC_FOLDER_TOKENS = ["conta corrente", "corrente", "cc", "c c", "c.c"]
APLICACAO_FOLDER_TOKENS = [
    "aplicacao", "aplicacoes", "investimento", "investimentos", "poupanca",
]

DEFAULT_FILE_CHECK_OPTIONS = {
    "layout_mode": LAYOUT_AUTO,
    "period_source": PERIOD_SOURCE_FILENAME_OR_FOLDER,
    "allow_generic_documents": True,
    "require_registered_terms": True,
    "bank_folder_aliases": "; ".join(EXTRATOS_FOLDER_TOKENS),
    "cc_folder_aliases": "; ".join(CC_FOLDER_TOKENS),
    "aplicacao_folder_aliases": "; ".join(APLICACAO_FOLDER_TOKENS),
    "filename_templates": "\n".join((
        "{codigo} {documento} {competencia}",
        "{codigo}. {banco} {tipo} {competencia}",
        "{documento} {competencia}",
    )),
    "require_template_match": False,
    "required_filename_terms": "",
    "forbidden_filename_terms": "",
}

# ── File-name type tokens ──────────────────────────────────────────────────────

CC_FILE_TOKENS = ["conta corrente", "cc", "c/c", "c.c", "corrente", "extrato"]
APLICACAO_FILE_TOKENS = [
    "aplicacao", "aplicacoes", "investimento", "investimentos",
    "rendimento", "resgate", "cdb", "poupanca",
]

DOCUMENT_BANK_STOPWORDS = {
    "banco", "do", "da", "de", "dos", "das", "c", "cc", "conta",
    "corrente", "aplicacao", "aplicacoes", "investimento", "investimentos",
    "extrato", "extratos", "capital", "consolidado", "identificado",
}

GENERIC_DOCUMENT_STOPWORDS = {
    "a", "as", "o", "os", "e", "de", "do", "da", "dos", "para", "por",
    "com", "sem", "no", "na", "nos", "nas", "documento", "documentos",
    "arquivo", "arquivos", "competencia", "mensal", "mes", "ano",
}

GENERIC_SHORT_TOKENS = {
    "cc", "das", "gps", "iss", "ipi", "ir", "nf", "nfs", "cte",
}

# ── Month names (BR) ───────────────────────────────────────────────────────────

MONTH_NAMES_BR: dict[int, list[str]] = {
    1: ["jan", "janeiro"],
    2: ["fev", "fevereiro"],
    3: ["mar", "marco"],
    4: ["abr", "abril"],
    5: ["mai", "maio"],
    6: ["jun", "junho"],
    7: ["jul", "julho"],
    8: ["ago", "agosto"],
    9: ["set", "setembro"],
    10: ["out", "outubro"],
    11: ["nov", "novembro"],
    12: ["dez", "dezembro"],
}

# ── Period helpers ─────────────────────────────────────────────────────────────

def _period_key(mes: int, ano: int) -> int:
    """Integer key for period comparison: larger = later."""
    return ano * 100 + mes


def _period_label(periods: list[tuple[int, int]]) -> str:
    if not periods:
        return "?"
    return ", ".join(f"{m:02d}/{a}" for m, a in periods)


# ── Document classification helpers ───────────────────────────────────────────

def is_bank_statement_document(nome_tipo: str, nome_documento: str) -> bool:
    combined = f"{nome_tipo} {nome_documento}"
    return contains_any(combined, EXTRATO_BASE_TOKENS)


def document_match_terms(nome_tipo: str, nome_documento: str) -> list[str]:
    """Build stable filename tokens from the registered document labels."""
    terms = _document_terms_from_text(nome_documento)
    if terms:
        return terms
    return _document_terms_from_text(nome_tipo)


def _document_terms_from_text(text: str) -> list[str]:
    terms: list[str] = []
    for token in tokenize(text):
        if token.isdigit():
            continue
        if token in GENERIC_DOCUMENT_STOPWORDS:
            continue
        if len(token) < 3 and token not in GENERIC_SHORT_TOKENS:
            continue
        if token not in terms:
            terms.append(token)
    return terms


def required_document_term_count(terms: list[str]) -> int:
    if not terms:
        return 0
    if len(terms) >= 3:
        return 2
    return 1


def match_document_terms(text: str, terms: list[str]) -> list[str]:
    norm = normalize(text)
    words = set(tokenize(text))
    matched: list[str] = []
    for term in terms:
        if term in words or (len(term) > 3 and term in norm):
            matched.append(term)
    return matched


def _literal_template_terms(template: str) -> list[str]:
    without_fields = re.sub(r"\{[a-z_]+\}", " ", normalize(template))
    return [
        token for token in tokenize(without_fields)
        if token not in GENERIC_DOCUMENT_STOPWORDS and not token.isdigit()
    ]


def _has_literal_terms(filename: str, terms: list[str]) -> bool:
    if not terms:
        return True
    return len(match_document_terms(filename, terms)) == len(terms)


def _template_fields(template: str) -> set[str]:
    return set(re.findall(r"\{([a-z_]+)\}", normalize(template)))


def filename_matches_template(
    filename: str,
    template: str,
    evidence: dict,
) -> bool:
    fields = _template_fields(template)
    literal_terms = _literal_template_terms(template)

    checks = {
        "codigo": bool(evidence.get("company_code_matched")),
        "competencia": bool(evidence.get("period_filename_matched")),
        "documento": bool(evidence.get("doc_terms_matched")),
        "banco": (not evidence.get("bank_required")) or bool(evidence.get("bank_matched")),
        "tipo": (
            not evidence.get("type_required")
            or bool(evidence.get("type_filename_matched"))
            or bool(evidence.get("type_folder_matched"))
        ),
    }

    for field in fields:
        if field in checks and not checks[field]:
            return False
    return _has_literal_terms(filename, literal_terms)


def match_filename_templates(
    filename: str,
    templates: list[str],
    evidence: dict,
) -> str | None:
    for template in templates:
        if filename_matches_template(filename, template, evidence):
            return template
    return None


def is_checkable_document(nome_tipo: str, nome_documento: str) -> bool:
    if is_bank_statement_document(nome_tipo, nome_documento):
        return True
    return bool(document_match_terms(nome_tipo, nome_documento))


def detect_document_bank(nome_documento: str) -> str | None:
    norm = normalize(nome_documento)
    for bank_key in BANK_ALIASES:
        if match_bank_in_text(norm, bank_key):
            return bank_key
    extracted = extract_bank_after_banco(nome_documento)
    if extracted:
        return extracted
    return None


def detect_document_type(nome_documento: str) -> str | None:
    norm = normalize(nome_documento)
    if any(normalize(t) in norm for t in CC_DOCUMENT_TOKENS):
        return "cc"
    if any(normalize(t) in norm for t in APLICACAO_DOCUMENT_TOKENS):
        return "aplicacao"
    return None


def bank_aliases(bank_key: str) -> list[str]:
    aliases = BANK_ALIASES.get(bank_key)
    if aliases:
        return aliases
    return [bank_key]


def match_bank_in_text(text: str, bank_key: str | None) -> bool:
    if not bank_key:
        return False

    norm = normalize(text)
    words = set(tokenize(text))
    for alias in bank_aliases(bank_key):
        alias_norm = normalize(alias)
        alias_words = tokenize(alias)
        if not alias_words:
            continue
        if len(alias_words) == 1:
            if alias_words[0] in words:
                return True
            continue
        if alias_norm in norm:
            return True
    return False


def detect_bank_in_text(text: str) -> str | None:
    for bank_key in BANK_ALIASES:
        if match_bank_in_text(text, bank_key):
            return bank_key
    return extract_bank_after_banco(text)


def extract_bank_after_banco(text: str) -> str | None:
    words = tokenize(text)
    for index, word in enumerate(words):
        if word != "banco":
            continue
        for next_word in words[index + 1:]:
            if next_word in DOCUMENT_BANK_STOPWORDS or next_word.isdigit():
                continue
            return next_word
    return None


# ── Period matching ────────────────────────────────────────────────────────────

def match_period_in_filename(filename: str, mes: int, ano: int) -> bool:
    norm = normalize(filename)
    ano_str = str(ano)
    mes_padded = f"{mes:02d}"
    patterns = [
        f"{mes_padded}/{ano_str}",
        f"{mes_padded}-{ano_str}",
        f"{mes_padded}.{ano_str}",
        f"{mes_padded}_{ano_str}",
        f"{mes_padded}{ano_str}",
        f"{ano_str}-{mes_padded}",
        f"{ano_str}/{mes_padded}",
        f"{ano_str}_{mes_padded}",
        f"{ano_str}{mes_padded}",
    ]
    for name in MONTH_NAMES_BR.get(mes, []):
        patterns.append(name)
        patterns.append(f"{name} {ano_str}")
        patterns.append(f"{name}{ano_str}")
    return any(p in norm for p in patterns)


def extract_periods_from_filename(
    filename: str, fallback_year: int | None = None
) -> list[tuple[int, int]]:
    """Return all (mes, ano) tuples detected in filename.

    If only a month name is found (no year digits in name), uses fallback_year.
    """
    norm = normalize(filename)
    found: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()

    def _add(mes: int, ano: int) -> None:
        key = (mes, ano)
        if key not in seen:
            found.append(key)
            seen.add(key)

    # MM[sep]YYYY  (separator: / - . _ space)
    for m in re.finditer(r"(0[1-9]|1[0-2])[/\-\._ ](20[2-9][0-9])", norm):
        _add(int(m.group(1)), int(m.group(2)))

    # YYYY[sep]MM
    for m in re.finditer(r"(20[2-9][0-9])[/\-\._ ](0[1-9]|1[0-2])", norm):
        _add(int(m.group(2)), int(m.group(1)))

    # Concatenated MMYYYY  (e.g. "012026" — not preceded by a digit)
    for m in re.finditer(r"(?<!\d)(0[1-9]|1[0-2])(20[2-9][0-9])(?!\d)", norm):
        _add(int(m.group(1)), int(m.group(2)))

    # Concatenated YYYYMM  (e.g. "202601" — not followed by a digit)
    for m in re.finditer(r"(?<!\d)(20[2-9][0-9])(0[1-9]|1[0-2])(?!\d)", norm):
        _add(int(m.group(2)), int(m.group(1)))

    # Month names with year (any non-alpha-nondigit separator, e.g. "jan_2026", "jan 2026")
    # Require the name is not immediately followed by another letter to avoid "jan" matching "janeiro"
    for mes, names in MONTH_NAMES_BR.items():
        for name in names:
            n = normalize(name)
            m = re.search(rf"{re.escape(n)}(?![a-z])[^a-z0-9]*(20[2-9][0-9])", norm)
            if m:
                _add(mes, int(m.group(1)))

    # Month names without year → use fallback_year only when nothing else matched
    if fallback_year and not found:
        for mes, names in MONTH_NAMES_BR.items():
            for name in names:
                n = normalize(name)
                if re.search(rf"(?<![a-z]){re.escape(n)}(?![a-z])", norm):
                    _add(mes, fallback_year)

    return found


def extract_periods_from_folder_name(
    folder_name: str, fallback_year: int | None = None
) -> list[tuple[int, int]]:
    """Folder names may be short ("05", "Maio") because the year is one level above."""
    found = extract_periods_from_filename(folder_name, fallback_year=fallback_year)
    seen = set(found)

    def _add(mes: int, ano: int) -> None:
        key = (mes, ano)
        if key not in seen:
            found.append(key)
            seen.add(key)

    if fallback_year:
        for token in tokenize(folder_name):
            if re.fullmatch(r"0?[1-9]|1[0-2]", token):
                _add(int(token), fallback_year)

    return found


def build_expected_periods(
    regra_ocorrencia: str | None, selected_mes: int, selected_ano: int
) -> list[tuple[int, int]]:
    """Return expected (mes, ano) pairs for the selected_ano up to selected period."""
    rule = normalize_type_occurrence_rule(regra_ocorrencia)
    allowed_months: frozenset[int] = TYPE_OCCURRENCE_ALLOWED_MONTHS[rule]
    selected_key = _period_key(selected_mes, selected_ano)
    result = []
    for mes in range(1, 13):
        if mes not in allowed_months:
            continue
        if _period_key(mes, selected_ano) <= selected_key:
            result.append((mes, selected_ano))
    return result


def match_bank_in_filename(filename: str, bank_key: str | None) -> bool:
    return match_bank_in_text(filename, bank_key)


def match_type_in_filename(filename: str, doc_type: str | None) -> bool:
    if not doc_type:
        return False
    tokens = CC_FILE_TOKENS if doc_type == "cc" else APLICACAO_FILE_TOKENS
    return contains_any(filename, tokens)


def detect_type_in_filename(filename: str) -> str | None:
    if contains_any(filename, APLICACAO_FILE_TOKENS):
        return "aplicacao"
    if contains_any(filename, CC_FILE_TOKENS):
        return "cc"
    return None


# ── Folder resolution ──────────────────────────────────────────────────────────

def resolve_company_folder(empresa: dict, root_dir: Path) -> tuple[Path | None, int, str]:
    dir_doc = empresa.get("diretorio_documentos")
    if dir_doc:
        p = Path(dir_doc)
        if p.exists() and p.is_dir():
            return p, 30, f"Pasta configurada: {p.name}"
        return None, 0, f"Pasta configurada nao encontrada: {p}"

    codigo = str(empresa["codigo_empresa"])
    prefixes = [f"{codigo}.", f"{codigo} -", f"{codigo}-", f"{codigo} ", f"{codigo}_", codigo]

    try:
        for child in root_dir.iterdir():
            if not child.is_dir():
                continue
            norm_name = normalize(child.name)
            for prefix in prefixes:
                if norm_name.startswith(normalize(prefix)):
                    return child, 30, f"Pasta encontrada pelo codigo: {child.name}"
    except PermissionError as exc:
        return None, 0, f"Sem permissao na raiz: {exc}"
    except OSError as exc:
        return None, 0, f"Erro ao acessar raiz: {exc}"

    return None, 0, f"Pasta da empresa {codigo} nao encontrada"


def bank_display_label(bank_key: str) -> str:
    return bank_aliases(bank_key)[0].title()


def resolve_year_folder(company_dir: Path, ano: int) -> tuple[Path | None, int, str]:
    ano_str = str(ano)
    try:
        for child in company_dir.iterdir():
            if child.is_dir() and child.name == ano_str:
                return child, 20, f"Pasta do ano {ano_str} encontrada"
    except (PermissionError, OSError) as exc:
        return None, 0, f"Erro ao ler pasta da empresa: {exc}"
    return None, 0, f"Pasta do ano {ano_str} nao encontrada"


def resolve_month_folder(parent_dir: Path, mes: int, ano: int) -> tuple[Path | None, int, str]:
    target = (mes, ano)
    try:
        for child in parent_dir.iterdir():
            if not child.is_dir():
                continue
            if target in extract_periods_from_folder_name(child.name, fallback_year=ano):
                return child, 15, f"Pasta da competencia {mes:02d}/{ano}: {child.name}"
    except (PermissionError, OSError) as exc:
        return None, 0, f"Erro ao procurar pasta da competencia: {exc}"
    return None, 0, f"Pasta da competencia {mes:02d}/{ano} nao encontrada"


def resolve_extratos_folder(
    year_dir: Path,
    folder_tokens: list[str] | None = None,
) -> tuple[Path | None, int, str]:
    folder_tokens = folder_tokens or EXTRATOS_FOLDER_TOKENS
    try:
        for child in year_dir.iterdir():
            if child.is_dir() and contains_any(child.name, folder_tokens):
                return child, 10, f"Pasta de extratos: {child.name}"
    except (PermissionError, OSError) as exc:
        return None, 0, f"Erro ao ler pasta do ano: {exc}"
    return None, 0, "Pasta de extratos bancarios nao encontrada"


def resolve_type_subfolder(
    extratos_dir: Path,
    doc_type: str | None,
    *,
    cc_tokens: list[str] | None = None,
    aplicacao_tokens: list[str] | None = None,
) -> tuple[Path | None, int, str]:
    if not doc_type:
        return None, 0, "Tipo de conta nao identificado no documento"
    tokens = (cc_tokens or CC_FOLDER_TOKENS) if doc_type == "cc" else (
        aplicacao_tokens or APLICACAO_FOLDER_TOKENS
    )
    try:
        for child in extratos_dir.iterdir():
            if child.is_dir() and contains_any(child.name, tokens):
                return child, 20, f"Subpasta correta: {child.name}"
    except (PermissionError, OSError) as exc:
        return None, 0, f"Erro ao ler pasta de extratos: {exc}"
    type_label = "conta corrente" if doc_type == "cc" else "aplicacao"
    return None, 0, f"Subpasta de {type_label} nao encontrada"


def resolve_document_folder(parent_dir: Path, doc_terms: list[str]) -> tuple[Path | None, int, str]:
    required = required_document_term_count(doc_terms)
    if not required:
        return None, 0, "Documento sem termos suficientes para procurar pasta propria"

    best: tuple[Path, int, list[str]] | None = None
    try:
        for child in parent_dir.iterdir():
            if not child.is_dir():
                continue
            matched = match_document_terms(child.name, doc_terms)
            if len(matched) < required:
                continue
            score = 15 + min(len(matched), 3) * 5
            if best is None or score > best[1]:
                best = (child, score, matched)
    except (PermissionError, OSError) as exc:
        return None, 0, f"Erro ao procurar pasta do documento: {exc}"

    if best:
        folder, score, matched = best
        return folder, score, f"Pasta do documento: {folder.name} ({', '.join(matched)})"
    return None, 0, "Pasta do documento nao encontrada"


# ── File scoring ───────────────────────────────────────────────────────────────

def score_file(
    file_path: Path,
    empresa_codigo: int,
    doc_bank: str | None,
    doc_type: str | None,
    mes: int,
    ano: int,
    base_score: int,
    *,
    expected_type_folder: bool = False,
    period_from_folder: tuple[int, int] | None = None,
    doc_terms: list[str] | None = None,
    require_doc_terms: bool = False,
    filename_templates: str | list[str] | tuple[str, ...] | None = None,
    require_template_match: bool = False,
    required_filename_terms: str | list[str] | tuple[str, ...] | None = None,
    forbidden_filename_terms: str | list[str] | tuple[str, ...] | None = None,
) -> dict:
    filename = file_path.name
    score = base_score
    motivo: list[str] = []
    conflicts: list[str] = []
    doc_terms = doc_terms or []
    evidence = {
        "period_matched": False,
        "period_filename_matched": False,
        "period_from_folder": False,
        "bank_required": bool(doc_bank),
        "bank_matched": False,
        "type_required": bool(doc_type),
        "type_filename_matched": False,
        "type_folder_matched": bool(doc_type and expected_type_folder),
        "doc_terms_required": require_doc_terms,
        "doc_terms_matched": False,
        "doc_terms_found": [],
        "template_required": False,
        "template_matched": False,
        "matched_template": None,
        "custom_required_terms_missing": [],
        "forbidden_terms_found": [],
    }

    if match_period_in_filename(filename, mes, ano):
        score += 30
        motivo.append(f"periodo {mes:02d}/{ano} no nome")
        evidence["period_matched"] = True
        evidence["period_filename_matched"] = True
    elif period_from_folder == (mes, ano):
        score += 20
        motivo.append(f"periodo {mes:02d}/{ano} pela pasta")
        evidence["period_matched"] = True
        evidence["period_from_folder"] = True
    else:
        ano_str = str(ano)
        if ano_str not in filename and any(str(y) in filename for y in range(2020, 2035) if str(y) != ano_str):
            conflicts.append("arquivo de ano diferente")

    if doc_bank and match_bank_in_filename(filename, doc_bank):
        score += 30
        motivo.append(f"banco '{doc_bank}'")
        evidence["bank_matched"] = True
    elif doc_bank:
        other_bank = detect_bank_in_text(filename)
        if other_bank and other_bank != doc_bank:
            conflicts.append(f"banco diferente: '{other_bank}'")

    if doc_type and match_type_in_filename(filename, doc_type):
        score += 20
        motivo.append(f"tipo '{doc_type}'")
        evidence["type_filename_matched"] = True

    file_type = detect_type_in_filename(filename)
    if doc_type and file_type and file_type != doc_type:
        conflicts.append(f"tipo diferente: '{file_type}'")

    if evidence["type_folder_matched"]:
        motivo.append(f"subpasta '{doc_type}'")

    if str(empresa_codigo) in filename:
        score += 10
        motivo.append("codigo da empresa no nome")
        evidence["company_code_matched"] = True
    else:
        evidence["company_code_matched"] = False

    matched_terms = match_document_terms(filename, doc_terms)
    document_term_count = required_document_term_count(doc_terms)
    required_terms = document_term_count if require_doc_terms else 0
    if matched_terms:
        score += 20 + min(len(matched_terms), 3) * 5
        motivo.append("documento '" + ", ".join(matched_terms[:3]) + "'")
    if document_term_count and len(matched_terms) >= document_term_count:
        evidence["doc_terms_matched"] = True
    evidence["doc_terms_found"] = matched_terms

    required_custom_terms = split_aliases(required_filename_terms, [])
    missing_custom_terms = [
        term for term in required_custom_terms
        if not _has_literal_terms(filename, [term])
    ]
    evidence["custom_required_terms_missing"] = missing_custom_terms
    if required_custom_terms and not missing_custom_terms:
        score += 10
        motivo.append("termos obrigatorios personalizados")

    forbidden_terms = split_aliases(forbidden_filename_terms, [])
    forbidden_found = [
        term for term in forbidden_terms
        if _has_literal_terms(filename, [term])
    ]
    evidence["forbidden_terms_found"] = forbidden_found
    if forbidden_found:
        conflicts.append("termo proibido no nome: " + ", ".join(forbidden_found))

    templates = split_lines(filename_templates)
    evidence["template_required"] = bool(require_template_match and templates)
    matched_template = match_filename_templates(filename, templates, evidence) if templates else None
    if matched_template:
        score += 25
        motivo.append("padrao de nomenclatura")
        evidence["template_matched"] = True
        evidence["matched_template"] = matched_template

    return {
        "path": file_path,
        "score": score,
        "motivo": motivo,
        "conflicts": conflicts,
        "evidence": evidence,
        "folder_period": period_from_folder,
    }


def scan_folder(
    folder: Path,
    empresa_codigo: int,
    doc_bank: str | None,
    doc_type: str | None,
    mes: int,
    ano: int,
    base_score: int,
    *,
    expected_type_folder: bool = False,
    period_from_folder: tuple[int, int] | None = None,
    doc_terms: list[str] | None = None,
    require_doc_terms: bool = False,
    filename_templates: str | list[str] | tuple[str, ...] | None = None,
    require_template_match: bool = False,
    required_filename_terms: str | list[str] | tuple[str, ...] | None = None,
    forbidden_filename_terms: str | list[str] | tuple[str, ...] | None = None,
) -> list[dict]:
    candidates = []
    try:
        for entry in folder.iterdir():
            if not entry.is_file():
                continue
            c = score_file(
                entry, empresa_codigo, doc_bank, doc_type, mes, ano, base_score,
                expected_type_folder=expected_type_folder,
                period_from_folder=period_from_folder,
                doc_terms=doc_terms,
                require_doc_terms=require_doc_terms,
                filename_templates=filename_templates,
                require_template_match=require_template_match,
                required_filename_terms=required_filename_terms,
                forbidden_filename_terms=forbidden_filename_terms,
            )
            if (
                require_doc_terms
                and not c["evidence"].get("doc_terms_matched")
            ):
                continue
            if c["score"] >= SCORE_REVIEW:
                candidates.append(c)
    except (PermissionError, OSError):
        pass
    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates


# ── Candidate classification ───────────────────────────────────────────────────

def classify_candidates(candidates: list[dict]) -> tuple[str, dict | None, str]:
    if not candidates:
        return RESULT_NAO_ENCONTRADO, None, "Nenhum candidato encontrado"

    best = candidates[0]

    if best["score"] < SCORE_REVIEW:
        return RESULT_NAO_ENCONTRADO, None, f"Melhor pontuacao insuficiente ({best['score']})"

    if best["conflicts"]:
        return RESULT_REVISAR, best, f"Conflito: {'; '.join(best['conflicts'])}"

    if "evidence" in best:
        evidence = best.get("evidence") or {}
        missing: list[str] = []
        if not evidence.get("period_matched"):
            missing.append("competencia nao identificada no nome do arquivo")
        if evidence.get("bank_required") and not evidence.get("bank_matched"):
            missing.append("banco esperado nao identificado no nome do arquivo")
        if evidence.get("type_required") and not (
            evidence.get("type_filename_matched") or evidence.get("type_folder_matched")
        ):
            missing.append("tipo do documento nao confirmado por nome ou subpasta")
        if evidence.get("doc_terms_required") and not evidence.get("doc_terms_matched"):
            missing.append("nome do documento cadastrado nao confirmado no arquivo")
        if evidence.get("template_required") and not evidence.get("template_matched"):
            missing.append("padrao de nomenclatura nao confirmado")
        custom_missing = evidence.get("custom_required_terms_missing") or []
        if custom_missing:
            missing.append("termos obrigatorios ausentes: " + ", ".join(custom_missing))
        if missing:
            return RESULT_REVISAR, best, "Validacao incompleta: " + "; ".join(missing)

    if len(candidates) > 1 and candidates[1]["score"] >= SCORE_REVIEW:
        diff = best["score"] - candidates[1]["score"]
        if diff < 20:
            return RESULT_REVISAR, best, (
                f"Possivel duplicidade: multiplos candidatos ({best['score']} vs {candidates[1]['score']}): "
                f"{best['path'].name} / {candidates[1]['path'].name}"
            )

    if best["score"] >= SCORE_HIGH:
        motivo = "; ".join(best["motivo"]) if best["motivo"] else f"Pontuacao {best['score']}"
        return RESULT_ALTA_CONFIANCA, best, motivo

    return RESULT_REVISAR, best, f"Pontuacao media ({best['score']}): " + "; ".join(best["motivo"])


# ── Temporal classification ────────────────────────────────────────────────────

def classify_file_period(
    file_period: tuple[int, int],
    target_period: tuple[int, int],
    status_map: dict[tuple[int, int], str | None],
    doc_id: int,
    period_id_by_key: dict[tuple[int, int], int],
) -> str:
    """Classify file_period relative to target_period.

    status_map keys are (doc_id, periodo_id); period_id_by_key maps (mes, ano) → periodo_id.
    """
    file_key = _period_key(*file_period)
    target_key = _period_key(*target_period)

    if file_key == target_key:
        return TEMPORAL_ATUAL

    if file_key > target_key:
        return TEMPORAL_FUTURA

    # File is from an earlier period — check if it's already received
    periodo_id = period_id_by_key.get(file_period)
    if periodo_id is not None:
        status = status_map.get((doc_id, periodo_id))
        if status == "Recebido":
            return TEMPORAL_ANTERIOR_RECEBIDA
        return TEMPORAL_ANTERIOR_PENDENTE

    return TEMPORAL_DIFERENTE


# ── Main service ───────────────────────────────────────────────────────────────

class FileCheckService:
    def __init__(self, empresa_service, documento_service, periodo_service, status_service) -> None:
        self._empresa_service = empresa_service
        self._documento_service = documento_service
        self._periodo_service = periodo_service
        self._status_service = status_service

    # ── Public API ────────────────────────────────────────────────────────────

    def check_period(
        self,
        periodo_id: int,
        empresa_ids: list[int] | None,
        root_dir: Path | None,
        progress_callback: Callable[[str], None] | None = None,
        *,
        mode: str = MODE_CURRENT_ONLY,
        skip_received: bool = True,
        options: dict | None = None,
    ) -> list[dict]:
        options = normalize_file_check_options(options)
        periodo = self._periodo_service.get_periodo(periodo_id)
        if not periodo:
            raise ValueError(f"Periodo {periodo_id} nao encontrado.")

        ano: int = periodo["ano"]
        mes: int = periodo["mes"]
        selected_key = _period_key(mes, ano)

        all_empresas = self._empresa_service.list_empresas(active_only=True)
        if empresa_ids is not None:
            id_set = set(empresa_ids)
            all_empresas = [e for e in all_empresas if e["id"] in id_set]

        # Load all DB periods up to and including selected period
        all_db_periods = self._periodo_service.list_periodos()
        relevant_periods = sorted(
            [p for p in all_db_periods if _period_key(p["mes"], p["ano"]) <= selected_key],
            key=lambda p: _period_key(p["mes"], p["ano"]),
        )
        period_by_key: dict[tuple[int, int], dict] = {
            (p["mes"], p["ano"]): p for p in relevant_periods
        }
        period_id_by_key: dict[tuple[int, int], int] = {
            (p["mes"], p["ano"]): p["id"] for p in relevant_periods
        }
        relevant_period_ids = [p["id"] for p in relevant_periods]

        results: list[dict] = []

        for idx, empresa in enumerate(all_empresas):
            if progress_callback:
                progress_callback(
                    f"Verificando {idx + 1}/{len(all_empresas)}: {empresa['nome_empresa']}"
                )

            documentos = self._documento_service.list_documentos_empresa(empresa["id"])
            checkable_docs = [
                d for d in documentos
                if (
                    is_bank_statement_document(d.get("nome_tipo", ""), d.get("nome_documento", ""))
                    or (
                        options["allow_generic_documents"]
                        and document_match_terms(d.get("nome_tipo", ""), d.get("nome_documento", ""))
                    )
                )
            ]

            if not checkable_docs:
                continue

            # Batch-load status history for all checkable documents in all relevant periods
            doc_ids = [d["id"] for d in checkable_docs]
            status_map: dict[tuple[int, int], str | None] = {}
            if relevant_period_ids:
                status_map = self._status_service.get_document_period_statuses(
                    doc_ids, relevant_period_ids
                )

            for doc in checkable_docs:
                regra = doc.get("regra_ocorrencia")

                if mode == MODE_CURRENT_ONLY:
                    results.extend(
                        self._check_mode_current(
                            empresa, doc, regra, root_dir, mes, ano, periodo_id,
                            period_by_key, period_id_by_key, status_map,
                            options=options,
                            skip_received=skip_received,
                        )
                    )
                else:
                    results.extend(
                        self._check_mode_history(
                            empresa, doc, regra, root_dir, mes, ano,
                            relevant_periods, period_by_key, period_id_by_key, status_map,
                            options=options,
                            skip_received=skip_received,
                        )
                    )

        return results

    def apply_safe_matches(self, results: list[dict]) -> dict:
        """Mark only high-confidence results whose file period matches the target period."""
        safe = [
            r for r in results
            if r["resultado"] == RESULT_ALTA_CONFIANCA
            and r.get("temporal_class") == TEMPORAL_ATUAL
            and r.get("periodo_id") is not None
            and r.get("status_atual") != "Recebido"
        ]
        if not safe:
            return {"selected": 0, "updated": 0, "applied": []}

        # Group by periodo_id for efficient batch updates
        by_period: dict[int, list[int]] = {}
        for r in safe:
            by_period.setdefault(r["periodo_id"], []).append(r["documento_id"])

        total_updated = 0
        for pid, doc_ids in by_period.items():
            outcome = self._status_service.update_status_batch(doc_ids, pid, "Recebido")
            total_updated += outcome.get("updated", 0)

        return {"selected": len(safe), "updated": total_updated, "applied": safe}

    def apply_high_confidence(self, results: list[dict], periodo_id: int) -> dict:
        """Backward-compatible: mark all ALTA_CONFIANCA rows for a single period."""
        high_conf_ids = [r["documento_id"] for r in results if r["resultado"] == RESULT_ALTA_CONFIANCA]
        if not high_conf_ids:
            return {"selected": 0, "updated": 0, "document_ids": []}
        return self._status_service.update_status_batch(high_conf_ids, periodo_id, "Recebido")

    # ── Mode implementations ──────────────────────────────────────────────────

    def _check_mode_current(
        self, empresa, doc, regra, root_dir, mes, ano, periodo_id,
        period_by_key, period_id_by_key, status_map, *, options: dict, skip_received: bool,
    ) -> list[dict]:
        """Mode 1: check only selected period, add timeline alerts."""
        if not is_chargeable_period(regra, mes):
            return []

        current_status = status_map.get((doc["id"], periodo_id))
        if skip_received and current_status == "Recebido":
            return []

        row = self._check_single_period(
            empresa, doc, root_dir,
            target_mes=mes, target_ano=ano, target_period_id=periodo_id,
            current_status=current_status,
            period_by_key=period_by_key,
            period_id_by_key=period_id_by_key,
            status_map=status_map,
            options=options,
        )

        # Add timeline gap alerts
        row["alertas"].extend(
            self._timeline_gap_alerts(doc, regra, mes, ano, period_by_key, period_id_by_key, status_map)
        )
        return [row]

    def _check_mode_history(
        self, empresa, doc, regra, root_dir, selected_mes, selected_ano,
        relevant_periods, period_by_key, period_id_by_key, status_map, *, options: dict, skip_received: bool,
    ) -> list[dict]:
        """Mode 2: check all chargeable pending periods up to selected period."""
        rows: list[dict] = []
        for period in relevant_periods:
            if not is_chargeable_period(regra, period["mes"]):
                continue
            current_status = status_map.get((doc["id"], period["id"]))
            if skip_received and current_status == "Recebido":
                continue
            row = self._check_single_period(
                empresa, doc, root_dir,
                target_mes=period["mes"], target_ano=period["ano"],
                target_period_id=period["id"],
                current_status=current_status,
                period_by_key=period_by_key,
                period_id_by_key=period_id_by_key,
                status_map=status_map,
                options=options,
            )
            rows.append(row)
        return rows

    def _collect_candidates(
        self,
        year_folder: Path,
        empresa_codigo: int,
        doc_bank: str | None,
        doc_type: str | None,
        target_mes: int,
        target_ano: int,
        base_score: int,
        *,
        is_bank_doc: bool,
        doc_terms: list[str],
        options: dict,
    ) -> list[dict]:
        target_period = (target_mes, target_ano)
        collected: dict[Path, dict] = {}
        layout_mode = options["layout_mode"]
        use_folder_period = options["period_source"] == PERIOD_SOURCE_FILENAME_OR_FOLDER
        bank_folder_tokens = split_aliases(options.get("bank_folder_aliases"), EXTRATOS_FOLDER_TOKENS)
        cc_folder_tokens = split_aliases(options.get("cc_folder_aliases"), CC_FOLDER_TOKENS)
        aplicacao_folder_tokens = split_aliases(
            options.get("aplicacao_folder_aliases"), APLICACAO_FOLDER_TOKENS
        )
        require_doc_terms = bool(options.get("require_registered_terms", True)) and not is_bank_doc

        def scan(
            folder: Path,
            score: int,
            *,
            expected_type_folder: bool = False,
            folder_period: tuple[int, int] | None = None,
        ) -> None:
            effective_folder_period = folder_period if use_folder_period else None
            candidates = scan_folder(
                folder,
                empresa_codigo,
                doc_bank if is_bank_doc else None,
                doc_type if is_bank_doc else None,
                target_mes,
                target_ano,
                score,
                expected_type_folder=expected_type_folder,
                period_from_folder=effective_folder_period,
                doc_terms=doc_terms,
                require_doc_terms=require_doc_terms,
                filename_templates=options.get("filename_templates"),
                require_template_match=bool(options.get("require_template_match", False)),
                required_filename_terms=options.get("required_filename_terms"),
                forbidden_filename_terms=options.get("forbidden_filename_terms"),
            )
            for candidate in candidates:
                existing = collected.get(candidate["path"])
                if existing is None or candidate["score"] > existing["score"]:
                    collected[candidate["path"]] = candidate

        def add_bank_layout(
            base_dir: Path,
            score: int,
            folder_period: tuple[int, int] | None = None,
            *,
            include_base_files: bool = True,
            include_month_folders: bool = True,
        ) -> bool:
            extratos_folder, extratos_score, _ = resolve_extratos_folder(
                base_dir, bank_folder_tokens
            )
            if not extratos_folder:
                return False

            extratos_base = score + extratos_score
            if include_base_files:
                scan(extratos_folder, extratos_base, folder_period=folder_period)

            type_folder, type_score, _ = resolve_type_subfolder(
                extratos_folder,
                doc_type,
                cc_tokens=cc_folder_tokens,
                aplicacao_tokens=aplicacao_folder_tokens,
            )
            if type_folder:
                type_base = extratos_base + type_score
                if include_base_files:
                    scan(
                        type_folder,
                        type_base,
                        expected_type_folder=True,
                        folder_period=folder_period,
                    )
                if include_month_folders:
                    month_in_type, month_score, _ = resolve_month_folder(type_folder, target_mes, target_ano)
                    if month_in_type:
                        scan(
                            month_in_type,
                            type_base + month_score,
                            expected_type_folder=True,
                            folder_period=target_period,
                        )

            if include_month_folders:
                month_in_extratos, month_score, _ = resolve_month_folder(
                    extratos_folder, target_mes, target_ano
                )
                if month_in_extratos:
                    month_base = extratos_base + month_score
                    scan(month_in_extratos, month_base, folder_period=target_period)
                    type_in_month, type_in_month_score, _ = resolve_type_subfolder(
                        month_in_extratos,
                        doc_type,
                        cc_tokens=cc_folder_tokens,
                        aplicacao_tokens=aplicacao_folder_tokens,
                    )
                    if type_in_month:
                        scan(
                            type_in_month,
                            month_base + type_in_month_score,
                            expected_type_folder=True,
                            folder_period=target_period,
                        )

            return True

        if is_bank_doc:
            if layout_mode in (LAYOUT_AUTO, LAYOUT_YEAR_DIRECT, LAYOUT_DOCUMENT_FIRST):
                found_bank_layout = add_bank_layout(
                    year_folder,
                    base_score,
                    include_base_files=True,
                    include_month_folders=layout_mode in (LAYOUT_AUTO, LAYOUT_DOCUMENT_FIRST),
                )
                if not found_bank_layout and layout_mode in (LAYOUT_AUTO, LAYOUT_YEAR_DIRECT):
                    scan(year_folder, base_score)

            if layout_mode in (LAYOUT_AUTO, LAYOUT_MONTH_FIRST):
                month_folder, month_score, _ = resolve_month_folder(year_folder, target_mes, target_ano)
                if month_folder:
                    found_month_bank_layout = add_bank_layout(
                        month_folder,
                        base_score + month_score,
                        target_period,
                        include_base_files=True,
                        include_month_folders=False,
                    )
                    if not found_month_bank_layout:
                        scan(month_folder, base_score + month_score, folder_period=target_period)
        else:
            if layout_mode in (LAYOUT_AUTO, LAYOUT_YEAR_DIRECT):
                scan(year_folder, base_score)

            if layout_mode in (LAYOUT_AUTO, LAYOUT_DOCUMENT_FIRST):
                doc_folder, doc_folder_score, _ = resolve_document_folder(year_folder, doc_terms)
                if doc_folder:
                    doc_base = base_score + doc_folder_score
                    scan(doc_folder, doc_base)
                    month_in_doc, month_in_doc_score, _ = resolve_month_folder(
                        doc_folder, target_mes, target_ano
                    )
                    if month_in_doc:
                        scan(
                            month_in_doc,
                            doc_base + month_in_doc_score,
                            folder_period=target_period,
                        )

            if layout_mode in (LAYOUT_AUTO, LAYOUT_MONTH_FIRST):
                month_folder, month_score, _ = resolve_month_folder(year_folder, target_mes, target_ano)
                if month_folder:
                    month_base = base_score + month_score
                    scan(month_folder, month_base, folder_period=target_period)
                    doc_in_month, doc_in_month_score, _ = resolve_document_folder(month_folder, doc_terms)
                    if doc_in_month:
                        scan(
                            doc_in_month,
                            month_base + doc_in_month_score,
                            folder_period=target_period,
                        )

        return sorted(collected.values(), key=lambda c: c["score"], reverse=True)

    # ── Core period check ─────────────────────────────────────────────────────

    def _check_single_period(
        self,
        empresa: dict,
        doc: dict,
        root_dir: Path | None,
        *,
        target_mes: int,
        target_ano: int,
        target_period_id: int,
        current_status: str | None,
        period_by_key: dict,
        period_id_by_key: dict,
        status_map: dict,
        options: dict,
    ) -> dict:
        is_bank_doc = is_bank_statement_document(
            doc.get("nome_tipo", ""), doc.get("nome_documento", "")
        )
        doc_bank = detect_document_bank(doc.get("nome_documento", ""))
        doc_type = detect_document_type(doc.get("nome_documento", ""))
        doc_terms = document_match_terms(doc.get("nome_tipo", ""), doc.get("nome_documento", ""))

        def make(resultado, arquivo, score, motivo, count, temporal=TEMPORAL_NAO_IDENTIFICADA, alertas=None, related=None):
            return self._make_result(
                empresa, doc, resultado, arquivo, score, motivo, count,
                periodo_id=target_period_id,
                periodo_analisado=(target_mes, target_ano),
                status_atual=current_status,
                arquivo_periodo=[],
                temporal_class=temporal,
                alertas=alertas or [],
                related_period_files=related or [],
            )

        if root_dir is None:
            return make(RESULT_ERRO, None, 0, "Pasta raiz nao configurada", 0)

        company_folder, folder_score, folder_note = resolve_company_folder(empresa, root_dir)
        if company_folder is None:
            resultado = RESULT_ERRO if "permissao" in folder_note.lower() else RESULT_NAO_ENCONTRADO
            return make(resultado, None, 0, folder_note, 0)

        year_folder, year_score, year_note = resolve_year_folder(company_folder, target_ano)
        if year_folder is None:
            return make(RESULT_NAO_ENCONTRADO, None, folder_score, year_note, 0)

        base_path_score = folder_score + year_score
        fallback_year = target_ano

        all_candidates = self._collect_candidates(
            year_folder,
            empresa["codigo_empresa"],
            doc_bank,
            doc_type,
            target_mes,
            target_ano,
            base_path_score,
            is_bank_doc=is_bank_doc,
            doc_terms=doc_terms,
            options=options,
        )

        # Partition candidates by detected period
        matching_period: list[dict] = []
        other_period: list[dict] = []
        unknown_period: list[dict] = []

        for cand in all_candidates:
            detected = extract_periods_from_filename(cand["path"].name, fallback_year=fallback_year)
            if not detected and cand.get("folder_period"):
                detected = [cand["folder_period"]]
            cand["_detected_periods"] = detected
            if not detected:
                unknown_period.append(cand)
            elif any(p == (target_mes, target_ano) for p in detected):
                matching_period.append(cand)
            else:
                other_period.append(cand)

        # Build alertas and related_period_files from other-period candidates
        alertas: list[str] = []
        related_period_files: list[dict] = []
        duplicate_files: list[dict] = []
        seen_ignored: set[str] = set()

        for cand in other_period:
            for (m, a) in cand["_detected_periods"]:
                lbl = f"{m:02d}/{a}"
                if lbl not in seen_ignored:
                    seen_ignored.add(lbl)
                    file_key = _period_key(m, a)
                    target_key = _period_key(target_mes, target_ano)
                    direction = "futuro" if file_key > target_key else "anterior"
                    alertas.append(f"Arquivo de mes {direction} ignorado: {lbl}")
                related_period_files.append({
                    "filename": cand["path"].name,
                    "period_label": lbl,
                    "detected_period": (m, a),
                })

        # Classify using partitioned candidates
        if matching_period:
            matching_period.sort(key=lambda c: c["score"], reverse=True)
            resultado, best, motivo = classify_candidates(matching_period)
            duplicate_files = [
                {"filename": c["path"].name, "score": c["score"]}
                for c in matching_period[1:]
                if c["score"] >= SCORE_REVIEW
            ]
            if duplicate_files:
                alertas.append(
                    f"Possivel duplicidade: {len(duplicate_files) + 1} arquivos para "
                    f"{target_mes:02d}/{target_ano}"
                )
            temporal_class = TEMPORAL_ATUAL
            arquivo_periodo = [(target_mes, target_ano)]
        elif unknown_period:
            unknown_period.sort(key=lambda c: c["score"], reverse=True)
            resultado, best, motivo = classify_candidates(unknown_period)
            if resultado == RESULT_ALTA_CONFIANCA:
                resultado = RESULT_REVISAR
                motivo = "Competencia nao identificada no arquivo; " + motivo
            if best is not None:
                alertas.append("Arquivo sem competencia identificada exige revisao")
            temporal_class = TEMPORAL_NAO_IDENTIFICADA
            arquivo_periodo = []
        else:
            resultado = RESULT_NAO_ENCONTRADO
            best = None
            arquivo_periodo = []
            temporal_class = TEMPORAL_NAO_IDENTIFICADA
            if other_period:
                ignored_labels = list(dict.fromkeys(
                    f"{m:02d}/{a}"
                    for cand in other_period
                    for (m, a) in cand["_detected_periods"]
                ))
                motivo = (
                    f"Nenhum arquivo encontrado para {target_mes:02d}/{target_ano}; "
                    f"arquivo(s) de outra competencia ignorado(s): {', '.join(ignored_labels)}"
                )
            else:
                motivo = "Nenhum candidato encontrado"

        return self._make_result(
            empresa, doc, resultado,
            best["path"] if best else None,
            best["score"] if best else 0,
            motivo,
            len(all_candidates),
            periodo_id=target_period_id,
            periodo_analisado=(target_mes, target_ano),
            status_atual=current_status,
            arquivo_periodo=arquivo_periodo,
            temporal_class=temporal_class,
            alertas=alertas,
            related_period_files=related_period_files,
            duplicate_files=duplicate_files,
        )

    def _timeline_gap_alerts(
        self, doc, regra, selected_mes, selected_ano,
        period_by_key, period_id_by_key, status_map,
    ) -> list[str]:
        """For Mode 1: summarize pending/gap periods before the selected period."""
        selected_key = _period_key(selected_mes, selected_ano)
        pending: list[str] = []
        for (mes, ano), period in sorted(period_by_key.items(), key=lambda kv: _period_key(*kv[0])):
            if _period_key(mes, ano) >= selected_key:
                continue
            if not is_chargeable_period(regra, mes):
                continue
            status = status_map.get((doc["id"], period["id"]))
            if status not in (None, "", "Pendente"):
                continue
            pending.append(f"{mes:02d}/{ano}")

        alerts: list[str] = []
        if pending:
            if len(pending) == 1:
                alerts.append(f"Mes anterior pendente sem arquivo: {pending[0]}")
            else:
                alerts.append(f"{len(pending)} meses anteriores pendentes: {', '.join(pending)}")
        return alerts

    # ── Result builder ────────────────────────────────────────────────────────

    @staticmethod
    def _make_result(
        empresa: dict,
        doc: dict,
        resultado: str,
        arquivo: Path | None,
        score: int,
        motivo: str,
        candidatos_count: int,
        *,
        periodo_id: int | None = None,
        periodo_analisado: tuple[int, int] | None = None,
        status_atual: str | None = None,
        arquivo_periodo: list[tuple[int, int]] | None = None,
        temporal_class: str = TEMPORAL_NAO_IDENTIFICADA,
        alertas: list[str] | None = None,
        related_period_files: list[dict] | None = None,
        duplicate_files: list[dict] | None = None,
    ) -> dict:
        return {
            "empresa_id": empresa["id"],
            "empresa_nome": empresa["nome_empresa"],
            "empresa_codigo": empresa["codigo_empresa"],
            "documento_id": doc["id"],
            "documento_nome": doc.get("nome_documento", ""),
            "documento_tipo": doc.get("nome_tipo", ""),
            "regra_ocorrencia": doc.get("regra_ocorrencia", ""),
            "resultado": resultado,
            "arquivo": str(arquivo) if arquivo else None,
            "score": score,
            "motivo": motivo,
            "candidatos_count": candidatos_count,
            "periodo_id": periodo_id,
            "periodo_analisado": periodo_analisado,
            "status_atual": status_atual,
            "arquivo_periodo": arquivo_periodo if arquivo_periodo is not None else [],
            "temporal_class": temporal_class,
            "alertas": alertas if alertas is not None else [],
            "related_period_files": related_period_files if related_period_files is not None else [],
            "duplicate_files": duplicate_files if duplicate_files is not None else [],
        }
