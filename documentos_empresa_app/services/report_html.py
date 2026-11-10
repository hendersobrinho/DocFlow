"""Relatorios do DocFlow em HTML (para imprimir ou salvar em PDF), na identidade visual do sistema:
cabecalho navy com o simbolo, filete ciano, laranja para o que falta e verde para o que chegou.

So usa o que o QTextDocument do Qt entende (tabelas, cor de fundo de celula, spans)."""

from __future__ import annotations

import base64
from html import escape
import io

try:
    from PIL import Image
except ImportError:  # pragma: no cover - depende do ambiente local
    Image = None

from documentos_empresa_app.utils.resources import get_icons_directory

NAVY = "#203461"
NAVY_DARK = "#16254A"
CYAN = "#4BBDCD"
ORANGE = "#F9B259"
MIST = "#F2F5FA"  # fundo da pagina (Nevoa)
LINE = "#DCE3EE"
TEXT = "#1B2335"
MUTED = "#5E6B82"
ON_NAVY = "#C9D3EA"

# status -> (fundo, texto, rotulo)
STATUS_STYLE = {
    "Recebido": ("#DDF3E8", "#17694A", "Recebido"),
    "Pendente": ("#FDEBD3", "#8A4E0B", "Pendente"),
    "Nao cobrar": ("#E8ECF4", "#4D5A73", "Não cobrar"),
    "Encerrado": ("#E3E6EC", "#4F5868", "Encerrado"),
}
STATUS_ORDER = {"Pendente": 0, "Recebido": 1, "Encerrado": 2, "Nao cobrar": 3}

PAGE_BACKGROUND = MIST
FOOTER_TEXT = "DocFlow"

_logo_cache: str | None = None


def _logo_data_uri(size: int = 96) -> str:
    """Simbolo do DocFlow embutido no HTML (vazio se nao der para carregar)."""
    global _logo_cache
    if _logo_cache is not None:
        return _logo_cache
    uri = ""
    if Image is not None:
        try:
            path = get_icons_directory() / "icon.png"
            if path.exists():
                imagem = Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
                buffer = io.BytesIO()
                imagem.save(buffer, "PNG")
                uri = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
        except Exception:  # noqa: BLE001 - sem logo o relatorio sai igual
            uri = ""
    _logo_cache = uri
    return uri


def _esc(value) -> str:
    return escape(str(value))


def _header(title: str, subtitle: str, generated_at: str) -> str:
    logo = _logo_data_uri()
    logo_html = f"<img src='{logo}' width='46' height='46'>" if logo else ""
    return (
        f"<table width='100%' cellspacing='0' cellpadding='9'><tr>"
        f"<td bgcolor='{NAVY}' style='background-color:{NAVY};' width='70' align='center' valign='middle'>{logo_html}</td>"
        f"<td bgcolor='{NAVY}' style='background-color:{NAVY};' valign='middle'>"
        f"<span style='color:#FFFFFF; font-size:19pt; font-weight:600;'>{_esc(title)}</span><br>"
        f"<span style='color:{ON_NAVY}; font-size:9.5pt;'>{subtitle}</span></td>"
        f"<td bgcolor='{NAVY}' style='background-color:{NAVY};' align='right' valign='middle'>"
        f"<span style='color:#FFFFFF; font-size:11pt; font-weight:600;'>DocFlow</span><br>"
        f"<span style='color:{ON_NAVY}; font-size:9pt;'>Gerado em {_esc(generated_at)}&nbsp;&nbsp;</span></td>"
        f"</tr></table>"
        f"<table width='100%' cellspacing='0' cellpadding='0'><tr>"
        f"<td bgcolor='{CYAN}' style='background-color:{CYAN};' height='4'></td></tr></table>"
    )


def _cards(items: list[tuple[str, int, str, str]]) -> str:
    """items: [(rotulo, numero, fundo, cor do texto)]"""
    largura = int(100 / max(len(items), 1))
    cells = "".join(
        f"<td width='{largura}%' bgcolor='{fundo}' style='background-color:{fundo};' align='center'>"
        f"<span style='color:{cor}; font-size:20pt; font-weight:600;'>{numero}</span><br>"
        f"<span style='color:{cor}; font-size:8.5pt;'>{_esc(rotulo)}</span></td>"
        for rotulo, numero, fundo, cor in items
    )
    return f"<table width='100%' cellspacing='8' cellpadding='7'><tr>{cells}</tr></table>"


def _section(title: str, color: str) -> str:
    return (
        f"<table width='100%' cellspacing='0' cellpadding='0' style='margin-top:10px;'><tr>"
        f"<td width='6' bgcolor='{color}' style='background-color:{color};'></td>"
        f"<td style='padding-left:8px;'><span style='color:{NAVY}; font-size:13pt; font-weight:600;'>{_esc(title)}</span></td>"
        f"</tr></table>"
    )


def _chip(status: str) -> str:
    fundo, cor, rotulo = STATUS_STYLE.get(status, ("#E8ECF4", "#4D5A73", status or "-"))
    return (
        f"<td bgcolor='{fundo}' style='background-color:{fundo};' align='center' width='15%'>"
        f"<span style='color:{cor}; font-weight:600; font-size:9pt;'>{_esc(rotulo)}</span></td>"
    )


