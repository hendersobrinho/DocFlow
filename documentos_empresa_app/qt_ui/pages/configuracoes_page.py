from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.dialogs.company_dialogs import CompanyMultiSelectDialog
from documentos_empresa_app.qt_ui.widgets.common import PageHeader, make_button
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
                "Configurações",
                "Regras que valem para o escritório inteiro: prazos de cobrança, o que fazer depois de "
                "cobrar e mala direta.",
            )
        )

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        self.tabs.addTab(self._build_collection_rule_tab(), "Prazos de cobrança")
        self.tabs.addTab(self._build_followup_tab(), "Depois de cobrar")
        self.tabs.addTab(self._build_mailing_tab(), "Mala direta por email")

    def refresh_data(self) -> None:
        self._load_collection_rule()
        self._load_followup_rules()

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

    # Aba admin - prazos de cobranca ------------------------------------------

    def _build_collection_rule_tab(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        hint = QLabel(
            "Define, para cada mês, quando os documentos começam a ser cobrados e quando passam a "
            "contar como atrasados. Vale para todas as empresas que não tenham uma regra própria "
            "(a regra própria fica no cadastro da empresa)."
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = self._new_form()
        self.rule_start_spin = QSpinBox()
        self.rule_start_spin.setRange(1, 31)
        self.rule_start_spin.setPrefix("dia ")
        self.rule_start_spin.setMaximumWidth(120)
        form.addRow("Começar a cobrar no", self.rule_start_spin)
        self.rule_end_spin = QSpinBox()
        self.rule_end_spin.setRange(1, 31)
        self.rule_end_spin.setPrefix("dia ")
        self.rule_end_spin.setMaximumWidth(120)
        form.addRow("Prazo final de entrega no", self.rule_end_spin)
        self.rule_alert_spin = QSpinBox()
        self.rule_alert_spin.setRange(0, 60)
        self.rule_alert_spin.setSuffix(" dia(s) de atraso")
        self.rule_alert_spin.setMaximumWidth(220)
        form.addRow("Priorizar depois de", self.rule_alert_spin)
        layout.addLayout(form)

        self.rule_example = QLabel()
        self.rule_example.setObjectName("Muted")
        self.rule_example.setWordWrap(True)
        layout.addWidget(self.rule_example)
        for spin in (self.rule_start_spin, self.rule_end_spin, self.rule_alert_spin):
            spin.valueChanged.connect(self._update_rule_example)

        actions = QHBoxLayout()
        save_button = make_button("Salvar prazos", "primary")
        save_button.clicked.connect(self._save_collection_rule)
        actions.addWidget(save_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addStretch(1)

        self._load_collection_rule()
        return self._wrap_in_scroll_area(content)

    def _load_collection_rule(self) -> None:
        settings = self.services.collection_service.get_global_settings()
        self.rule_start_spin.setValue(int(settings["inicio_cobranca_dia"]))
        self.rule_end_spin.setValue(int(settings["encerramento_cobranca_dia"]))
        self.rule_alert_spin.setValue(int(settings["alerta_apos_dias"]))
        self._update_rule_example()

    def _update_rule_example(self) -> None:
        inicio = self.rule_start_spin.value()
        fim = self.rule_end_spin.value()
        alerta = self.rule_alert_spin.value()
        self.rule_example.setText(
            f"Exemplo para os documentos de maio: a cobrança começa em {inicio:02d}/06 e o prazo vai até "
            f"{fim:02d}/06. Depois disso, o que faltar fica Em atraso, e passa a ser prioridade de "
            f"cobrança {alerta} dia(s) depois."
        )

    def _save_collection_rule(self) -> None:
        try:
            self.services.collection_service.update_global_settings(
                self.rule_start_spin.value(), self.rule_end_spin.value(), self.rule_alert_spin.value()
            )
        except ValidationError as exc:
            QMessageBox.critical(self, "Configurações", str(exc))
            return
        QMessageBox.information(self, "Configurações", "Prazos de cobrança salvos.")
        self.on_data_changed()

    # Aba admin - regras do acompanhamento -----------------------------------

    def _build_followup_tab(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        hint = QLabel(
            "Estas regras decidem o próximo passo de cada documento depois que ele foi cobrado. "
            "O Claude segue o que estiver aqui (ferramenta \"o que fazer agora\"), e o mesmo "
            "plano aparece em Cobranças > O que fazer agora."
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = self._new_form()
        self.followup_wait_spin = QSpinBox()
        self.followup_wait_spin.setRange(0, 60)
        self.followup_wait_spin.setSuffix(" dia(s)")
        self.followup_wait_spin.setMaximumWidth(140)
        form.addRow("Esperar depois de cobrar", self.followup_wait_spin)
        self.followup_max_spin = QSpinBox()
        self.followup_max_spin.setRange(0, 20)
        self.followup_max_spin.setSuffix(" vez(es)")
        self.followup_max_spin.setMaximumWidth(140)
        form.addRow("Recobrar no máximo", self.followup_max_spin)
        self.followup_problem_check = QCheckBox("Documento que chegar errado vai direto para uma pessoa")
        form.addRow("", self.followup_problem_check)
        layout.addLayout(form)

        self.followup_example = QLabel()
        self.followup_example.setObjectName("Muted")
        self.followup_example.setWordWrap(True)
        layout.addWidget(self.followup_example)
        self.followup_wait_spin.valueChanged.connect(self._update_followup_example)
        self.followup_max_spin.valueChanged.connect(self._update_followup_example)
        self.followup_problem_check.toggled.connect(self._update_followup_example)

        actions = QHBoxLayout()
        save_button = make_button("Salvar regras", "primary")
        save_button.clicked.connect(self._save_followup_rules)
        actions.addWidget(save_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addStretch(1)

        self._load_followup_rules()
        return self._wrap_in_scroll_area(content)

    def _load_followup_rules(self) -> None:
        rules = self.services.collection_service.get_followup_rules()
        self.followup_wait_spin.setValue(rules["dias_entre_cobrancas"])
        self.followup_max_spin.setValue(rules["max_recobrancas"])
        self.followup_problem_check.setChecked(rules["problema_vai_para_pessoa"])
        self._update_followup_example()

    def _update_followup_example(self) -> None:
        dias = self.followup_wait_spin.value()
        maximo = self.followup_max_spin.value()
        problema = (
            "Se chegar o documento errado, uma pessoa decide o que fazer."
            if self.followup_problem_check.isChecked()
            else "Se chegar o documento errado, ele é cobrado de novo como se não tivesse chegado."
        )
        limite = (
            "Não há recobrança: depois da primeira cobrança, o caso vai para uma pessoa."
            if maximo == 0
            else f"Depois de {maximo} recobrança(s) sem resposta, o caso vai para uma pessoa em Precisa de atenção."
        )
        self.followup_example.setText(
            f"Exemplo: o extrato foi cobrado hoje. Durante {dias} dia(s) ele fica Aguardando. Depois, o Claude "
            f"verifica de novo; se ainda não chegou, recobra. {limite} {problema}"
        )

    def _save_followup_rules(self) -> None:
        try:
            self.services.collection_service.update_followup_rules(
                self.followup_wait_spin.value(),
                self.followup_max_spin.value(),
                self.followup_problem_check.isChecked(),
            )
        except ValidationError as exc:
            QMessageBox.critical(self, "Configurações", str(exc))
            return
        QMessageBox.information(self, "Configurações", "Regras salvas.")
        self.on_data_changed()

    # Aba admin - mala direta por email --------------------------------------

    def _build_mailing_tab(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        hint = QLabel(
            "Monta um rascunho no seu cliente de email padrão com as empresas selecionadas em "
            "copia oculta (BCC) - ninguém ve o email dos outros. Nada e enviado por aqui: você "
            "revisa e clica em enviar no próprio cliente de email."
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
            text += f" Marcadas para não receber (opt-out): {shown}{extra}."
        self.mailing_companies_summary_label.setText(text)

    def save_mailing_settings(self) -> None:
        try:
            self._persist_mailing_settings()
        except ValidationError as exc:
            QMessageBox.critical(self, "Mala direta", str(exc))
            return
        QMessageBox.information(self, "Mala direta", "Configurações da mala direta salvas com sucesso.")

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
            message += "\n\nFicaram de fora (optaram por não receber): " + ", ".join(result["opted_out_companies"])
        QMessageBox.information(self, "Mala direta", message)
