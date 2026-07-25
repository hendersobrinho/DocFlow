from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.app_context import refresh_agent_runtime
from documentos_empresa_app.qt_ui.dialogs.company_dialogs import CompanyMultiSelectDialog
from documentos_empresa_app.qt_ui.widgets.common import PageHeader, make_button
from documentos_empresa_app.services.agent_config_service import AVAILABLE_MODELS, PROVIDER_LABELS
from documentos_empresa_app.utils.common import ValidationError

SECTION_TITLE_STYLE = "font-weight: 600; font-size: 10.5pt;"


class ConfiguracoesPage(QWidget):
    def __init__(self, services, on_data_changed, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.on_data_changed = on_data_changed

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        layout.addWidget(
            PageHeader(
                "Configuracoes",
                "Ajuste sua pasta de entrada pessoal e, se voce for administrador, os parametros do "
                "agente de IA e da mala direta por email.",
            )
        )

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        self.tabs.addTab(self._build_inbox_tab(), "Minha pasta de entrada")
        if self.services.session_service.is_admin():
            self.tabs.addTab(self._build_agent_tab(), "Agente de IA")
            self.tabs.addTab(self._build_mailing_tab(), "Mala direta por email")

    def refresh_data(self) -> None:
        self.inbox_edit.setText(self.services.user_service.get_own_inbox_folder() or "")

    # Utilitarios de layout ------------------------------------------------

    def _wrap_in_scroll_area(self, content: QWidget) -> QScrollArea:
        """Evita que o conteudo seja espremido quando a janela nao esta maximizada -
        se nao couber na altura disponivel, a aba ganha rolagem em vez de comprimir
        os campos ate ficarem ilegiveis."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        return scroll

    def _section_title(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(SECTION_TITLE_STYLE)
        return label

    def _new_form(self) -> QFormLayout:
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        return form

    # Aba pessoal - pasta de entrada ---------------------------------------

    def _build_inbox_tab(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        hint = QLabel(
            "Pasta onde o agente procura novos documentos para voce, na tela de Revisao de "
            "Documentos. Cada usuario pode apontar para uma pasta diferente."
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        row = QHBoxLayout()
        current_folder = self.services.user_service.get_own_inbox_folder()
        self.inbox_edit = QLineEdit(current_folder or "")
        self.inbox_edit.setReadOnly(True)
        row.addWidget(self.inbox_edit, 1)
        choose_button = make_button("Escolher pasta...")
        choose_button.clicked.connect(self.choose_inbox_folder)
        row.addWidget(choose_button)
        layout.addLayout(row)
        layout.addStretch(1)

        return self._wrap_in_scroll_area(content)

    def choose_inbox_folder(self) -> None:
        current = self.inbox_edit.text().strip()
        initial = current if current and Path(current).is_dir() else str(Path.home())
        selected = QFileDialog.getExistingDirectory(self, "Escolha a pasta de entrada dos documentos", initial)
        if not selected:
            return
        self.services.user_service.set_own_inbox_folder(selected)
        self.inbox_edit.setText(selected)

    # Aba admin - agente de IA ----------------------------------------------

    def _build_agent_tab(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        hint = QLabel(
            "Escolha o provedor de IA usado pelo agente organizador de documentos e pelo chat, "
            "defina o modelo e o limiar de confianca para a classificacao automatica."
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        privacy_notice = QLabel(
            "Aviso de privacidade (LGPD): ao ativar o agente de IA, o texto extraido dos documentos "
            "recebidos (e as perguntas feitas no chat) e enviado para os servidores do provedor de IA "
            "escolhido (Anthropic ou OpenAI), que podem processar os dados fora do Brasil. Numeros de "
            "CPF encontrados no texto sao removidos automaticamente antes do envio, mas outros dados "
            "do documento (nome da empresa, valores, datas) sao transmitidos normalmente."
        )
        privacy_notice.setObjectName("Muted")
        privacy_notice.setWordWrap(True)
        layout.addWidget(privacy_notice)

        settings = self.services.agent_config_service.get_settings()

        form = self._new_form()

        self.provider_combo = QComboBox()
        for provider_key, provider_label in PROVIDER_LABELS.items():
            self.provider_combo.addItem(provider_label, provider_key)
        self.provider_combo.setCurrentIndex(self.provider_combo.findData(settings.provider))
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow("Provedor de IA", self.provider_combo)

        api_key_row = QHBoxLayout()
        self.api_key_edit = QLineEdit(settings.api_key or "")
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        api_key_row.addWidget(self.api_key_edit, 1)
        self.test_connection_button = make_button("Testar conexao")
        self.test_connection_button.clicked.connect(self.test_connection)
        api_key_row.addWidget(self.test_connection_button)
        form.addRow("API key", api_key_row)

        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        form.addRow("Modelo usado", self.model_combo)

        self.threshold_edit = QLineEdit(f"{settings.confidence_threshold:.2f}")
        form.addRow("Limiar de confianca (0 a 1)", self.threshold_edit)

        layout.addLayout(form)

        self._populate_model_combo(settings.provider, settings.model)

        prompt_label = QLabel(
            "System prompt customizado (opcional, complementa o prompt padrao com prioridade e vale "
            "para o provedor escolhido)"
        )
        prompt_label.setWordWrap(True)
        layout.addWidget(prompt_label)
        self.custom_prompt_edit = QTextEdit()
        self.custom_prompt_edit.setPlainText(settings.custom_instructions or "")
        self.custom_prompt_edit.setMinimumHeight(120)
        layout.addWidget(self.custom_prompt_edit, 1)

        actions = QHBoxLayout()
        save_button = make_button("Salvar configuracoes do agente", "primary")
        save_button.clicked.connect(self.save_agent_settings)
        actions.addWidget(save_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        return self._wrap_in_scroll_area(content)

    def _populate_model_combo(self, provider: str, current_model: str) -> None:
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItems(AVAILABLE_MODELS[provider])
        if current_model not in AVAILABLE_MODELS[provider]:
            self.model_combo.addItem(current_model)
        self.model_combo.setCurrentText(current_model)
        self.model_combo.blockSignals(False)

    def _selected_provider(self) -> str:
        return self.provider_combo.currentData()

    def _on_provider_changed(self) -> None:
        provider = self._selected_provider()
        settings = self.services.agent_config_service.get_settings(provider)
        self.api_key_edit.setText(settings.api_key or "")
        self._populate_model_combo(provider, settings.model)

    def test_connection(self) -> None:
        provider = self._selected_provider()
        try:
            self.services.agent_config_service.test_connection(
                provider, self.api_key_edit.text(), self.model_combo.currentText()
            )
        except ValidationError as exc:
            QMessageBox.critical(self, "Configuracoes", str(exc))
            return
        QMessageBox.information(
            self, "Configuracoes", f"Conexao com {PROVIDER_LABELS[provider]} realizada com sucesso."
        )

    def save_agent_settings(self) -> None:
        try:
            threshold = float(self.threshold_edit.text().strip().replace(",", "."))
        except ValueError:
            QMessageBox.critical(self, "Configuracoes", "Informe um limiar de confianca numerico valido.")
            return

        try:
            self.services.agent_config_service.save_settings(
                self._selected_provider(),
                self.api_key_edit.text().strip() or None,
                self.model_combo.currentText(),
                threshold,
                self.custom_prompt_edit.toPlainText().strip() or None,
            )
        except ValidationError as exc:
            QMessageBox.critical(self, "Configuracoes", str(exc))
            return

        refresh_agent_runtime(self.services)
        QMessageBox.information(self, "Configuracoes", "Configuracoes do agente salvas com sucesso.")

    # Aba admin - mala direta por email --------------------------------------

    def _build_mailing_tab(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        hint = QLabel(
            "Monta um rascunho no seu cliente de email padrao com as empresas selecionadas em "
            "copia oculta (BCC) - ninguem ve o email dos outros. Nada e enviado por aqui: voce "
            "revisa e clica em enviar no proprio cliente de email."
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        campaign = self.services.email_campaign_service.get_campaign()
        self.mailing_selected_empresa_ids: list[int] = list(campaign.empresa_ids)

        layout.addWidget(self._section_title("Mensagem"))

        message_form = self._new_form()
        self.mailing_subject_edit = QLineEdit(campaign.subject)
        message_form.addRow("Assunto", self.mailing_subject_edit)
        layout.addLayout(message_form)

        body_label = QLabel("Corpo do email (mesmo texto para todas as empresas selecionadas)")
        body_label.setWordWrap(True)
        layout.addWidget(body_label)
        self.mailing_body_edit = QTextEdit()
        self.mailing_body_edit.setPlainText(campaign.body)
        self.mailing_body_edit.setMinimumHeight(160)
        layout.addWidget(self.mailing_body_edit, 1)

        layout.addWidget(self._section_title("Empresas"))

        companies_row = QHBoxLayout()
        choose_companies_button = make_button("Selecionar empresas...")
        choose_companies_button.clicked.connect(self.choose_mailing_companies)
        companies_row.addWidget(choose_companies_button)
        companies_row.addStretch(1)
        layout.addLayout(companies_row)

        self.mailing_companies_summary_label = QLabel("")
        self.mailing_companies_summary_label.setObjectName("Muted")
        self.mailing_companies_summary_label.setWordWrap(True)
        layout.addWidget(self.mailing_companies_summary_label)
        self._update_mailing_companies_summary()

        actions = QHBoxLayout()
        save_mailing_button = make_button("Salvar")
        save_mailing_button.clicked.connect(self.save_mailing_settings)
        actions.addWidget(save_mailing_button)
        open_draft_button = make_button("Abrir rascunho de email", "primary")
        open_draft_button.clicked.connect(self.open_mailing_draft)
        actions.addWidget(open_draft_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        return self._wrap_in_scroll_area(content)

    def choose_mailing_companies(self) -> None:
        companies = self.services.empresa_service.list_empresas(active_only=False)
        dialog = CompanyMultiSelectDialog(self, companies, self.mailing_selected_empresa_ids)
        if dialog.exec():
            self.mailing_selected_empresa_ids = dialog.selected_company_ids
            self._update_mailing_companies_summary()
            # Salva a selecao na hora - sem isso, escolher as empresas so "colava" ate
            # a proxima vez que a tela fosse aberta, entao no fim das contas era preciso
            # selecionar de novo todo mes se ninguem lembrasse de clicar em "Salvar".
            try:
                self._persist_mailing_settings()
            except ValidationError as exc:
                QMessageBox.critical(self, "Mala direta", str(exc))

    def _update_mailing_companies_summary(self) -> None:
        if not self.mailing_selected_empresa_ids:
            self.mailing_companies_summary_label.setText("Nenhuma empresa selecionada.")
            return

        emails, missing, opted_out = self.services.email_campaign_service.build_recipients(
            self.mailing_selected_empresa_ids
        )
        text = (
            f"{len(self.mailing_selected_empresa_ids)} empresa(s) selecionada(s), "
            f"{len(emails)} com email de contato cadastrado."
        )
        if missing:
            shown = ", ".join(missing[:5])
            extra = f" e mais {len(missing) - 5}" if len(missing) > 5 else ""
            text += f" Sem email cadastrado: {shown}{extra}."
        if opted_out:
            shown = ", ".join(opted_out[:5])
            extra = f" e mais {len(opted_out) - 5}" if len(opted_out) > 5 else ""
            text += f" Marcadas para nao receber (opt-out): {shown}{extra}."
        self.mailing_companies_summary_label.setText(text)

    def save_mailing_settings(self) -> None:
        try:
            self._persist_mailing_settings()
        except ValidationError as exc:
            QMessageBox.critical(self, "Mala direta", str(exc))
            return
        QMessageBox.information(self, "Mala direta", "Configuracoes da mala direta salvas com sucesso.")

    def _persist_mailing_settings(self) -> None:
        self.services.email_campaign_service.save_campaign(
            self.mailing_subject_edit.text(),
            self.mailing_body_edit.toPlainText(),
            self.mailing_selected_empresa_ids,
        )

    def open_mailing_draft(self) -> None:
        try:
            self._persist_mailing_settings()
        except ValidationError as exc:
            QMessageBox.critical(self, "Mala direta", str(exc))
            return

        try:
            result = self.services.email_campaign_service.open_draft(
                self.mailing_subject_edit.text(),
                self.mailing_body_edit.toPlainText(),
                self.mailing_selected_empresa_ids,
            )
        except ValidationError as exc:
            QMessageBox.critical(self, "Mala direta", str(exc))
            return

        message = (
            f'Rascunho aberto no seu cliente de email com {result["recipient_count"]} '
            "destinatario(s) em copia oculta (BCC). Revise e clique em enviar por la."
        )
        if result["missing_companies"]:
            message += "\n\nFicaram de fora (sem email cadastrado): " + ", ".join(result["missing_companies"])
        if result["opted_out_companies"]:
            message += "\n\nFicaram de fora (optaram por nao receber): " + ", ".join(result["opted_out_companies"])
        QMessageBox.information(self, "Mala direta", message)
