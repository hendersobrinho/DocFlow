from __future__ import annotations

from datetime import date
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QHeaderView,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.dialogs.resolver_dialog import ResolverDialog
from documentos_empresa_app.qt_ui.theme import status_colors, tokens
from documentos_empresa_app.qt_ui.widgets.acompanhamento import (
    DocLinkBrowser,
    open_document,
    open_folder,
    acao_color,
    acao_label,
    competencia_timeline_html,
    format_date_br,
    resultado_color,
    situacao_label,
    verificacao_item_label,
    verificacao_report_html,
)
from documentos_empresa_app.qt_ui.widgets.common import Card, KpiCard, PageHeader, make_button
from documentos_empresa_app.qt_ui.widgets.company_selector import CompanySelector
from documentos_empresa_app.qt_ui.widgets.tables import fill_table, make_readonly_table, selected_key, selected_keys
from documentos_empresa_app.qt_ui.widgets.visual import MapLegend, PillDelegate, YearMap, map_scroll_area
from documentos_empresa_app.services.cobranca_service import (
    ACAO_LABELS,
    ACOES,
    SITUACAO_LABELS,
    TIPO_RECOBRANCA,
    motivo_label,
    tipo_da_sequencia,
)
from documentos_empresa_app.utils.common import ValidationError, format_utc_timestamp, parse_delivery_methods

NO_STATUS_LABEL = "Sem marcacao"


def _status_pair(text: str) -> tuple[str, str] | None:
    return status_colors(text) if text in ("Recebido", "Pendente", "Encerrado", "Nao cobrar") else None


def _acao_color_by_text(text: str) -> str | None:
    acao = next((k for k, v in ACAO_LABELS.items() if text.startswith(v)), None)
    return acao_color(acao) if acao else None


def _situacao_color_by_text(text: str) -> str | None:
    t = tokens()
    for key, label in SITUACAO_LABELS.items():
        if text.startswith(label):
            return {
                "recebido": t["success"],
                "precisa_pessoa": t["danger"],
                "verificacao_falhou": t["danger"],
                "documento_com_problema": t["warning"],
                "nao_encontrado": t["warning"],
            }.get(key, t["accent"])
    return None


def plural(count: int, singular: str, plural_form: str) -> str:
    return f"{count} {singular if count == 1 else plural_form}"


