from __future__ import annotations

from datetime import date

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.dialogs.company_dialogs import CompanyMultiSelectDialog
from documentos_empresa_app.qt_ui.theme import tokens
from documentos_empresa_app.qt_ui.widgets.common import Card, PageHeader, ToolbarRow, make_button
from documentos_empresa_app.qt_ui.widgets.envios import CANAL_CURTO, EmailEnvioDialog, QuemRecebePanel
from documentos_empresa_app.qt_ui.widgets.tables import fill_table, make_readonly_table
from documentos_empresa_app.services.envio_programado_service import (
    CAMPOS_MODELO,
    CANAL_AUTOMATICO,
    CANAL_LABELS,
    ENVIAR_EM_LABELS,
    ENVIAR_MES_SEGUINTE,
    MESES_TRIMESTRAIS,
    MODO_CCO,
    MODO_LABELS,
    data_de_envio,
    split_emails,
)
from documentos_empresa_app.utils.common import MONTH_NAMES, ValidationError, format_utc_timestamp

PUBLICO_TODAS = "todas"
PUBLICO_ESCOLHIDAS = "escolhidas"
STATUS_LABELS = {"enviado": "Enviado", "falhou": "Falhou"}
ERRO = "#C0392B"
CAMPOS_CCO = "{competencia} (MM/AAAA), {mes} (nome do mês) e {ano}"
TEXTO_INICIAL_CCO = (
    "Prezados clientes,\n\n"
    "(cole aqui o texto da mala direta)\n\n"
    "Competência: {competencia}\n\n"
    "Atenciosamente,"
)


def _format_date(raw: str | None) -> str:
    return date.fromisoformat(raw).strftime("%d/%m/%Y") if raw else "-"


