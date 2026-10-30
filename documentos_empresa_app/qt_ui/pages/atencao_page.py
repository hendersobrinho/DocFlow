from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.dialogs.resolver_dialog import ResolverDialog
from documentos_empresa_app.qt_ui.theme import tokens
from documentos_empresa_app.qt_ui.widgets.acompanhamento import (
    DocLinkBrowser,
    competencia_timeline_html,
    open_document,
    open_folder,
)
from documentos_empresa_app.qt_ui.widgets.common import Card, KpiCard, PageHeader, make_button
from documentos_empresa_app.qt_ui.widgets.tables import fill_table, make_readonly_table, selected_key, selected_keys
from documentos_empresa_app.utils.common import ValidationError, format_utc_timestamp


# O que a pessoa deve fazer em cada tipo de caso. A chave vem de _tipo_do_caso.
O_QUE_FAZER = {
    "baixa_falhou": (
        "O Claude achou o documento, mas o sistema não aceitou a baixa (o erro aparece acima). Abra o "
        "documento, confira e use <b>Resolver &gt; Chegou e está certo</b>."
    ),
    "baixa_pendente": (
        "O documento foi encontrado, mas a baixa ficou para uma pessoa. Abra o documento, confira e use "
        "<b>Resolver &gt; Chegou e está certo</b>."
    ),
    "documento_com_problema": (
        "Chegou um documento, mas errado. Abra o documento para conferir. Se na verdade estiver certo, use "
        "<b>Resolver &gt; Chegou e está certo</b>. Se estiver errado mesmo, peça o certo ao cliente e use "
        "<b>Resolver &gt; Devolver para o Claude</b>: ele volta a verificar e a cobrar."
    ),
    "limite_de_tentativas": (
        "Já foi cobrado várias vezes sem resposta. Fale com o cliente por outro canal (telefone, por "
        "exemplo). Se ele mandar, use <b>Resolver &gt; Chegou e está certo</b>; se combinar uma data, use "
        "<b>Resolver &gt; O cliente prometeu enviar</b>."
    ),
    "cliente_respondeu": (
        "O cliente respondeu algo que precisa de uma decisão sua. Leia o detalhe, fale com ele e use "
        "<b>Resolver</b> para dizer como ficou."
    ),
    "sem_canal": (
        "Não há como cobrar esta empresa (falta email ou canal). Complete o cadastro na ficha da empresa, "
        "em Como receber, e use <b>Resolver &gt; Devolver para o Claude</b>."
    ),
    "outro": "Leia o detalhe acima, resolva e use <b>Resolver</b> para dizer como ficou.",
}


def _tipo_do_caso(caso: dict) -> str:
    if caso.get("situacao") == "precisa_pessoa":
        return caso.get("situacao_motivo") or "outro"
    if caso.get("situacao") == "documento_com_problema":
        return "documento_com_problema"
    return "limite_de_tentativas"


