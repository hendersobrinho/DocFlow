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
FALTANDO = ("Pendente", "")


def _ordem_codigo(codigo) -> tuple:
    texto = str(codigo)
    return (0, int(texto), "") if texto.isdigit() else (1, 0, texto.casefold())


def _ordem_doc(doc: dict) -> tuple:
    return (doc["tipo_documento"].casefold(), doc["nome_documento"].casefold())


def _rotulo(doc: dict, todos: list[dict]) -> str:
    """Nome do documento; quando a empresa tem dois documentos com o mesmo nome, o tipo entre
    parenteses separa um do outro."""
    mesmos = {d["documento_id"] for d in todos if d["nome_documento"] == doc["nome_documento"]}
    return f"{doc['nome_documento']} ({doc['tipo_documento']})" if len(mesmos) > 1 else doc["nome_documento"]


def _lista(docs: list[dict], todos: list[dict], cor: str) -> str:
    """Documentos separados por competencia (a mais recente primeiro), com o mes em cima de cada grupo."""
    if not docs:
        return f"<span style='color:{MUTED};'>-</span>"
    por_mes: dict[tuple[int, int], list[dict]] = {}
    for doc in docs:
        por_mes.setdefault((doc["ano"], doc["mes"]), []).append(doc)
    blocos = []
    for ano, mes in sorted(por_mes, reverse=True):
        linhas = [f"<span style='color:{NAVY}; font-size:8pt; font-weight:600;'>{mes:02d}/{ano}</span>"]
        for i, doc in enumerate(sorted(por_mes[(ano, mes)], key=_ordem_doc), start=1):
            linhas.append(f"<span style='color:{cor}; font-weight:600;'>{i}.</span>&nbsp;{_esc(_rotulo(doc, todos))}")
        blocos.append("<br>".join(linhas))
    return "<br><br>".join(blocos)


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


def _resumo_geral(chegou: int, falta: int, competencia: str, anteriores: int) -> str:
    total = chegou + falta
    pct = round(100 * chegou / total) if total else 0
    nota = (
        f"<br><span style='color:{MUTED}; font-size:8.5pt;'>Também aparecem {anteriores} documento(s) "
        f"pendente(s) de meses anteriores, cada um com a sua competência.</span>"
        if anteriores
        else ""
    )
    return (
        f"<table width='100%' cellspacing='0' cellpadding='10' style='margin-top:10px; border:1px solid {LINE};'><tr>"
        f"<td bgcolor='#FFFFFF' style='background-color:#FFFFFF;'>"
        f"<span style='color:{NAVY}; font-size:14pt; font-weight:600;'>Competência {_esc(competencia)}: "
        f"chegaram {chegou} de {total} documento(s) ({pct}%) &nbsp;·&nbsp; faltam {falta}</span>"
        f"{_barra(chegou, falta, 10)}{nota}"
        f"</td></tr></table>"
    )


