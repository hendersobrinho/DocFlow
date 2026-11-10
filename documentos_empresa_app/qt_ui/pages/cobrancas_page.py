from __future__ import annotations

from datetime import date, datetime
from html import escape
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.dialogs.resolver_dialog import ResolverDialog
from documentos_empresa_app.qt_ui.icons import app_icon
from documentos_empresa_app.qt_ui.report_printing import print_html, save_html_as_pdf
from documentos_empresa_app.qt_ui.theme import tokens
from documentos_empresa_app.qt_ui.widgets.acompanhamento import (
    DocLinkBrowser,
    FilterBar,
    acao_color,
    acao_label,
    competencia_timeline_html,
    format_date_br,
    situacao_label,
    verificacao_report_html,
)
from documentos_empresa_app.qt_ui.widgets.common import PageHeader, ToolbarRow, make_button
from documentos_empresa_app.qt_ui.widgets.tables import fill_table, make_readonly_table, selected_key, selected_keys
from documentos_empresa_app.qt_ui.widgets.visual import PillDelegate, PipelineBar
from documentos_empresa_app.services.cobranca_service import ACAO_LABELS
from documentos_empresa_app.onvio.robo import pasta_padrao
from documentos_empresa_app.services.relatorio_rodada import coletar_dia
from documentos_empresa_app.services.report_rodada_html import build_rodada_html
from documentos_empresa_app.utils.common import APP_NAME, ValidationError, format_utc_timestamp
from documentos_empresa_app.utils.helpers import get_documents_directory, load_ui_state, open_file_in_default_app

DEFAULT_CHANNELS = ("Email", "WhatsApp", "Onvio", "Telefone")