class AtencaoPage(QWidget):
    """O que o Claude (ou as regras) deixou para uma pessoa resolver: documentos travados,
    com o motivo e o caminho que fizeram, e as rodadas que falharam ou pararam no meio."""

    def __init__(self, services, on_data_changed, on_open_ficha=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.on_data_changed = on_data_changed
        self.on_open_ficha = on_open_ficha
        self.casos: dict[tuple[int, int], dict] = {}
        self.rodadas: list[dict] = []
        self._arquivo_atual: str | None = None
        self._pasta_empresa_atual: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(
            PageHeader(
                "Precisa de atenção",
                "Documentos que o Claude parou de cobrar porque precisam de uma decisão sua.",
            )
        )

        como = Card()
        como_layout = QVBoxLayout(como)
        como_layout.setContentsMargins(18, 12, 18, 12)
        como_texto = QLabel(
            "<b>Como funciona.</b> O Claude cuida das cobranças sozinho. Quando aparece algo que ele não "
            "deve decidir (documento errado, cliente que respondeu, muitas cobranças sem resposta, baixa "
            "que não deu certo), o documento sai da fila dele e vem para cá. Ele não mexe mais nesse "
            "documento até alguém resolver.<br>"
            "<b>1.</b> Clique no documento e leia o motivo e o que fazer. "
            "<b>2.</b> Resolva: abra o arquivo, fale com o cliente... "
            "<b>3.</b> Clique em <b>Resolver</b> e diga como terminou: chegou, chegou errado, cliente "
            "prometeu... ou <b>Devolver para o Claude</b> (ele volta a verificar e a cobrar)."
        )
        como_texto.setWordWrap(True)
        como_layout.addWidget(como_texto)
        layout.addWidget(como)

        kpis = QHBoxLayout()
        kpis.setSpacing(12)
        t = tokens()
        self.kpi_casos = KpiCard("Documentos esperando uma pessoa", t["danger"])
        self.kpi_empresas = KpiCard("Empresas envolvidas")
        self.kpi_rodadas = KpiCard("Rodadas com falha nos últimos 7 dias", t["danger"])
        for card in (self.kpi_casos, self.kpi_empresas, self.kpi_rodadas):
            kpis.addWidget(card)
        layout.addLayout(kpis)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_casos_tab(), "Documentos")
        self.tabs.addTab(self._build_rodadas_tab(), "Rodadas com problema")
        layout.addWidget(self.tabs, 1)

    def _build_casos_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        actions = QHBoxLayout()
        self.abrir_doc_button = make_button("Abrir documento")
        self.abrir_doc_button.setToolTip("Abre o arquivo que o Claude baixou na verificação.")
        self.abrir_doc_button.clicked.connect(lambda: open_document(self, self._arquivo_atual))
        actions.addWidget(self.abrir_doc_button)
        abrir_pasta_button = make_button("Abrir pasta")
        abrir_pasta_button.setToolTip("Abre a pasta do arquivo baixado ou, sem ele, a pasta da empresa.")
        abrir_pasta_button.clicked.connect(
            lambda: open_folder(self, self._arquivo_atual, self._pasta_empresa_atual)
        )
        actions.addWidget(abrir_pasta_button)
        actions.addStretch(1)
        hint = QLabel("Dá para selecionar vários (Ctrl/Shift).")
        hint.setObjectName("Muted")
        actions.addWidget(hint)
        ficha_button = make_button("Abrir ficha")
        ficha_button.clicked.connect(self._abrir_ficha)
        actions.addWidget(ficha_button)
        resolver_button = make_button("Resolver...", "primary")
        resolver_button.setToolTip(
            "Dizer como terminou: chegou, chegou errado, não chegou, cliente prometeu ou devolver para o Claude."
        )
        resolver_button.clicked.connect(self._resolver)
        actions.addWidget(resolver_button)
        layout.addLayout(actions)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.casos_table = make_readonly_table(
            ["Empresa", "Documento", "Competência", "Motivo", "Cobrado", "Desde"], stretch_column=3
        )
        self.casos_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.casos_table.itemSelectionChanged.connect(self._on_caso_selected)
        self.casos_table.doubleClicked.connect(lambda _index: self._abrir_ficha())
        splitter.addWidget(self.casos_table)
        self.caso_detail = DocLinkBrowser()
        self.caso_detail.setPlaceholderText("Selecione um documento para ver o motivo e tudo o que aconteceu com ele.")
        splitter.addWidget(self.caso_detail)
        splitter.setSizes([640, 500])
        layout.addWidget(splitter, 1)

        self.casos_empty = QLabel("Nada esperando uma pessoa. O Claude está dando conta de tudo.")
        self.casos_empty.setObjectName("Muted")
        self.casos_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.casos_empty)
        return tab

    def _build_rodadas_tab(self) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.rodadas_table = make_readonly_table(["Início", "Situação", "Falhas", "Avisos", "Resumo"], stretch_column=4)
        self.rodadas_table.itemSelectionChanged.connect(self._on_rodada_selected)
        splitter.addWidget(self.rodadas_table)
        self.rodada_detail = QTextBrowser()
        self.rodada_detail.setPlaceholderText("Selecione uma rodada para ver o que deu errado.")
        splitter.addWidget(self.rodada_detail)
        splitter.setSizes([560, 520])
        return splitter

    # Dados -------------------------------------------------------------------------

    def refresh_data(self) -> None:
        try:
            casos = self.services.cobranca_service.precisa_de_atencao()
            self.rodadas = self.services.rodada_service.rodadas_com_problema(50)
        except ValidationError as exc:
            QMessageBox.critical(self, "Precisa de atenção", str(exc))
            return
        self.casos = {(c["documento_id"], c["periodo_id"]): c for c in casos}

        t = tokens()
        rows = []
        colors = {}
        for index, caso in enumerate(casos):
            vezes = caso["vezes_cobrado"]
            rows.append(
                (
                    (caso["documento_id"], caso["periodo_id"]),
                    [
                        f'{caso["codigo_empresa"]} - {caso["nome_empresa"]}',
                        caso["nome_documento"],
                        caso["competencia"],
                        caso["porque"],
                        "Nunca" if vezes == 0 else f"{vezes}x",
                        format_utc_timestamp(caso["situacao_atualizada_em"], with_time=False)
                        if caso["situacao_atualizada_em"]
                        else "-",
                    ],
                )
            )
            colors[(index, 3)] = t["danger"]
        fill_table(self.casos_table, rows, colors)
        self.casos_table.setVisible(bool(casos))
        self.casos_empty.setVisible(not casos)
        self.caso_detail.clear()
        if casos:
            self.casos_table.selectRow(0)

        rodada_rows = []
        rodada_colors = {}
        for index, rodada in enumerate(self.rodadas):
            rodada_rows.append(
                (
                    rodada["id"],
                    [
                        format_utc_timestamp(rodada["iniciada_em"]),
                        rodada["status_label"],
                        str(rodada["falhas"]) if rodada["falhas"] else "-",
                        str(rodada["avisos"]) if rodada["avisos"] else "-",
                        rodada["resumo"] or "",
                    ],
                )
            )
            rodada_colors[(index, 1)] = t["danger"]
        fill_table(self.rodadas_table, rodada_rows, rodada_colors)
        self.rodada_detail.clear()

        self.kpi_casos.set_value(str(len(casos)))
        self.kpi_empresas.set_value(str(len({c["empresa_id"] for c in casos})))
        self.kpi_rodadas.set_value(str(len(self.rodadas)))
        self.kpi_casos.set_accent(t["danger"] if casos else t["success"])
        self.kpi_rodadas.set_accent(t["danger"] if self.rodadas else t["success"])
        self.tabs.setTabText(0, f"Documentos ({len(casos)})")
        self.tabs.setTabText(1, f"Rodadas com problema ({len(self.rodadas)})")

    def _on_caso_selected(self) -> None:
        chaves = selected_keys(self.casos_table)
        self._arquivo_atual = None
        self._pasta_empresa_atual = None
        self.abrir_doc_button.setEnabled(False)
        if len(chaves) != 1:
            if chaves:
                self.caso_detail.setHtml(f"<p>{len(chaves)} documentos selecionados.</p>")
            return
        caso = self.casos.get(chaves[0])
        if caso is None:
            return
        try:
            self._pasta_empresa_atual = self.services.empresa_service.get_empresa(caso["empresa_id"]).get(
                "diretorio_documentos"
            )
        except ValidationError:
            self._pasta_empresa_atual = None
        t = tokens()
        muted = f'style="color:{t["muted"]};"'
        parts = [
            f'<div style="font-size:12pt; font-weight:600;">{escape(caso["nome_documento"])} '
            f'<span {muted}>({caso["competencia"]})</span></div>',
            f'<div>{caso["codigo_empresa"]} - {escape(caso["nome_empresa"])}</div>',
            f'<div style="margin-top:8px; color:{t["danger"]}; font-weight:600;">{escape(caso["porque"])}</div>',
        ]
        if caso.get("situacao_detalhe"):
            parts.append(f'<div>{escape(caso["situacao_detalhe"])}</div>')
        parts.append(
            f'<div style="margin-top:10px; padding:8px; background:{t["accent_soft"]};">'
            f'<b>O que fazer:</b> {O_QUE_FAZER.get(_tipo_do_caso(caso), O_QUE_FAZER["outro"])}</div>'
        )
        if caso.get("email_contato"):
            parts.append(f'<div style="margin-top:6px;"><b>Contato:</b> {escape(caso["email_contato"])}</div>')

        try:
            registro = self.services.cobranca_service.registro_documento(caso["documento_id"])
        except ValidationError:
            registro = None
        competencia = None
        if registro:
            competencia = next((c for c in registro["competencias"] if c["competencia"] == caso["competencia"]), None)
        if competencia:
            self._arquivo_atual = next(
                (v["arquivo"] for v in competencia["verificacoes"] if v.get("arquivo")), None
            )
            self.abrir_doc_button.setEnabled(bool(self._arquivo_atual))
            parts.append("<div style='margin-top:12px; font-weight:600;'>O que aconteceu (mais recente primeiro)</div>")
            parts.append(competencia_timeline_html(competencia))
        self.caso_detail.setHtml("".join(parts))

    def _on_rodada_selected(self) -> None:
        rodada_id = selected_key(self.rodadas_table)
        rodada = next((r for r in self.rodadas if r["id"] == rodada_id), None)
        if rodada is None:
            return
        t = tokens()
        muted = f'style="color:{t["muted"]};"'
        parts = [
            f'<div style="font-size:12pt; font-weight:600;">Rodada {rodada["id"]} - {escape(rodada["status_label"])}</div>',
            f'<div {muted}>Início {escape(format_utc_timestamp(rodada["iniciada_em"]))}</div>',
        ]
        if rodada["status_efetivo"] == "interrompida":
            parts.append(
                "<p>Começou e nunca foi finalizada. O Claude pode ter parado no meio: confira em "
                "Cobranças &gt; Rodadas do Claude até onde ela chegou e rode de novo se precisar.</p>"
            )
        if rodada.get("resumo"):
            parts.append(f'<p>{escape(rodada["resumo"])}</p>')
        cores = {"falha": t["danger"], "aviso": t["warning"], "info": t["muted"]}
        for ocorrencia in rodada["ocorrencias"]:
            empresa = (
                f' <span {muted}>({ocorrencia["codigo_empresa"]} - {escape(ocorrencia["nome_empresa"])})</span>'
                if ocorrencia["codigo_empresa"] else ""
            )
            parts.append(
                f'<div><b style="color:{cores[ocorrencia["tipo"]]};">{ocorrencia["tipo"].capitalize()}</b> '
                f'{escape(ocorrencia["mensagem"])}{empresa}</div>'
            )
        self.rodada_detail.setHtml("".join(parts))

    # Acoes -------------------------------------------------------------------------

    def _selecionados(self) -> list[tuple[int, int]]:
        chaves = selected_keys(self.casos_table)
        if not chaves:
            QMessageBox.information(self, "Precisa de atenção", "Selecione pelo menos um documento.")
        return chaves

    def _abrir_ficha(self) -> None:
        chaves = selected_keys(self.casos_table)
        if not chaves or self.on_open_ficha is None:
            return
        caso = self.casos[chaves[0]]
        self.on_open_ficha(caso["empresa_id"], caso["documento_id"], caso["competencia"])

    def _resolver(self) -> None:
        chaves = self._selecionados()
        if not chaves:
            return
        casos = [self.casos[k] for k in chaves if k in self.casos]
        itens = [
            {
                "documento_id": c["documento_id"],
                "periodo_id": c["periodo_id"],
                "nome_documento": c["nome_documento"],
                "competencia": c["competencia"],
                "empresa": f'{c["codigo_empresa"]} - {c["nome_empresa"]}',
            }
            for c in casos
        ]
        dialog = ResolverDialog(
            self.services,
            itens,
            permitir_devolver=True,
            pasta_inicial=self._pasta_empresa_atual,
            arquivo_inicial=self._arquivo_atual if len(itens) == 1 else None,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.on_data_changed()
