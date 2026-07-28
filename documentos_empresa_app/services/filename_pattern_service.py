from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from documentos_empresa_app.services.file_check_service import (
    bank_display_label,
    extract_periods_from_filename,
    match_bank_in_filename,
    match_type_in_filename,
)

# Apenas formatos numericos de competencia (MM-AAAA, AAAA-MM, MMAAAA, AAAAMM, com
# separadores / - . _ espaco). Nomes de mes por extenso ficam fora do escopo do clone de
# nome: nao ha como reescrever "Marco"/"marco"/"MARCO" com seguranca sem arriscar um nome
# errado, entao esses arquivos simplesmente nao viram candidatos utilizaveis aqui.
_NUMERIC_PERIOD_PATTERNS = [
    re.compile(r"(?P<mes>0[1-9]|1[0-2])[/\-._ ](?P<ano>20[2-9][0-9])"),
    re.compile(r"(?P<ano>20[2-9][0-9])[/\-._ ](?P<mes>0[1-9]|1[0-2])"),
    re.compile(r"(?<!\d)(?P<mes>0[1-9]|1[0-2])(?P<ano>20[2-9][0-9])(?!\d)"),
    re.compile(r"(?<!\d)(?P<ano>20[2-9][0-9])(?P<mes>0[1-9]|1[0-2])(?!\d)"),
]


@dataclass(slots=True)
class InferredFilename:
    new_filename: str
    based_on: Path
    old_period_text: str
    new_period_text: str


def _period_key(mes: int, ano: int) -> int:
    return ano * 100 + mes


def find_period_span(filename: str, mes: int, ano: int) -> tuple[int, int] | None:
    """Localiza o span (start, end) da competencia mes/ano em `filename`. Opera direto no
    texto original (sem normalizar acento/maiuscula) porque os separadores numericos sao
    sempre ASCII - normalizar (NFD) poderia desalinhar indices se houver acento antes do
    trecho da data."""
    mes_str = f"{mes:02d}"
    ano_str = str(ano)
    for pattern in _NUMERIC_PERIOD_PATTERNS:
        for match in pattern.finditer(filename):
            if match.group("mes") == mes_str and match.group("ano") == ano_str:
                return match.span()
    return None


def _format_like(old_period_text: str, mes: int, ano: int) -> str:
    """Reescreve mes/ano dentro de old_period_text preservando separador/ordem originais."""
    mes_str = f"{mes:02d}"
    ano_str = str(ano)
    for pattern in _NUMERIC_PERIOD_PATTERNS:
        match = pattern.fullmatch(old_period_text)
        if not match:
            continue
        replacements = sorted(
            [("mes", match.span("mes"), mes_str), ("ano", match.span("ano"), ano_str)],
            key=lambda item: item[1][0],
            reverse=True,
        )
        rewritten = old_period_text
        for _name, (start, end), value in replacements:
            rewritten = rewritten[:start] + value + rewritten[end:]
        return rewritten
    return f"{mes_str}-{ano_str}"


def _gather_usable_siblings(
    destination_dir: Path,
    *,
    bank_key: str | None = None,
    doc_type: str | None = None,
) -> list[tuple[Path, tuple[int, int], tuple[int, int], str]]:
    try:
        candidates = [entry for entry in destination_dir.iterdir() if entry.is_file()]
    except (OSError, FileNotFoundError):
        return []
    if not candidates:
        return []

    if bank_key:
        narrowed = [entry for entry in candidates if match_bank_in_filename(entry.name, bank_key)]
        if narrowed:
            candidates = narrowed
    if doc_type:
        narrowed = [entry for entry in candidates if match_type_in_filename(entry.name, doc_type)]
        if narrowed:
            candidates = narrowed

    usable: list[tuple[Path, tuple[int, int], tuple[int, int], str]] = []
    for path in candidates:
        detected_periods = extract_periods_from_filename(path.name)
        if len(detected_periods) != 1:
            continue
        detected_mes, detected_ano = detected_periods[0]
        span = find_period_span(path.name, detected_mes, detected_ano)
        if span is None:
            continue
        template = path.name[: span[0]] + "\0" + path.name[span[1] :]
        usable.append((path, (detected_mes, detected_ano), span, template))

    return usable


def has_conflicting_naming_templates(
    destination_dir: Path,
    *,
    bank_key: str | None = None,
    doc_type: str | None = None,
) -> bool:
    """True somente quando ha arquivos-irmaos usaveis com mais de um padrao de nome
    distinto (ambiguidade real - inseguro adivinhar). False para pasta vazia/inexistente
    ou sem nenhum irmao com competencia numerica unica detectavel - nesses casos e seguro
    o chamador sintetizar um nome padrao em vez de perguntar."""
    usable = _gather_usable_siblings(destination_dir, bank_key=bank_key, doc_type=doc_type)
    templates = {item[3] for item in usable}
    return len(templates) > 1


def synthesize_default_filename(
    mes: int,
    ano: int,
    *,
    bank_key: str | None = None,
    doc_type: str | None = None,
    original_filename: str | None = None,
) -> str:
    """Monta um nome de arquivo padrao quando nao ha nenhum irmao para copiar o nome -
    usado apenas quando `has_conflicting_naming_templates` for False."""
    parts = [bank_display_label(bank_key) if bank_key else "Documento"]
    if doc_type:
        parts.append("CC" if doc_type == "cc" else "Aplicacao")
    parts.append(f"{mes:02d}-{ano}")
    suffix = Path(original_filename).suffix if original_filename else ""
    return " ".join(parts) + suffix


def infer_filename_from_siblings(
    destination_dir: Path,
    mes: int,
    ano: int,
    *,
    bank_key: str | None = None,
    doc_type: str | None = None,
) -> InferredFilename | None:
    usable = _gather_usable_siblings(destination_dir, bank_key=bank_key, doc_type=doc_type)
    if not usable:
        return None

    templates = {item[3] for item in usable}
    if len(templates) > 1:
        return None

    usable.sort(key=lambda item: _period_key(*item[1]), reverse=True)
    based_on, _detected_period, (start, end), _template = usable[0]

    old_period_text = based_on.name[start:end]
    new_period_text = _format_like(old_period_text, mes, ano)
    new_filename = based_on.name[:start] + new_period_text + based_on.name[end:]

    return InferredFilename(
        new_filename=new_filename,
        based_on=based_on,
        old_period_text=old_period_text,
        new_period_text=new_period_text,
    )
