"""Pecas visuais do acompanhamento de cobranca, usadas em Cobrancas, Precisa de atencao e
na Ficha: cores e rotulos das acoes/situacoes, barra de filtros e o relatorio de uma
verificacao."""

from __future__ import annotations

from html import escape
from pathlib import Path
from urllib.parse import quote, unquote

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QMessageBox, QTextBrowser, QWidget

from documentos_empresa_app.qt_ui.theme import tokens
from documentos_empresa_app.qt_ui.widgets.common import make_button
from documentos_empresa_app.services.cobranca_service import (
    ACAO_LABELS,
    RESULTADO_LABELS,
    SITUACAO_LABELS,
    motivo_label,
)
from documentos_empresa_app.utils.common import ValidationError, format_utc_timestamp
from documentos_empresa_app.utils.helpers import open_file_in_default_app

LINK_ABRIR = "docflow-abrir:"
LINK_PASTA = "docflow-pasta:"


# Arquivos baixados ----------------------------------------------------------------


def open_document(parent: QWidget, arquivo: str | None) -> None:
    """Abre o arquivo baixado no programa padrao (PDF, planilha...)."""
    if not arquivo:
        QMessageBox.information(
            parent, "Documento", "Nenhum arquivo foi anotado para este documento. Use Abrir pasta para procurar."
        )
        return
    try:
        open_file_in_default_app(arquivo)
    except ValidationError:
        QMessageBox.warning(
            parent,
            "Documento",
            f"O arquivo não está mais neste lugar:\n{arquivo}\n\nPode ter sido movido ou apagado. "
            "Use Abrir pasta para procurar.",
        )


def folder_for(arquivo: str | None, pasta_empresa: str | None = None) -> Path | None:
    """Pasta do arquivo baixado; sem ele (ou se sumiu), a pasta da empresa."""
    for candidato in (Path(arquivo).expanduser().parent if arquivo else None, pasta_empresa and Path(pasta_empresa).expanduser()):
        if candidato and candidato.is_dir():
            return candidato
    return None


def open_folder(parent: QWidget, arquivo: str | None, pasta_empresa: str | None = None) -> None:
    pasta = folder_for(arquivo, pasta_empresa)
    if pasta is None:
        QMessageBox.information(
            parent,
            "Pasta",
            "Não há pasta anotada para este documento nem para a empresa. A pasta da empresa é "
            "definida em Empresas > Mais ações.",
        )
        return
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(pasta)))


def file_links_html(arquivo: str | None) -> str:
    """Links "abrir documento | abrir pasta" para colocar ao lado de um item."""
    if not arquivo:
        return ""
    alvo = quote(arquivo)
    nome = escape(Path(arquivo).name)
    return (
        f' <span style="white-space:nowrap;">[{nome}: <a href="{LINK_ABRIR}{alvo}">abrir documento</a>'
        f' | <a href="{LINK_PASTA}{alvo}">abrir pasta</a>]</span>'
    )


