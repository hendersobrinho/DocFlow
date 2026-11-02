from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.widgets.common import PageHeader, make_button
from documentos_empresa_app.qt_ui.widgets.mcp_panel import McpPanel
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
                "cobrar e a conexão com o Claude. A mala direta fica em Envios automáticos.",
            )
        )

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        self.tabs.addTab(self._build_collection_rule_tab(), "Prazos de cobrança")
        self.tabs.addTab(self._build_followup_tab(), "Depois de cobrar")
        self.mcp_panel = McpPanel(services)
        self.tabs.addTab(self._wrap_in_scroll_area(self.mcp_panel), "Claude (MCP)")

    def refresh_data(self) -> None:
        self._load_collection_rule()
        self._load_followup_rules()
        self.mcp_panel.refresh()

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
