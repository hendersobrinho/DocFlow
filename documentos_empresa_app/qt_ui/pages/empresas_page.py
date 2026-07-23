from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.widgets.common import Card, PageHeader, make_button
from documentos_empresa_app.qt_ui.widgets.company_selector import CompanySelector
from documentos_empresa_app.utils.common import MAX_COMPANY_OBSERVATION_LENGTH, ValidationError


class ImportLayoutDialog(QDialog):
    def __init__(self, import_service, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Cadastro completo - Layout de importacao")
        self.resize(820, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        description = QLabel(
            "Use uma linha por documento. As quatro primeiras colunas identificam a empresa, depois vem "
            "nome do documento, meio de recebimento, tipo e observacao da empresa. As colunas de meses no "
            "final sao opcionais e aceitam OK para Recebido, P para Pendente, X para Nao cobrar e vazio "
            "para nao preencher nada. Para importar so a empresa, deixe as colunas de documento em branco."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        table = QTableWidget(0, 4)
        table.setHorizontalHeaderLabels(["Ordem", "Coluna", "Obrigatorio", "Exemplo"])
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        for item in import_service.get_cadastro_completo_import_layout():
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(str(item["index"])))
            table.setItem(row, 1, QTableWidgetItem(item["field"]))
            table.setItem(row, 2, QTableWidgetItem("Sim" if item["required"] else "Nao"))
            table.setItem(row, 3, QTableWidgetItem(str(item["example"])))
        layout.addWidget(table, 1)

        close_button = make_button("Fechar", "quiet")
        close_button.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)


class EmpresasPage(QWidget):
    def __init__(self, services, on_data_changed, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.on_data_changed = on_data_changed
        self.selected_company: dict | None = None
        self.form_mode = "idle"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        layout.addWidget(PageHeader("Empresas", "Consulte, cadastre e mantenha o cadastro das empresas atendidas."))

        columns = QHBoxLayout()
        columns.setSpacing(14)
        layout.addLayout(columns, 1)

        # Coluna esquerda: consulta + resumo
        left_card = Card()
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(18, 16, 18, 16)
        left_layout.setSpacing(10)
        columns.addWidget(left_card, 1)

        self.company_selector = CompanySelector(
            self.services.empresa_service, active_only=False, title="Localizar empresa"
        )
        self.company_selector.company_selected.connect(self._on_company_selected)
        self.company_selector.company_cleared.connect(self._on_company_cleared)
        left_layout.addWidget(self.company_selector)

        self.summary_status = QLabel("Nenhuma empresa consultada.")
        self.summary_status.setObjectName("Muted")
        left_layout.addWidget(self.summary_status)

        summary_form = QFormLayout()
        summary_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.summary_fields: dict[str, QLabel] = {}
        for key, label in (
            ("codigo", "Codigo"),
            ("nome", "Nome"),
            ("email", "Email"),
            ("contato", "Contato"),
            ("cnpj", "CNPJ"),
            ("observacao", "Observacao"),
            ("cobranca", "Cobranca"),
        ):
            value_label = QLabel("-")
            value_label.setWordWrap(True)
            self.summary_fields[key] = value_label
            summary_form.addRow(f"{label}:", value_label)
        left_layout.addLayout(summary_form)
        left_layout.addStretch(1)

        summary_actions = QHBoxLayout()
        self.edit_button = make_button("Editar cadastro")
        self.edit_button.clicked.connect(self.start_edit)
        summary_actions.addWidget(self.edit_button)
        self.toggle_active_button = make_button("Inativar")
        self.toggle_active_button.clicked.connect(self.toggle_active)
        summary_actions.addWidget(self.toggle_active_button)
        self.delete_button = make_button("Excluir", "danger")
        self.delete_button.clicked.connect(self.delete_company)
        summary_actions.addWidget(self.delete_button)
        left_layout.addLayout(summary_actions)

        # Coluna direita: formulario
        right_card = Card()
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(18, 16, 18, 16)
        right_layout.setSpacing(8)
        columns.addWidget(right_card, 1)

        form_title = QLabel("Cadastro e manutencao")
        form_title.setStyleSheet("font-weight: 600; font-size: 11pt;")
        right_layout.addWidget(form_title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)

        grid.addWidget(QLabel("Codigo da empresa"), 0, 0)
        self.codigo_edit = QLineEdit()
        grid.addWidget(self.codigo_edit, 1, 0)
        grid.addWidget(QLabel("Nome da empresa"), 0, 1)
        self.nome_edit = QLineEdit()
        grid.addWidget(self.nome_edit, 1, 1)

        grid.addWidget(QLabel("Email para contato (opcional)"), 2, 0)
        self.email_edit = QLineEdit()
        grid.addWidget(self.email_edit, 3, 0)
        grid.addWidget(QLabel("Nome de contato (opcional)"), 2, 1)
        self.contato_edit = QLineEdit()
        grid.addWidget(self.contato_edit, 3, 1)

        grid.addWidget(QLabel("CNPJ (opcional, usado pelo agente de documentos)"), 4, 0)
        self.cnpj_edit = QLineEdit()
        self.cnpj_edit.setPlaceholderText("00.000.000/0000-00")
        grid.addWidget(self.cnpj_edit, 5, 0)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        right_layout.addLayout(grid)

        right_layout.addWidget(QLabel(f"Observacao livre (opcional, max {MAX_COMPANY_OBSERVATION_LENGTH} caracteres)"))
        self.observacao_edit = QTextEdit()
        self.observacao_edit.setMaximumHeight(84)
        self.observacao_edit.textChanged.connect(self._enforce_observacao_limit)
        right_layout.addWidget(self.observacao_edit)
        self.observacao_counter = QLabel(f"0/{MAX_COMPANY_OBSERVATION_LENGTH}")
        self.observacao_counter.setObjectName("Muted")
        self.observacao_counter.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_layout.addWidget(self.observacao_counter)

        cobranca_label = QLabel("Regra propria de cobranca (deixe em branco para herdar a regra global)")
        cobranca_label.setObjectName("Muted")
        right_layout.addWidget(cobranca_label)
        cobranca_grid = QGridLayout()
        cobranca_grid.setHorizontalSpacing(10)
        cobranca_grid.addWidget(QLabel("Dia inicial"), 0, 0)
        self.cobranca_inicio_edit = QLineEdit()
        cobranca_grid.addWidget(self.cobranca_inicio_edit, 1, 0)
        cobranca_grid.addWidget(QLabel("Dia final"), 0, 1)
        self.cobranca_fim_edit = QLineEdit()
        cobranca_grid.addWidget(self.cobranca_fim_edit, 1, 1)
        cobranca_grid.addWidget(QLabel("Dias para alerta"), 0, 2)
        self.cobranca_alerta_edit = QLineEdit()
        cobranca_grid.addWidget(self.cobranca_alerta_edit, 1, 2)
        right_layout.addLayout(cobranca_grid)

        form_actions = QHBoxLayout()
        self.new_button = make_button("Novo cadastro")
        self.new_button.clicked.connect(self.start_new)
        form_actions.addWidget(self.new_button)
        self.save_button = make_button("Salvar", "primary")
        self.save_button.clicked.connect(self.save_company)
        form_actions.addWidget(self.save_button)
        self.cancel_button = make_button("Cancelar", "quiet")
        self.cancel_button.clicked.connect(self.cancel_edit)
        form_actions.addWidget(self.cancel_button)
        form_actions.addStretch(1)
        right_layout.addLayout(form_actions)

        right_layout.addStretch(1)

        import_row = QHBoxLayout()
        import_button = make_button("Importar planilha", "primary")
        import_button.clicked.connect(self.import_full_registrations)
        import_row.addWidget(import_button)
        layout_menu_button = make_button("Layout e modelo")
        layout_menu = QMenu(layout_menu_button)
        layout_menu.addAction("Ver layout", self.show_import_layout)
        layout_menu.addAction("Baixar modelo", self.download_import_template)
        layout_menu_button.setMenu(layout_menu)
        import_row.addWidget(layout_menu_button)
        import_row.addStretch(1)
        right_layout.addLayout(import_row)

        self._set_form_mode("idle")

    def refresh_data(self) -> None:
        self.company_selector.refresh_companies()

    # Selecao / resumo

    def _on_company_selected(self, company: dict) -> None:
        self.selected_company = company
        self._populate_form(company)
        self._update_summary(company)
        self._set_form_mode("view")

    def _on_company_cleared(self) -> None:
        self.selected_company = None
        self._clear_form_fields()
        self._update_summary(None)
        self._set_form_mode("idle")

    def _update_summary(self, company: dict | None) -> None:
        if company is None:
            self.summary_status.setText("Nenhuma empresa consultada.")
            for value_label in self.summary_fields.values():
                value_label.setText("-")
            return

        self.summary_status.setText("Empresa ativa." if company["ativa"] else "Empresa inativa.")
        self.summary_fields["codigo"].setText(str(company["codigo_empresa"]))
        self.summary_fields["nome"].setText(company["nome_empresa"])
        self.summary_fields["email"].setText(company.get("email_contato") or "-")
        self.summary_fields["contato"].setText(company.get("nome_contato") or "-")
        self.summary_fields["cnpj"].setText(company.get("cnpj") or "-")
        self.summary_fields["observacao"].setText(company.get("observacao") or "-")
        self.summary_fields["cobranca"].setText(self._format_collection_rule(company))
        self.toggle_active_button.setText("Inativar" if company["ativa"] else "Reativar")

    def _format_collection_rule(self, company: dict) -> str:
        if (
            company.get("cobranca_inicio_dia") is None
            and company.get("cobranca_fim_dia") is None
            and company.get("cobranca_alerta_dias") is None
        ):
            settings = self.services.collection_service.get_global_settings()
            return (
                f'Usa regra global: inicio dia {settings["inicio_cobranca_dia"]}, '
                f'fim dia {settings["encerramento_cobranca_dia"]}, '
                f'alerta apos {settings["alerta_apos_dias"]} dia(s).'
            )
        parts = []
        if company.get("cobranca_inicio_dia") is not None:
            parts.append(f'inicio dia {company["cobranca_inicio_dia"]}')
        if company.get("cobranca_fim_dia") is not None:
            parts.append(f'fim dia {company["cobranca_fim_dia"]}')
        if company.get("cobranca_alerta_dias") is not None:
            parts.append(f'alerta apos {company["cobranca_alerta_dias"]} dia(s)')
        return "Regra propria: " + ", ".join(parts) + "."

    # Formulario

    def _populate_form(self, company: dict) -> None:
        self.codigo_edit.setText(str(company["codigo_empresa"]))
        self.nome_edit.setText(company["nome_empresa"])
        self.email_edit.setText(company.get("email_contato") or "")
        self.contato_edit.setText(company.get("nome_contato") or "")
        self.cnpj_edit.setText(company.get("cnpj") or "")
        self.observacao_edit.setPlainText(company.get("observacao") or "")
        for edit, key in (
            (self.cobranca_inicio_edit, "cobranca_inicio_dia"),
            (self.cobranca_fim_edit, "cobranca_fim_dia"),
            (self.cobranca_alerta_edit, "cobranca_alerta_dias"),
        ):
            value = company.get(key)
            edit.setText("" if value is None else str(value))

    def _clear_form_fields(self) -> None:
        for edit in (
            self.codigo_edit,
            self.nome_edit,
            self.email_edit,
            self.contato_edit,
            self.cnpj_edit,
            self.cobranca_inicio_edit,
            self.cobranca_fim_edit,
            self.cobranca_alerta_edit,
        ):
            edit.clear()
        self.observacao_edit.clear()

    def _set_form_mode(self, mode: str) -> None:
        self.form_mode = mode
        editable = mode in {"new", "edit"}
        has_selection = self.selected_company is not None

        self.codigo_edit.setEnabled(mode == "new")
        for widget in (
            self.nome_edit,
            self.email_edit,
            self.contato_edit,
            self.cnpj_edit,
            self.observacao_edit,
            self.cobranca_inicio_edit,
            self.cobranca_fim_edit,
            self.cobranca_alerta_edit,
        ):
            widget.setEnabled(editable)
        self.save_button.setEnabled(editable)
        self.cancel_button.setEnabled(editable)
        self.new_button.setEnabled(not editable)
        self.edit_button.setEnabled(has_selection and not editable)
        self.delete_button.setEnabled(has_selection and not editable)
        self.toggle_active_button.setEnabled(has_selection and not editable)

    def _enforce_observacao_limit(self) -> None:
        text = self.observacao_edit.toPlainText()
        if len(text) > MAX_COMPANY_OBSERVATION_LENGTH:
            cursor = self.observacao_edit.textCursor()
            self.observacao_edit.blockSignals(True)
            self.observacao_edit.setPlainText(text[:MAX_COMPANY_OBSERVATION_LENGTH])
            cursor.setPosition(MAX_COMPANY_OBSERVATION_LENGTH)
            self.observacao_edit.setTextCursor(cursor)
            self.observacao_edit.blockSignals(False)
            text = self.observacao_edit.toPlainText()
        self.observacao_counter.setText(f"{len(text)}/{MAX_COMPANY_OBSERVATION_LENGTH}")

    # Acoes

    def start_new(self) -> None:
        self.company_selector.clear_selection()
        self._clear_form_fields()
        self._set_form_mode("new")
        self.codigo_edit.setFocus()

    def start_edit(self) -> None:
        if not self.selected_company:
            QMessageBox.warning(self, "Empresas", "Selecione uma empresa para editar.")
            return
        company = self.services.empresa_service.get_empresa(self.selected_company["id"])
        self.selected_company = company
        self._populate_form(company)
        self._set_form_mode("edit")

    def cancel_edit(self) -> None:
        if self.selected_company:
            company = self.services.empresa_service.get_empresa(self.selected_company["id"])
            self._on_company_selected(company)
            return
        self._on_company_cleared()

    def save_company(self) -> None:
        if self.form_mode not in {"new", "edit"}:
            return

        target_company_id = self.selected_company["id"] if self.selected_company else None
        try:
            self.services.collection_service.validate_company_settings_values(
                self.cobranca_inicio_edit.text(),
                self.cobranca_fim_edit.text(),
                self.cobranca_alerta_edit.text(),
            )
            if self.form_mode == "edit" and target_company_id:
                self.services.empresa_service.update_empresa(
                    target_company_id,
                    self.nome_edit.text(),
                    self.email_edit.text(),
                    self.contato_edit.text(),
                    self.observacao_edit.toPlainText(),
                    self.cnpj_edit.text(),
                )
                self.services.collection_service.update_company_settings(
                    target_company_id,
                    self.cobranca_inicio_edit.text(),
                    self.cobranca_fim_edit.text(),
                    self.cobranca_alerta_edit.text(),
                )
                QMessageBox.information(self, "Empresas", "Empresa atualizada com sucesso.")
            else:
                target_company_id = self.services.empresa_service.create_empresa(
                    self.codigo_edit.text(),
                    self.nome_edit.text(),
                    self.email_edit.text(),
                    self.contato_edit.text(),
                    self.observacao_edit.toPlainText(),
                    self.cnpj_edit.text(),
                )
                self.services.collection_service.update_company_settings(
                    target_company_id,
                    self.cobranca_inicio_edit.text(),
                    self.cobranca_fim_edit.text(),
                    self.cobranca_alerta_edit.text(),
                )
                QMessageBox.information(self, "Empresas", "Empresa cadastrada com sucesso.")
        except ValidationError as exc:
            QMessageBox.critical(self, "Empresas", str(exc))
            return

        self.on_data_changed()
        if target_company_id:
            self.company_selector.set_company(target_company_id)

    def toggle_active(self) -> None:
        if not self.selected_company:
            return
        active = not bool(self.selected_company.get("ativa"))
        self.services.empresa_service.set_empresa_ativa(self.selected_company["id"], active)
        estado = "reativada" if active else "inativada"
        QMessageBox.information(self, "Empresas", f"Empresa {estado} com sucesso.")
        company_id = self.selected_company["id"]
        self.on_data_changed()
        self.company_selector.set_company(company_id)

    def delete_company(self) -> None:
        if not self.selected_company:
            return
        answer = QMessageBox.question(
            self,
            "Excluir empresa",
            "Deseja excluir a empresa selecionada? Os documentos e status mensais vinculados tambem serao apagados.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.services.empresa_service.delete_empresa(self.selected_company["id"])
        self.company_selector.clear_selection()
        self.on_data_changed()
        QMessageBox.information(self, "Empresas", "Empresa excluida com sucesso.")

    # Importacao

    def show_import_layout(self) -> None:
        ImportLayoutDialog(self.services.import_service, self).exec()

    def download_import_template(self) -> None:
        file_path, _filter = QFileDialog.getSaveFileName(
            self,
            "Salvar modelo de importacao completa",
            "modelo_importacao_cadastro_completo.xlsx",
            "Planilha Excel (*.xlsx)",
        )
        if not file_path:
            return
        try:
            self.services.import_service.export_cadastro_completo_template(file_path)
        except ValidationError as exc:
            QMessageBox.critical(self, "Empresas", str(exc))
            return
        QMessageBox.information(self, "Empresas", f"Modelo salvo com sucesso em:\n{file_path}")

    def import_full_registrations(self) -> None:
        file_path, _filter = QFileDialog.getOpenFileName(
            self,
            "Selecione o arquivo Excel do cadastro completo",
            "",
            "Arquivos Excel (*.xlsx *.xlsm);;Todos os arquivos (*.*)",
        )
        if not file_path:
            return

        try:
            result = self.services.import_service.import_cadastros_completos(file_path)
        except ValidationError as exc:
            QMessageBox.critical(self, "Importacao de cadastro completo", str(exc))
            return

        self.on_data_changed()
        summary = [
            f'Linhas processadas: {result["processed_rows"]}',
            f'Empresas criadas: {result["companies_created"]}',
            f'Empresas atualizadas: {result["companies_updated"]}',
            f'Empresas reutilizadas: {result["companies_reused"]}',
            f'Tipos criados: {result["types_created"]}',
            f'Documentos importados: {result["documents_imported"]}',
            f'Status importados: {result["statuses_imported"]}',
            f'Linhas com falha: {result["failed"]}',
        ]
        if result["errors"]:
            summary.append("")
            summary.append("Erros encontrados:")
            summary.extend(result["errors"][:10])
        QMessageBox.information(self, "Importacao de cadastro completo", "\n".join(summary))
