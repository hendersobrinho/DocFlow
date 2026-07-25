from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication
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
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.icons import situation_icon
from documentos_empresa_app.qt_ui.theme import situation_color, status_colors, tokens
from documentos_empresa_app.qt_ui.viewmodels import (
    MONTH_STATUS_OVERDUE,
    PanoramaViewModel,
    UI_SITUATION_LABELS,
)
from documentos_empresa_app.qt_ui.dialogs.company_dialogs import CompanyMultiSelectDialog
from documentos_empresa_app.qt_ui.widgets.common import Card, PageHeader, ToolbarRow, make_button
from documentos_empresa_app.qt_ui.workers import BlockingTaskRunner
from documentos_empresa_app.services.collection_service import CollectionService
from documentos_empresa_app.utils.common import MONTH_NAMES, ValidationError, parse_period_label
from documentos_empresa_app.utils.helpers import open_email_draft

COLUMN_KEYS = ("codigo", "empresa", "situacao", "progresso", "cobranca", "historico", "ultima_marcacao")
COLUMN_HEADINGS = {
    "codigo": "Codigo",
    "empresa": "Empresa",
    "situacao": "Situacao do mes",
    "progresso": "Progresso",
    "cobranca": "Cobranca geral",
    "historico": "Pendencias anteriores",
    "ultima_marcacao": "Ultima marcacao",
}
COLUMN_TOOLTIPS = {
    "situacao": "Status apenas do mes selecionado no filtro de periodo acima.",
    "cobranca": (
        "Status combinando o mes selecionado com qualquer pendencia de meses anteriores.\n"
        "Fica 'Em atraso' se houver documento pendente de QUALQUER mes anterior ao selecionado, "
        "mesmo que o mes atual ainda esteja dentro do prazo de cobranca.\n"
        "Sem pendencia anterior, reflete o prazo de cobranca do proprio mes selecionado."
    ),
    "historico": "Lista os meses anteriores ao selecionado que ainda tem documento pendente.",
}