def _legenda() -> str:
    return (
        f"<p style='margin-top:4px; color:{MUTED}; font-size:8.5pt;'>"
        f"<b style='color:{BROWN};'>Ainda não chegou</b>: a empresa já mandou documento e falta o resto. "
        f"&nbsp;&nbsp;<b style='color:{RED};'>Procurado e não encontrado</b>: não chegou nenhum documento da "
        f"empresa no mês.</p>"
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


def _celula_empresa(codigo, nome, chegou: int, total: int) -> str:
    return (
        f"<td valign='top' width='22%'><span style='color:{NAVY}; font-weight:600;'>{_esc(codigo)}</span>"
        f"<span style='color:{TEXT}; font-weight:600;'> - {_esc(nome)}</span>"
        f"<br><span style='color:{MUTED}; font-size:8pt;'>chegaram {chegou} de {total} no mês</span>"
        f"{_barra(chegou, total - chegou)}</td>"
    )


def _celula(conteudo: str, fundo: str, largura: str = "") -> str:
    atributo = f" width='{largura}'" if largura else ""
    return f"<td valign='top'{atributo} bgcolor='{fundo}' style='background-color:{fundo};'>{conteudo}</td>"


def build_report_html(
    *,
    kind: str,
    rows: list[dict],
    competencia: str,
    company_label: str,
    generated_at: str,
    pendentes_anteriores: list[dict] | None = None,
    include_complete: bool = True,
    extra_html: str = "",
) -> str:
    """Relatorio da competencia, uma linha por empresa, so com o que interessa:
    - Chegou: o que chegou no mes;
    - Ainda nao chegou: a empresa ja mandou alguma coisa no mes e falta o resto;
    - Procurado e nao encontrado: nao chegou nenhum documento da empresa no mes.
    O que falta inclui o que ficou Pendente de meses anteriores; cada documento aparece debaixo
    da sua competencia. kind 'pendencias' mostra so o que falta. 'Nao cobrar' e encerrados nao entram.
    rows: as linhas da competencia (com as sem marcacao); pendentes_anteriores: os Pendente de antes."""
    empresas: dict = {}

    def empresa(row):
        return empresas.setdefault(
            row["empresa_id"],
            {"codigo": row["codigo_empresa"], "nome": row["nome_empresa"], "mes": [], "anteriores": []},
        )

    for row in rows:
        if row["status"] not in FORA:
            empresa(row)["mes"].append(row)
    for row in pendentes_anteriores or []:
        if row["status"] == "Pendente":
            empresa(row)["anteriores"].append(row)

    linhas = []
    chegou_total = falta_mes_total = anteriores_total = ainda_total = nao_achou_total = 0
    for dados in sorted(empresas.values(), key=lambda e: (_ordem_codigo(e["codigo"]), str(e["nome"]).casefold())):
        chegou = [d for d in dados["mes"] if d["status"] == "Recebido"]
        falta_mes = [d for d in dados["mes"] if d["status"] in FALTANDO]
        faltando = falta_mes + dados["anteriores"]
        ainda, nao_achou = (faltando, []) if chegou else ([], faltando)
        chegou_total += len(chegou)
        falta_mes_total += len(falta_mes)
        anteriores_total += len(dados["anteriores"])
        ainda_total += len(ainda)
        nao_achou_total += len(nao_achou)
        linhas.append((dados, chegou, falta_mes, ainda, nao_achou))

    if kind == "pendencias":
        title = "Relatório de pendências"
        visiveis = [linha for linha in linhas if linha[3] or linha[4]]
    else:
        title = "Situação da documentação"
        visiveis = linhas if include_complete else [linha for linha in linhas if linha[3] or linha[4]]
    completas = sum(1 for linha in linhas if not (linha[3] or linha[4]))

    subtitle = f"Competência: {_esc(competencia)} &nbsp;|&nbsp; Empresas: {_esc(company_label)}"
    parts = [
        f"<html><body style=\"font-family: 'Segoe UI', Arial, sans-serif; color:{TEXT}; font-size:9.5pt;\">",
        _header(title, subtitle, generated_at),
    ]
    if kind != "pendencias":
        parts.append(_resumo_geral(chegou_total, falta_mes_total, competencia, anteriores_total))
    parts.append(
        _cards(
            [
                ("empresa(s)", len(visiveis), "#FFFFFF", NAVY),
                ("documento(s) chegaram", chegou_total, STATUS_STYLE["Recebido"][0], STATUS_STYLE["Recebido"][1]),
                ("documento(s) ainda não chegaram", ainda_total, STATUS_STYLE["Pendente"][0], STATUS_STYLE["Pendente"][1]),
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
        parts.append(_legenda())
        colunas = [("Empresa", "22%", NAVY)]
        if kind != "pendencias":
            colunas.append(("Chegou", "26%", GREEN))
        colunas += [("Ainda não chegou", "", BROWN), ("Procurado e não encontrado", "26%", RED)]
        tabela = [
            f"<table width='100%' cellspacing='0' cellpadding='6' "
            f"style='margin-top:2px; border-collapse:collapse; border:1px solid {LINE};'>",
            _cabecalho_tabela(colunas),
        ]
        for index, (dados, chegou, falta_mes, ainda, nao_achou) in enumerate(visiveis):
            fundo = "#FFFFFF" if index % 2 == 0 else "#F7F9FC"
            todos = dados["mes"] + dados["anteriores"]
            celulas = [_celula_empresa(dados["codigo"], dados["nome"], len(chegou), len(chegou) + len(falta_mes))]
            if kind != "pendencias":
                celulas.append(_celula(_lista(chegou, todos, GREEN), CHEGOU_FUNDO if chegou else fundo))
            celulas.append(_celula(_lista(ainda, todos, BROWN), FALTA_FUNDO if ainda else fundo))
            celulas.append(_celula(_lista(nao_achou, todos, RED), NAO_ACHOU_FUNDO if nao_achou else fundo))
            tabela.append(f"<tr bgcolor='{fundo}' style='background-color:{fundo};'>{''.join(celulas)}</tr>")
        tabela.append("</table>")
        parts.append("".join(tabela))

    if kind != "pendencias" and len(visiveis) < len(linhas):
        parts.append(
            f"<p style='margin-top:8px; color:{MUTED};'>{completas} empresa(s) em que já chegou tudo não foram "
            f"listadas (marque a opção para listar também).</p>"
        )
    if extra_html:
        parts.append(extra_html)
    parts.append("</body></html>")
    return "".join(parts)