def _company_block(codigo, nome, rows: list[dict], multiple_periods: bool) -> str:
    received = sum(1 for r in rows if r["status"] == "Recebido")
    pending = sum(1 for r in rows if r["status"] == "Pendente")
    if pending:
        resumo = f"{pending} pendente(s)"
        resumo_fundo, resumo_cor = STATUS_STYLE["Pendente"][0], STATUS_STYLE["Pendente"][1]
    else:
        resumo = "Tudo em dia"
        resumo_fundo, resumo_cor = STATUS_STYLE["Recebido"][0], STATUS_STYLE["Recebido"][1]
    colunas = 4 if multiple_periods else 3
    parts = [
        f"<table width='100%' cellspacing='0' cellpadding='5' style='margin-top:10px; border-collapse:collapse; border:1px solid {LINE};'>",
        f"<tr><td colspan='{colunas - 1}' bgcolor='{NAVY_DARK}' style='background-color:{NAVY_DARK};'>"
        f"<span style='color:#FFFFFF; font-weight:600; font-size:10.5pt;'>{_esc(codigo)} - {_esc(nome)}</span>"
        f"<span style='color:{ON_NAVY}; font-size:8.5pt;'>&nbsp;&nbsp;{received} de {len(rows)} recebido(s)</span></td>"
        f"<td bgcolor='{resumo_fundo}' style='background-color:{resumo_fundo};' align='center'>"
        f"<span style='color:{resumo_cor}; font-weight:600; font-size:9pt;'>{_esc(resumo)}</span></td></tr>",
    ]
    ordered = sorted(
        rows,
        key=lambda r: (
            r["ano"], r["mes"], STATUS_ORDER.get(r["status"], 9), r["tipo_documento"].casefold(), r["nome_documento"].casefold()
        ),
    )
    for index, row in enumerate(ordered):
        fundo = "#FFFFFF" if index % 2 == 0 else "#F7F9FC"
        periodo = f"<td width='13%'>{row['mes']:02d}/{row['ano']}</td>" if multiple_periods else ""
        parts.append(
            f"<tr bgcolor='{fundo}' style='background-color:{fundo};'>{periodo}"
            f"<td width='30%'><span style='color:{MUTED};'>{_esc(row['tipo_documento'])}</span></td>"
            f"<td><span style='color:{TEXT};'>{_esc(row['nome_documento'])}</span></td>"
            f"{_chip(row['status'])}</tr>"
        )
    parts.append("</table>")
    return "".join(parts)


def build_report_html(
    *,
    kind: str,
    rows: list[dict],
    companies_total: int,
    period_text: str,
    company_label: str,
    generated_at: str,
    include_complete: bool = True,
) -> str:
    """kind: 'pendencias' (so o que falta) ou 'situacao' (tudo: o que chegou e o que falta)."""
    by_company: dict[tuple, list[dict]] = {}
    for row in rows:
        by_company.setdefault((row["codigo_empresa"], row["nome_empresa"]), []).append(row)

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    with_pending = {key for key, items in by_company.items() if any(r["status"] == "Pendente" for r in items)}
    complete = [key for key in by_company if key not in with_pending]

    title = "Relatório de pendências" if kind == "pendencias" else "Situação da documentação"
    subtitle = f"Competência: {_esc(period_text)} &nbsp;|&nbsp; Empresas: {_esc(company_label)}"
    multiple_periods = len({(r["ano"], r["mes"]) for r in rows}) > 1

    parts = [
        f"<html><body style=\"font-family: 'Segoe UI', Arial, sans-serif; color:{TEXT}; font-size:9.5pt;\">",
        _header(title, subtitle, generated_at),
    ]
    if kind == "pendencias":
        parts.append(
            _cards(
                [
                    ("documento(s) pendente(s)", len(rows), STATUS_STYLE["Pendente"][0], STATUS_STYLE["Pendente"][1]),
                    ("empresa(s) com pendência", len(with_pending), "#FFFFFF", NAVY),
                    ("empresa(s) no relatório", companies_total, "#FFFFFF", NAVY),
                ]
            )
        )
    else:
        outros = counts.get("Encerrado", 0) + counts.get("Nao cobrar", 0)
        parts.append(
            _cards(
                [
                    ("recebido(s)", counts.get("Recebido", 0), STATUS_STYLE["Recebido"][0], STATUS_STYLE["Recebido"][1]),
                    ("pendente(s)", counts.get("Pendente", 0), STATUS_STYLE["Pendente"][0], STATUS_STYLE["Pendente"][1]),
                    ("encerrado(s) / não cobrar", outros, STATUS_STYLE["Nao cobrar"][0], STATUS_STYLE["Nao cobrar"][1]),
                    ("empresa(s) em dia", len(complete), "#FFFFFF", NAVY),
                    ("empresa(s) com pendência", len(with_pending), "#FFFFFF", NAVY),
                ]
            )
        )

    ordered_pending = sorted(with_pending, key=lambda k: (int(k[0]) if str(k[0]).isdigit() else 0, str(k[1]).casefold()))
    if ordered_pending:
        parts.append(_section(f"Faltando documento ({len(ordered_pending)} empresa(s))", ORANGE))
        for key in ordered_pending:
            parts.append(_company_block(key[0], key[1], by_company[key], multiple_periods))

    if kind == "situacao" and include_complete and complete:
        ordered_complete = sorted(complete, key=lambda k: (int(k[0]) if str(k[0]).isdigit() else 0, str(k[1]).casefold()))
        parts.append(_section(f"Em dia ({len(ordered_complete)} empresa(s))", "#1F8A5B"))
        for key in ordered_complete:
            parts.append(_company_block(key[0], key[1], by_company[key], multiple_periods))
    elif kind == "situacao" and complete:
        parts.append(
            f"<p style='margin-top:12px; color:{MUTED};'>{len(complete)} empresa(s) em dia, sem pendência "
            f"(não listadas neste relatório).</p>"
        )

    parts.append("</body></html>")
    return "".join(parts)
