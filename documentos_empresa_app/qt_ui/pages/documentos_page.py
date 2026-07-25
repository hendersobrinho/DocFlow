from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.dialogs.manager_dialogs import (
    DocumentNameManagerDialog,
    DocumentTypeManagerDialog,
)
from documentos_empresa_app.qt_ui.widgets.common import Card, PageHeader, make_button
from documentos_empresa_app.qt_ui.widgets.company_selector import CompanySelector
from documentos_empresa_app.qt_ui.widgets.delivery_methods_field import DeliveryMethodsField
from documentos_empresa_app.utils.common import ValidationError


class DocumentosPage(QWidget):
    def __init__(self, services, on_data_changed, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.on_data_changed = on_data_changed
        self.editing_document_id: int | None = None
        self.form_mode = "idle"
        self.tipos: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        layout.addWidget(PageHeader("Documentos", "Cadastre os documentos cobrados de cada empresa."))

        self.company_selector = CompanySelector(
            self.services.empresa_service, active_only=False, title="Empresa"
        )
        self.company_selector.company_selected.connect(self._on_company_selected)
        self.company_selector.company_cleared.connect(self._on_company_cleared)
        layout.addWidget(self.company_selector)

        content = QHBoxLayout()
        content.setSpacing(14)
        layout.addLayout(content, 1)

        # Lista
        list_card = Card()
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(18, 16, 18, 16)
        content.addWidget(list_card, 3)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Nome", "Recebimento", "Tipo"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._on_document_selected)
        # activated cobre duplo-clique e Enter/Return sobre a linha selecionada -
        # antes disso nao havia nenhum jeito de abrir um documento para edicao
        # direto da lista, so pelo botao "Editar".
        self.table.activated.connect(lambda _index: self._activate_selected_document())
        list_layout.addWidget(self.table, 1)

        # Formulario
        form_card = Card()
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(18, 16, 18, 16)
        form_layout.setSpacing(8)
        content.addWidget(form_card, 2)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.addWidget(QLabel("Nome do documento"), 0, 0)
        self.nome_combo = QComboBox()
        self.nome_combo.setEditable(True)
        self.nome_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.nome_combo.lineEdit().textEdited.connect(lambda _t: self._refresh_name_suggestions())
        grid.addWidget(self.nome_combo, 1, 0)
        names_button = make_button("...")
        names_button.setMaximumWidth(40)
        names_button.clicked.connect(self._open_name_manager)
        grid.addWidget(names_button, 1, 1)

        grid.addWidget(QLabel("Tipo"), 2, 0)
        self.tipo_combo = QComboBox()
        self.tipo_combo.currentIndexChanged.connect(lambda _i: self._refresh_name_suggestions())
        grid.addWidget(self.tipo_combo, 3, 0)
        types_button = make_button("...")
        types_button.setMaximumWidth(40)
        types_button.clicked.connect(self._open_type_manager)
        grid.addWidget(types_button, 3, 1)
        grid.setColumnStretch(0, 1)
        form_layout.addLayout(grid)

        self.suggestion_label = QLabel("")
        self.suggestion_label.setObjectName("Muted")
        self.suggestion_label.setWordWrap(True)
        form_layout.addWidget(self.suggestion_label)

        self.delivery_field = DeliveryMethodsField(self.services.delivery_method_service)
        form_layout.addWidget(self.delivery_field)

        actions = QHBoxLayout()
        self.new_button = make_button("Novo")
        self.new_button.clicked.connect(self.start_new)
        actions.addWidget(self.new_button)
        self.edit_button = make_button("Editar")
        self.edit_button.clicked.connect(self.start_edit)
        actions.addWidget(self.edit_button)
        self.save_button = make_button("Salvar", "primary")
        self.save_button.clicked.connect(self.save_document)
        actions.addWidget(self.save_button)
        self.cancel_button = make_button("Cancelar", "quiet")
        self.cancel_button.clicked.connect(self.cancel_edit)
        actions.addWidget(self.cancel_button)
        actions.addStretch(1)
        self.delete_button = make_button("Excluir selecionados", "danger")
        self.delete_button.clicked.connect(self.delete_selected)
        actions.addWidget(self.delete_button)
        form_layout.addLayout(actions)
        form_layout.addStretch(1)

        self._set_form_mode("idle")

    def refresh_data(self) -> None:
        self._refresh_tipos()
        self.company_selector.refresh_companies()
        self._reload_documents()

    # Empresa

    def _on_company_selected(self, _company: dict) -> None:
        self._reload_documents()
        self._reset_form()
        self._set_form_mode("view")

    def _on_company_cleared(self) -> None:
        self.table.setRowCount(0)
        self._reset_form()
        self._set_form_mode("idle")

    # Tipos / sugestoes

    def _refresh_tipos(self) -> None:
        selected = self.tipo_combo.currentData()
        self.tipos = self.services.tipo_service.list_tipos()
        self.tipo_combo.blockSignals(True)
        self.tipo_combo.clear()
        for tipo in self.tipos:
            self.tipo_combo.addItem(tipo["nome_tipo"], tipo["id"])
        if selected is not None:
            index = self.tipo_combo.findData(selected)
            if index >= 0:
                self.tipo_combo.setCurrentIndex(index)
        self.tipo_combo.blockSignals(False)

    def _refresh_name_suggestions(self) -> None:
        tipo_id = self.tipo_combo.currentData()
        search = self.nome_combo.currentText().strip()
        suggestions = self.services.documento_service.list_document_name_suggestions(
            tipo_documento_id=tipo_id, search=search
        )
        current = self.nome_combo.lineEdit().text()
        cursor = self.nome_combo.lineEdit().cursorPosition()
        self.nome_combo.blockSignals(True)
        self.nome_combo.clear()
        self.nome_combo.addItems(suggestions)
        self.nome_combo.setCurrentText(current)
        self.nome_combo.lineEdit().setCursorPosition(cursor)
        self.nome_combo.blockSignals(False)

        if suggestions:
            self.suggestion_label.setText(f"{len(suggestions)} sugestao(oes) de nome disponiveis na lista.")
        elif search:
            self.suggestion_label.setText("Nenhuma sugestao para o texto informado — o nome sera criado como novo.")
        else:
            self.suggestion_label.setText("Digite o nome ou escolha uma sugestao da lista.")

    # Lista

    def _reload_documents(self) -> None:
        self.table.setRowCount(0)
        company_id = self.company_selector.get_selected_company_id()
        if not company_id:
            return
        for documento in self.services.documento_service.list_documentos_empresa(company_id):
            row = self.table.rowCount()
            self.table.insertRow(row)
            name_item = QTableWidgetItem(documento["nome_documento"])
            name_item.setData(Qt.ItemDataRole.UserRole, documento["id"])
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem(documento.get("meios_recebimento") or "-"))
            self.table.setItem(row, 2, QTableWidgetItem(documento.get("nome_tipo") or "-"))

    def _selected_document_ids(self) -> list[int]:
        ids = []
        for index in self.table.selectionModel().selectedRows():
            item = self.table.item(index.row(), 0)
            if item is not None:
                ids.append(int(item.data(Qt.ItemDataRole.UserRole)))
        return ids

    def _on_document_selected(self) -> None:
        if self.form_mode in {"new", "edit"}:
            return
        ids = self._selected_document_ids()
        if len(ids) != 1:
            return
        documento = self.services.documento_service.get_documento(ids[0])
        self.editing_document_id = ids[0]
        self.nome_combo.setCurrentText(documento["nome_documento"])
        index = self.tipo_combo.findData(documento["tipo_documento_id"])
        if index >= 0:
            self.tipo_combo.setCurrentIndex(index)
        self.delivery_field.set_values(documento.get("meios_recebimento"))

    # Formulario

    def _reset_form(self) -> None:
        self.editing_document_id = None
        self.nome_combo.setCurrentText("")
        self.delivery_field.clear()
        self._refresh_name_suggestions()

    def _set_form_mode(self, mode: str) -> None:
        self.form_mode = mode
        editable = mode in {"new", "edit"}
        has_company = self.company_selector.get_selected_company_id() is not None

        self.nome_combo.setEnabled(editable)
        self.tipo_combo.setEnabled(editable)
        self.delivery_field.set_editable(editable)
        self.save_button.setEnabled(editable)
        self.cancel_button.setEnabled(editable)
        self.new_button.setEnabled(has_company and not editable)
        self.edit_button.setEnabled(has_company and not editable)
        self.delete_button.setEnabled(has_company and not editable)

    def start_new(self) -> None:
        if not self.company_selector.get_selected_company_id():
            QMessageBox.warning(self, "Documentos", "Selecione uma empresa antes de cadastrar documentos.")
            return
        self.table.clearSelection()
        self._reset_form()
        self._set_form_mode("new")

    def start_edit(self) -> None:
        ids = self._selected_document_ids()
        if len(ids) != 1:
            QMessageBox.warning(self, "Documentos", "Selecione exatamente um documento para editar.")
            return
        self._on_document_selected()
        self._set_form_mode("edit")

    def _activate_selected_document(self) -> None:
        """Duplo-clique ou Enter numa linha abre o documento para edicao - se ja
        houver um cadastro novo ou uma edicao em andamento, ignora para nao
        descartar dados nao salvos."""
        if self.form_mode in {"new", "edit"}:
            return
        self.start_edit()

    def cancel_edit(self) -> None:
        self._reset_form()
        self._set_form_mode("view" if self.company_selector.get_selected_company_id() else "idle")

    def save_document(self) -> None:
        company_id = self.company_selector.get_selected_company_id()
        if not company_id:
            return
        tipo_id = self.tipo_combo.currentData()
        if tipo_id is None:
            QMessageBox.warning(self, "Documentos", "Cadastre um tipo de documento antes.")
            return

        try:
            if self.form_mode == "edit" and self.editing_document_id:
                self.services.documento_service.update_documento(
                    self.editing_document_id,
                    tipo_id,
                    self.nome_combo.currentText(),
                    self.delivery_field.get_values(),
                )
                QMessageBox.information(self, "Documentos", "Documento atualizado com sucesso.")
            else:
                self.services.documento_service.create_documento(
                    company_id,
                    tipo_id,
                    self.nome_combo.currentText(),
                    self.delivery_field.get_values(),
                )
                QMessageBox.information(self, "Documentos", "Documento cadastrado com sucesso.")
        except ValidationError as exc:
            QMessageBox.critical(self, "Documentos", str(exc))
            return

        self.on_data_changed()
        self.company_selector.set_company(company_id)

    def delete_selected(self) -> None:
        ids = self._selected_document_ids()
        if not ids:
            QMessageBox.warning(self, "Documentos", "Selecione os documentos que deseja excluir.")
            return
        answer = QMessageBox.question(
            self,
            "Documentos",
            f"Deseja excluir {len(ids)} documento(s)? Os status mensais vinculados tambem serao apagados.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        company_id = self.company_selector.get_selected_company_id()
        try:
            self.services.documento_service.delete_documentos(ids)
        except ValidationError as exc:
            QMessageBox.critical(self, "Documentos", str(exc))
            return

        self.on_data_changed()
        if company_id:
            self.company_selector.set_company(company_id)

    # Dialogos

    def _open_name_manager(self) -> None:
        dialog = DocumentNameManagerDialog(
            self.services.documento_service,
            self.services.tipo_service,
            "Documentos",
            self.tipo_combo.currentData(),
            allow_apply_to_document=self.form_mode in {"new", "edit"},
            parent=self,
        )
        dialog.exec()
        if dialog.applied_name is not None:
            self.nome_combo.setCurrentText(dialog.applied_name)
        self._refresh_name_suggestions()

    def _open_type_manager(self) -> None:
        dialog = DocumentTypeManagerDialog(
            self.services.tipo_service,
            "Documentos",
            self.tipo_combo.currentData(),
            allow_apply_to_document=self.form_mode in {"new", "edit"},
            parent=self,
        )
        dialog.exec()
        self._refresh_tipos()
        if dialog.applied_type_id is not None:
            index = self.tipo_combo.findData(dialog.applied_type_id)
            if index >= 0:
                self.tipo_combo.setCurrentIndex(index)
        if dialog.data_changed and self.form_mode not in {"new", "edit"}:
            self._reload_documents()