class DocLinkBrowser(QTextBrowser):
    """QTextBrowser que trata os links de arquivo dos relatorios (abrir documento/pasta)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setOpenLinks(False)
        self.anchorClicked.connect(self._on_anchor)

    def _on_anchor(self, url: QUrl) -> None:
        texto = url.toString()
        if texto.startswith(LINK_ABRIR):
            open_document(self, unquote(texto[len(LINK_ABRIR):]))
        elif texto.startswith(LINK_PASTA):
            open_folder(self, unquote(texto[len(LINK_PASTA):]))


def acao_color(acao: str) -> str:
    t = tokens()
    return {
        "verificar": t["accent"],
        "cobrar": t["warning"],
        "recobrar": t["danger"],
        "aguardar": t["muted"],
        "com_pessoa": t["danger"],
    }.get(acao, t["text"])


def resultado_color(resultado: str) -> str:
    t = tokens()
    return {
        "recebido": t["success"],
        "documento_com_problema": t["warning"],
        "nao_encontrado": t["danger"],
        "verificacao_falhou": t["danger"],
    }.get(resultado, t["text"])


def acao_label(acao: str) -> str:
    return ACAO_LABELS.get(acao, acao)


def situacao_label(situacao: str | None) -> str:
    if not situacao:
        return "Sem registro"
    return SITUACAO_LABELS.get(situacao, situacao)


def format_date_br(raw: str | None) -> str:
    if not raw:
        return ""
    text = str(raw)[:10]
    if len(text) == 10 and text[4] == "-":
        return f"{text[8:10]}/{text[5:7]}/{text[0:4]}"
    return text


class FilterBar(QWidget):
    """Linha de botoes-filtro exclusivos ("Tudo 12", "Verificar 4"...)."""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.labels = dict(options)
        self.buttons = {}
        for key, label in options:
            button = make_button(label, "filter")
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, k=key: self.changed.emit(k))
            self.group.addButton(button)
            self.buttons[key] = button
            layout.addWidget(button)
        layout.addStretch(1)
        if options:
            self.buttons[options[0][0]].setChecked(True)

    def current(self) -> str:
        for key, button in self.buttons.items():
            if button.isChecked():
                return key
        return next(iter(self.buttons), "")

    def set_counts(self, counts: dict[str, int]) -> None:
        for key, button in self.buttons.items():
            count = counts.get(key)
            button.setText(self.labels[key] if count is None else f"{self.labels[key]}  {count}")


def _counter_cell(valor: int, rotulo: str, cor: str) -> str:
    t = tokens()
    return (
        f'<td nowrap style="padding:6px 12px; background:{t["surface_alt"]}; border:1px solid {t["border"]};">'
        f'<span style="font-size:16pt; font-weight:700; color:{cor if valor else t["muted"]};">{valor}</span><br>'
        f'<span style="color:{t["muted"]};">{escape(rotulo)}</span></td>'
    )


def verificacao_report_html(verificacao: dict) -> str:
    """Relatorio de uma verificacao: contadores no topo e um bloco por resultado, com o que
    foi visto, onde, e o que deu errado (baixa nao feita, motivo do problema ou da falha)."""
    t = tokens()
    itens = verificacao["itens"]
    baixados = [i for i in itens if i["resultado"] == "recebido" and i["baixa_feita"]]
    sem_baixa = [i for i in itens if i["resultado"] == "recebido" and not i["baixa_feita"]]
    problema = [i for i in itens if i["resultado"] == "documento_com_problema"]
    faltando = [i for i in itens if i["resultado"] == "nao_encontrado"]
    falhou = [i for i in itens if i["resultado"] == "verificacao_falhou"]

    parts = [
        f'<div style="font-size:13pt; font-weight:600;">{verificacao["codigo_empresa"]} - '
        f'{escape(verificacao["nome_empresa"])}</div>',
        f'<div style="color:{t["muted"]};">Verificação em {escape(verificacao["fontes"])} - '
        f'{escape(format_utc_timestamp(verificacao["realizada_em"]))} - por {escape(verificacao["username"])}'
        + (f' - rodada {verificacao["rodada_id"]}' if verificacao.get("rodada_id") else "")
        + "</div>",
    ]
    if verificacao.get("resumo"):
        parts.append(f'<p style="margin-top:6px;">{escape(verificacao["resumo"])}</p>')

    parts.append('<table cellspacing="6" style="margin-top:6px;"><tr>')
    parts.append(_counter_cell(len(baixados), "Baixados", t["success"]))
    parts.append(_counter_cell(len(sem_baixa), "Sem baixa", t["danger"]))
    parts.append(_counter_cell(len(problema), "Problema", t["warning"]))
    parts.append(_counter_cell(len(faltando), "Faltando", t["danger"]))
    parts.append(_counter_cell(len(falhou), "Falhou", t["danger"]))
    parts.append("</tr></table>")

    def bloco(titulo: str, cor: str, linhas: list[dict], detalhe) -> None:
        if not linhas:
            return
        parts.append(
            f'<div style="margin-top:12px; font-weight:600; color:{cor};">{escape(titulo)} ({len(linhas)})</div>'
        )
        for item in linhas:
            extra = detalhe(item)
            parts.append(
                f'<div style="margin-left:10px;">{escape(item["nome_documento"])} '
                f'<span style="color:{t["muted"]};">({item["competencia"]})</span>'
                + (f' <span style="color:{t["muted"]};">- {escape(extra)}</span>' if extra else "")
                + file_links_html(item.get("arquivo"))
                + "</div>"
            )

    def juntar(*valores) -> str:
        return " - ".join(str(v) for v in valores if v)

    bloco(
        "Encontrados, mas a baixa não foi feita",
        t["danger"],
        sem_baixa,
        lambda i: juntar(i.get("baixa_erro") or "Baixa deixada para uma pessoa", i.get("onde")),
    )
    bloco(
        "Documento com problema",
        t["warning"],
        problema,
        lambda i: juntar(motivo_label(i.get("motivo")), i.get("onde"), i.get("observacao")),
    )
    bloco(
        "Verificação falhou (não gera cobrança)",
        t["danger"],
        falhou,
        lambda i: juntar(i.get("motivo"), i.get("observacao")),
    )
    bloco("Não encontrados", t["danger"], faltando, lambda i: juntar(i.get("observacao")))
    bloco("Recebidos e baixados", t["success"], baixados, lambda i: juntar(i.get("onde"), i.get("observacao")))
    return "".join(parts)


def resultado_label(resultado: str) -> str:
    return RESULTADO_LABELS.get(resultado, resultado)


def verificacao_item_label(verificacao: dict) -> str:
    resultado = verificacao.get("resultado") or ("recebido" if verificacao.get("encontrado") else "nao_encontrado")
    texto = resultado_label(resultado)
    if resultado == "recebido" and not verificacao.get("baixa_feita"):
        texto += " (sem baixa)"
    return texto


def competencia_timeline_html(competencia: dict) -> str:
    """Tudo o que aconteceu com um documento numa competencia (mudancas de situacao,
    cobrancas e verificacoes), do mais recente para o mais antigo."""
    t = tokens()
    muted = f'style="color:{t["muted"]};"'
    eventos = [(p["em"], "situacao", p) for p in competencia.get("caminho", [])]
    eventos += [(c["realizada_em"], "cobranca", c) for c in competencia.get("contatos", [])]
    eventos += [(v["realizada_em"], "verificacao", v) for v in competencia.get("verificacoes", [])]
    eventos.sort(key=lambda e: e[0] or "", reverse=True)
    if not eventos:
        return f"<p {muted}>Nada registrado nesta competência ainda.</p>"
    parts = []
    for quando, tipo, dado in eventos:
        data = escape(format_utc_timestamp(quando))
        if tipo == "situacao":
            texto = f'Situação: <b>{escape(situacao_label(dado["para"]))}</b>'
            if dado.get("motivo"):
                texto += f' - {escape(motivo_label(dado["motivo"]))}'
            if dado.get("detalhe"):
                texto += f" <span {muted}>- {escape(dado['detalhe'])}</span>"
        elif tipo == "cobranca":
            nome = "Cobrança" if dado["sequencia"] == 1 else f'{dado["sequencia"] - 1}a recobrança'
            texto = f'{nome} por {escape(dado["canal"])}'
            if dado.get("destinatario"):
                texto += f" <span {muted}>para {escape(dado['destinatario'])}</span>"
        else:
            cor = resultado_color(dado.get("resultado") or ("recebido" if dado.get("encontrado") else "nao_encontrado"))
            texto = (
                f'Verificação em {escape(dado["fontes"])}: '
                f'<b style="color:{cor};">{escape(verificacao_item_label(dado))}</b>'
            )
            extra = " - ".join(
                str(v)
                for v in (motivo_label(dado.get("motivo")), dado.get("onde"), dado.get("baixa_erro"), dado.get("observacao"))
                if v
            )
            if extra:
                texto += f" <span {muted}>- {escape(extra)}</span>"
            texto += file_links_html(dado.get("arquivo"))
        por = f' <span {muted}>({escape(dado.get("por") or "")})</span>' if dado.get("por") else ""
        parts.append(f"<div><span {muted}>{data}</span>&nbsp; {texto}{por}</div>")
    return "".join(parts)
