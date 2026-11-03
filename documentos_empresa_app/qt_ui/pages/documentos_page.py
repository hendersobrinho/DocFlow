from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.dialogs.manager_dialogs import (
    DeliveryMethodsManagerDialog,
    DocumentNameManagerDialog,
    DocumentTypeManagerDialog,
)
from documentos_empresa_app.qt_ui.widgets.check_choices import CheckChoices
from documentos_empresa_app.qt_ui.widgets.common import Card, PageHeader, ToolbarRow, make_button
from documentos_empresa_app.qt_ui.widgets.company_selector import CompanySelector
from documentos_empresa_app.qt_ui.widgets.tables import fill_table, make_readonly_table
from documentos_empresa_app.qt_ui.workers import BlockingTaskRunner
from documentos_empresa_app.utils.common import ValidationError, parse_delivery_methods
from documentos_empresa_app.utils.helpers import get_documents_directory


class DocumentoImportLayoutDialog(QDialog):
    """Mostra as colunas esperadas na planilha de cadastro em lote de documentos -
    mesmo padrao do dialogo de layout ja usado em Empresas (ImportLayoutDialog)."""

    def __init__(self, import_service, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Colunas da planilha de documentos")
        self.resize(760, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        description = QLabel(
            "Use uma linha por documento na planilha - todos serão cadastrados de uma vez para a "
            "empresa escolhida nesta tela. Tipos que ainda não existirem são criados automaticamente."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        table = QTableWidget(0, 4)
        table.setHorizontalHeaderLabels(["Ordem", "Coluna", "Obrigatório", "Exemplo"])
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        for item in import_service.get_documento_import_layout():
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(str(item["index"])))
            table.setItem(row, 1, QTableWidgetItem(item["field"]))
            table.setItem(row, 2, QTableWidgetItem("Sim" if item["required"] else "Não"))
            table.setItem(row, 3, QTableWidgetItem(str(item["example"])))
        layout.addWidget(table, 1)

        close_button = make_button("Fechar", "quiet")
        close_button.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)


SECTION_STYLE = "font-weight: 600; font-size: 10.5pt;"


class DocumentosPage(QWidget):
    """Documentos que cada empresa precisa entregar: lista da empresa escolhida e, ao
    lado, o cadastro do documento selecionado (ja editavel) ou de um documento novo."""

    def __init__(self, services, on_data_changed, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.on_data_changed = on_data_changed
        self.documentos: list[dict] = []
        self.editing_document_id: int | None = None
        self._company_id: int | None = None
        self.creating = False
        self.dirty = False
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(
            PageHeader(
                "Documentos",
                "O que cada empresa precisa entregar todo mês. Escolha a empresa e cadastre os documentos dela.",
            )
        )

        self.company_selector = CompanySelector(self.services.empresa_service, active_only=False, title="Empresa")
        self.company_selector.company_selected.connect(self._on_company_selected)
        self.company_selector.company_cleared.connect(self._on_company_cleared)
        layout.addWidget(self.company_selector)

        toolbar = ToolbarRow()
        self.list_info = QLabel("")
        self.list_info.setObjectName("Muted")
        toolbar.add(self.list_info)
        toolbar.add_stretch()
        self.import_button = make_button("Importar planilha")
        import_menu = QMenu(self.import_button)
        import_menu.addAction("Importar documentos desta empresa de uma planilha...", self.import_documentos_lote)
        import_menu.addSeparator()
        import_menu.addAction("Ver colunas da planilha", self.show_import_layout)
        import_menu.addAction("Baixar planilha modelo...", self.download_import_template)
        self.import_button.setMenu(import_menu)
        toolbar.add(self.import_button)
        self.new_button = make_button("Novo documento", "primary")
        self.new_button.clicked.connect(self.start_new)
        toolbar.add(self.new_button)
        layout.addWidget(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        self.table = make_readonly_table(["Tipo", "Documento", "Recebe por", "Observação"], stretch_column=3)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setToolTip("Segure Ctrl ou Shift para escolher vários e excluir de uma vez")
        self.table.itemSelectionChanged.connect(self._on_table_selection)
        splitter.addWidget(self.table)

        self.detail_stack = QStackedWidget()
        self.empty_label = QLabel()
        self.empty_label.setObjectName("Muted")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        empty_card = Card()
        QVBoxLayout(empty_card).addWidget(self.empty_label)
        self.detail_stack.addWidget(empty_card)
        self.detail_stack.addWidget(self._build_form())
        self.detail_stack.addWidget(self._build_multi_panel())
        splitter.addWidget(self.detail_stack)
        splitter.setSizes([640, 500])

        self._show_empty()

    # Paineis -----------------------------------------------------------------------

    def _build_form(self) -> QWidget:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 14)
        layout.setSpacing(10)

        self.form_title = QLabel()
        self.form_title.setStyleSheet("font-size: 13pt; font-weight: 600;")
        self.form_title.setWordWrap(True)
        layout.addWidget(self.form_title)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        tipo_row = QHBoxLayout()
        self.tipo_combo = QComboBox()
        self.tipo_combo.currentIndexChanged.connect(self._on_tipo_changed)
        tipo_row.addWidget(self.tipo_combo, 1)
        types_button = make_button("Tipos...", "quiet")
        types_button.setToolTip("Cadastrar, renomear ou excluir tipos de documento")
        types_button.clicked.connect(self._open_type_manager)
        tipo_row.addWidget(types_button)
        form.addRow("Tipo", tipo_row)

        nome_row = QHBoxLayout()
        self.nome_combo = QComboBox()
        self.nome_combo.setEditable(True)
        self.nome_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.nome_combo.lineEdit().setPlaceholderText("Ex: Extrato Itaú conta corrente")
        self.nome_combo.lineEdit().textEdited.connect(self._on_nome_edited)
        self.nome_combo.activated.connect(lambda _index: self._mark_dirty())
        nome_row.addWidget(self.nome_combo, 1)
        names_button = make_button("Nomes padrão...", "quiet")
        names_button.setToolTip("Lista de nomes sugeridos para cada tipo")
        names_button.clicked.connect(self._open_name_manager)
        nome_row.addWidget(names_button)
        form.addRow("Nome", nome_row)

        meios_box = QVBoxLayout()
        meios_box.setSpacing(4)
        self.meios_choices = CheckChoices(columns=3)
        self.meios_choices.changed.connect(self._mark_dirty)
        meios_box.addWidget(self.meios_choices)
        manage_meios = make_button("Gerenciar meios...", "quiet")
        manage_meios.setToolTip("Cadastrar ou renomear os meios de recebimento (Email, Onvio...)")
        manage_meios.clicked.connect(self._open_methods_manager)
        meios_row = QHBoxLayout()
        meios_row.addWidget(manage_meios)
        meios_row.addStretch(1)
        meios_box.addLayout(meios_row)
        form.addRow("Recebe por", meios_box)
        self.observacao_edit = QPlainTextEdit()
        self.observacao_edit.setPlaceholderText("Opcional: número da conta, produto da aplicação, contrato, quem envia...")
        self.observacao_edit.setMaximumHeight(72)
        self.observacao_edit.textChanged.connect(self._mark_dirty)
        form.addRow("Observação", self.observacao_edit)
        layout.addLayout(form)

        self.suggestion_label = QLabel("")
        self.suggestion_label.setObjectName("Muted")
        self.suggestion_label.setWordWrap(True)
        layout.addWidget(self.suggestion_label)
        layout.addStretch(1)

        actions = QHBoxLayout()
        self.delete_button = make_button("Excluir documento", "danger")
        self.delete_button.clicked.connect(self.delete_selected)
        actions.addWidget(self.delete_button)
        actions.addStretch(1)
        self.discard_button = make_button("Descartar", "quiet")
        self.discard_button.clicked.connect(self.discard_changes)
        actions.addWidget(self.discard_button)
        self.save_button = make_button("Salvar", "primary")
        self.save_button.clicked.connect(self.save_document)
        actions.addWidget(self.save_button)
        layout.addLayout(actions)
        return card

    def _build_multi_panel(self) -> QWidget:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 14)
        layout.addStretch(1)
        self.multi_label = QLabel()
        self.multi_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.multi_label.setStyleSheet("font-size: 12pt; font-weight: 600;")
        layout.addWidget(self.multi_label)
        hint = QLabel("O status de todos os meses desses documentos também será apagado.")
        hint.setObjectName("Muted")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)
        row = QHBoxLayout()
        row.addStretch(1)
        self.multi_delete_button = make_button("Excluir os documentos selecionados", "danger")
        self.multi_delete_button.clicked.connect(self.delete_selected)
        row.addWidget(self.multi_delete_button)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)
        return card

    # Dados -------------------------------------------------------------------------

    def refresh_data(self) -> None:
        self._refresh_tipos()
        self._refresh_meios_options()
        self.company_selector.refresh_companies()
        self._reload_documents()

    def _refresh_tipos(self) -> None:
        selected = self.tipo_combo.currentData()
        self.tipo_combo.blockSignals(True)
        self.tipo_combo.clear()
        for tipo in self.services.tipo_service.list_tipos():
            self.tipo_combo.addItem(tipo["nome_tipo"], tipo["id"])
        if selected is not None and self.tipo_combo.findData(selected) >= 0:
            self.tipo_combo.setCurrentIndex(self.tipo_combo.findData(selected))
        self.tipo_combo.blockSignals(False)

    def _refresh_meios_options(self) -> None:
        current = self.meios_choices.selected()
        options = [m["nome_meio"] for m in self.services.delivery_method_service.list_methods()]
        self.meios_choices.blockSignals(True)
        self.meios_choices.set_options(options, current)
        self.meios_choices.blockSignals(False)

    def _reload_documents(self) -> None:
        company_id = self.company_selector.get_selected_company_id()
        if not company_id:
            self.documentos = []
            fill_table(self.table, [])
            self.list_info.setText("")
            return
        self.documentos = self.services.documento_service.list_documentos_empresa(company_id)
        self.table.blockSignals(True)
        fill_table(
            self.table,
            [
                (
                    d["id"],
                    [d.get("nome_tipo") or "-", d["nome_documento"], d.get("meios_recebimento") or "-", d.get("observacao") or ""],
                )
                for d in self.documentos
            ],
        )
        if self.editing_document_id is not None:
            for row in range(self.table.rowCount()):
                if self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) == self.editing_document_id:
                    self.table.selectRow(row)
                    break
        self.table.blockSignals(False)
        total = len(self.documentos)
        self.list_info.setText(f"{total} documento(s) cadastrado(s)" if total else "Nenhum documento cadastrado")

    def _selected_document_ids(self) -> list[int]:
        ids = []
        for index in self.table.selectionModel().selectedRows():
            item = self.table.item(index.row(), 0)
            if item is not None:
                ids.append(int(item.data(Qt.ItemDataRole.UserRole)))
        return ids

    # Empresa e selecao -------------------------------------------------------------

    def _on_company_selected(self, company: dict) -> None:
        # O seletor avisa de novo a mesma empresa ao recarregar a lista (depois de salvar) e
        # quando o campo do codigo perde o foco: isso nao pode largar o documento aberto.
        if company["id"] == self._company_id:
            self._reload_documents()
            return
        self._company_id = company["id"]
        self.editing_document_id = None
        self._reload_documents()
        self._show_empty()

    def _on_company_cleared(self) -> None:
        self._company_id = None
        self.editing_document_id = None
        self._reload_documents()
        self._show_empty()

    def _on_table_selection(self) -> None:
        ids = self._selected_document_ids()
        if len(ids) > 1:
            if not self._confirm_discard():
                return
            self.creating = False
            self.multi_label.setText(f"{len(ids)} documentos selecionados")
            self.detail_stack.setCurrentIndex(2)
            return
        if len(ids) == 1 and ids[0] != self.editing_document_id:
            if not self._confirm_discard():
                return
            self._load_document(ids[0])

    def _show_empty(self) -> None:
        self.creating = False
        self.dirty = False
        has_company = self.company_selector.get_selected_company_id() is not None
        self.new_button.setEnabled(has_company)
        self.import_button.setEnabled(has_company)
        if not has_company:
            self.empty_label.setText("Escolha uma empresa acima para ver e cadastrar os documentos dela.")
        elif not self.documentos:
            self.empty_label.setText("Esta empresa ainda não tem documentos.\nClique em Novo documento para começar.")
        else:
            self.empty_label.setText("Clique num documento da lista para editar\nou em Novo documento.")
        self.detail_stack.setCurrentIndex(0)

    def _load_document(self, documento_id: int) -> None:
        documento = self.services.documento_service.get_documento(documento_id)
        self._loading = True
        self.editing_document_id = documento_id
        self.creating = False
        self.detail_stack.setCurrentIndex(1)
        self.form_title.setText(documento["nome_documento"])
        index = self.tipo_combo.findData(documento["tipo_documento_id"])
        if index >= 0:
            self.tipo_combo.setCurrentIndex(index)
        self.nome_combo.setCurrentText(documento["nome_documento"])
        self.meios_choices.set_selected(parse_delivery_methods(documento.get("meios_recebimento")))
        self.observacao_edit.setPlainText(documento.get("observacao") or "")
        self.delete_button.setVisible(True)
        self.suggestion_label.setText("")
        self._loading = False
        self._set_dirty(False)

    # Formulario --------------------------------------------------------------------

    def _on_tipo_changed(self, _index: int) -> None:
        self._refresh_name_suggestions()
        self._mark_dirty()

    def _on_nome_edited(self, _text: str) -> None:
        self._refresh_name_suggestions()
        self._mark_dirty()

    def _refresh_name_suggestions(self) -> None:
        if self._loading:
            return
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
            self.suggestion_label.setText(f"{len(suggestions)} nome(s) sugerido(s) - abra a lista do campo Nome.")
        elif search:
            self.suggestion_label.setText("Nenhum nome parecido cadastrado - será criado como novo.")
        else:
            self.suggestion_label.setText("")

    def _mark_dirty(self, *_args) -> None:
        if not self._loading:
            self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        self.dirty = dirty
        self.save_button.setEnabled(dirty or self.creating)
        self.discard_button.setEnabled(dirty or self.creating)
        self.save_button.setText("Cadastrar documento" if self.creating else "Salvar alterações")

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        answer = QMessageBox.question(self, "Documentos", "Há alterações não salvas. Deseja descartá-las?")
        if answer == QMessageBox.StandardButton.Yes:
            self.dirty = False
            return True
        return False

    # Acoes -------------------------------------------------------------------------

    def start_new(self) -> None:
        if not self.company_selector.get_selected_company_id():
            QMessageBox.information(self, "Documentos", "Escolha a empresa antes de cadastrar documentos.")
            return
        if not self._confirm_discard():
            return
        self._loading = True
        self.table.clearSelection()
        self.editing_document_id = None
        self.creating = True
        self.detail_stack.setCurrentIndex(1)
        self.form_title.setText("Novo documento")
        self.nome_combo.setCurrentText("")
        self.meios_choices.set_selected([])
        self.observacao_edit.clear()
        self.delete_button.setVisible(False)
        self._loading = False
        self._refresh_name_suggestions()
        self._set_dirty(False)
        self.nome_combo.setFocus()

    def discard_changes(self) -> None:
        self.dirty = False
        if self.creating or self.editing_document_id is None:
            self._show_empty()
            return
        self._load_document(self.editing_document_id)

    def save_document(self) -> None:
        company_id = self.company_selector.get_selected_company_id()
        if not company_id:
            return
        tipo_id = self.tipo_combo.currentData()
        if tipo_id is None:
            QMessageBox.warning(self, "Documentos", "Cadastre um tipo de documento antes (botão Tipos...).")
            return
        try:
            if self.creating:
                self.editing_document_id = self.services.documento_service.create_documento(
                    company_id,
                    tipo_id,
                    self.nome_combo.currentText(),
                    self.meios_choices.selected(),
                    observacao=self.observacao_edit.toPlainText(),
                )
            else:
                self.services.documento_service.update_documento(
                    self.editing_document_id,
                    tipo_id,
                    self.nome_combo.currentText(),
                    self.meios_choices.selected(),
                    observacao=self.observacao_edit.toPlainText(),
                )
        except ValidationError as exc:
            QMessageBox.critical(self, "Documentos", str(exc))
            return
        self.creating = False
        self.dirty = False
        self.on_data_changed()
        self._reload_documents()
        self._load_document(self.editing_document_id)

    def delete_selected(self) -> None:
        ids = self._selected_document_ids() or ([self.editing_document_id] if self.editing_document_id else [])
        if not ids:
            return
        texto = "este documento" if len(ids) == 1 else f"os {len(ids)} documentos selecionados"
        answer = QMessageBox.question(
            self,
            "Excluir documentos",
            f"Excluir {texto}? O status de todos os meses e o histórico de cobranças também serão apagados.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.services.documento_service.delete_documentos(ids)
        except ValidationError as exc:
            QMessageBox.critical(self, "Documentos", str(exc))
            return
        self.editing_document_id = None
        self.dirty = False
        self.on_data_changed()
        self._reload_documents()
        self._show_empty()

    # Planilha ----------------------------------------------------------------------

    def show_import_layout(self) -> None:
        DocumentoImportLayoutDialog(self.services.import_service, self).exec()

    def download_import_template(self) -> None:
        file_path, _filter = QFileDialog.getSaveFileName(
            self,
            "Salvar planilha modelo",
            str(get_documents_directory() / "modelo_documentos.xlsx"),
            "Planilha Excel (*.xlsx)",
        )
        if not file_path:
            return
        try:
            self.services.import_service.export_documento_template(file_path)
        except ValidationError as exc:
            QMessageBox.critical(self, "Documentos", str(exc))
            return
        QMessageBox.information(self, "Documentos", f"Planilha modelo salva em:\n{file_path}")

    def import_documentos_lote(self) -> None:
        company_id = self.company_selector.get_selected_company_id()
        if not company_id:
            QMessageBox.information(self, "Documentos", "Escolha a empresa antes de importar.")
            return
        file_path, _filter = QFileDialog.getOpenFileName(
            self,
            "Escolha a planilha de documentos",
            str(get_documents_directory()),
            "Planilhas Excel (*.xlsx *.xlsm);;Todos os arquivos (*.*)",
        )
        if not file_path:
            return
        runner = BlockingTaskRunner(self)
        runner.run(
            "Importando documentos...",
            lambda: self.services.import_service.import_documentos(file_path, company_id),
            on_success=self._on_import_documentos_finished,
            on_error=lambda message: QMessageBox.critical(self, "Importar documentos", message),
        )

    def _on_import_documentos_finished(self, result: dict) -> None:
        self.on_data_changed()
        self._reload_documents()
        self._show_empty()
        summary = [f'Documentos cadastrados: {result["imported"]}']
        if result["failed"]:
            summary.append(f'Linhas com problema: {result["failed"]}')
        if result["errors"]:
            summary.append("")
            summary.append("Problemas encontrados:")
            summary.extend(result["errors"][:10])
        QMessageBox.information(self, "Importar documentos", "\n".join(summary))

    # Gerenciadores -----------------------------------------------------------------

    def _open_name_manager(self) -> None:
        dialog = DocumentNameManagerDialog(
            self.services.documento_service,
            self.services.tipo_service,
            "Documentos",
            self.tipo_combo.currentData(),
            allow_apply_to_document=self.detail_stack.currentIndex() == 1,
            parent=self,
        )
        dialog.exec()
        if dialog.applied_name is not None:
            self.nome_combo.setCurrentText(dialog.applied_name)
            self._mark_dirty()
        self._refresh_name_suggestions()

    def _open_type_manager(self) -> None:
        dialog = DocumentTypeManagerDialog(
            self.services.tipo_service,
            "Documentos",
            self.tipo_combo.currentData(),
            allow_apply_to_document=self.detail_stack.currentIndex() == 1,
            parent=self,
        )
        dialog.exec()
        self._refresh_tipos()
        if dialog.applied_type_id is not None:
            index = self.tipo_combo.findData(dialog.applied_type_id)
            if index >= 0:
                self.tipo_combo.setCurrentIndex(index)
        if dialog.data_changed:
            self._reload_documents()

    def _open_methods_manager(self) -> None:
        dialog = DeliveryMethodsManagerDialog(self.services.delivery_method_service, allow_apply=False, parent=self)
        dialog.exec()
        if dialog.data_changed:
            self._refresh_meios_options()
            self._reload_documents()
