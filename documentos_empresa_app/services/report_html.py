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


GREEN = "#1F8A5B"
BROWN = "#B86E12"
RED = "#A93226"
CHEGOU_FUNDO = "#F1FAF5"
FALTA_FUNDO = "#FFF6EA"
NAO_ACHOU_FUNDO = "#FDF0EE"
FORA = ("Encerrado", "Nao cobrar")


def _ordem_codigo(codigo) -> tuple:
    texto = str(codigo)
    return (0, int(texto), "") if texto.isdigit() else (1, 0, texto.casefold())


def _rotulo(doc: dict, todos: list[dict]) -> str:
    """Nome do documento; quando a empresa tem dois com o mesmo nome, o tipo entre parenteses separa."""
    repetido = sum(1 for d in todos if d["nome_documento"] == doc["nome_documento"]) > 1
    return f"{doc['nome_documento']} ({doc['tipo_documento']})" if repetido else doc["nome_documento"]


def _lista(docs: list[dict], todos: list[dict], cor: str, detalhes: dict | None = None) -> str:
    if not docs:
        return f"<span style='color:{MUTED};'>-</span>"
    linhas = []
    for i, doc in enumerate(docs, start=1):
        linha = f"<span style='color:{cor}; font-weight:600;'>{i}.</span>&nbsp;{_esc(_rotulo(doc, todos))}"
        detalhe = (detalhes or {}).get((doc.get("documento_id"), doc.get("periodo_id")))
        if detalhe:
            linha += f"<br><span style='color:{MUTED}; font-size:8pt;'>&nbsp;&nbsp;&nbsp;&nbsp;{_esc(detalhe)}</span>"
        linhas.append(linha)
    return "<br>".join(linhas)


def _barra(chegou: int, falta: int, altura: int = 7) -> str:
    total = chegou + falta
    if not total:
        return ""
    verde = round(100 * chegou / total)
    celulas = ""
    if verde:
        celulas += f"<td width='{verde}%' bgcolor='{GREEN}' style='background-color:{GREEN};' height='{altura}'></td>"
    if verde < 100:
        celulas += f"<td width='{100 - verde}%' bgcolor='{ORANGE}' style='background-color:{ORANGE};' height='{altura}'></td>"
    return (
        f"<table width='100%' cellspacing='0' cellpadding='0' style='margin-top:4px; font-size:{altura}px;'>"
        f"<tr>{celulas}</tr></table>"
    )


def _resumo_geral(chegou: int, falta: int, period_text: str, sem_marcacao: int = 0) -> str:
    total = chegou + falta
    pct = round(100 * chegou / total) if total else 0
    nota = (
        f"<br><span style='color:{MUTED}; font-size:8.5pt;'>Dos que faltam, {sem_marcacao} ainda estão sem "
        f"marcação (ninguém marcou como recebido nem como pendente). Contam como “ainda não chegou”.</span>"
        if sem_marcacao
        else ""
    )
    return (
        f"<table width='100%' cellspacing='0' cellpadding='10' style='margin-top:10px; border:1px solid {LINE};'><tr>"
        f"<td bgcolor='#FFFFFF' style='background-color:#FFFFFF;'>"
        f"<span style='color:{NAVY}; font-size:14pt; font-weight:600;'>Competência {_esc(period_text)}: "
        f"chegaram {chegou} de {total} documento(s) ({pct}%) &nbsp;·&nbsp; faltam {falta}</span>"
        f"{_barra(chegou, falta, 10)}{nota}"
        f"</td></tr></table>"
    )


def _cabecalho_tabela(colunas: list[tuple[str, str, str]]) -> str:
    """colunas: [(titulo, largura, cor de fundo)]"""
    celulas = []
    for titulo, largura, cor in colunas:
        atributo = f" width='{largura}'" if largura else ""
        celulas.append(
            f"<td bgcolor='{cor}' style='background-color:{cor};'{atributo}>"
            f"<span style='color:#FFFFFF; font-weight:600; font-size:9pt;'>{_esc(titulo)}</span></td>"
        )
    return f"<tr>{''.join(celulas)}</tr>"


def _celula_empresa(codigo, nome, chegou: int, total: int, periodo: str = "") -> str:
    competencia = (
        f"<br><span style='color:{NAVY}; font-size:8pt; font-weight:600;'>Competência {periodo}</span>" if periodo else ""
    )
    return (
        f"<td valign='top' width='22%'><span style='color:{NAVY}; font-weight:600;'>{_esc(codigo)}</span>"
        f"<span style='color:{TEXT}; font-weight:600;'> - {_esc(nome)}</span>{competencia}"
        f"<br><span style='color:{MUTED}; font-size:8pt;'>chegaram {chegou} de {total}</span>"
        f"{_barra(chegou, total - chegou)}</td>"
    )


def _celula(conteudo: str, fundo: str, largura: str = "") -> str:
    atributo = f" width='{largura}'" if largura else ""
    return f"<td valign='top'{atributo} bgcolor='{fundo}' style='background-color:{fundo};'>{conteudo}</td>"


