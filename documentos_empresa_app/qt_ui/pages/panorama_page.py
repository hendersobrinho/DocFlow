from __future__ import annotations

from datetime import date, datetime
from html import escape
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QRadioButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.theme import situation_color, status_colors, tokens
from documentos_empresa_app.qt_ui.viewmodels import (
    MONTH_STATUS_OVERDUE,
    PanoramaViewModel,
    UI_SITUATION_LABELS,
)
from documentos_empresa_app.qt_ui.dialogs.company_dialogs import CompanyMultiSelectDialog
from documentos_empresa_app.qt_ui.dialogs.resolver_dialog import ResolverDialog
from documentos_empresa_app.qt_ui.widgets.acompanhamento import (
    DocLinkBrowser,
    competencia_timeline_html,
    situacao_label,
)
from documentos_empresa_app.qt_ui.widgets.common import Card, PageHeader, ToolbarRow, make_button
from documentos_empresa_app.qt_ui.widgets.visual import (
    PROGRESS_ROLE,
    MapLegend,
    PillDelegate,
    ProgressDelegate,
    YearMap,
    map_scroll_area,
    status_icon,
)
from documentos_empresa_app.services.cobranca_service import SITUACAO_LABELS
from documentos_empresa_app.onvio.robo import pasta_padrao
from documentos_empresa_app.services.relatorio_visao_geral import (
    coletar_visao_geral,
    rodadas_recentes,
)
from documentos_empresa_app.services.report_visao_geral_html import build_secao_robo_claude
from documentos_empresa_app.services.whatsapp_service import build_link
from documentos_empresa_app.qt_ui.report_printing import print_html, save_html_as_pdf
from documentos_empresa_app.qt_ui.workers import BlockingTaskRunner
from documentos_empresa_app.utils.common import ValidationError, format_utc_timestamp
from documentos_empresa_app.qt_ui.widgets.tables import natural_key, remember_sort
from documentos_empresa_app.utils.helpers import (
    get_documents_directory,
    load_ui_state,
    open_email_draft,
    open_file_in_default_app,
    save_ui_state,
)

COLUMN_KEYS = ("codigo", "empresa", "situacao", "progresso", "historico", "ultima_marcacao")
COLUMN_HEADINGS = {
    "codigo": "Código",
    "empresa": "Empresa",
    "situacao": "Situação do mês",
    "progresso": "Progresso",
    "historico": "Meses anteriores em aberto",
    "ultima_marcacao": "Última marcação",
}
COLUMN_TOOLTIPS = {
    "situacao": "Situação só da competência escolhida acima.",
    "historico": (
        "Quantos meses ANTERIORES à competência escolhida ainda têm documento sem receber.\n"
        "Passe o mouse na célula para ver a lista de meses; o detalhe abaixo mostra os documentos."
    ),
}
SORT_ROLE = Qt.ItemDataRole.UserRole + 1
PERIODO_KEY = "panorama:competencia"  # ultima competencia escolhida (MM/AAAA), volta ao abrir


class _SortableItem(QTableWidgetItem):
    """Ordena pelo valor guardado em SORT_ROLE quando houver (ex: quantidade de meses),
    em vez do texto exibido - senao "10 meses" ficaria antes de "2 meses"."""

    def __lt__(self, other: QTableWidgetItem) -> bool:
        mine = self.data(SORT_ROLE)
        theirs = other.data(SORT_ROLE)
        if mine is not None and theirs is not None:
            return mine < theirs
        return natural_key(self.text()) < natural_key(other.text())


# Botoes de marcacao do mapa: (texto, status gravado, teclas de atalho, dica). O e X sao as
# letras da planilha de controle ("OK" chegou, "X" nao cobrar) - digitar "OK" marca no O.
MARK_ACTIONS = (
    ("Recebido", "Recebido", ("O", "R"), "Chegou: marca como Recebido"),
    ("Pendente", "Pendente", ("P",), "Ainda falta: marca como Pendente"),
    ("Encerrado", "Encerrado", ("E",), "Para de cobrar este documento a partir deste mês"),
    ("Não cobrar", "Nao cobrar", ("X", "N"), "Não cobrar neste mês"),
    ("Limpar", "", ("Del",), "Tira a marcação"),
)


def _situation_color_by_label(label: str) -> str | None:
    key = next((k for k, v in UI_SITUATION_LABELS.items() if v == label), None)
    return situation_color(key) if key else None


def _short_period_label(periodo_label: str) -> str:
    """'01/2026 - Janeiro' -> '01/2026'."""
    return periodo_label.split(" - ", 1)[0]


def _previous_months_text(period_items: list[dict]) -> str:
    if not period_items:
        return "Nenhum"
    first = _short_period_label(period_items[0]["periodo_label"])
    if len(period_items) == 1:
        return f"1 mês ({first})"
    return f"{len(period_items)} meses (desde {first})"


def _previous_months_tooltip(period_items: list[dict]) -> str:
    if not period_items:
        return "Nenhum mês anterior com documento em aberto."
    return "\n".join(
        f'{item["periodo_label"]}: {item["document_count"]} documento(s) em aberto' for item in period_items
    )