class FichaEmpresaPage(QWidget):
    """Ficha da empresa: quem e, como envia os documentos, cada documento com o seu
    proprio registro de cobrancas e o historico de cobrancas e verificacoes."""

    def __init__(self, services, on_data_changed, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.on_data_changed = on_data_changed
        self.empresa_id: int | None = None
        self.ficha: dict | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(
            PageHeader(
                "Ficha da empresa",
                "Como a empresa envia os documentos, o registro de cada documento e o histórico de cobranças.",
            )
        )

        self.selector = CompanySelector(self.services.empresa_service, active_only=False, title="Empresa")
        self.selector.company_selected.connect(lambda company: self.open_company(company["id"]))
        self.selector.company_cleared.connect(self._clear)
        layout.addWidget(self.selector)

        self.empty_label = QLabel("Selecione uma empresa para ver a ficha.")
        self.empty_label.setObjectName("Muted")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_label, 1)

        self.content = QWidget()
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)
        layout.addWidget(self.content, 1)

        identity_card = Card()
        identity_layout = QVBoxLayout(identity_card)
        identity_layout.setContentsMargins(18, 12, 18, 12)
        identity_layout.setSpacing(2)
        self.identity_title = QLabel()
        self.identity_title.setStyleSheet("font-size: 15pt; font-weight: 600;")
        identity_layout.addWidget(self.identity_title)
        self.identity_details = QLabel()
        self.identity_details.setObjectName("Muted")
        self.identity_details.setWordWrap(True)
        identity_layout.addWidget(self.identity_details)
        content_layout.addWidget(identity_card)

        kpis = QGridLayout()
        kpis.setHorizontalSpacing(12)
        self.kpi_em_aberto = KpiCard("Documentos em aberto")
        self.kpi_cobrancas = KpiCard("Cobranças enviadas")
        self.kpi_recobrancas = KpiCard("Recobranças enviadas")
        self.kpi_ultima = KpiCard("Último contato")
        for column, card in enumerate((self.kpi_em_aberto, self.kpi_cobrancas, self.kpi_recobrancas, self.kpi_ultima)):
            kpis.addWidget(card, 0, column)
        content_layout.addLayout(kpis)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_visao_tab(), "Visão geral")
        self.documentos_tab = self._build_documentos_tab()
        self.tabs.addTab(self.documentos_tab, "Documentos")
        self.tabs.addTab(self._build_recebimento_tab(), "Como receber")
        self.tabs.addTab(self._build_historico_tab(), "Histórico")
        content_layout.addWidget(self.tabs, 1)

        self._clear()

    # Montagem das abas -----------------------------------------------------------

    def _build_visao_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)

        self.visao_resumo = QLabel()
        self.visao_resumo.setWordWrap(True)
        self.visao_resumo.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.visao_resumo)

        card = Card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 10, 16, 8)
        card_layout.setSpacing(4)
        cabecalho = QHBoxLayout()
        cabecalho.setSpacing(6)
        # Navegacao entre anos: ultimos 12 meses (padrao) ou um ano inteiro, de janeiro a
        # dezembro. As setas pulam de ano em ano.
        self.ano_anterior_button = make_button("\u2039")
        self.ano_anterior_button.setToolTip("Ano anterior")
        self.ano_anterior_button.setFixedSize(34, 32)
        self.ano_anterior_button.setStyleSheet("font-size: 14pt; padding: 0px;")
        self.ano_anterior_button.clicked.connect(lambda: self._mudar_ano(-1))
        cabecalho.addWidget(self.ano_anterior_button)
        self.periodo_mapa_combo = QComboBox()
        self.periodo_mapa_combo.setMinimumWidth(170)
        self.periodo_mapa_combo.currentIndexChanged.connect(lambda _i: self._render_mapa())
        cabecalho.addWidget(self.periodo_mapa_combo)
        self.proximo_ano_button = make_button("\u203a")
        self.proximo_ano_button.setToolTip("Próximo ano")
        self.proximo_ano_button.setFixedSize(34, 32)
        self.proximo_ano_button.setStyleSheet("font-size: 14pt; padding: 0px;")
        self.proximo_ano_button.clicked.connect(lambda: self._mudar_ano(1))
        cabecalho.addWidget(self.proximo_ano_button)
        dica = QLabel("cada quadradinho é um documento num mês; passe o mouse para o detalhe e clique para o histórico")
        dica.setObjectName("Muted")
        cabecalho.addWidget(dica, 1)
        card_layout.addLayout(cabecalho)
        self.year_map = YearMap()
        self.year_map.cell_clicked.connect(self._on_map_cell_clicked)
        self.map_area = map_scroll_area(self.year_map)
        card_layout.addWidget(self.map_area)
        card_layout.addWidget(MapLegend())
        self.map_card = card
        layout.addWidget(card)

        aberto = Card()
        aberto_layout = QVBoxLayout(aberto)
        aberto_layout.setContentsMargins(16, 12, 16, 12)
        aberto_layout.setSpacing(8)
        aberto_header = QHBoxLayout()
        aberto_titulo = QLabel("Em aberto agora")
        aberto_titulo.setStyleSheet("font-weight: 600;")
        aberto_header.addWidget(aberto_titulo)
        aberto_dica = QLabel("Selecione um ou vários e use Resolver. Clique duas vezes para ver o histórico.")
        aberto_dica.setObjectName("Muted")
        aberto_header.addWidget(aberto_dica, 1)
        resolver_aberto = make_button("Resolver...", "primary")
        resolver_aberto.clicked.connect(self._resolver_abertos)
        aberto_header.addWidget(resolver_aberto)
        aberto_layout.addLayout(aberto_header)
        self.abertos_table = make_readonly_table(["Documento", "Competência", "Ação", "Por quê"], stretch_column=3)
        self.abertos_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.abertos_table.setItemDelegateForColumn(2, PillDelegate(color_for=_acao_color_by_text, parent=self))
        self.abertos_table.doubleClicked.connect(self._on_aberto_double_clicked)
        aberto_layout.addWidget(self.abertos_table, 1)
        self.abertos_vazio = QLabel("Nada em aberto nesta empresa.")
        self.abertos_vazio.setObjectName("Muted")
        aberto_layout.addWidget(self.abertos_vazio)
        layout.addWidget(aberto, 1)
        return tab

    def _refresh_anos_mapa(self) -> None:
        """Opcoes do mapa: "Ultimos 12 meses" e cada ano que existe no sistema."""
        self._periodos_por_ano: dict[int, list[dict]] = {}
        for periodo in self.services.periodo_service.list_periodos():
            self._periodos_por_ano.setdefault(periodo["ano"], []).append(periodo)
        atual = self.periodo_mapa_combo.currentData()
        self.periodo_mapa_combo.blockSignals(True)
        self.periodo_mapa_combo.clear()
        self.periodo_mapa_combo.addItem("Últimos 12 meses", None)
        for ano in sorted(self._periodos_por_ano, reverse=True):
            self.periodo_mapa_combo.addItem(f"Ano de {ano}", ano)
        indice = self.periodo_mapa_combo.findData(atual)
        self.periodo_mapa_combo.setCurrentIndex(indice if indice >= 0 else 0)
        self.periodo_mapa_combo.blockSignals(False)

    def _mudar_ano(self, passo: int) -> None:
        """Setas: de "Ultimos 12 meses" vai para o ano anterior/seguinte ao atual; dentro de
        um ano, anda de ano em ano (so entre anos que existem no sistema)."""
        destino = self._ano_destino(passo)
        if destino is not None:
            self.periodo_mapa_combo.setCurrentIndex(self.periodo_mapa_combo.findData(destino))

    def _ano_destino(self, passo: int) -> int | None:
        anos = sorted(getattr(self, "_periodos_por_ano", {}))
        atual = self.periodo_mapa_combo.currentData()
        base = date.today().year if atual is None else atual
        destino = base + passo
        return destino if destino in anos else None

    def _render_mapa(self) -> None:
        if self.empresa_id is None:
            return
        ano = self.periodo_mapa_combo.currentData()
        try:
            if ano is None:
                mapa = self.services.cobranca_service.mapa_empresa(self.empresa_id)
            else:
                ultimo = max(self._periodos_por_ano.get(ano, []), key=lambda p: p["mes"], default=None)
                mapa = self.services.cobranca_service.mapa_empresa(
                    self.empresa_id, meses=12, ate_periodo_id=ultimo["id"] if ultimo else None
                )
                # So os meses daquele ano (sem pegar dezembro do ano anterior se faltar mes).
                manter = [i for i, p in enumerate(mapa["periodos"]) if p["ano"] == ano]
                mapa = {
                    "periodos": [mapa["periodos"][i] for i in manter],
                    "documentos": [{**d, "celulas": [d["celulas"][i] for i in manter]} for d in mapa["documentos"]],
                }
        except ValidationError:
            mapa = {"periodos": [], "documentos": []}
        self.year_map.set_data(mapa, SITUACAO_LABELS)
        self.ano_anterior_button.setEnabled(self._ano_destino(-1) is not None)
        self.proximo_ano_button.setEnabled(self._ano_destino(1) is not None)
        # O cartao abraca o mapa; com muitos documentos, para em ~12 linhas e rola.
        self.map_area.setFixedHeight(min(self.year_map.sizeHint().height() + 6, 300))
        self.map_card.setMinimumHeight(self.map_card.sizeHint().height())

    def _render_visao(self) -> None:
        self._refresh_anos_mapa()
        self._render_mapa()
        t = tokens()
        docs = (self.ficha.get("proximas_acoes") or {}).get("documentos", [])
        self._abertos = {(d["documento_id"], d["periodo_id"]): d for d in docs}
        fill_table(
            self.abertos_table,
            [
                ((d["documento_id"], d["periodo_id"]), [d["nome_documento"], d["competencia"], acao_label(d["acao"]), d["porque"]])
                for d in sorted(docs, key=lambda d: (ACOES.index(d["acao"]), d["nome_documento"]))
            ],
        )
        self.abertos_table.setVisible(bool(docs))
        self.abertos_vazio.setVisible(not docs)
        if not docs:
            self.visao_resumo.setText(
                f'<span style="font-size:12pt; color:{t["success"]}; font-weight:600;">Tudo em dia.</span> '
                "Nenhum documento em aberto nesta empresa."
            )
            return
        contagem = {acao: sum(1 for d in docs if d["acao"] == acao) for acao in ACOES}
        partes = [
            f'<span style="color:{acao_color(acao)}; font-weight:600;">{n} {acao_label(acao).lower()}</span>'
            for acao, n in contagem.items()
            if n
        ]
        self.visao_resumo.setText(
            f'<span style="font-size:12pt; font-weight:600;">{len(docs)} documento(s) em aberto</span>'
            f'&nbsp;&nbsp;<span style="color:{t["muted"]};">próximo passo:</span> ' + " &middot; ".join(partes)
        )

    def _on_map_cell_clicked(self, documento_id: int, _periodo_id: int, competencia: str) -> None:
        self.focus_document(documento_id, competencia)

    def _on_aberto_double_clicked(self, _index) -> None:
        chave = selected_key(self.abertos_table)
        doc = getattr(self, "_abertos", {}).get(chave)
        if doc:
            self.focus_document(doc["documento_id"], doc["competencia"])

    def _resolver_abertos(self) -> None:
        docs = [self._abertos[k] for k in selected_keys(self.abertos_table) if k in getattr(self, "_abertos", {})]
        if not docs:
            QMessageBox.information(self, "Ficha da empresa", "Selecione um ou mais documentos da lista.")
            return
        empresa = self.ficha["empresa"]
        dialog = ResolverDialog(
            self.services,
            [
                {
                    "documento_id": d["documento_id"],
                    "periodo_id": d["periodo_id"],
                    "nome_documento": d["nome_documento"],
                    "competencia": d["competencia"],
                    "empresa": f'{empresa["codigo_empresa"]} - {empresa["nome_empresa"]}',
                }
                for d in docs
            ],
            permitir_devolver=all(d["acao"] == "com_pessoa" for d in docs),
            opcao_inicial="recebido" if all(d["acao"] == "verificar" for d in docs) else None,
            pasta_inicial=empresa.get("diretorio_documentos"),
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.on_data_changed()

    def _build_documentos_tab(self) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.documentos_table = make_readonly_table(
            ["Tipo", "Documento", "Mês atual", "Próxima ação", "Cobranças", "Recobranças", "Última cobrança"],
            stretch_column=1,
        )
        self.documentos_table.setItemDelegateForColumn(2, PillDelegate(pair_for=_status_pair, parent=self))
        self.documentos_table.setItemDelegateForColumn(3, PillDelegate(color_for=_acao_color_by_text, parent=self))
        self.documentos_table.itemSelectionChanged.connect(self._on_documento_selected)
        splitter.addWidget(self.documentos_table)

        registro = QWidget()
        registro_layout = QVBoxLayout(registro)
        registro_layout.setContentsMargins(0, 8, 0, 0)
        registro_layout.setSpacing(6)
        self.registro_title = QLabel("Selecione um documento para ver o registro dele.")
        self.registro_title.setStyleSheet("font-weight: 600;")
        registro_layout.addWidget(self.registro_title)
        registro_split = QSplitter(Qt.Orientation.Horizontal)
        self.registro_table = make_readonly_table(
            ["Competência", "Status", "Situação", "Cobrado", "Última verificação"], stretch_column=2
        )
        self.registro_table.setItemDelegateForColumn(1, PillDelegate(pair_for=_status_pair, parent=self))
        self.registro_table.setItemDelegateForColumn(2, PillDelegate(color_for=_situacao_color_by_text, parent=self))
        self.registro_table.itemSelectionChanged.connect(self._on_competencia_selected)
        # "Ultima verificacao" pode ser longa; fica com largura fixa (texto inteiro na dica)
        # para a Situacao, que e o mais importante, ter espaco.
        self.registro_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.registro_table.horizontalHeader().resizeSection(4, 170)
        registro_split.addWidget(self.registro_table)
        caminho = QWidget()
        caminho_layout = QVBoxLayout(caminho)
        caminho_layout.setContentsMargins(0, 0, 0, 0)
        caminho_layout.setSpacing(6)
        acoes = QHBoxLayout()
        acoes.setSpacing(6)
        self.abrir_doc_button = make_button("Abrir documento")
        self.abrir_doc_button.setToolTip("Abre o arquivo que foi baixado na última verificação.")
        self.abrir_doc_button.clicked.connect(self._abrir_documento)
        acoes.addWidget(self.abrir_doc_button)
        self.abrir_pasta_button = make_button("Abrir pasta")
        self.abrir_pasta_button.setToolTip("Abre a pasta do arquivo baixado ou, sem ele, a pasta da empresa.")
        self.abrir_pasta_button.clicked.connect(self._abrir_pasta)
        acoes.addWidget(self.abrir_pasta_button)
        acoes.addStretch(1)
        self.resolver_button = make_button("Resolver...", "primary")
        self.resolver_button.setToolTip(
            "Dizer o que aconteceu com este documento neste mês: chegou, chegou errado, não chegou, "
            "cliente prometeu, precisa de uma pessoa..."
        )
        self.resolver_button.clicked.connect(self._resolver)
        acoes.addWidget(self.resolver_button)
        caminho_layout.addLayout(acoes)
        self.caminho_detail = DocLinkBrowser()
        self.caminho_detail.setPlaceholderText("Selecione uma competência para ver tudo o que aconteceu com o documento.")
        caminho_layout.addWidget(self.caminho_detail, 1)
        registro_split.addWidget(caminho)
        registro_split.setSizes([600, 520])
        registro_layout.addWidget(registro_split, 1)
        splitter.addWidget(registro)
        splitter.setSizes([190, 330])
        return splitter

    def _build_recebimento_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        hint = QLabel(
            "Por onde a empresa envia os documentos e onde procura-los. E isso que o Claude usa para "
            "verificar se os documentos chegaram antes de cobrar."
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.canais_row = QHBoxLayout()
        self.canais_row.setSpacing(14)
        self.canal_checks: dict[str, QCheckBox] = {}
        canais_widget = QWidget()
        canais_widget.setLayout(self.canais_row)
        form.addRow("Canais", canais_widget)

        self.emails_edit = QLineEdit()
        self.emails_edit.setPlaceholderText("financeiro@empresa.com, contador@empresa.com")
        form.addRow("Emails de origem", self.emails_edit)

        self.instrucoes_edit = QPlainTextEdit()
        self.instrucoes_edit.setPlaceholderText(
            "Ex: extratos chegam por email com assunto 'Extrato'; folha fica no Onvio > Departamento Pessoal."
        )
        self.instrucoes_edit.setMinimumHeight(110)
        form.addRow("Onde procurar", self.instrucoes_edit)
        layout.addLayout(form)

        actions = QHBoxLayout()
        actions.addStretch(1)
        save_button = make_button("Salvar", "primary")
        save_button.clicked.connect(self._save_recebimento)
        actions.addWidget(save_button)
        layout.addLayout(actions)
        layout.addStretch(1)
        return tab

    def _build_historico_tab(self) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.historico_table = make_readonly_table(["Data", "Evento", "Canal", "Resumo", "Por"], stretch_column=3)
        self.historico_table.itemSelectionChanged.connect(self._on_evento_selected)
        splitter.addWidget(self.historico_table)
        self.evento_detail = QTextBrowser()
        self.evento_detail.setOpenLinks(False)
        self.evento_detail.setPlaceholderText("Selecione um evento para ver os detalhes.")
        splitter.addWidget(self.evento_detail)
        splitter.setSizes([280, 200])
        return splitter

    # Carregamento ----------------------------------------------------------------

    def refresh_data(self) -> None:
        self.selector.refresh_companies()
        if self.empresa_id is not None:
            self.open_company(self.empresa_id)

    def open_company(self, empresa_id: int) -> None:
        try:
            self.ficha = self.services.cobranca_service.ficha_empresa(empresa_id)
        except ValidationError as exc:
            QMessageBox.warning(self, "Ficha da empresa", str(exc))
            return
        self.empresa_id = empresa_id
        if self.selector.get_selected_company_id() != empresa_id:
            self.selector.set_company(empresa_id)
        self.empty_label.hide()
        self.content.show()
        self._render_identity()
        self._render_documentos()
        self._render_visao()
        self._render_recebimento()
        self._render_historico()

    def _clear(self) -> None:
        self.empresa_id = None
        self.ficha = None
        self.registro = None
        self.content.hide()
        self.empty_label.show()

    def _render_identity(self) -> None:
        empresa = self.ficha["empresa"]
        self.identity_title.setText(f'{empresa["codigo_empresa"]} - {empresa["nome_empresa"]}')
        details = ["Ativa" if empresa["ativa"] else "Inativa"]
        if empresa.get("cnpj"):
            details.append(f'CNPJ {empresa["cnpj"]}')
        contato = " ".join(filter(None, [empresa.get("nome_contato"), empresa.get("email_contato")]))
        details.append(f"Contato: {contato}" if contato else "Sem contato cadastrado")
        canais = empresa.get("canais_recebimento")
        details.append(f"Envia por: {canais}" if canais else "Canais de envio não informados")
        self.identity_details.setText("  |  ".join(details))

        totais = self.ficha["totais"]
        em_aberto = sum(len(periodo["documentos"]) for periodo in self.ficha["em_aberto"])
        self.kpi_em_aberto.set_value(str(em_aberto))
        self.kpi_em_aberto.set_accent(tokens()["danger"] if em_aberto else tokens()["success"])
        self.kpi_cobrancas.set_value(str(totais["cobrancas"]))
        self.kpi_recobrancas.set_value(str(totais["recobrancas"]))
        ultimo = max(filter(None, [totais["ultima_cobranca_em"], totais["ultima_verificacao_em"]]), default=None)
        self.kpi_ultima.set_value(format_utc_timestamp(ultimo, with_time=False) if ultimo else "Nenhum")

    def _render_documentos(self) -> None:
        rows = []
        colors = {}
        # Acao mais urgente de cada documento entre as competencias em aberto.
        acoes: dict[int, list[dict]] = {}
        for doc in (self.ficha.get("proximas_acoes") or {}).get("documentos", []):
            acoes.setdefault(doc["documento_id"], []).append(doc)
        for index, documento in enumerate(self.ficha["documentos"]):
            pendentes = sorted(acoes.get(documento["documento_id"], []), key=lambda d: ACOES.index(d["acao"]))
            if pendentes:
                principal = pendentes[0]
                proxima = f'{acao_label(principal["acao"])} ({principal["competencia"]})'
                if len(pendentes) > 1:
                    proxima += f" +{len(pendentes) - 1}"
                colors[(index, 3)] = acao_color(principal["acao"])
            else:
                proxima = "Nada em aberto"
                colors[(index, 3)] = tokens()["muted"]
            status = documento["status_mes_atual"]
            rows.append(
                (
                    documento["documento_id"],
                    [
                        documento["tipo"],
                        documento["nome_documento"],
                        status or NO_STATUS_LABEL,
                        proxima,
                        str(documento["cobrancas"]),
                        str(documento["recobrancas"]),
                        format_utc_timestamp(documento["ultima_cobranca_em"]) if documento["ultima_cobranca_em"] else "-",
                    ],
                )
            )
            if status:
                colors[(index, 2)] = status_colors(status)[1]
        fill_table(self.documentos_table, rows, colors)
        competencia = self.ficha.get("competencia_atual") or "-"
        self.documentos_table.horizontalHeaderItem(2).setText(f"Status em {competencia}")
        self.registro_table.setRowCount(0)
        self.caminho_detail.clear()
        self.registro = None
        self.registro_title.setText("Selecione um documento para ver o registro dele.")

    def _render_recebimento(self) -> None:
        empresa = self.ficha["empresa"]
        while self.canais_row.count():
            widget = self.canais_row.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        self.canal_checks = {}
        selecionados = parse_delivery_methods(empresa.get("canais_recebimento"))
        disponiveis = [m["nome_meio"] for m in self.services.delivery_method_service.list_methods()]
        for canal in disponiveis + [c for c in selecionados if c not in disponiveis]:
            check = QCheckBox(canal)
            check.setChecked(canal in selecionados)
            self.canal_checks[canal] = check
            self.canais_row.addWidget(check)
        self.canais_row.addStretch(1)
        self.emails_edit.setText(empresa.get("emails_origem_documentos") or "")
        self.instrucoes_edit.setPlainText(empresa.get("instrucoes_busca") or "")

    def _render_historico(self) -> None:
        rows = []
        colors = {}
        t = tokens()
        for index, evento in enumerate(self.ficha["historico"]):
            if evento["tipo_evento"] == "verificacao":
                nome = "Verificação"
                canal = evento["fontes"]
                partes = [
                    f"{evento[chave]} {rotulo}"
                    for chave, rotulo in (
                        ("recebidos", "recebido(s)"),
                        ("com_problema", "com problema"),
                        ("nao_encontrados", "não encontrado(s)"),
                        ("falhas", "falha(s)"),
                    )
                    if evento.get(chave)
                ]
                resumo = ", ".join(partes) or evento.get("resumo") or ""
                problema = evento.get("falhas") or evento.get("sem_baixa") or evento.get("com_problema")
                colors[(index, 1)] = t["danger"] if problema else t["success"]
            else:
                nome = "Recobrança" if evento.get("recobranca") else "Cobrança"
                canal = evento["canal"]
                resumo = plural(len(evento["itens"]), "documento", "documentos")
                if evento.get("destinatario"):
                    resumo += f' para {evento["destinatario"]}'
                if evento.get("recobranca"):
                    colors[(index, 1)] = t["danger"]
            rows.append(
                (
                    (evento["tipo_evento"], evento["id"]),
                    [format_utc_timestamp(evento["realizada_em"]), nome, canal, resumo, evento["username"]],
                )
            )
        fill_table(self.historico_table, rows, colors)
        self.evento_detail.clear()

    # Interacoes ------------------------------------------------------------------

    def _on_documento_selected(self) -> None:
        documento_id = selected_key(self.documentos_table)
        if documento_id is None:
            return
        registro = self.services.cobranca_service.registro_documento(documento_id)
        self.registro_title.setText(
            f'Registro de {registro["nome_documento"]}: '
            f'{plural(registro["total_cobrancas"], "cobrança", "cobranças")}, '
            f'{plural(registro["total_recobrancas"], "recobrança", "recobranças")}'
            + (f'  |  {registro["observacao"]}' if registro.get("observacao") else "")
        )
        self.registro = registro
        rows = []
        colors = {}
        for index, competencia in enumerate(registro["competencias"]):
            verificacoes = competencia["verificacoes"]
            if verificacoes:
                ultima = verificacoes[0]
                verificacao = (
                    f'{verificacao_item_label(ultima)} em '
                    f'{format_utc_timestamp(ultima["realizada_em"], with_time=False)}'
                )
                colors[(index, 4)] = resultado_color(
                    ultima.get("resultado") or ("recebido" if ultima["encontrado"] else "nao_encontrado")
                )
            else:
                verificacao = "-"
            situacao = situacao_label(competencia["situacao"]) if competencia.get("situacao") else "-"
            if competencia.get("situacao_motivo"):
                situacao += f' - {motivo_label(competencia["situacao_motivo"])}'
            if competencia.get("aguardar_ate"):
                situacao += f' até {format_date_br(competencia["aguardar_ate"])}'
            status = competencia["status"]
            rows.append(
                (
                    competencia["competencia"],
                    [
                        competencia["competencia"],
                        status or NO_STATUS_LABEL,
                        situacao,
                        self._cobrado_texto(competencia),
                        verificacao,
                    ],
                )
            )
            if status:
                colors[(index, 1)] = status_colors(status)[1]
            if competencia.get("situacao") == "precisa_pessoa":
                colors[(index, 2)] = tokens()["danger"]
        fill_table(self.registro_table, rows, colors)
        self.caminho_detail.clear()
        # Abre na competencia mais recente que tem alguma historia (situacao, cobranca ou
        # verificacao); sem nenhuma, na primeira linha.
        com_historia = next(
            (
                i
                for i, c in enumerate(registro["competencias"])
                if c.get("situacao") or c["contatos"] or c["verificacoes"]
            ),
            0,
        )
        if registro["competencias"]:
            self.registro_table.selectRow(com_historia)
            self.registro_table.scrollToItem(self.registro_table.item(com_historia, 0))

    @staticmethod
    def _cobrado_texto(competencia: dict) -> str:
        total = competencia["cobrancas"] + competencia["recobrancas"]
        if not total:
            return "Nunca"
        return f"{total}x" + (f' ({competencia["recobrancas"]} recobr.)' if competencia["recobrancas"] else "")

    def _on_competencia_selected(self) -> None:
        chave = selected_key(self.registro_table)
        if chave is None or not getattr(self, "registro", None):
            return
        competencia = next((c for c in self.registro["competencias"] if c["competencia"] == chave), None)
        if competencia is None:
            return
        cabecalho = (
            f'<div style="font-weight:600;">{escape(self.registro["nome_documento"])} - {competencia["competencia"]}</div>'
        )
        if competencia.get("situacao_detalhe"):
            cabecalho += f'<div>{escape(competencia["situacao_detalhe"])}</div>'
        self.caminho_detail.setHtml(cabecalho + "<br>" + competencia_timeline_html(competencia))
        self.abrir_doc_button.setEnabled(bool(self._arquivo_da_competencia(competencia)))
        recebido = competencia.get("status") in ("Recebido", "Encerrado")
        self.resolver_button.setEnabled(not recebido)

    def _competencia_selecionada(self) -> dict | None:
        chave = selected_key(self.registro_table)
        if chave is None or not getattr(self, "registro", None):
            return None
        return next((c for c in self.registro["competencias"] if c["competencia"] == chave), None)

    @staticmethod
    def _arquivo_da_competencia(competencia: dict) -> str | None:
        # Verificacoes vem da mais recente para a mais antiga.
        return next((v["arquivo"] for v in competencia["verificacoes"] if v.get("arquivo")), None)

    def _abrir_documento(self) -> None:
        competencia = self._competencia_selecionada()
        if competencia:
            open_document(self, self._arquivo_da_competencia(competencia))

    def _abrir_pasta(self) -> None:
        competencia = self._competencia_selecionada()
        pasta_empresa = (self.ficha or {}).get("empresa", {}).get("diretorio_documentos")
        open_folder(self, self._arquivo_da_competencia(competencia) if competencia else None, pasta_empresa)

    def _resolver(self) -> None:
        competencia = self._competencia_selecionada()
        if competencia is None or not getattr(self, "registro", None):
            return
        documento_id = self.registro["documento_id"]
        empresa = self.ficha["empresa"]
        dialog = ResolverDialog(
            self.services,
            [
                {
                    "documento_id": documento_id,
                    "periodo_id": competencia["periodo_id"],
                    "nome_documento": self.registro["nome_documento"],
                    "competencia": competencia["competencia"],
                    "empresa": f'{empresa["codigo_empresa"]} - {empresa["nome_empresa"]}',
                }
            ],
            permitir_devolver=competencia.get("situacao") == "precisa_pessoa",
            pasta_inicial=empresa.get("diretorio_documentos"),
            arquivo_inicial=self._arquivo_da_competencia(competencia),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.on_data_changed()
        self._reabrir_documento(documento_id, competencia["competencia"])

    def focus_document(self, documento_id: int, competencia: str | None = None) -> None:
        self.tabs.setCurrentWidget(self.documentos_tab)
        self._reabrir_documento(documento_id, competencia)

    def _reabrir_documento(self, documento_id: int, competencia: str | None) -> None:
        for row in range(self.documentos_table.rowCount()):
            if self.documentos_table.item(row, 0).data(Qt.ItemDataRole.UserRole) == documento_id:
                self.documentos_table.selectRow(row)
                break
        for row in range(self.registro_table.rowCount() if competencia else 0):
            if self.registro_table.item(row, 0).data(Qt.ItemDataRole.UserRole) == competencia:
                self.registro_table.selectRow(row)
                self.registro_table.scrollToItem(self.registro_table.item(row, 0))
                break

    def _on_evento_selected(self) -> None:
        key = selected_key(self.historico_table)
        if key is None or self.ficha is None:
            return
        tipo, evento_id = key
        evento = next(
            (e for e in self.ficha["historico"] if e["tipo_evento"] == tipo and e["id"] == evento_id), None
        )
        if evento is None:
            return
        self.evento_detail.setHtml(self._evento_html(evento))

    def _evento_html(self, evento: dict) -> str:
        if evento["tipo_evento"] == "verificacao":
            return verificacao_report_html(evento)
        t = tokens()
        muted = f'style="color:{t["muted"]};"'
        parts = [f'<div {muted}>{escape(format_utc_timestamp(evento["realizada_em"]))} - por {escape(evento["username"])}</div>']

        titulo = "Recobrança" if evento.get("recobranca") else "Cobrança"
        parts.append(f'<h3>{titulo} por {escape(evento["canal"])}</h3>')
        for rotulo, chave in (("Para", "destinatario"), ("Assunto", "assunto"), ("Observação", "observacao")):
            if evento.get(chave):
                parts.append(f"<div><b>{rotulo}:</b> {escape(evento[chave])}</div>")
        parts.append("<div style='margin-top:6px;'><b>Documentos cobrados:</b></div>")
        for item in evento["itens"]:
            tipo = tipo_da_sequencia(item["sequencia"])
            sufixo = f' - {item["sequencia"] - 1}a recobrança' if tipo == TIPO_RECOBRANCA else ""
            parts.append(f'<div>{escape(item["nome_documento"])} ({item["competencia"]}){sufixo}</div>')
        if evento.get("mensagem"):
            mensagem = escape(evento["mensagem"]).replace("\n", "<br>")
            parts.append(f"<div style='margin-top:8px;'><b>Mensagem enviada:</b><br>{mensagem}</div>")
        return "".join(parts)

    def _save_recebimento(self) -> None:
        if self.empresa_id is None:
            return
        canais = [canal for canal, check in self.canal_checks.items() if check.isChecked()]
        try:
            self.services.empresa_service.set_recebimento(
                self.empresa_id, canais, self.emails_edit.text(), self.instrucoes_edit.toPlainText()
            )
        except ValidationError as exc:
            QMessageBox.critical(self, "Ficha da empresa", str(exc))
            return
        QMessageBox.information(self, "Ficha da empresa", "Forma de envio salva.")
        self.open_company(self.empresa_id)
        self.on_data_changed()