class EnvioDialog(QDialog):
    """Cria ou edita uma regra de envio automatico (cobranca por tipo de documento ou mala
    direta), sempre pensada por competencia."""

    def __init__(
        self,
        parent: QWidget,
        tipos: list[dict],
        empresas: list[dict],
        envio: dict | None = None,
        publico=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Editar envio automático" if envio else "Novo envio automático")
        self.setMinimumWidth(660)
        envio = envio or {}
        self.empresas = empresas
        self.empresa_ids: list[int] = list(envio.get("empresa_ids_lista") or [])

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.nome_edit = QLineEdit(envio.get("nome", ""))
        self.nome_edit.setPlaceholderText("Ex: Informe de Rendimentos trimestral")
        form.addRow("Nome", self.nome_edit)

        self.publico_combo = QComboBox()
        self.publico_combo.addItem("Mala direta - todas as empresas ativas", PUBLICO_TODAS)
        self.publico_combo.addItem("Mala direta - empresas escolhidas", PUBLICO_ESCOLHIDAS)
        for tipo in tipos:
            self.publico_combo.addItem(f'Cobrança - quem tem "{tipo["nome_tipo"]}"', tipo["id"])
        if envio.get("tipo_documento_id") is not None:
            atual = envio["tipo_documento_id"]
        elif not envio and publico is not None:
            atual = publico
        else:
            atual = PUBLICO_ESCOLHIDAS if self.empresa_ids else PUBLICO_TODAS
        self.publico_combo.setCurrentIndex(max(self.publico_combo.findData(atual), 0))
        form.addRow("Enviar para", self.publico_combo)

        empresas_row = QHBoxLayout()
        self.empresas_button = make_button("Escolher empresas...")
        self.empresas_button.clicked.connect(self._choose_companies)
        empresas_row.addWidget(self.empresas_button)
        self.empresas_label = QLabel("")
        self.empresas_label.setObjectName("Muted")
        empresas_row.addWidget(self.empresas_label, 1)
        self.empresas_widget = QWidget()
        self.empresas_widget.setLayout(empresas_row)
        empresas_row.setContentsMargins(0, 0, 0, 0)
        form.addRow("", self.empresas_widget)

        self.modo_combo = QComboBox()
        for chave, texto in MODO_LABELS.items():
            self.modo_combo.addItem(texto, chave)
        self.modo_combo.setCurrentIndex(max(self.modo_combo.findData(envio.get("modo")), 0))
        self.modo_label = QLabel("Forma de envio")
        form.addRow(self.modo_label, self.modo_combo)

        self.para_edit = QLineEdit(envio.get("email_para") or "")
        self.para_edit.setPlaceholderText("Email do escritório - os clientes vão em cópia oculta")
        self.para_label = QLabel("Para")
        form.addRow(self.para_label, self.para_edit)

        self.pendentes_check = QCheckBox("Só para quem ainda não entregou o documento da competência")
        self.pendentes_check.setChecked(bool(envio.get("somente_pendentes", True)))
        form.addRow("", self.pendentes_check)
        self.publico_combo.currentIndexChanged.connect(self._sync_publico)
        self.modo_combo.currentIndexChanged.connect(self._sync_publico)

        self.canal_combo = QComboBox()
        for chave, texto in CANAL_LABELS.items():
            self.canal_combo.addItem(texto, chave)
        self.canal_combo.setCurrentIndex(max(self.canal_combo.findData(envio.get("canal")), 0))
        form.addRow("Canal", self.canal_combo)

        meses_widget = QWidget()
        meses_layout = QGridLayout(meses_widget)
        meses_layout.setContentsMargins(0, 0, 0, 0)
        selecionados = set(envio.get("meses_lista") or MESES_TRIMESTRAIS)
        self.mes_checks: dict[int, QCheckBox] = {}
        for mes in range(1, 13):
            check = QCheckBox(MONTH_NAMES[mes][:3])
            check.setChecked(mes in selecionados)
            check.toggled.connect(self._update_exemplo)
            self.mes_checks[mes] = check
            meses_layout.addWidget(check, (mes - 1) // 6, (mes - 1) % 6)
        atalhos = QHBoxLayout()
        for texto, meses in (("Trimestral", MESES_TRIMESTRAIS), ("Todo mês", range(1, 13))):
            botao = make_button(texto, "quiet")
            botao.clicked.connect(lambda _c=False, m=tuple(meses): self._set_meses(m))
            atalhos.addWidget(botao)
        atalhos.addStretch(1)
        meses_layout.addLayout(atalhos, 2, 0, 1, 6)
        form.addRow("Competências cobradas", meses_widget)

        quando = QHBoxLayout()
        self.enviar_em_combo = QComboBox()
        for chave, texto in ENVIAR_EM_LABELS.items():
            self.enviar_em_combo.addItem(texto, chave)
        self.enviar_em_combo.setCurrentIndex(max(self.enviar_em_combo.findData(envio.get("enviar_em")), 0))
        self.enviar_em_combo.currentIndexChanged.connect(self._update_exemplo)
        quando.addWidget(self.enviar_em_combo, 1)
        quando.addWidget(QLabel("a partir do"))
        self.dia_spin = QSpinBox()
        self.dia_spin.setRange(1, 31)
        self.dia_spin.setPrefix("dia ")
        self.dia_spin.setValue(int(envio.get("dia_envio") or 5))
        self.dia_spin.setMaximumWidth(110)
        self.dia_spin.valueChanged.connect(self._update_exemplo)
        quando.addWidget(self.dia_spin)
        form.addRow("Quando enviar", quando)

        self.exemplo_label = QLabel("")
        self.exemplo_label.setObjectName("Muted")
        self.exemplo_label.setWordWrap(True)
        form.addRow("", self.exemplo_label)

        self.assunto_edit = QLineEdit(envio.get("assunto", ""))
        self.assunto_edit.setPlaceholderText("Ex: Informe de Rendimentos - {competencia}")
        form.addRow("Assunto do email", self.assunto_edit)

        self.corpo_edit = QTextEdit()
        self.corpo_edit.setPlainText(envio.get("corpo", ""))
        self.corpo_edit.setAcceptRichText(False)
        self.corpo_edit.setMinimumHeight(140)
        form.addRow("Texto do email", self.corpo_edit)

        self.whatsapp_edit = QTextEdit()
        self.whatsapp_edit.setAcceptRichText(False)
        self.whatsapp_edit.setPlainText(envio.get("corpo_whatsapp") or "")
        self.whatsapp_edit.setPlaceholderText("Opcional - vazio usa o mesmo texto do email.")
        self.whatsapp_edit.setMaximumHeight(100)
        form.addRow("Texto do WhatsApp", self.whatsapp_edit)

        self.campos_label = QLabel("")
        self.campos_label.setObjectName("Muted")
        self.campos_label.setWordWrap(True)
        form.addRow("", self.campos_label)

        self.instrucoes_edit = QTextEdit()
        self.instrucoes_edit.setPlainText(envio.get("instrucoes") or "")
        self.instrucoes_edit.setPlaceholderText("Opcional. Ex: anexar o modelo de informe; responder no mesmo email da última cobrança.")
        self.instrucoes_edit.setMaximumHeight(70)
        form.addRow("Instruções para o Claude", self.instrucoes_edit)

        self.ativo_check = QCheckBox("Ativo")
        self.ativo_check.setChecked(bool(envio.get("ativo", True)))
        form.addRow("", self.ativo_check)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel_button = make_button("Cancelar", "quiet")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(cancel_button)
        save_button = make_button("Salvar", "primary")
        save_button.clicked.connect(self.accept)
        buttons.addWidget(save_button)
        layout.addLayout(buttons)
        self._sync_publico()
        self._update_exemplo()

    def _set_meses(self, meses: tuple[int, ...]) -> None:
        for mes, check in self.mes_checks.items():
            check.setChecked(mes in meses)

    def _choose_companies(self) -> None:
        dialog = CompanyMultiSelectDialog(self, [e for e in self.empresas if e["ativa"]], self.empresa_ids)
        if dialog.exec():
            self.empresa_ids = list(dialog.selected_company_ids)
            self._sync_publico()

    def _sync_publico(self) -> None:
        publico = self.publico_combo.currentData()
        mala_direta = publico in (PUBLICO_TODAS, PUBLICO_ESCOLHIDAS)
        cco = mala_direta and self.modo_combo.currentData() == MODO_CCO
        self.pendentes_check.setEnabled(not mala_direta)
        self.empresas_widget.setVisible(publico == PUBLICO_ESCOLHIDAS)
        self.modo_label.setVisible(mala_direta)
        self.modo_combo.setVisible(mala_direta)
        self.para_label.setVisible(cco)
        self.para_edit.setVisible(cco)
        campos = ", ".join(f"{{{campo}}} ({descricao})" for campo, descricao in CAMPOS_MODELO.items())
        if cco:
            self.campos_label.setText(
                f"Email único em cópia oculta: no email use só {CAMPOS_CCO}. Quem liberou o WhatsApp recebe "
                f"a mensagem individual, onde valem todos os campos: {campos}."
            )
        else:
            self.campos_label.setText(f"Campos que viram o dado de cada empresa: {campos}.")
        self.empresas_label.setText(
            f"{len(self.empresa_ids)} empresa(s) escolhida(s)" if self.empresa_ids else "Nenhuma empresa escolhida."
        )

    def _update_exemplo(self) -> None:
        meses = [mes for mes, check in self.mes_checks.items() if check.isChecked()]
        if not meses:
            self.exemplo_label.setText("Escolha pelo menos uma competência.")
            return
        hoje = date.today()
        competencia = meses[-1]
        ano_envio, mes_envio = hoje.year, competencia
        if self.enviar_em_combo.currentData() == ENVIAR_MES_SEGUINTE:
            ano_envio, mes_envio = (hoje.year + 1, 1) if competencia == 12 else (hoje.year, competencia + 1)
        quando = data_de_envio(ano_envio, mes_envio, self.dia_spin.value())
        self.exemplo_label.setText(
            f"Exemplo: a competência {competencia:02d}/{hoje.year} é cobrada a partir de "
            f"{quando.strftime('%d/%m/%Y')}. Quem perder o dia continua na lista até o fim daquele mês."
        )

    def values(self) -> dict:
        publico = self.publico_combo.currentData()
        mala_direta = publico in (PUBLICO_TODAS, PUBLICO_ESCOLHIDAS)
        return {
            "nome": self.nome_edit.text(),
            "tipo_documento_id": None if mala_direta else publico,
            "empresa_ids": self.empresa_ids if publico == PUBLICO_ESCOLHIDAS else [],
            "modo": self.modo_combo.currentData() if mala_direta else "individual",
            "email_para": self.para_edit.text(),
            "somente_pendentes": self.pendentes_check.isChecked(),
            "canal": self.canal_combo.currentData(),
            "meses": [mes for mes, check in self.mes_checks.items() if check.isChecked()],
            "enviar_em": self.enviar_em_combo.currentData(),
            "dia_envio": self.dia_spin.value(),
            "assunto": self.assunto_edit.text(),
            "corpo": self.corpo_edit.toPlainText(),
            "corpo_whatsapp": self.whatsapp_edit.toPlainText(),
            "instrucoes": self.instrucoes_edit.toPlainText(),
            "ativo": self.ativo_check.isChecked(),
        }


class MensagemTab(QWidget):
    """Texto do envio: assunto e email, texto proprio do WhatsApp (opcional), campos que viram
    o dado da empresa e os modelos prontos para carregar ou guardar."""

    def __init__(self, services, on_changed, on_edit_rule, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.on_changed = on_changed
        self.envio: dict | None = None
        self.dirty = False
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)

        topo = ToolbarRow()
        self.modelos_button = make_button("Modelos de texto")
        self.modelos_button.setToolTip("Carregue um texto pronto ou guarde este para usar de novo.")
        self.modelos_menu = QMenu(self.modelos_button)
        self.modelos_menu.aboutToShow.connect(self._montar_menu_modelos)
        self.modelos_button.setMenu(self.modelos_menu)
        topo.add(self.modelos_button)
        topo.add_stretch()
        self.agenda_label = QLabel("")
        self.agenda_label.setObjectName("Muted")
        topo.add(self.agenda_label)
        agenda = make_button("Alterar agenda e público...", "quiet")
        agenda.clicked.connect(on_edit_rule)
        topo.add(agenda)
        layout.addWidget(topo)

        form = QFormLayout()
        form.setSpacing(8)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.para_edit = QLineEdit()
        self.para_edit.setPlaceholderText("Email do escritório - os clientes vão em cópia oculta")
        self.para_label = QLabel("Para")
        form.addRow(self.para_label, self.para_edit)
        self.assunto_edit = QLineEdit()
        form.addRow("Assunto", self.assunto_edit)
        layout.addLayout(form)

        textos = QSplitter(Qt.Orientation.Horizontal)
        for titulo, atributo, dica in (
            ("Texto do email", "corpo_edit", ""),
            ("Texto do WhatsApp", "whatsapp_edit", "Vazio = o mesmo texto do email. Dica: no WhatsApp, *negrito* e _itálico_."),
        ):
            bloco = QWidget()
            bloco_layout = QVBoxLayout(bloco)
            bloco_layout.setContentsMargins(0, 0, 0, 0)
            bloco_layout.setSpacing(4)
            rotulo = QLabel(titulo)
            rotulo.setStyleSheet("font-weight: 600;")
            bloco_layout.addWidget(rotulo)
            editor = QTextEdit()
            editor.setAcceptRichText(False)
            editor.setMinimumHeight(180)
            if dica:
                editor.setPlaceholderText(dica)
            editor.installEventFilter(self)
            setattr(self, atributo, editor)
            bloco_layout.addWidget(editor, 1)
            textos.addWidget(bloco)
        layout.addWidget(textos, 1)
        self._editor_atual: QTextEdit | QLineEdit = self.corpo_edit
        self.assunto_edit.installEventFilter(self)

        campos = QHBoxLayout()
        campos.setSpacing(6)
        self.campos_label = QLabel("Inserir:")
        self.campos_label.setObjectName("Muted")
        campos.addWidget(self.campos_label)
        self.campo_buttons: dict[str, QPushButton] = {}
        for campo, descricao in CAMPOS_MODELO.items():
            botao = make_button("{" + campo + "}", "quiet")
            botao.setToolTip(f"Vira o {descricao}.")
            botao.clicked.connect(lambda _c=False, nome=campo: self._inserir_campo(nome))
            campos.addWidget(botao)
            self.campo_buttons[campo] = botao
        campos.addStretch(1)
        layout.addLayout(campos)

        acoes = QHBoxLayout()
        self.dica_label = QLabel("")
        self.dica_label.setObjectName("Muted")
        self.dica_label.setWordWrap(True)
        acoes.addWidget(self.dica_label, 1)
        self.descartar_button = make_button("Descartar alterações", "quiet")
        self.descartar_button.clicked.connect(lambda: self.load(self.envio, force=True))
        acoes.addWidget(self.descartar_button)
        self.salvar_button = make_button("Salvar mensagem", "primary")
        self.salvar_button.clicked.connect(self.save)
        acoes.addWidget(self.salvar_button)
        layout.addLayout(acoes)

        for edit in (self.para_edit, self.assunto_edit):
            edit.textChanged.connect(self._mark_dirty)
        for editor in (self.corpo_edit, self.whatsapp_edit):
            editor.textChanged.connect(self._mark_dirty)
        self._set_clean()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - API do Qt
        if event.type() == QEvent.Type.FocusIn and watched in (self.corpo_edit, self.whatsapp_edit, self.assunto_edit):
            self._editor_atual = watched
        return super().eventFilter(watched, event)

    def _inserir_campo(self, campo: str) -> None:
        texto = "{" + campo + "}"
        if isinstance(self._editor_atual, QLineEdit):
            self._editor_atual.insert(texto)
        else:
            self._editor_atual.insertPlainText(texto)
        self._editor_atual.setFocus()

    def load(self, envio: dict | None, force: bool = False) -> None:
        if not force and self.dirty and envio and self.envio and envio["id"] == self.envio["id"]:
            self.envio = envio  # nao apaga o que a pessoa ainda esta escrevendo
            self._update_agenda()
            return
        self.envio = envio
        self._loading = True
        envio = envio or {}
        self.para_edit.setText(envio.get("email_para") or "")
        self.assunto_edit.setText(envio.get("assunto") or "")
        self.corpo_edit.setPlainText(envio.get("corpo") or "")
        self.whatsapp_edit.setPlainText(envio.get("corpo_whatsapp") or "")
        cco = envio.get("modo") == MODO_CCO
        self.para_label.setVisible(cco)
        self.para_edit.setVisible(cco)
        for campo, botao in self.campo_buttons.items():
            # No email unico em copia oculta nao ha empresa: so os campos da competencia.
            botao.setVisible(not cco or campo in ("competencia", "mes", "ano"))
        self.dica_label.setText(
            "Email único em cópia oculta: o texto do email não tem dados de empresa. Quem recebe por WhatsApp "
            "recebe a mensagem individual, com o nome da empresa."
            if cco
            else "Os campos entre chaves viram o dado de cada empresa. Veja como fica em Quem recebe."
        )
        self._loading = False
        self._set_clean()
        self._update_agenda()

    def _update_agenda(self) -> None:
        envio = self.envio
        if not envio:
            self.agenda_label.setText("")
            return
        quando = "mês seguinte" if envio["enviar_em"] == ENVIAR_MES_SEGUINTE else "mesmo mês"
        self.agenda_label.setText(f'{envio["meses_label"]}  ·  {quando}, dia {envio["dia_envio"]}  ·  {envio["canal_label"].split(" (")[0]}')

    def _mark_dirty(self, *_args) -> None:
        if self._loading:
            return
        self.dirty = True
        self.salvar_button.setText("Salvar mensagem *")
        self.descartar_button.setEnabled(True)

    def _set_clean(self) -> None:
        self.dirty = False
        self.salvar_button.setText("Salvar mensagem")
        self.descartar_button.setEnabled(False)

    def values(self) -> dict:
        return {
            "email_para": self.para_edit.text(),
            "assunto": self.assunto_edit.text(),
            "corpo": self.corpo_edit.toPlainText(),
            "corpo_whatsapp": self.whatsapp_edit.toPlainText(),
        }

    def save(self) -> bool:
        if not self.envio:
            return False
        if self.envio["modo"] == MODO_CCO and self.envio["ativo"] and not self.para_edit.text().strip():
            QMessageBox.warning(self, "Mensagem", "Preencha o email do escritório em Para: a cópia oculta precisa dele.")
            return False
        try:
            self.services.envio_programado_service.atualizar(self.envio["id"], self.values())
        except ValidationError as exc:
            QMessageBox.critical(self, "Mensagem", str(exc))
            return False
        self._set_clean()
        self.on_changed()
        return True

    # Modelos ---------------------------------------------------------------------------

    def _montar_menu_modelos(self) -> None:
        menu = self.modelos_menu
        menu.clear()
        modelos = self.services.envio_programado_service.listar_modelos()
        if modelos:
            titulo = menu.addAction("Carregar texto pronto")
            titulo.setEnabled(False)
            for modelo in modelos:
                acao = menu.addAction(f'   {modelo["nome"]}')
                acao.triggered.connect(lambda _c=False, m=modelo: self.carregar_modelo(m))
            menu.addSeparator()
        salvar = menu.addAction("Guardar este texto como modelo...")
        salvar.triggered.connect(self.salvar_modelo)
        if modelos:
            excluir = menu.addMenu("Excluir modelo")
            for modelo in modelos:
                acao = excluir.addAction(modelo["nome"])
                acao.triggered.connect(lambda _c=False, m=modelo: self.excluir_modelo(m))

    def carregar_modelo(self, modelo: dict) -> None:
        if modelo.get("assunto"):
            self.assunto_edit.setText(modelo["assunto"])
        self.corpo_edit.setPlainText(modelo["corpo"])
        self.whatsapp_edit.setPlainText(modelo.get("corpo_whatsapp") or "")
        self._mark_dirty()

    def salvar_modelo(self) -> None:
        sugestao = self.envio["nome"] if self.envio else ""
        nome, ok = QInputDialog.getText(self, "Guardar modelo", "Nome do modelo:", text=sugestao)
        if not ok or not nome.strip():
            return
        valores = self.values()
        try:
            self.services.envio_programado_service.salvar_modelo(
                nome, valores["assunto"], valores["corpo"], valores["corpo_whatsapp"]
            )
        except ValidationError as exc:
            QMessageBox.critical(self, "Modelos", str(exc))
            return
        QMessageBox.information(self, "Modelos", f'Modelo "{nome.strip()}" guardado. Use em qualquer envio, em Modelos de texto.')

    def excluir_modelo(self, modelo: dict) -> None:
        if QMessageBox.question(self, "Modelos", f'Excluir o modelo "{modelo["nome"]}"?') != QMessageBox.StandardButton.Yes:
            return
        try:
            self.services.envio_programado_service.excluir_modelo(modelo["id"])
        except ValidationError as exc:
            QMessageBox.critical(self, "Modelos", str(exc))


class EnvioListaItem(QWidget):
    """Linha da lista de envios: nome, publico e o que esta pendente (ou o proximo envio)."""

    def __init__(self, envio: dict, pendentes: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        t = tokens()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)
        topo = QHBoxLayout()
        topo.setSpacing(6)
        nome = QLabel(envio["nome"], self)
        nome.setStyleSheet("font-weight: 600;")
        nome.setWordWrap(True)
        topo.addWidget(nome, 1)
        if pendentes:
            selo = QLabel(f"{pendentes} para enviar", self)
            selo.setStyleSheet(
                f"background: {t['warning_soft']}; color: {t['warning']}; border-radius: 9px; padding: 1px 8px; font-weight: 600;"
            )
        elif not envio["ativo"]:
            selo = QLabel("Desativado", self)
            selo.setStyleSheet(f"color: {t['muted']};")
        else:
            selo = QLabel("Em dia ✓", self)
            selo.setStyleSheet(f"color: {t['success']};")
        topo.addWidget(selo, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(topo)
        publico = QLabel(envio["publico_label"], self)
        publico.setObjectName("Muted")
        publico.setWordWrap(True)
        layout.addWidget(publico)
        if envio["proximo_envio"]:
            proximo = QLabel(f'Próximo: {_format_date(envio["proximo_envio"])} · comp. {envio["proxima_competencia"]}', self)
            proximo.setObjectName("Muted")
            layout.addWidget(proximo)


class EnviosPage(QWidget):
    """Envios automaticos (cobrancas e mala direta, por email ou WhatsApp). A esquerda, todos
    os envios; a direita, o envio escolhido: quem recebe (email, WhatsApp e quem fica de fora),
    a mensagem e o historico. Os emails saem pelo email do escritorio cadastrado (ou pelo
    Claude); as conversas de WhatsApp abrem prontas, uma a uma."""

    def __init__(self, services, on_data_changed, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.on_data_changed = on_data_changed
        self.envios: list[dict] = []
        self.pendentes: dict[int, int] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(
            PageHeader(
                "Envios automáticos",
                "Cobranças e mala direta por competência - por exemplo, cobrar o Informe de Rendimentos de cada "
                "trimestre no mês seguinte. Escolha um envio para ver quem recebe por email e por WhatsApp, "
                "conferir a mensagem de cada um e enviar.",
            )
        )

        barra = ToolbarRow()
        novo = make_button("Novo envio", "primary")
        novo_menu = QMenu(novo)
        novo_menu.addAction("Cobrança de documento (ex: Informe trimestral)...").triggered.connect(self.new_rule)
        novo_menu.addAction("Mala direta em cópia oculta (ex: Distribuição de lucros)...").triggered.connect(self.new_mailing)
        novo_menu.addAction("Aviso para empresas escolhidas...").triggered.connect(lambda: self._open_dialog(None, PUBLICO_ESCOLHIDAS))
        novo.setMenu(novo_menu)
        barra.add(novo)
        barra.add_stretch()
        self.email_status = QLabel("")
        self.email_status.setObjectName("Muted")
        barra.add(self.email_status)
        email_button = make_button("Email de envio...")
        email_button.setToolTip("O login do email do escritório que o DocFlow usa para enviar.")
        email_button.clicked.connect(self.configure_email)
        barra.add(email_button)
        layout.addWidget(barra)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.tabs.addTab(self._build_envios_tab(), "Envios")
        self.tabs.addTab(self._build_history_tab(), "Histórico")
        self.refresh_data()

    # Montagem --------------------------------------------------------------------------

    def _build_envios_tab(self) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        lista_card = Card()
        lista_layout = QVBoxLayout(lista_card)
        lista_layout.setContentsMargins(10, 10, 10, 10)
        titulo = QLabel("Seus envios")
        titulo.setStyleSheet("font-weight: 600; font-size: 10.5pt;")
        lista_layout.addWidget(titulo)
        self.lista = QListWidget()
        self.lista.setSpacing(2)
        # Os textos quebram linha em vez de empurrar o selo para fora da lista.
        self.lista.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.lista.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.lista.currentItemChanged.connect(self._on_envio_changed)
        lista_layout.addWidget(self.lista, 1)
        splitter.addWidget(lista_card)

        self.detalhe = QStackedWidget()
        vazio = Card()
        vazio_layout = QVBoxLayout(vazio)
        vazio_layout.setContentsMargins(28, 28, 28, 28)
        vazio_texto = QLabel(
            "<b>Nenhum envio ainda.</b><br><br>Comece por <b>Novo envio</b>: uma cobrança de documento (o Informe de "
            "Rendimentos de cada trimestre, por exemplo) ou uma mala direta em cópia oculta."
        )
        vazio_texto.setWordWrap(True)
        vazio_layout.addWidget(vazio_texto)
        vazio_layout.addStretch(1)
        self.detalhe.addWidget(vazio)

        area = Card()
        area_layout = QVBoxLayout(area)
        area_layout.setContentsMargins(18, 14, 18, 14)
        area_layout.setSpacing(6)
        cabecalho = QHBoxLayout()
        textos = QVBoxLayout()
        textos.setSpacing(2)
        self.titulo_label = QLabel("")
        self.titulo_label.setStyleSheet("font-weight: 700; font-size: 13pt;")
        textos.addWidget(self.titulo_label)
        self.subtitulo_label = QLabel("")
        self.subtitulo_label.setObjectName("Muted")
        self.subtitulo_label.setWordWrap(True)
        textos.addWidget(self.subtitulo_label)
        cabecalho.addLayout(textos, 1)
        self.ativo_button = make_button("Desativar")
        self.ativo_button.clicked.connect(self.toggle_rule)
        cabecalho.addWidget(self.ativo_button, 0, Qt.AlignmentFlag.AlignTop)
        editar = make_button("Editar...")
        editar.setToolTip("Público, competências, quando enviar, canal e textos.")
        editar.clicked.connect(self.edit_rule)
        cabecalho.addWidget(editar, 0, Qt.AlignmentFlag.AlignTop)
        excluir = make_button("Excluir", "quiet")
        excluir.clicked.connect(self.delete_rule)
        cabecalho.addWidget(excluir, 0, Qt.AlignmentFlag.AlignTop)
        area_layout.addLayout(cabecalho)

        self.area_tabs = QTabWidget()
        self.quem_recebe = QuemRecebePanel(self.services, self.refresh_data)
        self.mensagem = MensagemTab(self.services, self.refresh_data, self.edit_rule)
        self.area_tabs.addTab(self.quem_recebe, "Quem recebe")
        self.area_tabs.addTab(self.mensagem, "Mensagem")
        self.envio_history_table = make_readonly_table(
            ["Quando", "Competência", "Empresa", "Canal", "Situação", "Para", "Detalhe"], stretch_column=6,
            sort_key="envios:historico_envio",
        )
        self.area_tabs.addTab(self.envio_history_table, "Histórico")
        area_layout.addWidget(self.area_tabs, 1)
        self.detalhe.addWidget(area)
        splitter.addWidget(self.detalhe)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 7)
        splitter.setSizes([330, 980])
        return splitter

    def _build_history_tab(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        filtros = ToolbarRow()
        filtros.add(QLabel("Envio"))
        self.history_filter = QComboBox()
        self.history_filter.setMinimumWidth(240)
        self.history_filter.currentIndexChanged.connect(self._load_history)
        filtros.add(self.history_filter)
        filtros.add_stretch()
        layout.addWidget(filtros)
        self.history_table = make_readonly_table(
            ["Quando", "Envio", "Competência", "Empresa", "Canal", "Situação", "Para", "Detalhe"], stretch_column=7,
            sort_key="envios:historico",
        )
        layout.addWidget(self.history_table, 1)
        return content

    # Dados -----------------------------------------------------------------------------

    def refresh_data(self) -> None:
        servico = self.services.envio_programado_service
        self.envios = servico.listar()
        self.pendentes = {}
        for item in servico.a_enviar():
            quantas = len(item["empresas"]) if item.get("modo") == MODO_CCO else 1
            self.pendentes[item["envio_id"]] = self.pendentes.get(item["envio_id"], 0) + quantas
        atual = self.envio_atual()
        self.lista.blockSignals(True)
        self.lista.clear()
        for envio in self.envios:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, envio["id"])
            widget = EnvioListaItem(envio, self.pendentes.get(envio["id"], 0))
            item.setSizeHint(widget.sizeHint())
            self.lista.addItem(item)
            self.lista.setItemWidget(item, widget)
        alvo = next((i for i, e in enumerate(self.envios) if atual and e["id"] == atual["id"]), 0 if self.envios else -1)
        self.lista.setCurrentRow(alvo)
        self.lista.blockSignals(False)
        self._show_envio()
        self._update_email_status()
        self._fill_history_filter()
        self._load_history()

    def envio_atual(self) -> dict | None:
        item = self.lista.currentItem() if hasattr(self, "lista") else None
        if item is None:
            return None
        envio_id = item.data(Qt.ItemDataRole.UserRole)
        return next((e for e in self.envios if e["id"] == envio_id), None)

    def select_envio(self, envio_id: int) -> None:
        for linha in range(self.lista.count()):
            if self.lista.item(linha).data(Qt.ItemDataRole.UserRole) == envio_id:
                self.lista.setCurrentRow(linha)
                return

    def _on_envio_changed(self, atual, anterior) -> None:
        if anterior is not None and self.mensagem.dirty and self.mensagem.envio:
            if QMessageBox.question(
                self, "Mensagem", f'Salvar as alterações da mensagem de "{self.mensagem.envio["nome"]}"?'
            ) == QMessageBox.StandardButton.Yes:
                self.mensagem.save()
        self.mensagem.dirty = False
        self._show_envio()

    def _show_envio(self) -> None:
        envio = self.envio_atual()
        self.detalhe.setCurrentIndex(1 if envio else 0)
        if not envio:
            self.quem_recebe.set_envio(None)
            self.mensagem.load(None, force=True)
            return
        self.titulo_label.setText(envio["nome"])
        pendentes = self.pendentes.get(envio["id"], 0)
        partes = [
            envio["publico_label"],
            f'competências: {envio["meses_label"]}',
            ("mês seguinte" if envio["enviar_em"] == ENVIAR_MES_SEGUINTE else "mesmo mês") + f', dia {envio["dia_envio"]}',
        ]
        if not envio["ativo"]:
            partes.append("desativado")
        elif pendentes:
            partes.append(f"{pendentes} para enviar agora")
        self.subtitulo_label.setText("  ·  ".join(partes))
        self.ativo_button.setText("Desativar" if envio["ativo"] else "Ativar")
        mesma = self.quem_recebe.envio and self.quem_recebe.envio["id"] == envio["id"]
        self.quem_recebe.set_envio(envio, self.quem_recebe.competencia() if mesma else None)
        self.mensagem.load(envio)
        self._load_envio_history(envio)

    def _update_email_status(self) -> None:
        sender = self.services.email_sender_service
        if sender.configurado():
            self.email_status.setText(f"Emails saem de {sender.remetente()}")
        else:
            self.email_status.setText("Email de envio não configurado")

    def _history_rows(self, registros: list[dict], com_envio: bool) -> list:
        linhas = []
        for registro in registros:
            valores = [
                format_utc_timestamp(registro["registrado_em"]),
                f'{registro["mes"]:02d}/{registro["ano"]}',
                f'{registro["codigo_empresa"]} - {registro["nome_empresa"]}',
                CANAL_CURTO.get(registro.get("canal"), "-"),
                STATUS_LABELS.get(registro["status"], registro["status"]),
                registro["destinatarios"] or "-",
                registro["detalhe"] or "",
            ]
            if com_envio:
                valores.insert(1, registro["envio_nome"])
            linhas.append((registro["id"], valores))
        return linhas

    def _load_envio_history(self, envio: dict) -> None:
        registros = self.services.envio_programado_service.historico(envio["id"])
        fill_table(
            self.envio_history_table,
            self._history_rows(registros, False),
            colors={(i, 4): ERRO for i, r in enumerate(registros) if r["status"] == "falhou"},
        )

    def _fill_history_filter(self) -> None:
        atual = self.history_filter.currentData()
        self.history_filter.blockSignals(True)
        self.history_filter.clear()
        self.history_filter.addItem("Todos os envios", None)
        for envio in self.envios:
            self.history_filter.addItem(envio["nome"], envio["id"])
        indice = self.history_filter.findData(atual)
        self.history_filter.setCurrentIndex(max(indice, 0))
        self.history_filter.blockSignals(False)

    def _load_history(self) -> None:
        registros = self.services.envio_programado_service.historico(self.history_filter.currentData())
        fill_table(
            self.history_table,
            self._history_rows(registros, True),
            colors={(i, 5): ERRO for i, r in enumerate(registros) if r["status"] == "falhou"},
        )

    # Acoes -----------------------------------------------------------------------------

    def configure_email(self) -> None:
        if EmailEnvioDialog(self, self.services.email_sender_service).exec():
            self._update_email_status()

    def new_rule(self) -> None:
        tipos = self.services.tipo_service.list_tipos()
        self._open_dialog(None, tipos[0]["id"] if tipos else PUBLICO_TODAS)

    def edit_rule(self) -> None:
        envio = self.envio_atual()
        if not envio:
            return
        if self.mensagem.dirty and not self.mensagem.save():
            return
        self._open_dialog(self.services.envio_programado_service.obter(envio["id"]))

    def _open_dialog(self, envio: dict | None, publico=None) -> None:
        dialog = EnvioDialog(
            self,
            self.services.tipo_service.list_tipos(),
            self.services.empresa_service.list_empresas(),
            envio,
            publico=publico,
        )
        while dialog.exec():
            try:
                if envio:
                    salvo = self.services.envio_programado_service.atualizar(envio["id"], dialog.values())
                else:
                    salvo = self.services.envio_programado_service.criar(dialog.values())
            except ValidationError as exc:
                QMessageBox.critical(self, "Envios automáticos", str(exc))
                continue
            self.mensagem.dirty = False
            self.refresh_data()
            self.select_envio(salvo["id"])
            return

    def new_mailing(self) -> None:
        nome, ok = QInputDialog.getText(self, "Nova mala direta", "Nome da mala direta:", text="Distribuição de lucros")
        if not ok or not nome.strip():
            return
        empresas = [
            e for e in self.services.empresa_service.list_empresas(active_only=True)
            if not e.get("nao_contatar_mala_direta")
            and (split_emails(e.get("email_contato")) or (e.get("whatsapp_envios") and (e.get("whatsapp") or e.get("whatsapp_grupo"))))
        ]
        try:
            envio = self.services.envio_programado_service.criar(
                {
                    "nome": nome.strip(),
                    "modo": MODO_CCO,
                    "canal": CANAL_AUTOMATICO,
                    "empresa_ids": [e["id"] for e in empresas] or None,
                    "meses": "mensal",
                    "enviar_em": ENVIAR_MES_SEGUINTE,
                    "dia_envio": 5,
                    "assunto": f"{nome.strip()} - competência {{competencia}}",
                    "corpo": TEXTO_INICIAL_CCO,
                    "ativo": False,
                }
            )
        except ValidationError as exc:
            QMessageBox.critical(self, "Mala direta", str(exc))
            return
        self.refresh_data()
        self.select_envio(envio["id"])
        self.area_tabs.setCurrentWidget(self.mensagem)
        QMessageBox.information(
            self,
            "Mala direta",
            f"Mala direta criada com as {len(empresas)} empresas ativas que têm email ou WhatsApp liberado.\n\n"
            "Agora: preencha o email do escritório em Para, cole o texto (ou carregue um modelo), confira em "
            "Quem recebe e, quando estiver tudo certo, clique em Ativar.",
        )

    def toggle_rule(self) -> None:
        envio = self.envio_atual()
        if not envio:
            return
        if not envio["ativo"] and envio["modo"] == MODO_CCO and not envio.get("email_para"):
            QMessageBox.warning(self, "Envios automáticos", "Preencha o email do escritório em Para (aba Mensagem) antes de ativar.")
            self.area_tabs.setCurrentWidget(self.mensagem)
            return
        try:
            self.services.envio_programado_service.definir_ativo(envio["id"], not envio["ativo"])
        except ValidationError as exc:
            QMessageBox.critical(self, "Envios automáticos", str(exc))
            return
        self.refresh_data()

    def delete_rule(self) -> None:
        envio = self.envio_atual()
        if not envio:
            return
        answer = QMessageBox.question(
            self,
            "Excluir envio",
            f'Excluir o envio "{envio["nome"]}" e todo o histórico dele? Não dá para desfazer.',
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.services.envio_programado_service.excluir(envio["id"])
        except ValidationError as exc:
            QMessageBox.critical(self, "Envios automáticos", str(exc))
            return
        self.mensagem.dirty = False
        self.refresh_data()