def build_report_html(
    *,
    kind: str,
    rows: list[dict],
    companies_total: int,
    period_text: str,
    company_label: str,
    generated_at: str,
    include_complete: bool = True,
    extra_html: str = "",
    nao_encontrados: dict | None = None,
) -> str:
    """Uma linha por empresa (e competencia), em pagina deitada, so com o que interessa: o que
    chegou, o que ainda nao chegou e o que foi procurado e nao encontrado.
    kind 'pendencias' mostra so o que falta. Documentos 'nao cobrar' e encerrados nao entram.
    nao_encontrados: {(documento_id, periodo_id): detalhe} dos pendentes que o Claude procurou
    e nao achou (ou que vieram errados)."""
    nao_encontrados = nao_encontrados or {}
    grupos: dict[tuple, list[dict]] = {}
    for row in rows:
        if row["status"] in FORA:
            continue
        grupos.setdefault((row["codigo_empresa"], row["nome_empresa"], row["ano"], row["mes"]), []).append(row)
    ordenados = sorted(
        grupos.items(), key=lambda kv: (_ordem_codigo(kv[0][0]), str(kv[0][1]).casefold(), kv[0][2], kv[0][3])
    )

    def ordem_doc(r):
        return (r["tipo_documento"].casefold(), r["nome_documento"].casefold())

    linhas = []
    completas: set = set()
    com_falta: set = set()
    chegou_total = falta_total = nao_achou_total = sem_marcacao_total = 0
    for (codigo, nome, ano, mes), docs in ordenados:
        chegou = sorted((d for d in docs if d["status"] == "Recebido"), key=ordem_doc)
        pendentes = sorted((d for d in docs if d["status"] in ("Pendente", "")), key=ordem_doc)
        nao_achou = [d for d in pendentes if (d.get("documento_id"), d.get("periodo_id")) in nao_encontrados]
        falta = [d for d in pendentes if d not in nao_achou]
        chegou_total += len(chegou)
        falta_total += len(pendentes)
        nao_achou_total += len(nao_achou)
        sem_marcacao_total += sum(1 for d in pendentes if d["status"] == "")
        (com_falta if pendentes else completas).add(codigo)
        linhas.append((codigo, nome, ano, mes, docs, chegou, falta, nao_achou))
    completas -= com_falta

    if kind == "pendencias":
        title = "Relatório de pendências"
        visiveis = [linha for linha in linhas if linha[6] or linha[7]]
    else:
        title = "Situação da documentação"
        visiveis = linhas if include_complete else [linha for linha in linhas if linha[6] or linha[7]]

    subtitle = f"Competência: {_esc(period_text)} &nbsp;|&nbsp; Empresas: {_esc(company_label)}"
    parts = [
        f"<html><body style=\"font-family: 'Segoe UI', Arial, sans-serif; color:{TEXT}; font-size:9.5pt;\">",
        _header(title, subtitle, generated_at),
    ]
    if kind != "pendencias":
        parts.append(_resumo_geral(chegou_total, falta_total, period_text, sem_marcacao_total))
    parts.append(
        _cards(
            [
                ("empresa(s)", len(linhas) if kind != "pendencias" else len(com_falta), "#FFFFFF", NAVY),
                ("documento(s) chegaram", chegou_total, STATUS_STYLE["Recebido"][0], STATUS_STYLE["Recebido"][1]),
                ("documento(s) ainda não chegaram", falta_total - nao_achou_total, STATUS_STYLE["Pendente"][0], STATUS_STYLE["Pendente"][1]),
                ("procurado(s) e não encontrado(s)", nao_achou_total, "#FBE3E0", RED),
            ]
        )
    )

    if not visiveis:
        parts.append(
            f"<table width='100%' cellspacing='0' cellpadding='10' style='margin-top:8px;'><tr>"
            f"<td bgcolor='#FFFFFF' style='background-color:#FFFFFF; border:1px solid {LINE};' align='center'>"
            f"<span style='color:{MUTED};'>Nenhuma empresa para mostrar no filtro escolhido.</span></td></tr></table>"
        )
    else:
        colunas = [("Empresa", "22%", NAVY)]
        if kind != "pendencias":
            colunas.append(("Chegou", "26%", GREEN))
        colunas += [("Ainda não chegou", "", BROWN), ("Procurado e não encontrado", "26%", RED)]
        tabela = [
            f"<table width='100%' cellspacing='0' cellpadding='6' "
            f"style='margin-top:6px; border-collapse:collapse; border:1px solid {LINE};'>",
            _cabecalho_tabela(colunas),
        ]
        for index, (codigo, nome, ano, mes, docs, chegou, falta, nao_achou) in enumerate(visiveis):
            fundo = "#FFFFFF" if index % 2 == 0 else "#F7F9FC"
            periodo = f"{mes:02d}/{ano}"  # sempre: deixa claro de que mes e cada documento
            celulas = [_celula_empresa(codigo, nome, len(chegou), len(docs), periodo)]
            if kind != "pendencias":
                celulas.append(_celula(_lista(chegou, docs, GREEN), CHEGOU_FUNDO if chegou else fundo))
            celulas.append(_celula(_lista(falta, docs, BROWN), FALTA_FUNDO if falta else fundo))
            celulas.append(_celula(_lista(nao_achou, docs, RED, nao_encontrados), NAO_ACHOU_FUNDO if nao_achou else fundo))
            tabela.append(f"<tr bgcolor='{fundo}' style='background-color:{fundo};'>{''.join(celulas)}</tr>")
        tabela.append("</table>")
        parts.append("".join(tabela))

    if kind != "pendencias" and len(visiveis) < len(linhas):
        parts.append(
            f"<p style='margin-top:8px; color:{MUTED};'>{len(completas)} empresa(s) em que já chegou tudo não foram "
            f"listadas (marque a opção para listar também).</p>"
        )
    if extra_html:
        parts.append(extra_html)
    parts.append("</body></html>")
    return "".join(parts)
