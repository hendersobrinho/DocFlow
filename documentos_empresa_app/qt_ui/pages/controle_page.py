from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.theme import status_colors, tokens
from documentos_empresa_app.qt_ui.widgets.common import Card, PageHeader, ToolbarRow, make_button
from documentos_empresa_app.qt_ui.widgets.company_selector import CompanySelector
from documentos_empresa_app.utils.common import (
    STATUS_OPTIONS,
    ValidationError,
    parse_delivery_methods,
    parse_period_label,
)

BULK_STATUS_OPTIONS = {
    "Recebido": "Recebido",
    "Pendente": "Pendente",
    "Encerrado": "Encerrado",
    "Nao cobrar": "Nao cobrar",
    "Limpar status": "",
}


class ControlePage(QWidget):
    def __init__(self, services, on_data_changed, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.on_data_changed = on_data_changed
        self.periods_by_year: dict[int, list[dict]] = {}
        self.current_view: dict | None = None
        self.current_period_ids: list[int] = []
        self.bulk_mode = False
        self.bulk_selection: set[int] = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(PageHeader("Controle", "Marque o status mensal de cada documento da empresa consultada."))

        self.company_selector = CompanySelector(self.services.empresa_service, active_only=True, title="Empresa")
        self.company_selector.company_selected.connect(lambda _c: self._on_company_changed())
        self.company_selector.company_cleared.connect(self._on_company_cleared)
        layout.addWidget(self.company_selector)

        toolbar = ToolbarRow()
        toolbar.add(QLabel("Periodo"))
        self.start_period_edit = QLineEdit()
        self.start_period_edit.setPlaceholderText("MM/AAAA")
        self.start_period_edit.setMaximumWidth(90)
        self.start_period_edit.returnPressed.connect(self.consult)
        toolbar.add(self.start_period_edit)
        toolbar.add(QLabel("ate"))
        self.end_period_edit = QLineEdit()
        self.end_period_edit.setPlaceholderText("MM/AAAA (opcional)")
        self.end_period_edit.setMaximumWidth(130)
        self.end_period_edit.returnPressed.connect(self.consult)
        toolbar.add(self.end_period_edit)
        consult_button = make_button("Consultar", "primary")
        consult_button.clicked.connect(self.consult)
        toolbar.add(consult_button)
        clear_button = make_button("Limpar", "quiet")
        clear_button.clicked.connect(self.clear_filters)
        toolbar.add(clear_button)
        self.directory_button = make_button("Abrir pasta...")
        self.directory_button.clicked.connect(self.choose_company_directory)
        self.directory_button.setEnabled(False)
        toolbar.add(self.directory_button)
        self.bulk_button = make_button("Selecao em lote")
        self.bulk_button.clicked.connect(self.toggle_bulk_mode)
        self.bulk_button.setEnabled(False)
        toolbar.add(self.bulk_button)
        toolbar.add_stretch()
        hint = QLabel("Se o periodo final ficar em branco, consulta so o mes inicial. Limite de 12 meses.")
        hint.setObjectName("Muted")
        toolbar.add(hint)
        layout.addWidget(toolbar)

        self.company_info_label = QLabel("")
        self.company_info_label.setObjectName("Muted")
        self.company_info_label.setWordWrap(True)
        layout.addWidget(self.company_info_label)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(1)
        self.tree.setHeaderLabels(["Documento"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tree.setUniformRowHeights(True)
        self.tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.tree, 1)

        bulk_card = Card()
        self.bulk_panel = bulk_card
        bulk_layout = QHBoxLayout(bulk_card)
        bulk_layout.setContentsMargins(14, 10, 14, 10)
        bulk_layout.setSpacing(8)
        self.bulk_summary_label = QLabel("Nenhum documento selecionado.")
        bulk_layout.addWidget(self.bulk_summary_label)
        mark_all_button = make_button("Marcar todos")
        mark_all_button.clicked.connect(self._bulk_mark_all)
        bulk_layout.addWidget(mark_all_button)
        clear_selection_button = make_button("Limpar selecao", "quiet")
        clear_selection_button.clicked.connect(self._bulk_clear_selection)
        bulk_layout.addWidget(clear_selection_button)
        bulk_layout.addStretch(1)
        bulk_layout.addWidget(QLabel("Periodo"))
        self.bulk_period_combo = QComboBox()
        self.bulk_period_combo.setMinimumWidth(120)
        bulk_layout.addWidget(self.bulk_period_combo)
        bulk_layout.addWidget(QLabel("Status"))
        self.bulk_status_combo = QComboBox()
        self.bulk_status_combo.addItems(list(BULK_STATUS_OPTIONS))
        bulk_layout.addWidget(self.bulk_status_combo)
        apply_button = make_button("Aplicar nos selecionados", "primary")
        apply_button.clicked.connect(self._bulk_apply)
        bulk_layout.addWidget(apply_button)
        bulk_card.setVisible(False)
        layout.addWidget(bulk_card)

        self.message_label = QLabel("Selecione a empresa e o intervalo para consultar.")
        self.message_label.setObjectName("Muted")
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)

    # Periodos / filtros

    def refresh_data(self) -> None:
        self.company_selector.refresh_companies()
        self._refresh_period_options()

    def _refresh_period_options(self) -> None:
        periodos = self.services.periodo_service.list_periodos()
        self.periods_by_year = {}
        for periodo in periodos:
            self.periods_by_year.setdefault(periodo["ano"], []).append(periodo)

    def clear_filters(self) -> None:
        self.company_selector.clear_selection()
        self.start_period_edit.clear()
        self.end_period_edit.clear()
        self.tree.clear()
        self.current_view = None
        self.bulk_button.setEnabled(False)
        self._exit_bulk_mode()
        self.company_info_label.setText("")
        self.message_label.setText("Selecione a empresa e o intervalo para consultar.")

    def _on_company_changed(self) -> None:
        self.directory_button.setEnabled(True)

    def _on_company_cleared(self) -> None:
        self.directory_button.setEnabled(False)

    def _resolve_period_id(self, raw: str) -> int | None:
        parsed = parse_period_label(raw)
        if not parsed:
            return None
        year, month = parsed
        return next((p["id"] for p in self.periods_by_year.get(year, []) if p["mes"] == month), None)

    # Consulta

    def open_company_period(self, company_id: int, period_id: int) -> bool:
        self.refresh_data()
        self.company_selector.set_company(company_id)
        if not self.company_selector.get_selected_company_id():
            QMessageBox.warning(self, "Controle", "A empresa nao esta ativa para consulta no Controle.")
            return False
        periodo = self.services.periodo_service.get_periodo(period_id)
        period_text = f'{periodo["mes"]:02d}/{periodo["ano"]}'
        self.start_period_edit.setText(period_text)
        self.end_period_edit.setText(period_text)
        self.consult()
        return True

    def consult(self) -> None:
        company_id = self.company_selector.get_selected_company_id()
        if not company_id:
            QMessageBox.warning(self, "Controle", "Selecione uma empresa para consultar.")
            return

        start_id = self._resolve_period_id(self.start_period_edit.text())
        if start_id is None:
            QMessageBox.warning(self, "Controle", "Informe um periodo inicial valido no formato MM/AAAA.")
            return

        end_raw = self.end_period_edit.text().strip()
        end_id = self._resolve_period_id(end_raw) if end_raw else start_id
        if end_id is None:
            QMessageBox.warning(self, "Controle", "Informe um periodo final valido no formato MM/AAAA.")
            return

        try:
            view = self.services.status_service.build_control_view(company_id, start_id, end_id)
        except ValidationError as exc:
            QMessageBox.critical(self, "Controle", str(exc))
            return

        self.current_view = view
        self._populate_tree()
        self._update_company_info(view)
        self.bulk_button.setEnabled(True)
        self.message_label.setText(
            f'Empresa consultada: {view["empresa"]["nome_empresa"]}. Clique em uma celula de mes para marcar o status.'
        )

    def _update_company_info(self, view: dict) -> None:
        empresa = view["empresa"]
        methods: list[str] = []
        for group in view["groups"]:
            for documento in group["documentos"]:
                methods.extend(parse_delivery_methods(documento.get("meios_recebimento")))
        distinct = ", ".join(dict.fromkeys(methods)) or "-"
        self.company_info_label.setText(
            f'Observacao: {empresa.get("observacao") or "-"}    |    Recebimentos dos documentos: {distinct}'
        )

    def _populate_tree(self) -> None:
        self.tree.clear()
        view = self.current_view
        if not view:
            return

        periodos = view["periodos"]
        self.current_period_ids = [p["id"] for p in periodos]
        headers = ["Documento"] + [f'{p["mes"]:02d}/{p["ano"]}' for p in periodos]
        self.tree.setColumnCount(len(headers))
        self.tree.setHeaderLabels(headers)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.tree.setColumnWidth(0, 320)
        for col in range(1, len(headers)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)

        self.bulk_period_combo.clear()
        for periodo in periodos:
            self.bulk_period_combo.addItem(f'{periodo["mes"]:02d}/{periodo["ano"]}', periodo["id"])

        t = tokens()
        for group in view["groups"]:
            occurrence = ""
            if group.get("regra_ocorrencia") and group.get("regra_ocorrencia") != "mensal":
                occurrence = f' ({group.get("tipo_ocorrencia_label") or group.get("regra_ocorrencia")})'
            elif group.get("tipo_ocorrencia_label") and group.get("tipo_ocorrencia_label") != "Mensal":
                occurrence = f' ({group["tipo_ocorrencia_label"]})'
            group_item = QTreeWidgetItem(
                [f'{group["tipo_nome"]}{occurrence} — {len(group["documentos"])} documento(s)']
            )
            font = group_item.font(0)
            font.setBold(True)
            group_item.setFont(0, font)
            group_item.setBackground(0, QBrush(QColor(t["surface_alt"])))
            self.tree.addTopLevelItem(group_item)
            group_item.setFirstColumnSpanned(True)

            for documento in group["documentos"]:
                doc_item = QTreeWidgetItem([documento["nome_documento"]])
                doc_item.setData(0, Qt.ItemDataRole.UserRole, documento["id"])
                doc_item.setToolTip(0, f'{documento["nome_documento"]} | {documento.get("meios_recebimento") or "-"}')
                if self.bulk_mode:
                    doc_item.setFlags(doc_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    doc_item.setCheckState(
                        0,
                        Qt.CheckState.Checked
                        if documento["id"] in self.bulk_selection
                        else Qt.CheckState.Unchecked,
                    )
                for col, cell in enumerate(documento["cells"], start=1):
                    self._apply_cell(doc_item, col, cell)
                group_item.addChild(doc_item)
            group_item.setExpanded(True)

    def _apply_cell(self, item: QTreeWidgetItem, col: int, cell: dict) -> None:
        status = cell.get("status") or ""
        display = status if status else ("-" if not cell.get("available") else "")
        item.setText(col, display)
        item.setTextAlignment(col, Qt.AlignmentFlag.AlignCenter)
        bg, fg = status_colors(status)
        item.setBackground(col, QBrush(QColor(bg)))
        item.setForeground(col, QBrush(QColor(fg)))
        item.setData(col, Qt.ItemDataRole.UserRole, cell)

        if not cell.get("available"):
            hint = cell.get("read_only_hint") or "Celula somente leitura."
            item.setToolTip(col, hint)
        elif cell.get("updated_at"):
            actor = cell.get("updated_by_username") or "Sistema"
            item.setToolTip(col, f'Status "{status or "-"}" alterado por {actor} em {cell["updated_at"]}.')
        else:
            item.setToolTip(col, "Nenhuma alteracao registrada ainda.")

    # Edicao de celula

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        document_id = item.data(0, Qt.ItemDataRole.UserRole)
        if document_id is None:
            return

        if column == 0:
            if self.bulk_mode:
                if item.checkState(0) == Qt.CheckState.Checked:
                    self.bulk_selection.add(int(document_id))
                else:
                    self.bulk_selection.discard(int(document_id))
                self._update_bulk_summary()
            return

        cell = item.data(column, Qt.ItemDataRole.UserRole)
        if not cell or not cell.get("available"):
            if cell and cell.get("read_only_hint"):
                self.message_label.setText(cell["read_only_hint"])
            return

        menu = QMenu(self)
        current_status = cell.get("status") or ""
        for option in STATUS_OPTIONS:
            label = option if option else "Limpar status"
            marker = "  ✓" if option == current_status else ""
            action = menu.addAction(f"{label}{marker}")
            action.triggered.connect(
                lambda _checked=False, status=option: self._set_status(item, column, int(document_id), status)
            )
        menu.exec(QCursor.pos())

    def _set_status(self, item: QTreeWidgetItem, column: int, document_id: int, status: str) -> None:
        period_id = self.current_period_ids[column - 1]
        try:
            self.services.status_service.update_status(document_id, period_id, status)
        except ValidationError as exc:
            QMessageBox.critical(self, "Controle", str(exc))
            return

        refreshed = self.services.status_service.build_control_document_view(
            document_id, self.current_period_ids[0], self.current_period_ids[-1]
        )
        if refreshed:
            for col, cell in enumerate(refreshed["cells"], start=1):
                self._apply_cell(item, col, cell)
        self.on_data_changed()

    # Lote

    def toggle_bulk_mode(self) -> None:
        if self.bulk_mode:
            self._exit_bulk_mode()
        else:
            self.bulk_mode = True
            self.bulk_selection = set()
            self.bulk_button.setText("Fechar lote")
            self.bulk_panel.setVisible(True)
            self._populate_tree()
            self._update_bulk_summary()

    def _exit_bulk_mode(self) -> None:
        self.bulk_mode = False
        self.bulk_selection = set()
        self.bulk_button.setText("Selecao em lote")
        self.bulk_panel.setVisible(False)
        if self.current_view:
            self._populate_tree()

    def _iter_document_items(self):
        for group_index in range(self.tree.topLevelItemCount()):
            group_item = self.tree.topLevelItem(group_index)
            for child_index in range(group_item.childCount()):
                yield group_item.child(child_index)

    def _bulk_mark_all(self) -> None:
        for item in self._iter_document_items():
            item.setCheckState(0, Qt.CheckState.Checked)
            self.bulk_selection.add(int(item.data(0, Qt.ItemDataRole.UserRole)))
        self._update_bulk_summary()

    def _bulk_clear_selection(self) -> None:
        for item in self._iter_document_items():
            item.setCheckState(0, Qt.CheckState.Unchecked)
        self.bulk_selection = set()
        self._update_bulk_summary()

    def _update_bulk_summary(self) -> None:
        count = len(self.bulk_selection)
        self.bulk_summary_label.setText(
            f"{count} documento(s) selecionado(s)." if count else "Nenhum documento selecionado."
        )

    def _bulk_apply(self) -> None:
        if not self.bulk_selection:
            QMessageBox.warning(self, "Controle", "Selecione ao menos um documento.")
            return
        period_id = self.bulk_period_combo.currentData()
        if period_id is None:
            QMessageBox.warning(self, "Controle", "Escolha o periodo do lote.")
            return
        status_value = BULK_STATUS_OPTIONS[self.bulk_status_combo.currentText()]
        answer = QMessageBox.question(
            self,
            "Controle",
            f'Aplicar "{self.bulk_status_combo.currentText()}" em {len(self.bulk_selection)} documento(s) '
            f"no periodo {self.bulk_period_combo.currentText()}?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            result = self.services.status_service.update_status_batch(
                sorted(self.bulk_selection), period_id, status_value
            )
        except ValidationError as exc:
            QMessageBox.critical(self, "Controle", str(exc))
            return

        self.consult()
        self.message_label.setText(
            f'Lote aplicado: {result["updated"]} de {result["selected"]} documento(s) atualizados.'
        )
        self.on_data_changed()

    # Pasta da empresa

    def choose_company_directory(self) -> None:
        from pathlib import Path

        from PySide6.QtWidgets import QFileDialog

        company_id = self.company_selector.get_selected_company_id()
        if not company_id:
            return
        company = self.services.empresa_service.get_empresa(company_id)
        current = str(company.get("diretorio_documentos") or "").strip()
        initial = current if current and Path(current).is_dir() else str(Path.home())
        selected = QFileDialog.getExistingDirectory(
            self, f'Escolha a pasta para "{company["nome_empresa"]}"', initial
        )
        if not selected:
            return
        self.services.empresa_service.set_empresa_directory(company_id, selected)
        self.message_label.setText(f'Pasta vinculada da empresa atualizada para: {selected}')
