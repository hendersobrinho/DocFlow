from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.theme import tokens
from documentos_empresa_app.qt_ui.widgets.common import Card, PageHeader, ToolbarRow, make_button
from documentos_empresa_app.qt_ui.widgets.tables import fill_table, make_readonly_table, selected_key
from documentos_empresa_app.qt_ui.workers import BlockingTaskRunner
from documentos_empresa_app.services.whatsapp_service import format_whatsapp, normalize_grupo_link, normalize_whatsapp
from documentos_empresa_app.utils.common import MAX_COMPANY_OBSERVATION_LENGTH, ValidationError
from documentos_empresa_app.utils.helpers import get_documents_directory


class ImportLayoutDialog(QDialog):
    def __init__(self, import_service, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Layout da planilha de importação")
        self.resize(820, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        description = QLabel(
            "Use uma linha por documento. As quatro primeiras colunas identificam a empresa; depois vêm "
            "nome do documento, meio de recebimento, tipo e observação da empresa. As colunas de meses no "
            "final são opcionais e aceitam OK para Recebido, P para Pendente, X para Não cobrar e vazio "
            "para não preencher nada. Para importar só a empresa, deixe as colunas de documento em branco."
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

        for item in import_service.get_cadastro_completo_import_layout():
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


SECTION_STYLE = "font-weight: 600; font-size: 10.5pt; margin-top: 6px;"


class EmpresasPage(QWidget):
    """Lista de empresas (com busca) e, ao lado, o cadastro da empresa escolhida, ja
    editavel. Acoes raras (inativar, remover contato, excluir) ficam em 'Mais acoes'."""

    def __init__(self, services, on_data_changed, on_open_ficha=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.on_data_changed = on_data_changed
        self.on_open_ficha = on_open_ficha
        self.companies: list[dict] = []
        self.selected_company: dict | None = None
        self.creating = False
        self.dirty = False
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(
            PageHeader("Empresas", "Todas as empresas atendidas. Clique numa empresa para ver e editar o cadastro.")
        )

        toolbar = ToolbarRow()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Buscar por código, nome ou CNPJ")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMinimumWidth(320)
        self.search_edit.textChanged.connect(lambda _text: self._render_list())
        toolbar.add(self.search_edit)
        self.show_inactive_check = QCheckBox("Mostrar inativas")
        self.show_inactive_check.toggled.connect(lambda _checked: self._render_list())
        toolbar.add(self.show_inactive_check)
        toolbar.add_stretch()
        import_button = make_button("Importar planilha")
        import_menu = QMenu(import_button)
        import_menu.addAction("Importar empresas e documentos de uma planilha...", self.import_full_registrations)
        import_menu.addSeparator()
        import_menu.addAction("Ver colunas da planilha", self.show_import_layout)
        import_menu.addAction("Baixar planilha modelo...", self.download_import_template)
        import_button.setMenu(import_menu)
        toolbar.add(import_button)
        new_button = make_button("Nova empresa", "primary")
        new_button.clicked.connect(self.start_new)
        toolbar.add(new_button)
        layout.addWidget(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        self.table = make_readonly_table(["Código", "Empresa", "CNPJ", "Contato", "Situação"], stretch_column=1)
        self.table.itemSelectionChanged.connect(self._on_table_selection)
        splitter.addWidget(self.table)

        self.detail_stack = QStackedWidget()
        empty = QLabel("Escolha uma empresa na lista\nou clique em Nova empresa.")
        empty.setObjectName("Muted")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_card = Card()
        QVBoxLayout(empty_card).addWidget(empty)
        self.detail_stack.addWidget(empty_card)
        self.detail_stack.addWidget(self._build_form())
        splitter.addWidget(self.detail_stack)
        splitter.setSizes([620, 520])
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

    # Formulario --------------------------------------------------------------------

    def _build_form(self) -> QWidget:
        card = Card()
        outer = QVBoxLayout(card)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll, 1)
        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 16, 20, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self.form_title = QLabel()
        self.form_title.setStyleSheet("font-size: 13pt; font-weight: 600;")
        self.form_title.setWordWrap(True)
        header.addWidget(self.form_title, 1)
        self.status_badge = QLabel()
        header.addWidget(self.status_badge)
        layout.addLayout(header)

        # Um unico formulario para todas as secoes - assim os rotulos ficam alinhados.
        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        layout.addLayout(form)

        def section(title: str) -> QFormLayout:
            label = QLabel(title)
            label.setStyleSheet(SECTION_STYLE)
            form.addRow(label)
            return form

        ident = section("Identificação")
        self.codigo_edit = QLineEdit()
        self.codigo_edit.setPlaceholderText("Número usado no escritório")
        ident.addRow("Código", self.codigo_edit)
        self.nome_edit = QLineEdit()
        ident.addRow("Nome", self.nome_edit)
        self.cnpj_edit = QLineEdit()
        self.cnpj_edit.setPlaceholderText("Opcional - ex: 12.345.678/0001-90")
        self.cnpj_edit.setToolTip("Aceita o CNPJ tradicional e o novo formato alfanumérico da Receita Federal.")
        ident.addRow("CNPJ", self.cnpj_edit)

        contato = section("Contato para cobrança")
        self.contato_edit = QLineEdit()
        self.contato_edit.setPlaceholderText("Opcional")
        contato.addRow("Nome", self.contato_edit)
        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("Opcional - mais de um? separe por vírgula: a@empresa.com, b@empresa.com")
        self.email_edit.setToolTip("A cobrança e os envios por email vão para todos os emails informados aqui.")
        contato.addRow("Email(s)", self.email_edit)
        self.whatsapp_edit = QLineEdit()
        self.whatsapp_edit.setPlaceholderText("Opcional - ex: (27) 99999-8888; usado nas cobranças por WhatsApp")
        contato.addRow("WhatsApp", self.whatsapp_edit)
        self.whatsapp_grupo_edit = QLineEdit()
        self.whatsapp_grupo_edit.setPlaceholderText("Opcional - link do grupo, se a empresa é atendida num grupo")
        self.whatsapp_grupo_edit.setToolTip(
            "No WhatsApp: abra o grupo > Convidar via link > Copiar link (https://chat.whatsapp.com/...).\n"
            "Com o link, os envios abrem o grupo em vez da conversa com o número."
        )
        contato.addRow("Grupo do WhatsApp", self.whatsapp_grupo_edit)
        self.whatsapp_envios_check = QCheckBox("Pode usar o WhatsApp nos envios (cobranças e mala direta)")
        self.whatsapp_envios_check.setToolTip(
            "Marcado: os envios automáticos vão por WhatsApp para esta empresa (no grupo, se houver link),\n"
            "em vez de email. Sem marcar, o WhatsApp fica só como contato."
        )
        contato.addRow("", self.whatsapp_envios_check)
        self.opt_out_checkbox = QCheckBox("Não incluir esta empresa na mala direta por email")
        contato.addRow("", self.opt_out_checkbox)

        cobranca = section("Prazos de cobrança")
        self.own_rule_check = QCheckBox("Usar prazos próprios para esta empresa")
        self.own_rule_check.setToolTip("Sem marcar, a empresa segue os prazos gerais de Configurações.")
        self.own_rule_check.toggled.connect(self._on_own_rule_toggled)
        cobranca.addRow("", self.own_rule_check)
        self.rule_start_spin = QSpinBox()
        self.rule_start_spin.setRange(1, 31)
        self.rule_start_spin.setPrefix("dia ")
        self.rule_start_spin.setMaximumWidth(120)
        cobranca.addRow("Começar a cobrar no", self.rule_start_spin)
        self.rule_end_spin = QSpinBox()
        self.rule_end_spin.setRange(1, 31)
        self.rule_end_spin.setPrefix("dia ")
        self.rule_end_spin.setMaximumWidth(120)
        cobranca.addRow("Prazo final no", self.rule_end_spin)
        self.rule_alert_spin = QSpinBox()
        self.rule_alert_spin.setRange(0, 60)
        self.rule_alert_spin.setSuffix(" dia(s) de atraso")
        self.rule_alert_spin.setMaximumWidth(240)
        cobranca.addRow("Priorizar depois de", self.rule_alert_spin)
        self.rule_hint = QLabel()
        self.rule_hint.setObjectName("Muted")
        self.rule_hint.setWordWrap(True)
        cobranca.addRow("", self.rule_hint)

        obs_label = QLabel("Observação")
        obs_label.setStyleSheet(SECTION_STYLE)
        layout.addWidget(obs_label)
        self.observacao_edit = QTextEdit()
        self.observacao_edit.setPlaceholderText("Qualquer informação útil sobre a empresa (opcional)")
        self.observacao_edit.setMaximumHeight(80)
        self.observacao_edit.textChanged.connect(self._enforce_observacao_limit)
        layout.addWidget(self.observacao_edit)
        self.observacao_counter = QLabel(f"0/{MAX_COMPANY_OBSERVATION_LENGTH}")
        self.observacao_counter.setObjectName("Muted")
        self.observacao_counter.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.observacao_counter)
        layout.addStretch(1)

        for edit in (
            self.codigo_edit, self.nome_edit, self.cnpj_edit, self.contato_edit, self.email_edit,
            self.whatsapp_edit, self.whatsapp_grupo_edit,
        ):
            edit.textEdited.connect(self._mark_dirty)
        for check in (self.opt_out_checkbox, self.own_rule_check, self.whatsapp_envios_check):
            check.toggled.connect(self._mark_dirty)
        for spin in (self.rule_start_spin, self.rule_end_spin, self.rule_alert_spin):
            spin.valueChanged.connect(self._mark_dirty)
        self.observacao_edit.textChanged.connect(self._mark_dirty)

        actions = QHBoxLayout()
        actions.setContentsMargins(20, 8, 20, 14)
        self.more_button = make_button("Mais ações")
        more_menu = QMenu(self.more_button)
        self.toggle_active_action = more_menu.addAction("Inativar empresa", self.toggle_active)
        more_menu.addAction("Remover dados de contato (LGPD)...", self.clear_contact_info)
        more_menu.addSeparator()
        more_menu.addAction("Excluir empresa...", self.delete_company)
        self.more_button.setMenu(more_menu)
        actions.addWidget(self.more_button)
        self.ficha_button = make_button("Abrir ficha")
        self.ficha_button.setToolTip("Forma de envio, registro dos documentos e histórico de cobranças")
        self.ficha_button.clicked.connect(self.open_ficha)
        actions.addWidget(self.ficha_button)
        actions.addStretch(1)
        self.discard_button = make_button("Descartar", "quiet")
        self.discard_button.clicked.connect(self.discard_changes)
        actions.addWidget(self.discard_button)
        self.save_button = make_button("Salvar", "primary")
        self.save_button.clicked.connect(self.save_company)
        actions.addWidget(self.save_button)
        outer.addLayout(actions)
        return card

    # Lista -------------------------------------------------------------------------

    def refresh_data(self) -> None:
        self.companies = self.services.empresa_service.list_empresas(active_only=False)
        self._render_list()
        if self.selected_company is not None and not self.dirty:
            fresh = next((c for c in self.companies if c["id"] == self.selected_company["id"]), None)
            if fresh is None:
                self._show_empty()
            else:
                self._load_company(fresh)

    def _render_list(self) -> None:
        search = self.search_edit.text().strip().casefold()
        digits = "".join(ch for ch in search if ch.isalnum())
        rows = []
        colors = {}
        muted = tokens()["muted"]
        for company in self.companies:
            if not company["ativa"] and not self.show_inactive_check.isChecked():
                continue
            if search:
                haystack = f'{company["codigo_empresa"]} {company["nome_empresa"]}'.casefold()
                cnpj = (company.get("cnpj") or "").casefold()
                if search not in haystack and not (digits and digits in cnpj):
                    continue
            contato = company.get("nome_contato") or company.get("email_contato") or "-"
            index = len(rows)
            rows.append(
                (
                    company["id"],
                    [
                        str(company["codigo_empresa"]),
                        company["nome_empresa"],
                        company.get("cnpj") or "-",
                        contato,
                        "Ativa" if company["ativa"] else "Inativa",
                    ],
                )
            )
            if not company["ativa"]:
                for column in range(5):
                    colors[(index, column)] = muted
        self.table.blockSignals(True)
        fill_table(self.table, rows, colors)
        if self.selected_company is not None:
            for row in range(self.table.rowCount()):
                if self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) == self.selected_company["id"]:
                    self.table.selectRow(row)
                    break
        self.table.blockSignals(False)

    def _on_table_selection(self) -> None:
        company_id = selected_key(self.table)
        if company_id is None:
            return
        if self.selected_company is not None and self.selected_company["id"] == company_id and not self.creating:
            return
        if not self._confirm_discard():
            self._render_list()
            return
        company = next((c for c in self.companies if c["id"] == company_id), None)
        if company is not None:
            self._load_company(company)

    # Estado do formulario ------------------------------------------------------------

    def _show_empty(self) -> None:
        self.selected_company = None
        self.creating = False
        self.dirty = False
        self.detail_stack.setCurrentIndex(0)

    def _load_company(self, company: dict) -> None:
        self._loading = True
        self.selected_company = company
        self.creating = False
        self.detail_stack.setCurrentIndex(1)
        self.form_title.setText(f'{company["codigo_empresa"]} - {company["nome_empresa"]}')
        self._set_badge(bool(company["ativa"]))
        self.codigo_edit.setText(str(company["codigo_empresa"]))
        self.codigo_edit.setReadOnly(True)
        self.codigo_edit.setToolTip("O código não pode ser alterado depois do cadastro.")
        self.nome_edit.setText(company["nome_empresa"])
        self.cnpj_edit.setText(company.get("cnpj") or "")
        self.contato_edit.setText(company.get("nome_contato") or "")
        self.email_edit.setText(company.get("email_contato") or "")
        self.whatsapp_edit.setText(format_whatsapp(company.get("whatsapp")))
        self.whatsapp_grupo_edit.setText(company.get("whatsapp_grupo") or "")
        self.whatsapp_envios_check.setChecked(bool(company.get("whatsapp_envios")))
        self.opt_out_checkbox.setChecked(bool(company.get("nao_contatar_mala_direta")))
        self.observacao_edit.setPlainText(company.get("observacao") or "")
        self._load_rule(company)
        self.toggle_active_action.setText("Inativar empresa" if company["ativa"] else "Reativar empresa")
        self.more_button.setEnabled(True)
        self.ficha_button.setEnabled(True)
        self._loading = False
        self._set_dirty(False)

    def _load_rule(self, company: dict | None) -> None:
        settings = self.services.collection_service.get_global_settings()
        own = company is not None and any(
            company.get(key) is not None for key in ("cobranca_inicio_dia", "cobranca_fim_dia", "cobranca_alerta_dias")
        )

        def value(key: str, global_key: str) -> int:
            if company is not None and company.get(key) is not None:
                return int(company[key])
            return int(settings[global_key])

        self.rule_start_spin.setValue(value("cobranca_inicio_dia", "inicio_cobranca_dia"))
        self.rule_end_spin.setValue(value("cobranca_fim_dia", "encerramento_cobranca_dia"))
        self.rule_alert_spin.setValue(value("cobranca_alerta_dias", "alerta_apos_dias"))
        self.own_rule_check.setChecked(own)
        self._on_own_rule_toggled(own)
        self.rule_hint.setText(
            f'Prazos gerais: cobrar a partir do dia {settings["inicio_cobranca_dia"]}, prazo final no dia '
            f'{settings["encerramento_cobranca_dia"]}, prioridade após {settings["alerta_apos_dias"]} dia(s) de atraso.'
        )

    def _on_own_rule_toggled(self, checked: bool) -> None:
        for spin in (self.rule_start_spin, self.rule_end_spin, self.rule_alert_spin):
            spin.setEnabled(checked)
        self.rule_hint.setVisible(not checked)

    def _set_badge(self, active: bool | None) -> None:
        t = tokens()
        if active is None:
            self.status_badge.setText("")
            return
        color, background = (t["success"], t["success_soft"]) if active else (t["muted"], t["surface_alt"])
        self.status_badge.setText("Ativa" if active else "Inativa")
        self.status_badge.setStyleSheet(
            f"color: {color}; background: {background}; border-radius: 9px; padding: 3px 10px; font-weight: 600;"
        )

    def _mark_dirty(self, *_args) -> None:
        if not self._loading:
            self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        self.dirty = dirty
        self.save_button.setEnabled(dirty or self.creating)
        self.discard_button.setEnabled(dirty or self.creating)
        self.save_button.setText("Cadastrar empresa" if self.creating else "Salvar alterações")

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        answer = QMessageBox.question(
            self, "Empresas", "Há alterações não salvas nesta empresa. Deseja descartá-las?"
        )
        return answer == QMessageBox.StandardButton.Yes

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

    # Acoes -------------------------------------------------------------------------

    def start_new(self) -> None:
        if not self._confirm_discard():
            return
        self._loading = True
        self.table.clearSelection()
        self.selected_company = None
        self.creating = True
        self.detail_stack.setCurrentIndex(1)
        self.form_title.setText("Nova empresa")
        self._set_badge(None)
        for edit in (
            self.codigo_edit, self.nome_edit, self.cnpj_edit, self.contato_edit, self.email_edit,
            self.whatsapp_edit, self.whatsapp_grupo_edit,
        ):
            edit.clear()
        self.codigo_edit.setReadOnly(False)
        self.codigo_edit.setToolTip("")
        self.opt_out_checkbox.setChecked(False)
        self.whatsapp_envios_check.setChecked(False)
        self.observacao_edit.clear()
        self._load_rule(None)
        self.more_button.setEnabled(False)
        self.ficha_button.setEnabled(False)
        self._loading = False
        self._set_dirty(False)
        self.codigo_edit.setFocus()

    def discard_changes(self) -> None:
        if self.creating:
            self._show_empty()
            return
        if self.selected_company is not None:
            self._load_company(self.services.empresa_service.get_empresa(self.selected_company["id"]))

    def _rule_values(self) -> tuple[str, str, str]:
        if not self.own_rule_check.isChecked():
            return "", "", ""
        return str(self.rule_start_spin.value()), str(self.rule_end_spin.value()), str(self.rule_alert_spin.value())

    def save_company(self) -> None:
        inicio, fim, alerta = self._rule_values()
        try:
            self.services.collection_service.validate_company_settings_values(inicio, fim, alerta)
            # Numero ou link invalido barra antes de gravar a empresa.
            tem_whatsapp = normalize_whatsapp(self.whatsapp_edit.text()) or normalize_grupo_link(self.whatsapp_grupo_edit.text())
            if self.whatsapp_envios_check.isChecked() and not tem_whatsapp:
                raise ValidationError("Para usar o WhatsApp nos envios, informe o número ou o link do grupo.")
            if self.creating:
                company_id = self.services.empresa_service.create_empresa(
                    self.codigo_edit.text(),
                    self.nome_edit.text(),
                    self.email_edit.text(),
                    self.contato_edit.text(),
                    self.observacao_edit.toPlainText(),
                    self.cnpj_edit.text(),
                )
            else:
                company_id = self.selected_company["id"]
                self.services.empresa_service.update_empresa(
                    company_id,
                    self.nome_edit.text(),
                    self.email_edit.text(),
                    self.contato_edit.text(),
                    self.observacao_edit.toPlainText(),
                    self.cnpj_edit.text(),
                )
            self.services.collection_service.update_company_settings(company_id, inicio, fim, alerta)
            self.services.empresa_service.set_nao_contatar_mala_direta(company_id, self.opt_out_checkbox.isChecked())
            self.services.empresa_service.set_whatsapp(company_id, self.whatsapp_edit.text())
            self.services.empresa_service.set_whatsapp_envios(
                company_id, self.whatsapp_envios_check.isChecked(), self.whatsapp_grupo_edit.text()
            )
        except ValidationError as exc:
            QMessageBox.critical(self, "Empresas", str(exc))
            return

        criada = self.creating
        self.dirty = False
        self.creating = False
        self.selected_company = {"id": company_id}
        self.on_data_changed()
        self.refresh_data()
        if criada:
            QMessageBox.information(
                self,
                "Empresas",
                "Empresa cadastrada. Agora cadastre os documentos dela na tela Documentos.",
            )

    def open_ficha(self) -> None:
        if self.selected_company and self.on_open_ficha:
            self.on_open_ficha(self.selected_company["id"])

    def toggle_active(self) -> None:
        if not self.selected_company:
            return
        company = self.services.empresa_service.get_empresa(self.selected_company["id"])
        active = not bool(company.get("ativa"))
        if not active:
            answer = QMessageBox.question(
                self,
                "Inativar empresa",
                f'Inativar "{company["nome_empresa"]}"? Ela sai do Panorama e das cobranças, mas o histórico '
                "fica guardado e dá para reativar depois.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.services.empresa_service.set_empresa_ativa(company["id"], active)
        if not active and not self.show_inactive_check.isChecked():
            self.show_inactive_check.setChecked(True)
        self.on_data_changed()
        self.refresh_data()

    def delete_company(self) -> None:
        if not self.selected_company:
            return
        company = self.services.empresa_service.get_empresa(self.selected_company["id"])
        answer = QMessageBox.question(
            self,
            "Excluir empresa",
            f'Excluir "{company["nome_empresa"]}" de vez? Todos os documentos, status e o histórico de '
            "cobranças dela também serão apagados. Se só não atende mais, prefira Inativar.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.services.empresa_service.delete_empresa(company["id"])
        self._show_empty()
        self.on_data_changed()
        self.refresh_data()

    def clear_contact_info(self) -> None:
        if not self.selected_company:
            return
        answer = QMessageBox.question(
            self,
            "Remover dados de contato",
            "Isso apaga o email, o WhatsApp e o nome de contato desta empresa (o cadastro e o histórico de "
            "documentos continuam). Use quando o titular dos dados pedir a remoção. Continuar?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.services.empresa_service.clear_contact_info(self.selected_company["id"])
        self.on_data_changed()
        self.refresh_data()

    # Importacao --------------------------------------------------------------------

    def show_import_layout(self) -> None:
        ImportLayoutDialog(self.services.import_service, self).exec()

    def download_import_template(self) -> None:
        file_path, _filter = QFileDialog.getSaveFileName(
            self,
            "Salvar planilha modelo",
            str(get_documents_directory() / "modelo_importacao_empresas.xlsx"),
            "Planilha Excel (*.xlsx)",
        )
        if not file_path:
            return
        try:
            self.services.import_service.export_cadastro_completo_template(file_path)
        except ValidationError as exc:
            QMessageBox.critical(self, "Empresas", str(exc))
            return
        QMessageBox.information(self, "Empresas", f"Planilha modelo salva em:\n{file_path}")

    def import_full_registrations(self) -> None:
        file_path, _filter = QFileDialog.getOpenFileName(
            self,
            "Escolha a planilha com empresas e documentos",
            str(get_documents_directory()),
            "Planilhas Excel (*.xlsx *.xlsm);;Todos os arquivos (*.*)",
        )
        if not file_path:
            return

        runner = BlockingTaskRunner(self)
        runner.run(
            "Importando planilha...",
            lambda: self.services.import_service.import_cadastros_completos(file_path),
            on_success=self._on_import_finished,
            on_error=lambda message: QMessageBox.critical(self, "Importar planilha", message),
        )

    def _on_import_finished(self, result: dict) -> None:
        self.on_data_changed()
        self.refresh_data()
        summary = [
            f'Linhas lidas: {result["processed_rows"]}',
            f'Empresas novas: {result["companies_created"]}',
            f'Empresas atualizadas: {result["companies_updated"]}',
            f'Documentos importados: {result["documents_imported"]}',
            f'Status importados: {result["statuses_imported"]}',
        ]
        if result["types_created"]:
            summary.append(f'Tipos de documento criados: {result["types_created"]}')
        if result["failed"]:
            summary.append(f'Linhas com problema: {result["failed"]}')
        if result["errors"]:
            summary.append("")
            summary.append("Problemas encontrados:")
            summary.extend(result["errors"][:10])
        QMessageBox.information(self, "Importar planilha", "\n".join(summary))