class ExportReportDialog(QDialog):
    """Relatorio da documentacao (o que chegou e o que falta) ou so das pendencias: imprime direto
    ou salva em PDF/Excel."""

    def __init__(self, services, default_period_id: int | None, visible_company_ids: list[int], parent=None) -> None:
        super().__init__(parent)
        self.services = services
        self.visible_company_ids = visible_company_ids
        self.manual_ids: list[int] = []
        self.setWindowTitle("Relatório de documentação")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        title = QLabel("Relatório de documentação")
        title.setStyleSheet("font-size: 13pt; font-weight: 600;")
        layout.addWidget(title)
        hint = QLabel("O retrato de como está a documentação das empresas no período escolhido.")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.kind_situacao = QRadioButton("Completo: o que chegou, o que ainda não chegou e o que foi procurado e não encontrado")
        self.kind_situacao.setChecked(True)
        layout.addWidget(self.kind_situacao)
        self.kind_pendencias = QRadioButton("Só o que falta (o que ainda não chegou e o que foi procurado e não encontrado)")
        layout.addWidget(self.kind_pendencias)
        self.include_complete_check = QCheckBox("Listar também as empresas completas (em que já chegou tudo)")
        self.include_complete_check.setChecked(True)
        self.kind_situacao.toggled.connect(self.include_complete_check.setEnabled)
        layout.addWidget(self.include_complete_check)
        self.robo_claude_check = QCheckBox("Incluir no fim o resumo do robô do Onvio e das rodadas do Claude")
        self.robo_claude_check.setChecked(True)
        self.kind_situacao.toggled.connect(self.robo_claude_check.setEnabled)
        layout.addWidget(self.robo_claude_check)

        period_row = QHBoxLayout()
        period_row.setSpacing(8)
        period_row.addWidget(QLabel("De"))
        self.start_combo = QComboBox()
        period_row.addWidget(self.start_combo)
        period_row.addWidget(QLabel("até"))
        self.end_combo = QComboBox()
        period_row.addWidget(self.end_combo)
        period_row.addStretch(1)
        periodos = sorted(services.periodo_service.list_periodos(), key=lambda p: (p["ano"], p["mes"]))
        for periodo in periodos:
            label = f'{periodo["mes"]:02d}/{periodo["ano"]}'
            self.start_combo.addItem(label, periodo["id"])
            self.end_combo.addItem(label, periodo["id"])
        if default_period_id is not None:
            self.start_combo.setCurrentIndex(max(0, self.start_combo.findData(default_period_id)))
            self.end_combo.setCurrentIndex(max(0, self.end_combo.findData(default_period_id)))
        layout.addLayout(period_row)
        period_hint = QLabel(
            "Com “De” e “até” no mesmo mês, o relatório mostra só aquele mês. Escolhendo um "
            "intervalo, o que ficou pendente nos meses anteriores do intervalo entra junto, com o "
            "mês de cada documento."
        )
        period_hint.setObjectName("Muted")
        period_hint.setWordWrap(True)
        layout.addWidget(period_hint)

        scope_title = QLabel("Empresas")
        scope_title.setStyleSheet("font-weight: 600;")
        layout.addWidget(scope_title)
        self.scope_all = QRadioButton("Todas as empresas")
        self.scope_all.setChecked(True)
        layout.addWidget(self.scope_all)
        self.scope_visible = QRadioButton(f"Só as que estão na lista do Panorama ({len(visible_company_ids)})")
        self.scope_visible.setEnabled(bool(visible_company_ids))
        layout.addWidget(self.scope_visible)
        manual_row = QHBoxLayout()
        self.scope_manual = QRadioButton("Escolher empresas")
        manual_row.addWidget(self.scope_manual)
        pick_button = make_button("Escolher...", "quiet")
        pick_button.clicked.connect(self._pick_companies)
        manual_row.addWidget(pick_button)
        self.manual_label = QLabel("")
        self.manual_label.setObjectName("Muted")
        manual_row.addWidget(self.manual_label)
        manual_row.addStretch(1)
        layout.addLayout(manual_row)

        buttons = QHBoxLayout()
        cancel_button = make_button("Fechar", "quiet")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(cancel_button)
        buttons.addStretch(1)
        excel_button = make_button("Salvar Excel")
        excel_button.clicked.connect(self._save_excel)
        buttons.addWidget(excel_button)
        pdf_button = make_button("Salvar PDF")
        pdf_button.clicked.connect(self._save_pdf)
        buttons.addWidget(pdf_button)
        print_button = make_button("Imprimir", "primary")
        print_button.clicked.connect(self._print)
        buttons.addWidget(print_button)
        layout.addLayout(buttons)

    def _pick_companies(self) -> None:
        companies = self.services.empresa_service.list_empresas(active_only=False)
        dialog = CompanyMultiSelectDialog(self, companies, self.manual_ids)
        if dialog.exec():
            self.manual_ids = dialog.selected_company_ids
            self.manual_label.setText(f"{len(self.manual_ids)} selecionada(s)")
            self.scope_manual.setChecked(True)

    def _filters(self) -> tuple[list[int] | None, int, int] | None:
        start_id = self.start_combo.currentData()
        end_id = self.end_combo.currentData()
        if start_id is None:
            QMessageBox.warning(self, "Relatório de documentação", "Nenhuma competência cadastrada ainda.")
            return None
        start_index, end_index = self.start_combo.currentIndex(), self.end_combo.currentIndex()
        if end_index < start_index:
            start_id, end_id = end_id, start_id
        if self.scope_visible.isChecked():
            return self.visible_company_ids, start_id, end_id
        if self.scope_manual.isChecked():
            if not self.manual_ids:
                QMessageBox.warning(self, "Relatório de documentação", "Escolha as empresas do relatório.")
                return None
            return self.manual_ids, start_id, end_id
        return None, start_id, end_id

    def _kind(self) -> str:
        return "situacao" if self.kind_situacao.isChecked() else "pendencias"

    def _robo_claude_html(self, periodo_id: int) -> str:
        """Resumo do robo do Onvio e das rodadas do Claude da competencia (o fim do relatorio completo).
        Se algo der errado aqui, o relatorio sai sem essa parte."""
        if not self.robo_claude_check.isChecked():
            return ""
        try:
            periodo = next(p for p in self.services.periodo_service.list_periodos() if p["id"] == periodo_id)
            pasta = Path(str(load_ui_state("onvio:destino", "") or pasta_padrao()))
            dados = coletar_visao_geral(
                self.services.pending_report_service,
                self.services.cobranca_service,
                self.services.rodada_service,
                periodo["ano"],
                periodo["mes"],
                date.today(),
                pasta,
            )
            return build_secao_robo_claude(dados, rodadas_recentes(self.services.rodada_service))
        except Exception:  # noqa: BLE001 - o relatorio principal nao depende disso
            return ""

    def _printable(self) -> dict | None:
        filters = self._filters()
        if filters is None:
            return None
        extra = self._robo_claude_html(filters[2]) if self._kind() == "situacao" else ""
        try:
            return self.services.pending_report_service.build_printable_report(
                *filters,
                kind=self._kind(),
                include_complete=self.include_complete_check.isChecked(),
                extra_html=extra,
            )
        except ValidationError as exc:
            QMessageBox.information(self, "Relatório de documentação", str(exc))
            return None

    def _default_path(self, extension: str) -> str:
        label = self.start_combo.currentText().replace("/", "-")
        prefix = "situacao" if self._kind() == "situacao" else "pendencias"
        return str(get_documents_directory() / f"{prefix}_{label}.{extension}")

    def _print(self) -> None:
        printable = self._printable()
        if printable is None:
            return
        try:
            printed = print_html(printable["html"], self, "Imprimir relatório", landscape=True)
        except Exception as exc:  # noqa: BLE001 - impressora/driver: mostra o motivo em vez de falhar calado
            QMessageBox.critical(self, "Relatório de documentação", f"Não foi possível imprimir:\n{exc}")
            return
        if printed:
            self.accept()

    def _save_pdf(self) -> None:
        printable = self._printable()
        if printable is None:
            return
        file_path, _f = QFileDialog.getSaveFileName(self, "Salvar PDF", self._default_path("pdf"), "PDF (*.pdf)")
        if not file_path:
            return
        try:
            saved = save_html_as_pdf(printable["html"], file_path, landscape=True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Relatório de documentação", f"Não foi possível salvar o PDF:\n{exc}")
            return
        self._offer_to_open(saved, printable["result"])

    def _save_excel(self) -> None:
        filters = self._filters()
        if filters is None:
            return
        file_path, _f = QFileDialog.getSaveFileName(
            self, "Salvar Excel", self._default_path("xlsx"), "Planilha Excel (*.xlsx)"
        )
        if not file_path:
            return
        runner = BlockingTaskRunner(self)
        runner.run(
            "Gerando planilha...",
            lambda: self.services.pending_report_service.export_pending_report(
                file_path, *filters, all_statuses=self._kind() == "situacao"
            ),
            on_success=lambda result: self._offer_to_open(Path(file_path), result),
            on_error=lambda message: QMessageBox.critical(self, "Relatório de documentação", message),
        )

    def _offer_to_open(self, path: Path, result: dict) -> None:
        if self._kind() == "situacao":
            resumo = (
                f'{result["received"]} recebido(s) e {result["pending"]} pendente(s), '
                f'{result["pending_company_count"]} empresa(s) com pendência'
            )
        else:
            resumo = f'{result["rows"]} pendência(s) de {result["pending_company_count"]} empresa(s)'
        answer = QMessageBox.question(
            self,
            "Relatório de documentação",
            f"Relatório salvo: {resumo}.\n\n{path}\n\nDeseja abrir o arquivo agora?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            try:
                open_file_in_default_app(path)
            except ValidationError as exc:
                QMessageBox.warning(self, "Relatório de documentação", str(exc))
        self.accept()


class PanoramaPage(QWidget):
    def __init__(self, services, on_data_changed, on_open_ficha=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.on_data_changed = on_data_changed
        self.on_open_ficha = on_open_ficha
        self._map_company_id: int | None = None
        self.viewmodel = PanoramaViewModel(services)
        self.periods: list[dict] = []
        self.filtered_rows: list[dict] = []
        salvos = load_ui_state("panorama:filtros", {})
        self.column_filters: dict[str, str] = {
            key: str(salvos.get(key) or "") if isinstance(salvos, dict) else "" for key in COLUMN_KEYS
        }

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(
            PageHeader(
                "Panorama",
                "Como está cada empresa no mês escolhido. Clique numa empresa para ver e marcar os documentos dela embaixo.",
            )
        )

        toolbar = ToolbarRow()
        toolbar.add(QLabel("Competência"))
        self.period_combo = QComboBox()
        self.period_combo.setMinimumWidth(130)
        self.period_combo.currentIndexChanged.connect(self._periodo_escolhido)
        toolbar.add(self.period_combo)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Buscar empresa...")
        self.search_edit.setMinimumWidth(220)
        self.search_edit.textChanged.connect(lambda _t: self._apply_filters())
        toolbar.add(self.search_edit)
        self.active_only_check = QCheckBox("Somente ativas")
        self.active_only_check.setChecked(bool(load_ui_state("panorama:somente_ativas", True)))
        self.active_only_check.toggled.connect(lambda c: (save_ui_state("panorama:somente_ativas", bool(c)), self.reload()))
        toolbar.add(self.active_only_check)
        clear_button = make_button("Limpar filtros", "quiet")
        clear_button.clicked.connect(self.clear_filters)
        toolbar.add(clear_button)
        tools_button = make_button("Ferramentas")
        tools_menu = QMenu(tools_button)
        tools_menu.addAction("Relatório de documentação (imprimir, PDF ou Excel)...", self.open_export_dialog)
        tools_menu.addSeparator()
        tools_menu.addAction("Gerar os meses de um ano...", self.generate_year_periods)
        tools_menu.addAction("Excluir os meses de um ano...", self.delete_year_periods)
        tools_menu.addSeparator()
        tools_menu.addAction("Preparar email de cobrança", self.prepare_email)
        tools_menu.addAction("Mensagem de WhatsApp (abre a conversa, se tiver o número)", self.copy_whatsapp)
        tools_menu.addSeparator()
        tools_menu.addAction("Baixar documentos do Onvio...", self.open_onvio_dialog)
        tools_button.setMenu(tools_menu)
        toolbar.add(tools_button)
        toolbar.add_stretch()

        layout.addWidget(toolbar)

        self.summary_label = QLabel("Selecione um período para carregar a conferência mensal.")
        self.summary_label.setObjectName("Muted")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter, 1)

        self.table = QTableWidget(0, len(COLUMN_KEYS))
        self.table.setHorizontalHeaderLabels([COLUMN_HEADINGS[k] for k in COLUMN_KEYS])
        for col, key in enumerate(COLUMN_KEYS):
            tooltip = COLUMN_TOOLTIPS.get(key)
            if tooltip:
                self.table.horizontalHeaderItem(col).setToolTip(tooltip)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setWordWrap(False)
        # Abre na ordem que a pessoa deixou (padrao: codigo crescente) - antes o Qt abria
        # do maior para o menor.
        remember_sort(self.table, "panorama")
        header = self.table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._open_column_filter_menu)
        for col, key in enumerate(COLUMN_KEYS):
            mode = QHeaderView.ResizeMode.ResizeToContents if key != "empresa" else QHeaderView.ResizeMode.Stretch
            header.setSectionResizeMode(col, mode)
        col = COLUMN_KEYS.index
        self.table.setItemDelegateForColumn(col("situacao"), PillDelegate(color_for=_situation_color_by_label, parent=self))
        self.table.setItemDelegateForColumn(col("progresso"), ProgressDelegate(self))
        self.table.setItemDelegateForColumn(
            col("historico"),
            PillDelegate(color_for=lambda text: tokens()["danger"] if text[:1].isdigit() else None, parent=self),
        )
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        self.table.doubleClicked.connect(lambda _index: self.year_map.setFocus())
        splitter.addWidget(self.table)

        detail_card = Card()
        detail_layout = QVBoxLayout(detail_card)
        detail_layout.setContentsMargins(14, 10, 14, 10)
        detail_layout.setSpacing(8)
        detail_header = QHBoxLayout()
        self.detail_title = QLabel("Clique numa empresa acima para ver e marcar os documentos dela.")
        self.detail_title.setStyleSheet("font-weight: 600;")
        self.detail_title.setWordWrap(True)
        detail_header.addWidget(self.detail_title, 1)
        folder_button = make_button("Pasta da empresa...", "quiet")
        folder_button.setToolTip("Escolher a pasta no computador onde ficam os documentos desta empresa")
        folder_button.clicked.connect(self.choose_company_directory)
        detail_header.addWidget(folder_button)
        open_ficha_button = make_button("Abrir na ficha")
        open_ficha_button.setToolTip("Abre a ficha da empresa, já no documento e mês selecionados no mapa")
        open_ficha_button.clicked.connect(self.open_selected_ficha)
        detail_header.addWidget(open_ficha_button)
        detail_layout.addLayout(detail_header)

        # Barra de marcacao: vale para os quadradinhos selecionados no mapa.
        marcar = QHBoxLayout()
        marcar.setSpacing(6)
        self.selection_label = QLabel()
        self.selection_label.setObjectName("Muted")
        marcar.addWidget(self.selection_label, 1)
        self.mark_buttons: list = []
        for texto, status, atalhos, dica in MARK_ACTIONS:
            button = make_button(texto)
            button.setIcon(status_icon(status))
            button.setToolTip(f"{dica} (atalho: {' ou '.join(atalhos)})")
            button.clicked.connect(lambda _c=False, st=status: self.mark_selection(st))
            marcar.addWidget(button)
            self.mark_buttons.append((button, status))
            for atalho in atalhos:
                shortcut = QShortcut(QKeySequence(atalho if atalho != "Del" else "Delete"), detail_card)
                shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
                shortcut.activated.connect(lambda st=status: self.mark_selection(st))
        self._undo: list[dict] = []  # ultimas marcacoes no mapa, para o Ctrl+Z
        desfazer = QShortcut(QKeySequence(QKeySequence.StandardKey.Undo), detail_card)
        desfazer.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        desfazer.activated.connect(self.undo_last)
        self.resolver_button = make_button("Resolver...", "primary")
        self.resolver_button.setToolTip(
            "Registrar o que aconteceu com observação: chegou errado, cliente prometeu, precisa de uma pessoa..."
        )
        self.resolver_button.clicked.connect(self.resolve_selection)
        marcar.addWidget(self.resolver_button)
        detail_layout.addLayout(marcar)

        detail_split = QSplitter(Qt.Orientation.Horizontal)
        mapa_box = QWidget()
        mapa_layout = QVBoxLayout(mapa_box)
        mapa_layout.setContentsMargins(0, 0, 0, 0)
        mapa_layout.setSpacing(4)
        self.year_map = YearMap(multi_select=True)
        self.year_map.selection_changed.connect(self._on_map_selection_changed)
        self.year_map.context_menu_requested.connect(self._open_mark_menu)
        self.year_map.fill_requested.connect(self.fill_cells)
        self.year_map.paste_requested.connect(self.paste_cells)
        mapa_layout.addWidget(map_scroll_area(self.year_map), 1)
        detail_split.addWidget(mapa_box)
        self.detail_browser = DocLinkBrowser()
        detail_split.addWidget(self.detail_browser)
        detail_split.setSizes([800, 380])
        detail_layout.addWidget(detail_split, 1)
        detail_layout.addWidget(MapLegend())
        splitter.addWidget(detail_card)
        splitter.setSizes([250, 470])


    # Carregamento

    def refresh_data(self) -> None:
        # As cores dos icones seguem o tema atual (claro/escuro).
        for button, status in self.mark_buttons:
            button.setIcon(status_icon(status))
        self._refresh_periods()
        self.reload()

    def _periodo_escolhido(self, _index: int) -> None:
        if self.period_combo.currentText():
            save_ui_state(PERIODO_KEY, self.period_combo.currentText())
        self.reload()

    def _refresh_periods(self) -> None:
        selected = self.period_combo.currentData()
        self.periods = self.services.periodo_service.list_periodos()
        self.period_combo.blockSignals(True)
        self.period_combo.clear()
        for periodo in sorted(self.periods, key=lambda p: (p["ano"], p["mes"])):
            self.period_combo.addItem(f'{periodo["mes"]:02d}/{periodo["ano"]}', periodo["id"])
        salva = self.period_combo.findText(str(load_ui_state(PERIODO_KEY, "") or ""))
        if selected is not None and self.period_combo.findData(selected) >= 0:
            self.period_combo.setCurrentIndex(self.period_combo.findData(selected))
        elif salva >= 0:
            # A ultima competencia escolhida volta quando o sistema abre de novo.
            self.period_combo.setCurrentIndex(salva)
        else:
            now = datetime.now()
            current = next((p for p in self.periods if p["ano"] == now.year and p["mes"] == now.month), None)
            if current:
                self.period_combo.setCurrentIndex(self.period_combo.findData(current["id"]))
            elif self.period_combo.count():
                self.period_combo.setCurrentIndex(self.period_combo.count() - 1)
        self.period_combo.blockSignals(False)

    def reload(self) -> None:
        period_id = self.period_combo.currentData()
        if period_id is None:
            self.table.setRowCount(0)
            self.summary_label.setText("Cadastre períodos (Ferramentas > Gerar períodos do ano) para começar.")
            return
        self.viewmodel.load(period_id, self.active_only_check.isChecked())
        self._apply_filters()

    # Filtros

    def clear_filters(self) -> None:
        self.search_edit.clear()
        self.column_filters = {key: "" for key in COLUMN_KEYS}
        save_ui_state("panorama:filtros", self.column_filters)
        self._apply_filters()

    def _row_display_values(self, row: dict) -> dict[str, str]:
        situacao_label = UI_SITUATION_LABELS.get(row["month_status_key"], row.get("situacao") or "-")
        historico_text = _previous_months_text(row.get("previous_period_items") or [])
        ultima = "-"
        if row.get("ultima_marcacao_em"):
            # updated_at e gravado em UTC (docflow_utc_now) - exibe no horario local.
            ultima = format_utc_timestamp(str(row["ultima_marcacao_em"]))
            if row.get("ultima_marcacao_por"):
                ultima += f' - {row["ultima_marcacao_por"]}'
        return {
            "codigo": str(row["codigo_empresa"]),
            "empresa": row["nome_empresa"] + ("" if row["ativa"] else " [Inativa]"),
            "situacao": situacao_label,
            "progresso": f'{row["marcados"]}/{row["total_cobravel"]}',
            "historico": historico_text,
            "ultima_marcacao": ultima,
        }

    def _apply_filters(self) -> None:
        search = self.search_edit.text().strip().casefold()
        self.filtered_rows = []
        for row in self.viewmodel.rows:
            values = self._row_display_values(row)
            if search and search not in f'{values["codigo"]} {values["empresa"]}'.casefold():
                continue
            if any(
                filter_value and values[key] != filter_value
                for key, filter_value in self.column_filters.items()
            ):
                continue
            self.filtered_rows.append(row)
        self._populate_table()
        self._update_summary()

    def _open_column_filter_menu(self, pos) -> None:
        header = self.table.horizontalHeader()
        col = header.logicalIndexAt(pos)
        if col < 0:
            return
        key = COLUMN_KEYS[col]
        menu = QMenu(self)
        current = self.column_filters.get(key, "")

        def set_filter(value: str) -> None:
            self.column_filters[key] = value
            save_ui_state("panorama:filtros", self.column_filters)  # o filtro fica para a proxima vez
            self._apply_filters()

        action_all = menu.addAction("Todos")
        action_all.setCheckable(True)
        action_all.setChecked(not current)
        action_all.triggered.connect(lambda: set_filter(""))
        menu.addSeparator()

        distinct = sorted({self._row_display_values(row)[key] for row in self.viewmodel.rows})
        for value in distinct[:40]:
            action = menu.addAction(value)
            action.setCheckable(True)
            action.setChecked(value == current)
            action.triggered.connect(lambda _checked=False, v=value: set_filter(v))
        menu.exec(header.mapToGlobal(pos))

    def _populate_table(self) -> None:
        selected = self._selected_row()
        selected_id = selected["empresa_id"] if selected else self._map_company_id
        self.table.blockSignals(True)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for row in self.filtered_rows:
            values = self._row_display_values(row)
            table_row = self.table.rowCount()
            self.table.insertRow(table_row)
            for col, key in enumerate(COLUMN_KEYS):
                item = _SortableItem(values[key])
                if key == "codigo":
                    item.setData(Qt.ItemDataRole.UserRole, row["empresa_id"])
                    item.setData(SORT_ROLE, int(row["codigo_empresa"]))
                if key == "situacao":
                    item.setForeground(QColor(situation_color(row["month_status_key"])))
                if key == "progresso":
                    t = tokens()
                    recebidos = int(row.get("recebidos") or 0)
                    pendentes = int(row.get("pendentes") or 0)
                    outros = max(int(row.get("marcados") or 0) - recebidos - pendentes, 0)
                    item.setData(
                        PROGRESS_ROLE,
                        (
                            [(recebidos, t["success"]), (outros, t["muted"]), (pendentes, t["danger"])],
                            int(row.get("total_cobravel") or 0),
                        ),
                    )
                    item.setToolTip(
                        f"{recebidos} recebido(s), {pendentes} pendente(s), {outros} encerrado(s)/não cobrar, "
                        f'{int(row.get("faltando") or 0)} sem marcação'
                    )
                if key == "historico":
                    previous_items = row.get("previous_period_items") or []
                    item.setData(SORT_ROLE, len(previous_items))
                    item.setToolTip(_previous_months_tooltip(previous_items))
                    if previous_items:
                        item.setForeground(QColor(situation_color(MONTH_STATUS_OVERDUE)))
                self.table.setItem(table_row, col, item)
        self.table.setSortingEnabled(True)
        self.table.blockSignals(False)
        # Recarregar (ex: depois de marcar um documento) mantem a empresa aberta embaixo.
        for table_row in range(self.table.rowCount()):
            item = self.table.item(table_row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == selected_id:
                self.table.selectRow(table_row)
                break
        else:
            self._clear_detail()

    def _update_summary(self) -> None:
        total = len(self.viewmodel.rows)
        counts = self.viewmodel.count_month_statuses(self.filtered_rows)
        parts = [f"{len(self.filtered_rows)} de {total} empresa(s) em {self.period_combo.currentText()}."]
        parts.extend(
            f"{label}: {counts[key]}" for key, label in UI_SITUATION_LABELS.items() if counts.get(key)
        )
        with_previous = sum(1 for row in self.filtered_rows if row.get("previous_period_items"))
        parts.append(f"Com meses anteriores em aberto: {with_previous}")
        self.summary_label.setText(" | ".join(parts))

    # Detalhe

    def _selected_row(self) -> dict | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        if item is None:
            return None
        empresa_id = int(item.data(Qt.ItemDataRole.UserRole))
        return next((r for r in self.viewmodel.rows if r["empresa_id"] == empresa_id), None)

    def _clear_detail(self) -> None:
        self._map_company_id = None
        self.detail_title.setText("Clique numa empresa acima para ver e marcar os documentos dela.")
        self.year_map.set_data({"periodos": [], "documentos": []})
        self.detail_browser.clear()

    def _on_row_selected(self) -> None:
        row = self._selected_row()
        if not row:
            return
        situacao_label = UI_SITUATION_LABELS.get(row["month_status_key"], "-")
        self.detail_title.setText(
            f'{row["codigo_empresa"]} - {row["nome_empresa"]}  |  {self.period_combo.currentText()}: {situacao_label}  |  '
            f'Meses anteriores em aberto: {_previous_months_text(row.get("previous_period_items") or [])}'
        )
        mesma_empresa = self._map_company_id == row["empresa_id"]
        self._map_company_id = row["empresa_id"]
        self._reload_map(keep_selection=mesma_empresa)

    def _reload_map(self, keep_selection: bool = False) -> None:
        if self._map_company_id is None:
            return
        try:
            mapa = self.services.cobranca_service.mapa_empresa(
                self._map_company_id, ate_periodo_id=self.period_combo.currentData()
            )
        except ValidationError:
            mapa = {"periodos": [], "documentos": []}
        self.year_map.set_data(mapa, SITUACAO_LABELS, keep_selection=keep_selection)

    def _on_map_selection_changed(self) -> None:
        celulas = self.year_map.selected_cells()
        tem = bool(celulas)
        for button, _status in self.mark_buttons:
            button.setEnabled(tem)
        self.resolver_button.setEnabled(tem)
        if not celulas:
            self.selection_label.setText(
                "Clique num quadradinho para marcar. Vários: Ctrl ou Shift, ou clique no mês ou no nome do documento."
            )
            row = self._selected_row()
            self.detail_browser.setHtml(self._build_detail_html(row) if row else "")
            return
        if len(celulas) == 1:
            celula = celulas[0]
            self.selection_label.setText(f'{celula["nome_documento"]} - {celula["competencia"]}')
            self.detail_browser.setHtml(self._cell_detail_html(celula))
            return
        meses = len({c["periodo_id"] for c in celulas})
        docs = len({c["documento_id"] for c in celulas})
        self.selection_label.setText(f"{len(celulas)} quadradinhos selecionados ({docs} documento(s), {meses} mês(es))")
        t = tokens()
        linhas = "".join(
            f'<div>{escape(c["nome_documento"])} <span style="color:{t["muted"]};">({c["competencia"]})</span></div>'
            for c in celulas[:40]
        )
        extra = f"<div>... e mais {len(celulas) - 40}</div>" if len(celulas) > 40 else ""
        self.detail_browser.setHtml(
            f"<p><b>{len(celulas)} selecionados.</b> Use os botões acima (ou R, P, E, N, Del) para marcar "
            f"todos de uma vez, ou Resolver para registrar o que aconteceu.</p>{linhas}{extra}"
        )

    def _cell_detail_html(self, celula: dict) -> str:
        t = tokens()
        muted = f'style="color:{t["muted"]};"'
        status = {"Nao cobrar": "Não cobrar"}.get(celula["status"], celula["status"]) or "Sem marcação"
        bg, fg = status_colors(celula["status"])
        parts = [
            f'<div style="font-size:12pt; font-weight:600;">{escape(celula["nome_documento"])} '
            f'<span {muted}>({celula["competencia"]})</span></div>',
            f'<div {muted}>{escape(celula.get("tipo") or "")}</div>',
            f'<div style="margin-top:6px;"><span style="background:{bg}; color:{fg}; padding:2px 10px;">'
            f"&nbsp;{status}&nbsp;</span>"
            + (
                f' <span {muted}>marcado por {escape(celula.get("marcado_por") or "Sistema")} em '
                f'{escape(format_utc_timestamp(str(celula["marcado_em"])))}</span>'
                if celula.get("marcado_em")
                else ""
            )
            + "</div>",
        ]
        try:
            registro = self.services.cobranca_service.registro_documento(celula["documento_id"])
        except ValidationError:
            registro = None
        if registro and registro.get("meios_recebimento"):
            parts.append(f'<div><b>Chega por:</b> {escape(registro["meios_recebimento"])}</div>')
        if registro and registro.get("observacao"):
            parts.append(f'<div><b>Observação:</b> {escape(registro["observacao"])}</div>')
        competencia = next(
            (c for c in (registro or {}).get("competencias", []) if c.get("periodo_id") == celula["periodo_id"]), None
        )
        if competencia and competencia.get("situacao"):
            parts.append(f'<div><b>Cobrança:</b> {escape(situacao_label(competencia["situacao"]))}</div>')
        if competencia and (competencia["caminho"] or competencia["contatos"] or competencia["verificacoes"]):
            parts.append("<div style='margin-top:10px; font-weight:600;'>O que aconteceu</div>")
            parts.append(competencia_timeline_html(competencia))
        else:
            parts.append(f"<p {muted}>Nenhuma cobrança ou verificação registrada neste mês.</p>")
        return "".join(parts)

    def _build_detail_html(self, row: dict) -> str:
        t = tokens()
        parts = [
            f'<div style="font-weight:600;">Resumo de {self.period_combo.currentText()}</div>',
            f'<div>Recebidos: {row["recebidos"]} &middot; Pendentes: {row["pendentes"]} &middot; '
            f'Sem marcação: {row["faltando"]} &middot; Marcados {row["marcados"]} de {row["total_cobravel"]}</div>',
        ]
        previous_items = row.get("previous_period_items") or []
        parts.append('<div style="font-weight:600; margin-top:10px;">Em aberto de meses anteriores</div>')
        if not previous_items:
            parts.append(f'<div style="color:{t["success"]};">Nada em aberto de meses anteriores.</div>')
        else:
            for period_item in previous_items:
                nomes = ", ".join(escape(d.get("nome_documento", "-")) for d in period_item["documents"])
                parts.append(
                    f'<div><b>{_short_period_label(period_item["periodo_label"])}</b> '
                    f'<span style="color:{t["muted"]};">{nomes}</span></div>'
                )
        parts.append(
            f'<p style="color:{t["muted"]}; margin-top:10px;">Clique num quadradinho do mapa para ver o '
            "histórico daquele documento e marcar o status.</p>"
        )
        return "".join(parts)

    # Marcacao

    def _company_is_active(self) -> bool:
        row = self._selected_row()
        if row and not row.get("ativa", True):
            QMessageBox.warning(
                self, "Panorama", "Esta empresa está inativa. Reative-a em Empresas para marcar documentos."
            )
            return False
        return True

    def mark_selection(self, status: str) -> None:
        celulas = self.year_map.selected_cells()
        if not celulas or not self._company_is_active():
            return
        rotulo = {"": "Limpar", "Nao cobrar": "Não cobrar"}.get(status, status)
        if status == "Encerrado":
            pergunta = (
                f"Marcar {len(celulas)} como Encerrado? O documento deixa de ser cobrado a partir "
                "desse mês (os meses seguintes ficam bloqueados)."
            )
            if QMessageBox.question(self, "Panorama", pergunta) != QMessageBox.StandardButton.Yes:
                return
        elif status == "" and len(celulas) > 1:
            if QMessageBox.question(self, "Panorama", f"Limpar o status de {len(celulas)} quadradinhos?") != QMessageBox.StandardButton.Yes:
                return
        pares = [(c["documento_id"], c["periodo_id"]) for c in celulas]
        antes = self._snapshot([(d, p, status) for d, p in pares])
        try:
            self.services.status_service.update_status_many(pares, status)
        except ValidationError as exc:
            QMessageBox.critical(self, "Panorama", str(exc))
            return
        self._push_undo(f"{rotulo} em {len(celulas)} quadradinho(s)", antes)
        self.selection_label.setText(f"{rotulo}: {len(celulas)} marcado(s). Ctrl+Z desfaz.")
        self.on_data_changed()

    def fill_cells(self, status: str, celulas: list) -> None:
        """Alca de preencher do mapa: copia o status do quadradinho para os do caminho."""
        if not celulas or not self._company_is_active():
            return
        antes = self._snapshot([(d, p, status) for d, p in celulas])
        try:
            self.services.status_service.update_status_many(celulas, status)
        except ValidationError as exc:
            QMessageBox.critical(self, "Panorama", str(exc))
            return
        rotulo = {"Nao cobrar": "Não cobrar"}.get(status, status)
        self._push_undo(f"preencher {len(celulas)} quadradinho(s)", antes)
        self.selection_label.setText(f"{rotulo}: {len(celulas)} preenchido(s) arrastando. Ctrl+Z desfaz.")
        self.on_data_changed()

    def paste_cells(self, texto: str) -> None:
        """Ctrl+V no mapa: cola os status copiados (do proprio mapa ou de uma planilha)."""
        if not self._company_is_active():
            return
        try:
            plano = self.year_map.paste_plan(texto)
        except ValidationError as exc:
            QMessageBox.warning(self, "Colar", str(exc))
            return
        if not plano:
            QMessageBox.information(self, "Colar", "Nenhum quadradinho daqui recebe o que foi copiado.")
            return
        encerrar = sum(1 for _d, _p, status in plano if status == "Encerrado")
        if encerrar and QMessageBox.question(
            self,
            "Colar",
            f"Isso marca {encerrar} quadradinho(s) como Encerrado: o documento deixa de ser cobrado a partir "
            "daquele mês. Continuar?",
        ) != QMessageBox.StandardButton.Yes:
            return
        antes = self._snapshot(plano)
        por_status: dict[str, list] = {}
        for documento_id, periodo_id, status in plano:
            por_status.setdefault(status, []).append((documento_id, periodo_id))
        try:
            # Encerrado por ultimo: ele bloqueia os meses seguintes do documento.
            for status in sorted(por_status, key=lambda s: s == "Encerrado"):
                self.services.status_service.update_status_many(por_status[status], status)
        except ValidationError as exc:
            QMessageBox.critical(self, "Colar", str(exc))
            self._push_undo("colar (incompleto)", antes)
            self.on_data_changed()
            return
        self._push_undo(f"colar em {len(plano)} quadradinho(s)", antes)
        self.year_map.selection = {(d, p) for d, p, _s in plano}
        self.selection_label.setText(f"Colado em {len(plano)} quadradinho(s). Ctrl+Z desfaz.")
        self.on_data_changed()

    # Desfazer (Ctrl+Z)

    UNDO_LIMIT = 20

    def _snapshot(self, plano: list) -> list[tuple[int, int, str]]:
        """Status de antes, do que o plano [(documento_id, periodo_id, novo_status)] vai mexer.
        Encerrado apaga os meses seguintes do documento, entao eles entram tambem."""
        alvos = {(int(d), int(p)) for d, p, _s in plano}
        encerra = {int(d): int(p) for d, p, s in plano if s == "Encerrado"}
        antes = []
        for doc in self.year_map.documentos:
            depois_de = None
            for celula in doc["celulas"]:
                chave = (doc["documento_id"], celula["periodo_id"])
                if depois_de is None and encerra.get(doc["documento_id"]) == celula["periodo_id"]:
                    depois_de = True
                    antes.append((*chave, celula["status"] or ""))
                    continue
                if chave in alvos or (depois_de and celula["disponivel"] and celula["status"]):
                    antes.append((*chave, celula["status"] or ""))
        return antes

    def _push_undo(self, rotulo: str, antes: list) -> None:
        if not antes:
            return
        self._undo.append({"rotulo": rotulo, "celulas": antes})
        del self._undo[: -self.UNDO_LIMIT]

    def undo_last(self) -> None:
        """Volta os quadradinhos da ultima marcacao feita no mapa para como estavam."""
        if not self._undo:
            self.selection_label.setText("Nada para desfazer.")
            return
        acao = self._undo.pop()
        ordem = {p["id"]: (p["ano"], p["mes"]) for p in self.periods}
        grupos: dict[tuple[int, str], list] = {}
        for documento_id, periodo_id, status in acao["celulas"]:
            grupos.setdefault((periodo_id, status), []).append((documento_id, periodo_id))
        try:
            # Mes a mes, do mais antigo: tirar um Encerrado libera os meses seguintes antes de
            # eles receberem o status antigo de volta.
            for periodo_id, status in sorted(grupos, key=lambda g: (ordem.get(g[0], (0, 0)), g[1] == "Encerrado")):
                self.services.status_service.update_status_many(grupos[(periodo_id, status)], status)
        except ValidationError as exc:
            QMessageBox.critical(self, "Desfazer", str(exc))
            self.on_data_changed()
            return
        self.year_map.selection = {(d, p) for d, p, _s in acao["celulas"]}
        self.selection_label.setText(f'Desfeito: {acao["rotulo"]}.')
        self.on_data_changed()

    def resolve_selection(self) -> None:
        celulas = self.year_map.selected_cells()
        row = self._selected_row()
        if not celulas or not row or not self._company_is_active():
            return
        empresa = f'{row["codigo_empresa"]} - {row["nome_empresa"]}'
        pasta = None
        try:
            pasta = self.services.empresa_service.get_empresa(row["empresa_id"]).get("diretorio_documentos")
        except ValidationError:
            pass
        dialog = ResolverDialog(
            self.services,
            [
                {
                    "documento_id": c["documento_id"],
                    "periodo_id": c["periodo_id"],
                    "nome_documento": c["nome_documento"],
                    "competencia": c["competencia"],
                    "empresa": empresa,
                }
                for c in celulas
            ],
            permitir_devolver=all(c.get("situacao") == "precisa_pessoa" for c in celulas),
            pasta_inicial=pasta,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.on_data_changed()

    def _open_mark_menu(self, global_pos) -> None:
        menu = QMenu(self)
        for texto, status, atalhos, _dica in MARK_ACTIONS:
            menu.addAction(status_icon(status), f"{texto}\t{atalhos[0]}", lambda st=status: self.mark_selection(st))
        menu.addSeparator()
        menu.addAction("Copiar\tCtrl+C", self.year_map.copy_selection)
        menu.addAction("Colar\tCtrl+V", lambda: self.paste_cells(QGuiApplication.clipboard().text()))
        if self._undo:
            menu.addAction(f'Desfazer {self._undo[-1]["rotulo"]}\tCtrl+Z', self.undo_last)
        menu.addSeparator()
        menu.addAction("Resolver (com observação)...", self.resolve_selection)
        celulas = self.year_map.selected_cells()
        if len(celulas) == 1:
            menu.addAction("Abrir na ficha", self.open_selected_ficha)
        menu.exec(global_pos)

    def open_selected_ficha(self) -> None:
        row = self._selected_row()
        if not row:
            QMessageBox.warning(self, "Panorama", "Selecione uma empresa primeiro.")
            return
        if not self.on_open_ficha:
            return
        celulas = self.year_map.selected_cells()
        if celulas:
            self.on_open_ficha(row["empresa_id"], celulas[0]["documento_id"], celulas[0]["competencia"])
        else:
            self.on_open_ficha(row["empresa_id"])

    def choose_company_directory(self) -> None:
        row = self._selected_row()
        if not row:
            QMessageBox.warning(self, "Panorama", "Selecione uma empresa primeiro.")
            return
        company = self.services.empresa_service.get_empresa(row["empresa_id"])
        current = str(company.get("diretorio_documentos") or "").strip()
        initial = current if current and Path(current).is_dir() else str(Path.home())
        selected = QFileDialog.getExistingDirectory(self, f'Escolha a pasta para "{company["nome_empresa"]}"', initial)
        if not selected:
            return
        self.services.empresa_service.set_empresa_directory(row["empresa_id"], selected)
        QMessageBox.information(self, "Panorama", f"Pasta da empresa definida:\n{selected}")

    # Ferramentas

    def open_export_dialog(self) -> None:
        visible_ids = [row["empresa_id"] for row in self.filtered_rows]
        ExportReportDialog(self.services, self.period_combo.currentData(), visible_ids, self).exec()

    def open_onvio_dialog(self) -> None:
        from documentos_empresa_app.qt_ui.dialogs.onvio_dialog import OnvioDownloadDialog

        competencia = None
        texto = self.period_combo.currentText().strip()[:7]
        if len(texto) == 7 and texto[2] == "/" and texto.replace("/", "").isdigit():
            competencia = (int(texto[3:]), int(texto[:2]))
        OnvioDownloadDialog(self.services, competencia, self).exec()

    def generate_year_periods(self) -> None:
        year, confirmed = QInputDialog.getInt(
            self, "Gerar períodos", "Informe o ano para gerar os 12 períodos:", datetime.now().year, 2000, 2100
        )
        if not confirmed:
            return
        result = self.services.periodo_service.generate_year(year)
        QMessageBox.information(
            self,
            "Gerar períodos",
            f'Ano {result["ano"]}: {result["created"]} período(s) criados, {result["existing"]} já existiam.',
        )
        self.on_data_changed()

    def delete_year_periods(self) -> None:
        years = self.services.periodo_service.list_available_years()
        if not years:
            QMessageBox.information(self, "Excluir ano", "Nenhum ano cadastrado.")
            return
        year_label, confirmed = QInputDialog.getItem(
            self, "Excluir ano", "Escolha o ano para excluir:", [str(y) for y in years], len(years) - 1, False
        )
        if not confirmed:
            return
        year = int(year_label)
        answer = QMessageBox.question(
            self,
            "Excluir ano",
            f"Excluir todos os períodos de {year}? Os status mensais desse ano serao apagados. "
            "Empresas, tipos e documentos base são mantidos.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        result = self.services.periodo_service.delete_year(year)
        QMessageBox.information(self, "Excluir ano", f'{result["deleted"]} período(s) de {result["ano"]} excluidos.')
        self.on_data_changed()

    def prepare_email(self) -> None:
        row = self._selected_row()
        queue_item = (row or {}).get("queue_item")
        if not queue_item:
            QMessageBox.warning(self, "Panorama", "Selecione uma empresa com cobrança em aberto.")
            return
        try:
            draft = self.services.collection_service.build_email_draft(queue_item)
            handler = open_email_draft(draft["to"], draft["subject"], draft["body"])
        except ValidationError as exc:
            QMessageBox.critical(self, "Panorama", str(exc))
            return
        QMessageBox.information(self, "Panorama", f"Rascunho aberto em: {handler}")

    def copy_whatsapp(self) -> None:
        row = self._selected_row()
        queue_item = (row or {}).get("queue_item")
        if not queue_item:
            QMessageBox.warning(self, "Panorama", "Selecione uma empresa com cobrança em aberto.")
            return
        message = self.services.collection_service.build_whatsapp_message(queue_item)
        QGuiApplication.clipboard().setText(message)
        numero = self.services.empresa_service.get_empresa(queue_item["empresa_id"]).get("whatsapp")
        if numero:
            QDesktopServices.openUrl(QUrl.fromEncoded(build_link(numero, message).encode("ascii")))
            return
        QMessageBox.information(
            self,
            "Panorama",
            "Mensagem copiada para a area de transferencia. Cadastre o WhatsApp da empresa (tela Empresas) "
            "para a conversa abrir pronta.",
        )