class RegistrarCobrancaDialog(QDialog):
    """Registra uma cobranca ja feita (o envio em si acontece fora do DocFlow)."""

    def __init__(self, item: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.item = item
        self.result_data: dict | None = None
        self.setWindowTitle(f"{APP_NAME} - Registrar cobrança")
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        title = QLabel(f'{item["codigo_empresa"]} - {item["nome_empresa"]}')
        title.setStyleSheet("font-weight: 600; font-size: 12pt;")
        layout.addWidget(title)

        layout.addWidget(QLabel("Documentos cobrados"))
        self.documentos_list = QListWidget()
        # Vem marcado o que o planejador manda cobrar/recobrar; o resto fica disponivel
        # para marcar a mao (ex: cobrar junto algo que ainda estava aguardando).
        algum_sugerido = any(d.get("acao") in ("cobrar", "recobrar") for d in item["documentos"])
        for documento in item["documentos"]:
            vezes = documento["vezes_cobrado"]
            sufixo = "primeira cobrança" if vezes == 0 else f"já cobrado {vezes}x - será recobrança"
            entry = QListWidgetItem(f'{documento["nome_documento"]} ({documento["competencia"]}) - {sufixo}')
            entry.setFlags(entry.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            sugerido = documento.get("acao") in ("cobrar", "recobrar") or not algum_sugerido
            entry.setCheckState(Qt.CheckState.Checked if sugerido else Qt.CheckState.Unchecked)
            entry.setData(Qt.ItemDataRole.UserRole, (documento["documento_id"], documento["periodo_id"]))
            self.documentos_list.addItem(entry)
        layout.addWidget(self.documentos_list, 1)

        form = QFormLayout()
        form.setSpacing(8)
        self.canal_combo = QComboBox()
        self.canal_combo.setEditable(True)
        canais = list(dict.fromkeys(["Email", *item["canais_recebimento"], *DEFAULT_CHANNELS]))
        self.canal_combo.addItems(canais)
        form.addRow("Canal", self.canal_combo)
        self.destinatario_edit = QLineEdit(item.get("email_contato") or "")
        form.addRow("Para", self.destinatario_edit)
        self.observacao_edit = QPlainTextEdit()
        self.observacao_edit.setPlaceholderText("Opcional")
        self.observacao_edit.setMaximumHeight(70)
        form.addRow("Observação", self.observacao_edit)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = make_button("Cancelar", "quiet")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = make_button("Registrar", "primary")
        save.clicked.connect(self._confirm)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _confirm(self) -> None:
        itens = [
            self.documentos_list.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self.documentos_list.count())
            if self.documentos_list.item(row).checkState() == Qt.CheckState.Checked
        ]
        if not itens:
            QMessageBox.warning(self, APP_NAME, "Marque pelo menos um documento.")
            return
        self.result_data = {
            "itens": itens,
            "canal": self.canal_combo.currentText(),
            "destinatario": self.destinatario_edit.text(),
            "observacao": self.observacao_edit.toPlainText(),
        }
        self.accept()


class CobrancasPage(QWidget):
    """O acompanhamento das cobrancas: o que fazer agora com cada documento (pelas regras do
    sistema), os relatorios de verificacao, as cobrancas feitas e as rodadas do Claude."""

    # Etapas do funil: (acao, titulo, dica, token de cor do tema).
    ETAPAS = [
        ("verificar", "Verificar", "Ver se chegou", "accent"),
        ("cobrar", "Cobrar", "Pedir pela 1a vez", "warning"),
        ("recobrar", "Recobrar", "Pedir de novo", "danger"),
        ("aguardar", "Aguardando", "Esperando o cliente", "muted"),
        ("com_pessoa", "Com uma pessoa", "Precisa de atenção", "danger"),
    ]
    VERIFICACAO_FILTRO = [("todas", "Todas"), ("problemas", "Com algo a resolver")]

    def __init__(self, services, on_data_changed, on_open_ficha=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.on_data_changed = on_data_changed
        self.on_open_ficha = on_open_ficha
        self.plano: dict = {"empresas": [], "resumo": {}}
        self.linhas_plano: dict[tuple[int, int], tuple[dict, dict]] = {}
        self.cobrancas: list[dict] = []
        self.verificacoes: list[dict] = []
        self.rodadas: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(
            PageHeader(
                "Cobranças",
                "O trabalho de cobrança, feito pelo Claude ou por você: o que fazer agora, o que já foi "
                "conferido, o que já foi pedido ao cliente e cada passada do Claude.",
            )
        )

        toolbar = ToolbarRow()
        self.active_only_check = QCheckBox("Somente empresas ativas")
        self.active_only_check.setChecked(True)
        self.active_only_check.toggled.connect(lambda _checked: self.refresh_data())
        toolbar.add(self.active_only_check)
        toolbar.add_stretch()
        self.summary_label = QLabel()
        self.summary_label.setObjectName("Muted")
        toolbar.add(self.summary_label)
        layout.addWidget(toolbar)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_plano_tab(), "O que fazer agora")
        self.tabs.addTab(self._build_verificacoes_tab(), "Conferências feitas")
        self.tabs.addTab(self._build_cobrancas_tab(), "Cobranças enviadas")
        self.tabs.addTab(self._build_rodadas_tab(), "Rodadas do Claude")
        self.relatorio_tab_index = self.tabs.addTab(self._build_relatorio_tab(), "Relatório do dia")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs, 1)

    # Abas ------------------------------------------------------------------------

    def _build_plano_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(
            self._tab_hint(
                "Cada documento em aberto passa por estas etapas, da esquerda para a direita. Clique numa "
                "etapa para ver só ela (clique de novo para ver tudo). Selecione um ou vários documentos e "
                "use <b>Resolver</b> para dizer o que aconteceu."
            )
        )

        self.plano_filter = PipelineBar(self.ETAPAS)
        self.plano_filter.changed.connect(lambda _key: self._render_plano())
        layout.addWidget(self.plano_filter)

        top = QHBoxLayout()
        self.plano_selecao_label = QLabel("Selecione um documento.")
        self.plano_selecao_label.setObjectName("Muted")
        top.addWidget(self.plano_selecao_label, 1)
        ficha_button = make_button("Abrir na ficha")
        ficha_button.clicked.connect(self._open_selected_ficha)
        top.addWidget(ficha_button)
        self.resolver_button = make_button("Resolver...")
        self.resolver_button.setToolTip(
            "Dizer o que aconteceu: chegou, chegou errado, não chegou, cliente prometeu, precisa de uma pessoa."
        )
        self.resolver_button.clicked.connect(self._resolver_plano)
        top.addWidget(self.resolver_button)
        self.registrar_button = make_button("Registrar cobrança...", "primary")
        self.registrar_button.setToolTip("Anota uma cobrança que você fez por fora (email, WhatsApp, telefone).")
        self.registrar_button.clicked.connect(self._registrar_cobranca)
        top.addWidget(self.registrar_button)
        layout.addLayout(top)
        self._sync_plano_buttons(None)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.plano_table = make_readonly_table(
            ["Empresa", "Documento", "Competência", "Ação", "Por quê", "Cobrado", "Próximo passo em"],
            stretch_column=4,
        )
        self.plano_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.plano_table.setItemDelegateForColumn(3, PillDelegate(color_for=self._acao_color_by_label, parent=self))
        self.plano_table.itemSelectionChanged.connect(self._on_plano_selected)
        self.plano_table.doubleClicked.connect(lambda _index: self._open_selected_ficha())
        splitter.addWidget(self.plano_table)
        self.plano_detail = DocLinkBrowser()
        self.plano_detail.setPlaceholderText("Selecione um documento para ver a empresa, onde procurar e o histórico.")
        splitter.addWidget(self.plano_detail)
        splitter.setSizes([320, 180])
        layout.addWidget(splitter, 1)
        return tab

    def _build_verificacoes_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(
            self._tab_hint(
                "Cada vez que alguém procurou os documentos de uma empresa: o que achou e já deu baixa, o que "
                "chegou errado, o que não estava lá e onde não deu para olhar. Clique para ver o relatório; "
                "quando o documento foi baixado, dá para abrir o arquivo ou a pasta direto pelo relatório."
            )
        )
        top = QHBoxLayout()
        self.verificacao_filter = FilterBar(self.VERIFICACAO_FILTRO)
        self.verificacao_filter.changed.connect(lambda _key: self._render_verificacoes())
        top.addWidget(self.verificacao_filter, 1)
        ficha_button = make_button("Abrir ficha")
        ficha_button.clicked.connect(self._open_verificacao_ficha)
        top.addWidget(ficha_button)
        self.baixa_button = make_button("Dar baixa no que foi encontrado")
        self.baixa_button.setToolTip("Marca como Recebido os documentos encontrados nesta verificação que ficaram sem baixa.")
        self.baixa_button.clicked.connect(self._dar_baixa_verificacao)
        top.addWidget(self.baixa_button)
        layout.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.verificacoes_table = make_readonly_table(
            ["Data", "Empresa", "Recebidos", "Problema", "Faltando", "Falhou", "Sem baixa"], stretch_column=1
        )
        self.verificacoes_table.itemSelectionChanged.connect(self._on_verificacao_selected)
        splitter.addWidget(self.verificacoes_table)
        self.verificacao_detail = DocLinkBrowser()
        self.verificacao_detail.setPlaceholderText("Selecione uma verificação para ver o relatório completo.")
        splitter.addWidget(self.verificacao_detail)
        splitter.setSizes([700, 480])
        layout.addWidget(splitter, 1)
        return tab

    def _build_cobrancas_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(
            self._tab_hint(
                "Cada pedido feito ao cliente, por quem, por qual canal e com qual mensagem. A primeira vez que "
                "um documento é pedido num mês é <b>cobrança</b>; as seguintes são <b>recobranças</b>."
            )
        )
        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter, 1)
        self.cobrancas_table = make_readonly_table(
            ["Data", "Empresa", "Tipo", "Canal", "Documentos", "Por"], stretch_column=1
        )
        self.cobrancas_table.itemSelectionChanged.connect(self._on_cobranca_selected)
        splitter.addWidget(self.cobrancas_table)
        self.cobranca_detail = QTextBrowser()
        self.cobranca_detail.setPlaceholderText("Selecione uma cobrança para ver os detalhes.")
        splitter.addWidget(self.cobranca_detail)
        splitter.setSizes([300, 200])
        return tab

    def _build_rodadas_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(
            self._tab_hint(
                "Cada vez que o Claude passou pelas cobranças: quando, quantas empresas, o que conferiu, o que "
                "cobrou e o que deu errado. <b>Interrompida</b> = começou e não terminou."
            )
        )
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)
        self.rodadas_table = make_readonly_table(
            ["Início", "Situação", "Empresas", "Verificações", "Cobranças", "Falhas", "Avisos"], stretch_column=1
        )
        self.rodadas_table.itemSelectionChanged.connect(self._on_rodada_selected)
        splitter.addWidget(self.rodadas_table)
        self.rodada_detail = QTextBrowser()
        self.rodada_detail.setPlaceholderText(
            "Cada vez que o Claude passa pelas cobranças é uma rodada. Selecione uma para ver o que aconteceu."
        )
        splitter.addWidget(self.rodada_detail)
        splitter.setSizes([700, 480])
        return tab

    def _build_relatorio_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(
            self._tab_hint(
                "O sistema monta sozinho o que aconteceu no dia: o que chegou e foi marcado como recebido, o que o "
                "robô baixou do Onvio e as cobranças enviadas. Se o Claude fez uma rodada, as conferências dele "
                "entram também. Imprima ou salve em PDF."
            )
        )
        linha = QHBoxLayout()
        linha.addWidget(QLabel("Dia"))
        self.relatorio_data = QDateEdit(QDate.currentDate())
        self.relatorio_data.setCalendarPopup(True)
        self.relatorio_data.setDisplayFormat("dd/MM/yyyy")
        self.relatorio_data.dateChanged.connect(lambda _d: self._gerar_relatorio())
        linha.addWidget(self.relatorio_data)
        hoje_button = make_button("Hoje", "quiet")
        hoje_button.clicked.connect(lambda: self.relatorio_data.setDate(QDate.currentDate()))
        linha.addWidget(hoje_button)
        atualizar_button = make_button("Atualizar", "quiet")
        atualizar_button.clicked.connect(self._gerar_relatorio)
        linha.addWidget(atualizar_button)
        linha.addStretch(1)
        self.relatorio_pdf_button = make_button("Salvar PDF")
        self.relatorio_pdf_button.clicked.connect(self._salvar_relatorio_pdf)
        linha.addWidget(self.relatorio_pdf_button)
        self.relatorio_print_button = make_button("Imprimir", "primary")
        self.relatorio_print_button.clicked.connect(self._imprimir_relatorio)
        linha.addWidget(self.relatorio_print_button)
        layout.addLayout(linha)
        self.relatorio_html = ""
        self.relatorio_view = QTextBrowser()
        self.relatorio_view.setOpenLinks(False)
        self.relatorio_view.setStyleSheet("QTextBrowser { background-color: #F2F5FA; border: 1px solid #DCE3EE; }")
        layout.addWidget(self.relatorio_view, 1)
        return tab

    def _on_tab_changed(self, index: int) -> None:
        if index == self.relatorio_tab_index:
            self._gerar_relatorio()

    def _gerar_relatorio(self) -> None:
        dia = self.relatorio_data.date().toPython()
        pasta_onvio = Path(str(load_ui_state("onvio:destino", "") or pasta_padrao()))
        try:
            dados = coletar_dia(
                self.services.cobranca_service,
                self.services.rodada_service,
                dia,
                pasta_onvio,
                recebidos_no_dia=self.services.pending_report_service.recebidos_no_dia,
            )
        except ValidationError as exc:
            QMessageBox.critical(self, "Relatório do dia", str(exc))
            return
        self.relatorio_html = build_rodada_html(dados, datetime.now().strftime("%d/%m/%Y %H:%M"))
        self.relatorio_view.setHtml(self.relatorio_html)

    def _imprimir_relatorio(self) -> None:
        if not self.relatorio_html:
            self._gerar_relatorio()
        try:
            print_html(self.relatorio_html, self, "Imprimir relatório da rodada")
        except Exception as exc:  # noqa: BLE001 - impressora/driver: mostra o motivo
            QMessageBox.critical(self, "Relatório do dia", f"Não foi possível imprimir:\n{exc}")

    def _salvar_relatorio_pdf(self) -> None:
        if not self.relatorio_html:
            self._gerar_relatorio()
        dia = self.relatorio_data.date().toPython()
        sugestao = str(get_documents_directory() / f"rodada_{dia:%Y-%m-%d}.pdf")
        caminho, _filtro = QFileDialog.getSaveFileName(self, "Salvar PDF", sugestao, "PDF (*.pdf)")
        if not caminho:
            return
        try:
            salvo = save_html_as_pdf(self.relatorio_html, caminho)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Relatório do dia", f"Não foi possível salvar o PDF:\n{exc}")
            return
        if QMessageBox.question(self, "Relatório do dia", f"PDF salvo em:\n{salvo}\n\nDeseja abrir agora?") == QMessageBox.StandardButton.Yes:
            try:
                open_file_in_default_app(salvo)
            except ValidationError as exc:
                QMessageBox.warning(self, "Relatório do dia", str(exc))

    @staticmethod
    def _tab_hint(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("Muted")
        label.setWordWrap(True)
        return label

    # Carregamento ----------------------------------------------------------------

    def refresh_data(self) -> None:
        service = self.services.cobranca_service
        try:
            self.plano = service.proximas_acoes(somente_ativas=self.active_only_check.isChecked())
            self.cobrancas = service.listar_cobrancas(200)
            self.verificacoes = service.listar_verificacoes(200)
            self.rodadas = self.services.rodada_service.listar(100)
        except ValidationError as exc:
            QMessageBox.critical(self, "Cobranças", str(exc))
            return
        self._render_plano()
        self._render_cobrancas()
        self._render_verificacoes()
        self._render_rodadas()

        resumo = self.plano["resumo"]
        self.plano_filter.set_counts(resumo)
        problemas = sum(1 for v in self.verificacoes if self._verificacao_tem_problema(v))
        self.verificacao_filter.set_counts({"todas": len(self.verificacoes), "problemas": problemas})
        regras = self.plano["regras"]
        self.summary_label.setText(
            f'{len(self.plano["empresas"])} empresa(s) com documento em aberto  |  '
            f'regras: esperar {regras["dias_entre_cobrancas"]} dia(s) entre cobranças, '
            f'até {regras["max_recobrancas"]} recobrança(s)'
        )

    def _render_plano(self) -> None:
        filtro = self.plano_filter.current()
        rows = []
        colors = {}
        self.linhas_plano = {}
        for empresa in self.plano["empresas"]:
            for doc in empresa["documentos"]:
                if filtro != "todas" and doc["acao"] != filtro:
                    continue
                chave = (doc["documento_id"], doc["periodo_id"])
                self.linhas_plano[chave] = (empresa, doc)
                index = len(rows)
                vezes = doc["vezes_cobrado"]
                rows.append(
                    (
                        chave,
                        [
                            f'{empresa["codigo_empresa"]} - {empresa["nome_empresa"]}',
                            doc["nome_documento"],
                            doc["competencia"],
                            acao_label(doc["acao"]),
                            doc["porque"],
                            "Nunca" if vezes == 0 else f"{vezes}x",
                            format_date_br(doc["proxima_acao_em"]) or ("Agora" if doc["acao"] != "com_pessoa" else "-"),
                        ],
                    )
                )
        fill_table(self.plano_table, rows, colors)
        self.plano_detail.clear()

    def _render_cobrancas(self) -> None:
        t = tokens()
        rows = []
        colors = {}
        for index, cobranca in enumerate(self.cobrancas):
            rows.append(
                (
                    cobranca["id"],
                    [
                        format_utc_timestamp(cobranca["realizada_em"]),
                        f'{cobranca["codigo_empresa"]} - {cobranca["nome_empresa"]}',
                        "Recobrança" if cobranca["recobranca"] else "Cobrança",
                        cobranca["canal"],
                        str(len(cobranca["itens"])),
                        cobranca["username"],
                    ],
                )
            )
            if cobranca["recobranca"]:
                colors[(index, 2)] = t["danger"]
        fill_table(self.cobrancas_table, rows, colors)
        self.cobranca_detail.clear()

    @staticmethod
    def _verificacao_tem_problema(verificacao: dict) -> bool:
        return bool(verificacao["com_problema"] or verificacao["falhas"] or verificacao["sem_baixa"])

    def _render_verificacoes(self) -> None:
        t = tokens()
        somente_problemas = self.verificacao_filter.current() == "problemas"
        rows = []
        colors = {}
        for verificacao in self.verificacoes:
            if somente_problemas and not self._verificacao_tem_problema(verificacao):
                continue
            index = len(rows)
            valores = {
                2: (verificacao["recebidos"], t["success"]),
                3: (verificacao["com_problema"], t["warning"]),
                4: (verificacao["nao_encontrados"], t["danger"]),
                5: (verificacao["falhas"], t["danger"]),
                6: (verificacao["sem_baixa"], t["danger"]),
            }
            rows.append(
                (
                    verificacao["id"],
                    [
                        format_utc_timestamp(verificacao["realizada_em"], with_time=False),
                        f'{verificacao["codigo_empresa"]} - {verificacao["nome_empresa"]}',
                        *[str(valores[c][0]) if valores[c][0] else "-" for c in range(2, 7)],
                    ],
                )
            )
            for column, (valor, cor) in valores.items():
                colors[(index, column)] = cor if valor else t["muted"]
        fill_table(self.verificacoes_table, rows, colors)
        self.verificacao_detail.clear()
        self.baixa_button.setEnabled(False)

    def _render_rodadas(self) -> None:
        t = tokens()
        rows = []
        colors = {}
        for index, rodada in enumerate(self.rodadas):
            rows.append(
                (
                    rodada["id"],
                    [
                        format_utc_timestamp(rodada["iniciada_em"]),
                        rodada["status_label"],
                        str(rodada["empresas"]),
                        str(rodada["verificacoes"]),
                        str(rodada["cobrancas"]),
                        str(rodada["falhas"]) if rodada["falhas"] else "-",
                        str(rodada["avisos"]) if rodada["avisos"] else "-",
                    ],
                )
            )
            status_cor = {
                "concluida": t["success"],
                "concluida_com_falhas": t["danger"],
                "interrompida": t["danger"],
                "em_andamento": t["accent"],
            }[rodada["status_efetivo"]]
            colors[(index, 1)] = status_cor
            if rodada["falhas"]:
                colors[(index, 5)] = t["danger"]
            if rodada["avisos"]:
                colors[(index, 6)] = t["warning"]
        fill_table(self.rodadas_table, rows, colors)
        self.rodada_detail.clear()

    # Detalhes --------------------------------------------------------------------

    def _selected_plano(self) -> tuple[dict, dict] | tuple[None, None]:
        chave = selected_key(self.plano_table)
        return self.linhas_plano.get(chave, (None, None))

    @staticmethod
    def _acao_color_by_label(label: str) -> str | None:
        acao = next((k for k, v in ACAO_LABELS.items() if v == label), None)
        return acao_color(acao) if acao else None

    def show_action(self, acao: str) -> None:
        """Abre a aba "O que fazer agora" ja filtrada numa etapa (usado pelo Painel)."""
        self.tabs.setCurrentIndex(0)
        self.plano_filter.select(acao)
        self._render_plano()

    def _selected_plano_items(self) -> list[tuple[dict, dict]]:
        return [self.linhas_plano[k] for k in selected_keys(self.plano_table) if k in self.linhas_plano]

    def _sync_plano_buttons(self, doc: dict | None) -> None:
        acao = doc["acao"] if doc else None
        self.resolver_button.setEnabled(acao is not None)
        self.registrar_button.setEnabled(acao is not None)
        # O botao principal acompanha a acao do documento selecionado.
        for button, principal in (
            (self.resolver_button, acao in ("verificar", "aguardar", "com_pessoa")),
            (self.registrar_button, acao in ("cobrar", "recobrar") or acao is None),
        ):
            button.setProperty("variant", "primary" if principal else "")
            button.style().unpolish(button)
            button.style().polish(button)
        if doc is None:
            self.plano_selecao_label.setText("Selecione um documento.")
        else:
            textos = {
                "verificar": "Procure o documento e diga se chegou.",
                "cobrar": "Peça ao cliente e registre a cobrança.",
                "recobrar": "Peça de novo e registre a recobrança.",
                "aguardar": "Nada a fazer agora; o cliente ainda está no prazo.",
                "com_pessoa": "Este documento está em Precisa de atenção.",
            }
            self.plano_selecao_label.setText(textos.get(acao, ""))

    def _on_plano_selected(self) -> None:
        selecionados = self._selected_plano_items()
        empresa, doc = selecionados[0] if selecionados else (None, None)
        self._sync_plano_buttons(doc)
        if len(selecionados) > 1:
            self.plano_selecao_label.setText(f"{len(selecionados)} documentos selecionados. Use Resolver para todos.")
            self.plano_detail.setHtml(
                "<p>" + "<br>".join(
                    f'{escape(d["nome_documento"])} ({d["competencia"]}) - {escape(e["nome_empresa"])}'
                    for e, d in selecionados
                ) + "</p>"
            )
            return
        if empresa is None:
            return
        t = tokens()
        muted = f'style="color:{t["muted"]};"'
        parts = [
            f'<div style="font-size:12pt; font-weight:600;">{escape(doc["nome_documento"])} '
            f'<span {muted}>({doc["competencia"]})</span></div>',
            f'<div>{empresa["codigo_empresa"]} - {escape(empresa["nome_empresa"])}</div>',
            (f'<div {muted}>{escape(doc["observacao_documento"])}</div>' if doc.get("observacao_documento") else ""),
            f'<div style="margin-top:6px;"><b style="color:{acao_color(doc["acao"])};">{acao_label(doc["acao"])}</b>'
            f' - {escape(doc["porque"])}</div>',
            f'<div><b>Situação:</b> {escape(situacao_label(doc["situacao"]))}'
            + (f' <span {muted}>desde {escape(format_utc_timestamp(doc["situacao_atualizada_em"]))}</span>'
               if doc["situacao_atualizada_em"] else "")
            + "</div>",
        ]
        if doc.get("situacao_detalhe"):
            parts.append(f'<div><b>Detalhe:</b> {escape(doc["situacao_detalhe"])}</div>')
        vezes = doc["vezes_cobrado"]
        if vezes:
            parts.append(
                f"<div><b>Cobrado:</b> {vezes}x, última em "
                f'{escape(format_utc_timestamp(doc["ultima_cobranca_em"], with_time=False))}</div>'
            )
        canais = ", ".join(empresa["canais_recebimento"]) or "não informado"
        parts.append(f"<div style='margin-top:6px;'><b>Envia por:</b> {escape(canais)}</div>")
        if empresa.get("emails_origem_documentos"):
            parts.append(f'<div><b>Emails de origem:</b> {escape(empresa["emails_origem_documentos"])}</div>')
        if empresa.get("instrucoes_busca"):
            parts.append(f'<div><b>Onde procurar:</b> {escape(empresa["instrucoes_busca"])}</div>')
        if empresa.get("email_contato"):
            parts.append(f'<div><b>Contato:</b> {escape(empresa.get("nome_contato") or "")} '
                         f'{escape(empresa["email_contato"])}</div>')
        try:
            registro = self.services.cobranca_service.registro_documento(doc["documento_id"])
        except ValidationError:
            registro = None
        competencia = next(
            (c for c in (registro or {}).get("competencias", []) if c.get("periodo_id") == doc["periodo_id"]), None
        )
        if competencia and (competencia["caminho"] or competencia["contatos"] or competencia["verificacoes"]):
            parts.append("<div style='margin-top:10px; font-weight:600;'>O que já aconteceu</div>")
            parts.append(competencia_timeline_html(competencia))
        self.plano_detail.setHtml("".join(parts))

    def _on_cobranca_selected(self) -> None:
        cobranca_id = selected_key(self.cobrancas_table)
        cobranca = next((c for c in self.cobrancas if c["id"] == cobranca_id), None)
        if cobranca is None:
            return
        parts = [
            f'<h3>{"Recobrança" if cobranca["recobranca"] else "Cobrança"} por {escape(cobranca["canal"])}</h3>',
            f'<div>{cobranca["codigo_empresa"]} - {escape(cobranca["nome_empresa"])}</div>',
            f'<div>{escape(format_utc_timestamp(cobranca["realizada_em"]))} - por {escape(cobranca["username"])}'
            + (f' - rodada {cobranca["rodada_id"]}' if cobranca.get("rodada_id") else "")
            + "</div>",
        ]
        for rotulo, chave in (("Para", "destinatario"), ("Assunto", "assunto"), ("Observação", "observacao")):
            if cobranca.get(chave):
                parts.append(f"<div><b>{rotulo}:</b> {escape(cobranca[chave])}</div>")
        parts.append("<div style='margin-top:6px;'><b>Documentos:</b></div>")
        for item in cobranca["itens"]:
            sufixo = f' - {item["sequencia"] - 1}a recobrança' if item["sequencia"] > 1 else ""
            parts.append(f'<div>{escape(item["nome_documento"])} ({item["competencia"]}){sufixo}</div>')
        if cobranca.get("mensagem"):
            parts.append(
                "<div style='margin-top:8px;'><b>Mensagem enviada:</b><br>"
                + escape(cobranca["mensagem"]).replace("\n", "<br>")
                + "</div>"
            )
        self.cobranca_detail.setHtml("".join(parts))

    def _selected_verificacao(self) -> dict | None:
        verificacao_id = selected_key(self.verificacoes_table)
        return next((v for v in self.verificacoes if v["id"] == verificacao_id), None)

    def _on_verificacao_selected(self) -> None:
        verificacao = self._selected_verificacao()
        if verificacao is None:
            return
        self.verificacao_detail.setHtml(verificacao_report_html(verificacao))
        self.baixa_button.setEnabled(bool(verificacao["sem_baixa"]))

    def _on_rodada_selected(self) -> None:
        rodada_id = selected_key(self.rodadas_table)
        rodada = next((r for r in self.rodadas if r["id"] == rodada_id), None)
        if rodada is None:
            return
        t = tokens()
        muted = f'style="color:{t["muted"]};"'
        fim = format_utc_timestamp(rodada["finalizada_em"]) if rodada["finalizada_em"] else "não finalizada"
        parts = [
            f'<div style="font-size:12pt; font-weight:600;">Rodada {rodada["id"]} - {escape(rodada["status_label"])}</div>',
            f'<div {muted}>Início {escape(format_utc_timestamp(rodada["iniciada_em"]))} - fim {escape(fim)} - '
            f'por {escape(rodada["username"])}</div>',
        ]
        if rodada["status_efetivo"] == "interrompida":
            parts.append(
                f'<p style="color:{t["danger"]};">Esta rodada começou e nunca foi finalizada: o Claude pode ter '
                "parado no meio. Veja abaixo até onde ela chegou.</p>"
            )
        if rodada.get("resumo"):
            parts.append(f'<p>{escape(rodada["resumo"])}</p>')
        parts.append(
            f'<div>{rodada["empresas"]} empresa(s), {rodada["verificacoes"]} verificação(ões), '
            f'{rodada["cobrancas"]} cobrança(s).</div>'
        )
        cores = {"falha": t["danger"], "aviso": t["warning"], "info": t["muted"]}
        rotulos = {"falha": "Falha", "aviso": "Aviso", "info": "Info"}
        if rodada["ocorrencias"]:
            parts.append("<div style='margin-top:10px; font-weight:600;'>Ocorrências</div>")
            for ocorrencia in rodada["ocorrencias"]:
                empresa = (
                    f' <span {muted}>({ocorrencia["codigo_empresa"]} - {escape(ocorrencia["nome_empresa"])})</span>'
                    if ocorrencia["codigo_empresa"] else ""
                )
                parts.append(
                    f'<div><b style="color:{cores[ocorrencia["tipo"]]};">{rotulos[ocorrencia["tipo"]]}</b> '
                    f'{escape(ocorrencia["mensagem"])}{empresa} '
                    f'<span {muted}>- {escape(format_utc_timestamp(ocorrencia["criado_em"]))}</span></div>'
                )
        verificacoes = [v for v in self.verificacoes if v.get("rodada_id") == rodada["id"]]
        if verificacoes:
            parts.append("<div style='margin-top:10px; font-weight:600;'>Verificações desta rodada</div>")
            for v in verificacoes:
                resumo = ", ".join(
                    f"{valor} {rotulo}"
                    for valor, rotulo in (
                        (v["recebidos"], "recebido(s)"),
                        (v["com_problema"], "com problema"),
                        (v["nao_encontrados"], "não encontrado(s)"),
                        (v["falhas"], "falha(s)"),
                    )
                    if valor
                )
                parts.append(f'<div>{v["codigo_empresa"]} - {escape(v["nome_empresa"])} <span {muted}>- {resumo}</span></div>')
        cobrancas = [c for c in self.cobrancas if c.get("rodada_id") == rodada["id"]]
        if cobrancas:
            parts.append("<div style='margin-top:10px; font-weight:600;'>Cobranças desta rodada</div>")
            for c in cobrancas:
                tipo = "Recobrança" if c["recobranca"] else "Cobrança"
                parts.append(
                    f'<div>{c["codigo_empresa"]} - {escape(c["nome_empresa"])} <span {muted}>- {tipo} por '
                    f'{escape(c["canal"])}, {len(c["itens"])} documento(s)</span></div>'
                )
        self.rodada_detail.setHtml("".join(parts))

    # Acoes -----------------------------------------------------------------------

    def _open_selected_ficha(self) -> None:
        empresa, doc = self._selected_plano()
        if empresa is None:
            QMessageBox.information(self, "Cobranças", "Selecione um documento na lista.")
            return
        if self.on_open_ficha:
            self.on_open_ficha(empresa["empresa_id"], doc["documento_id"], doc["competencia"])

    def _resolver_plano(self) -> None:
        selecionados = self._selected_plano_items()
        if not selecionados:
            QMessageBox.information(self, "Cobranças", "Selecione um ou mais documentos na lista.")
            return
        itens = [
            {
                "documento_id": d["documento_id"],
                "periodo_id": d["periodo_id"],
                "nome_documento": d["nome_documento"],
                "competencia": d["competencia"],
                "empresa": f'{e["codigo_empresa"]} - {e["nome_empresa"]}',
            }
            for e, d in selecionados
        ]
        acoes = {d["acao"] for _e, d in selecionados}
        empresa = selecionados[0][0]
        pasta = None
        try:
            pasta = self.services.empresa_service.get_empresa(empresa["empresa_id"]).get("diretorio_documentos")
        except ValidationError:
            pass
        dialog = ResolverDialog(
            self.services,
            itens,
            permitir_devolver=acoes == {"com_pessoa"},
            opcao_inicial="recebido" if acoes == {"verificar"} else None,
            pasta_inicial=pasta,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.on_data_changed()

    def _open_verificacao_ficha(self) -> None:
        verificacao = self._selected_verificacao()
        if verificacao is None:
            QMessageBox.information(self, "Cobranças", "Selecione uma verificação.")
            return
        if self.on_open_ficha:
            self.on_open_ficha(verificacao["empresa_id"])

    def _dar_baixa_verificacao(self) -> None:
        verificacao = self._selected_verificacao()
        if verificacao is None:
            return
        pendentes = [i for i in verificacao["itens"] if i["resultado"] == "recebido" and not i["baixa_feita"]]
        if not pendentes:
            return
        nomes = "\n".join(f'- {i["nome_documento"]} ({i["competencia"]})' for i in pendentes)
        answer = QMessageBox.question(
            self, "Cobranças", f"Marcar como Recebido os documentos encontrados sem baixa?\n\n{nomes}"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.services.cobranca_service.dar_baixa_manual(
                [(i["documento_id"], i["periodo_id"]) for i in pendentes],
                f'Baixa dada a partir da verificação de {format_utc_timestamp(verificacao["realizada_em"])}.',
            )
        except ValidationError as exc:
            QMessageBox.critical(self, "Cobranças", str(exc))
            return
        self.on_data_changed()

    def _registrar_cobranca(self) -> None:
        empresa, _doc = self._selected_plano()
        if empresa is None:
            QMessageBox.information(self, "Cobranças", "Selecione um documento da empresa a cobrar.")
            return
        dialog = RegistrarCobrancaDialog(empresa, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.result_data is None:
            return
        data = dialog.result_data
        try:
            resultado = self.services.cobranca_service.registrar_cobranca(
                empresa["empresa_id"],
                data["canal"],
                data["itens"],
                destinatario=data["destinatario"],
                observacao=data["observacao"],
            )
        except ValidationError as exc:
            QMessageBox.critical(self, "Cobranças", str(exc))
            return
        recobrancas = sum(1 for i in resultado["itens"] if i["tipo"] == "Recobranca")
        QMessageBox.information(
            self,
            "Cobranças",
            f'Cobrança registrada: {len(resultado["itens"])} documento(s), {recobrancas} recobrança(s).',
        )
        self.on_data_changed()