class ExportReportDialog(QDialog):
    def __init__(self, services, default_period_label: str, visible_company_ids: list[int], parent=None) -> None:
        super().__init__(parent)
        self.services = services
        self.visible_company_ids = visible_company_ids
        self.setWindowTitle("Exportar relatorio de pendencias")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        period_row = QHBoxLayout()
        period_row.addWidget(QLabel("Periodo inicial (MM/AAAA)"))
        self.start_edit = QLineEdit(default_period_label)
        self.start_edit.setMaximumWidth(110)
        period_row.addWidget(self.start_edit)
        period_row.addWidget(QLabel("final (opcional)"))
        self.end_edit = QLineEdit()
        self.end_edit.setMaximumWidth(110)
        period_row.addWidget(self.end_edit)
        period_row.addStretch(1)
        layout.addLayout(period_row)

        layout.addWidget(QLabel("Empresas:"))
        self.scope_all = QRadioButton("Todas as empresas")
        self.scope_all.setChecked(True)
        layout.addWidget(self.scope_all)
        self.scope_visible = QRadioButton(f"Somente empresas visiveis no Panorama ({len(visible_company_ids)})")
        self.scope_visible.setEnabled(bool(visible_company_ids))
        layout.addWidget(self.scope_visible)
        manual_row = QHBoxLayout()
        self.scope_manual = QRadioButton("Selecionar manualmente")
        manual_row.addWidget(self.scope_manual)
        pick_button = make_button("Escolher...")
        pick_button.clicked.connect(self._pick_companies)
        manual_row.addWidget(pick_button)
        manual_row.addStretch(1)
        layout.addLayout(manual_row)
        self.manual_ids: list[int] = []
        self.manual_label = QLabel("Nenhuma empresa selecionada manualmente.")
        self.manual_label.setObjectName("Muted")
        layout.addWidget(self.manual_label)

        layout.addWidget(QLabel("Formato:"))
        format_row = QHBoxLayout()
        self.format_pdf = QRadioButton("PDF")
        self.format_pdf.setChecked(True)
        format_row.addWidget(self.format_pdf)
        self.format_excel = QRadioButton("Excel")
        format_row.addWidget(self.format_excel)
        format_row.addStretch(1)
        layout.addLayout(format_row)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel_button = make_button("Cancelar", "quiet")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(cancel_button)
        export_button = make_button("Exportar", "primary")
        export_button.clicked.connect(self._export)
        buttons.addWidget(export_button)
        layout.addLayout(buttons)

    def _pick_companies(self) -> None:
        companies = self.services.empresa_service.list_empresas(active_only=False)
        dialog = CompanyMultiSelectDialog(self, companies, self.manual_ids)
        if dialog.exec():
            self.manual_ids = dialog.selected_company_ids
            self.manual_label.setText(f"{len(self.manual_ids)} empresa(s) selecionada(s) manualmente.")
            self.scope_manual.setChecked(True)

    def _resolve_period_id(self, raw: str) -> int | None:
        parsed = parse_period_label(raw)
        if not parsed:
            return None
        year, month = parsed
        periodo = self.services.periodo_service.list_periodos()
        match = next((p for p in periodo if p["ano"] == year and p["mes"] == month), None)
        return match["id"] if match else None

    def _export(self) -> None:
        start_id = self._resolve_period_id(self.start_edit.text())
        if start_id is None:
            QMessageBox.warning(self, "Exportar relatorio", "Informe um periodo inicial valido e cadastrado.")
            return
        end_raw = self.end_edit.text().strip()
        end_id = self._resolve_period_id(end_raw) if end_raw else start_id
        if end_id is None:
            QMessageBox.warning(self, "Exportar relatorio", "Informe um periodo final valido e cadastrado.")
            return

        if self.scope_visible.isChecked():
            company_ids: list[int] | None = self.visible_company_ids
        elif self.scope_manual.isChecked():
            if not self.manual_ids:
                QMessageBox.warning(self, "Exportar relatorio", "Selecione as empresas manualmente.")
                return
            company_ids = self.manual_ids
        else:
            company_ids = None

        if self.format_pdf.isChecked():
            file_path, _f = QFileDialog.getSaveFileName(
                self, "Salvar relatorio", "relatorio_pendencias.pdf", "PDF (*.pdf)"
            )
            exporter = self.services.pending_report_service.export_pending_report_pdf
        else:
            file_path, _f = QFileDialog.getSaveFileName(
                self, "Salvar relatorio", "relatorio_pendencias.xlsx", "Planilha Excel (*.xlsx)"
            )
            exporter = self.services.pending_report_service.export_pending_report
        if not file_path:
            return

        runner = BlockingTaskRunner(self)
        runner.run(
            "Gerando relatorio de pendencias...",
            lambda: exporter(file_path, company_ids, start_id, end_id),
            on_success=self._on_export_finished,
            on_error=lambda message: QMessageBox.critical(self, "Exportar relatorio", message),
        )

    def _on_export_finished(self, result: dict) -> None:
        QMessageBox.information(
            self,
            "Exportar relatorio",
            (
                f'Relatorio gerado com sucesso.\n\nEmpresas consideradas: {result["company_count"]}\n'
                f'Empresas com pendencias: {result["pending_company_count"]}\nLinhas: {result["rows"]}'
            ),
        )
        self.accept()


class PanoramaPage(QWidget):
    def __init__(self, services, on_data_changed, on_open_control=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.on_data_changed = on_data_changed
        self.on_open_control = on_open_control
        self.viewmodel = PanoramaViewModel(services)
        self.periods: list[dict] = []
        self.filtered_rows: list[dict] = []
        self.column_filters: dict[str, str] = {key: "" for key in COLUMN_KEYS}
        self.global_settings: dict | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(PageHeader("Panorama", "Conferencia operacional de todas as empresas na competencia."))

        toolbar = ToolbarRow()
        toolbar.add(QLabel("Competencia"))
        self.period_combo = QComboBox()
        self.period_combo.setMinimumWidth(130)
        self.period_combo.currentIndexChanged.connect(lambda _i: self.reload())
        toolbar.add(self.period_combo)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Buscar empresa...")
        self.search_edit.setMinimumWidth(220)
        self.search_edit.textChanged.connect(lambda _t: self._apply_filters())
        toolbar.add(self.search_edit)
        self.active_only_check = QCheckBox("Somente ativas")
        self.active_only_check.setChecked(True)
        self.active_only_check.toggled.connect(lambda _c: self.reload())
        toolbar.add(self.active_only_check)
        clear_button = make_button("Limpar filtros", "quiet")
        clear_button.clicked.connect(self.clear_filters)
        toolbar.add(clear_button)
        tools_button = make_button("Ferramentas")
        tools_menu = QMenu(tools_button)
        tools_menu.addAction("Exportar relatorio...", self.open_export_dialog)
        tools_menu.addSeparator()
        tools_menu.addAction("Gerar periodos do ano...", self.generate_year_periods)
        tools_menu.addAction("Excluir ano...", self.delete_year_periods)
        tools_menu.addSeparator()
        tools_menu.addAction("Preparar email", self.prepare_email)
        tools_menu.addAction("Copiar WhatsApp", self.copy_whatsapp)
        tools_button.setMenu(tools_menu)
        toolbar.add(tools_button)
        toolbar.add_stretch()

        toolbar.add(QLabel("Cobranca global:"))
        self.global_inicio_edit = QLineEdit()
        self.global_inicio_edit.setMaximumWidth(44)
        toolbar.add(self.global_inicio_edit)
        self.global_fim_edit = QLineEdit()
        self.global_fim_edit.setMaximumWidth(44)
        toolbar.add(self.global_fim_edit)
        self.global_alerta_edit = QLineEdit()
        self.global_alerta_edit.setMaximumWidth(44)
        toolbar.add(self.global_alerta_edit)
        self.global_edit_button = make_button("Editar")
        self.global_edit_button.clicked.connect(self._toggle_global_edit)
        toolbar.add(self.global_edit_button)
        layout.addWidget(toolbar)

        self.summary_label = QLabel("Selecione um periodo para carregar a conferencia mensal.")
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
        self.table.setSortingEnabled(True)
        header = self.table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._open_column_filter_menu)
        for col, key in enumerate(COLUMN_KEYS):
            mode = QHeaderView.ResizeMode.ResizeToContents if key != "empresa" else QHeaderView.ResizeMode.Stretch
            header.setSectionResizeMode(col, mode)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        self.table.doubleClicked.connect(lambda _index: self.open_selected_company())
        splitter.addWidget(self.table)

        detail_card = Card()
        detail_layout = QVBoxLayout(detail_card)
        detail_layout.setContentsMargins(14, 10, 14, 10)
        detail_header = QHBoxLayout()
        self.detail_title = QLabel("Selecione uma empresa para ver o detalhe do mes e as pendencias anteriores.")
        self.detail_title.setStyleSheet("font-weight: 600;")
        self.detail_title.setWordWrap(True)
        detail_header.addWidget(self.detail_title, 1)
        open_control_button = make_button("Abrir no Controle", "primary")
        open_control_button.clicked.connect(self.open_selected_company)
        detail_header.addWidget(open_control_button)
        detail_layout.addLayout(detail_header)
        self.detail_browser = QTextBrowser()
        self.detail_browser.setOpenLinks(False)
        detail_layout.addWidget(self.detail_browser, 1)
        splitter.addWidget(detail_card)
        splitter.setSizes([440, 240])

        self._load_global_settings()
        self._set_global_edit_mode(False)

    # Carregamento

    def refresh_data(self) -> None:
        self._refresh_periods()
        self._load_global_settings()
        self.reload()

    def _refresh_periods(self) -> None:
        selected = self.period_combo.currentData()
        self.periods = self.services.periodo_service.list_periodos()
        self.period_combo.blockSignals(True)
        self.period_combo.clear()
        for periodo in sorted(self.periods, key=lambda p: (p["ano"], p["mes"])):
            self.period_combo.addItem(f'{periodo["mes"]:02d}/{periodo["ano"]}', periodo["id"])
        if selected is not None and self.period_combo.findData(selected) >= 0:
            self.period_combo.setCurrentIndex(self.period_combo.findData(selected))
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
            self.summary_label.setText("Cadastre periodos (Ferramentas > Gerar periodos do ano) para comecar.")
            return
        self.viewmodel.load(period_id, self.active_only_check.isChecked())
        self._apply_filters()

    # Filtros

    def clear_filters(self) -> None:
        self.search_edit.clear()
        self.column_filters = {key: "" for key in COLUMN_KEYS}
        self._apply_filters()

    def _row_display_values(self, row: dict) -> dict[str, str]:
        situacao_label = UI_SITUATION_LABELS.get(row["month_status_key"], row.get("situacao") or "-")
        prefix = "🚨 " if row["month_status_key"] == MONTH_STATUS_OVERDUE else (
            "⚠ " if row["month_status_key"] == "com_pendencia" else ""
        )
        cobranca_prefix = "🚨 " if row["collection_status_key"] == CollectionService.PHASE_EM_ATRASO else (
            "⚠ " if row["collection_status_key"] == CollectionService.PHASE_EM_COBRANCA else ""
        )
        historico = row["previous_pending_summary"]
        historico_text = "Em dia" if historico == "-" else f"🚨 {historico}"
        ultima = "-"
        if row.get("ultima_marcacao_em"):
            try:
                stamp = datetime.fromisoformat(str(row["ultima_marcacao_em"]))
                ultima = stamp.strftime("%d/%m/%Y %H:%M")
            except ValueError:
                ultima = str(row["ultima_marcacao_em"])
            if row.get("ultima_marcacao_por"):
                ultima += f' - {row["ultima_marcacao_por"]}'
        return {
            "codigo": str(row["codigo_empresa"]),
            "empresa": row["nome_empresa"] + ("" if row["ativa"] else " [Inativa]"),
            "situacao": prefix + situacao_label,
            "progresso": f'{row["marcados"]}/{row["total_cobravel"]}',
            "cobranca": cobranca_prefix + row["collection_status"],
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
            self._apply_filters()

        action_all = menu.addAction("Todos" + ("  ✓" if not current else ""))
        action_all.triggered.connect(lambda: set_filter(""))
        menu.addSeparator()

        distinct = sorted({self._row_display_values(row)[key] for row in self.viewmodel.rows})
        for value in distinct[:40]:
            marker = "  ✓" if value == current else ""
            action = menu.addAction(f"{value}{marker}")
            action.triggered.connect(lambda _checked=False, v=value: set_filter(v))
        menu.exec(header.mapToGlobal(pos))

    def _populate_table(self) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for row in self.filtered_rows:
            values = self._row_display_values(row)
            table_row = self.table.rowCount()
            self.table.insertRow(table_row)
            for col, key in enumerate(COLUMN_KEYS):
                item = QTableWidgetItem(values[key])
                if key == "codigo":
                    item.setData(Qt.ItemDataRole.UserRole, row["empresa_id"])
                    item.setIcon(situation_icon(row["month_status_key"]))
                if key == "situacao":
                    item.setForeground(QColor(situation_color(row["month_status_key"])))
                if key == "cobranca" and row["collection_status_key"] != "em_dia":
                    item.setForeground(QColor(situation_color("com_pendencia")))
                self.table.setItem(table_row, col, item)
        self.table.setSortingEnabled(True)

    def _update_summary(self) -> None:
        total = len(self.viewmodel.rows)
        counts = self.viewmodel.count_month_statuses(self.filtered_rows)
        collection = self.viewmodel.count_collection_statuses(self.filtered_rows)
        parts = [f"{len(self.filtered_rows)} de {total} empresa(s) em {self.period_combo.currentText()}."]
        parts.extend(
            f"{label}: {counts[key]}" for key, label in UI_SITUATION_LABELS.items() if counts.get(key)
        )
        parts.append(f'Cobranca em dia: {collection.get("em_dia", 0)}')
        parts.append(f'Em cobranca: {collection.get(CollectionService.PHASE_EM_COBRANCA, 0)}')
        parts.append(f'Cobranca em atraso: {collection.get(CollectionService.PHASE_EM_ATRASO, 0)}')
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

    def _on_row_selected(self) -> None:
        row = self._selected_row()
        if not row:
            return
        situacao_label = UI_SITUATION_LABELS.get(row["month_status_key"], "-")
        self.detail_title.setText(
            f'{row["codigo_empresa"]} - {row["nome_empresa"]}  |  Mes: {situacao_label}  |  '
            f'Cobranca: {row["collection_status"]}'
        )
        self.detail_browser.setHtml(self._build_detail_html(row))

    def _build_detail_html(self, row: dict) -> str:
        t = tokens()
        period_id = self.period_combo.currentData()
        parts = [
            f'<div style="color:{t["muted"]};">Periodo selecionado: {self.period_combo.currentText()} | '
            f'Progresso atual: {row["marcados"]}/{row["total_cobravel"]} | Recebidos: {row["recebidos"]} | '
            f'Pendentes: {row["pendentes"]} | Faltando: {row["faltando"]}</div>'
        ]

        try:
            control_view = self.services.status_service.build_control_view(
                row["empresa_id"], period_id, period_id
            )
        except ValidationError:
            control_view = None

        if control_view and control_view.get("groups"):
            parts.append(f'<h3 style="margin-bottom:4px;">Mes atual</h3>')
            for group in control_view["groups"]:
                parts.append(f'<div style="font-weight:600; margin-top:6px;">{group["tipo_nome"]}</div>')
                for documento in group["documentos"]:
                    cell = documento["cells"][0] if documento["cells"] else None
                    status = (cell or {}).get("status") or "Nao iniciado"
                    bg, fg = status_colors((cell or {}).get("status") or "")
                    meios = documento.get("meios_recebimento") or "-"
                    parts.append(
                        f'<div style="margin-left:12px;">{documento["nome_documento"]} — '
                        f'<span style="background:{bg}; color:{fg}; padding:1px 8px; border-radius:8px;">{status}</span>'
                        f' <span style="color:{t["muted"]};">| {meios}</span></div>'
                    )

        previous_items = row.get("previous_period_items") or []
        parts.append('<h3 style="margin-bottom:4px;">Documentos em aberto de meses anteriores</h3>')
        if not previous_items:
            parts.append(
                f'<div style="color:{t["success"]};">Nenhum documento em aberto de meses anteriores.</div>'
            )
        else:
            for period_item in previous_items:
                parts.append(
                    f'<div style="font-weight:600; margin-top:6px;">{period_item["periodo_label"]} '
                    f'<span style="color:{t["danger"]};">({period_item["phase_label"]})</span></div>'
                )
                for document in period_item["documents"]:
                    meios = ", ".join(document.get("meios_recebimento") or []) or "-"
                    parts.append(
                        f'<div style="margin-left:12px;">{document.get("nome_documento", "-")} '
                        f'<span style="color:{t["muted"]};">| {meios}</span></div>'
                    )
        return "".join(parts)

    def open_selected_company(self) -> None:
        row = self._selected_row()
        period_id = self.period_combo.currentData()
        if not row or period_id is None:
            QMessageBox.warning(self, "Panorama", "Selecione uma empresa e uma competencia primeiro.")
            return
        if self.on_open_control:
            self.on_open_control(row["empresa_id"], period_id)

    # Cobranca global

    def _load_global_settings(self) -> None:
        self.global_settings = self.services.collection_service.get_global_settings()
        self.global_inicio_edit.setText(str(self.global_settings["inicio_cobranca_dia"]))
        self.global_fim_edit.setText(str(self.global_settings["encerramento_cobranca_dia"]))
        self.global_alerta_edit.setText(str(self.global_settings["alerta_apos_dias"]))

    def _set_global_edit_mode(self, editing: bool) -> None:
        for edit in (self.global_inicio_edit, self.global_fim_edit, self.global_alerta_edit):
            edit.setEnabled(editing)
        self.global_edit_button.setText("Salvar" if editing else "Editar")
        self.global_edit_button.setProperty("variant", "primary" if editing else None)
        self.global_edit_button.style().unpolish(self.global_edit_button)
        self.global_edit_button.style().polish(self.global_edit_button)

    def _toggle_global_edit(self) -> None:
        editing = self.global_inicio_edit.isEnabled()
        if not editing:
            self._set_global_edit_mode(True)
            return
        try:
            self.services.collection_service.update_global_settings(
                self.global_inicio_edit.text(),
                self.global_fim_edit.text(),
                self.global_alerta_edit.text(),
            )
        except ValidationError as exc:
            QMessageBox.critical(self, "Panorama", str(exc))
            return
        self._set_global_edit_mode(False)
        self._load_global_settings()
        self.reload()
        self.on_data_changed()

    # Ferramentas

    def open_export_dialog(self) -> None:
        visible_ids = [row["empresa_id"] for row in self.filtered_rows]
        ExportReportDialog(self.services, self.period_combo.currentText(), visible_ids, self).exec()

    def generate_year_periods(self) -> None:
        year, confirmed = QInputDialog.getInt(
            self, "Gerar periodos", "Informe o ano para gerar os 12 periodos:", datetime.now().year, 2000, 2100
        )
        if not confirmed:
            return
        result = self.services.periodo_service.generate_year(year)
        QMessageBox.information(
            self,
            "Gerar periodos",
            f'Ano {result["ano"]}: {result["created"]} periodo(s) criados, {result["existing"]} ja existiam.',
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
            f"Excluir todos os periodos de {year}? Os status mensais desse ano serao apagados. "
            "Empresas, tipos e documentos base sao mantidos.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        result = self.services.periodo_service.delete_year(year)
        QMessageBox.information(self, "Excluir ano", f'{result["deleted"]} periodo(s) de {result["ano"]} excluidos.')
        self.on_data_changed()

    def prepare_email(self) -> None:
        row = self._selected_row()
        queue_item = (row or {}).get("queue_item")
        if not queue_item:
            QMessageBox.warning(self, "Panorama", "Selecione uma empresa com cobranca em aberto.")
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
            QMessageBox.warning(self, "Panorama", "Selecione uma empresa com cobranca em aberto.")
            return
        message = self.services.collection_service.build_whatsapp_message(queue_item)
        QGuiApplication.clipboard().setText(message)
        QMessageBox.information(self, "Panorama", "Mensagem copiada para a area de transferencia.")
