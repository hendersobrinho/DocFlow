"""Pecas da tela de Envios automaticos: quem recebe cada envio (separado em email, WhatsApp e
quem fica de fora), o envio de WhatsApp em sequencia (uma conversa ou grupo por vez, ja com a
mensagem) e o login do email que o DocFlow usa para enviar."""

from __future__ import annotations

from datetime import date
from urllib.parse import quote

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QProgressDialog,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.dialogs.company_dialogs import CompanyMultiSelectDialog
from documentos_empresa_app.qt_ui.theme import tokens
from documentos_empresa_app.qt_ui.widgets.common import Card, KpiCard, ToolbarRow, make_button
from documentos_empresa_app.qt_ui.widgets.tables import fill_table, make_readonly_table, selected_key, selected_keys
from documentos_empresa_app.services.email_sender_service import (
    PROVEDORES_SMTP,
    SEGURANCA_LABELS,
    load_email_settings,
    save_email_settings,
)
from documentos_empresa_app.services.envio_programado_service import (
    CANAL_EMAIL,
    CANAL_WHATSAPP,
    CONF_FORA,
    CONF_JA_ENTREGOU,
    CONF_JA_RECEBEU,
    CONF_SEM_CONTATO,
    CONF_VAI_RECEBER,
    MODO_CCO,
    MOTIVO_TIRADA,
)
from documentos_empresa_app.utils.common import ValidationError
from documentos_empresa_app.utils.helpers import open_bcc_email_draft

# Acima disso o link mailto: costuma ser cortado pelo Windows/Outlook - a Cco vai pela area de
# transferencia.
MAILTO_LIMITE = 1900
CANAL_CURTO = {"email": "Email", "whatsapp": "WhatsApp", None: "-"}


def competencia_do_item(item: dict) -> tuple[int, int]:
    mes, ano = (int(parte) for parte in item["competencia"].split("/"))
    return ano, mes


def abrir_link(link: str) -> None:
    QDesktopServices.openUrl(QUrl.fromEncoded(link.encode("ascii")))


def abrir_rascunho_cco(parent: QWidget, para: str | None, cco: list[str], assunto: str, corpo: str) -> bool:
    """Abre o rascunho com a Cco. Lista grande demais para o link vai para a area de
    transferencia (o usuario cola no campo Cco)."""
    try:
        if len(quote(",".join(cco))) + len(quote(assunto)) + len(quote(corpo)) <= MAILTO_LIMITE:
            open_bcc_email_draft(cco, assunto, corpo, to=para)
            return True
        QGuiApplication.clipboard().setText("; ".join(cco))
        abrir_link(f"mailto:{quote(para or '', safe='@')}?subject={quote(assunto)}&body={quote(corpo)}")
    except ValidationError as exc:
        QMessageBox.critical(parent, "Email", str(exc))
        return False
    QMessageBox.information(
        parent,
        "Email",
        f"São {len(cco)} emails - grande demais para irem pelo link do email.\n\n"
        "Eles já estão copiados: no rascunho que abriu, clique em Cco e cole (Ctrl+V).",
    )
    return True


def registrar_itens(services, itens: list[dict], canal: str | None = None) -> None:
    """Marca como enviados itens de 'a enviar'/'conferencia' (individuais ou em copia oculta)."""
    servico = services.envio_programado_service
    for item in itens:
        if item.get("modo") == MODO_CCO:
            servico.registrar_mala_direta(item["envio_id"], competencia_do_item(item), "enviado")
            continue
        usado = canal or item["canal"]
        servico.registrar(
            item["envio_id"],
            item["empresa_id"],
            competencia_do_item(item),
            "enviado",
            item["whatsapp_destino"] if usado == CANAL_WHATSAPP else item["destinatarios"],
            canal=usado,
        )


def abrir_whatsapp(item: dict) -> bool:
    """Abre a conversa (com a mensagem pronta) ou o grupo. Grupo nao aceita texto no link: a
    mensagem vai para a area de transferencia. Devolve True quando copiou a mensagem."""
    if item.get("whatsapp_e_grupo"):
        QGuiApplication.clipboard().setText(item["mensagem_whatsapp"])
        abrir_link(item["whatsapp_link"])
        return True
    abrir_link(item["whatsapp_link"])
    return False


def enviar_emails_agora(parent: QWidget, services, envio: dict, competencia: tuple[int, int], empresa_ids=None) -> bool:
    """Envia pelo email do escritorio cadastrado no DocFlow, com barra de progresso. Devolve
    True se algo foi enviado."""
    sender = services.email_sender_service
    if not sender.configurado():
        if QMessageBox.question(
            parent,
            "Enviar emails",
            "O email de envio do DocFlow ainda não foi configurado.\n\nConfigurar agora?",
        ) != QMessageBox.StandardButton.Yes:
            return False
        if not EmailEnvioDialog(parent, sender).exec():
            return False
    progresso = QProgressDialog("Conectando ao servidor de email...", None, 0, 0, parent)
    progresso.setWindowTitle("Enviando emails")
    progresso.setWindowModality(Qt.WindowModality.WindowModal)
    progresso.setMinimumDuration(0)
    progresso.setCancelButton(None)
    progresso.show()
    QApplication.processEvents()

    def andamento(feitos: int, total: int) -> None:
        progresso.setMaximum(total)
        progresso.setValue(feitos)
        progresso.setLabelText(f"Enviando {min(feitos + 1, total)} de {total}...")
        QApplication.processEvents()

    try:
        resultado = services.envio_programado_service.enviar_emails(
            envio["id"], *competencia, sender, empresa_ids=empresa_ids, on_progress=andamento
        )
    except ValidationError as exc:
        progresso.close()
        QMessageBox.critical(parent, "Enviar emails", str(exc))
        return False
    progresso.close()
    if not resultado["mensagens"]:
        QMessageBox.information(parent, "Enviar emails", "Nenhum email pendente para enviar.")
        return False
    texto = f'{resultado["enviadas"]} de {resultado["mensagens"]} email(s) enviado(s) e registrado(s).'
    if resultado["falhas"]:
        texto += "\n\nNão foram:\n" + "\n".join(resultado["falhas"][:10])
        QMessageBox.warning(parent, "Enviar emails", texto)
    else:
        QMessageBox.information(parent, "Enviar emails", texto)
    return resultado["enviadas"] > 0


class EmailEnvioDialog(QDialog):
    """Login do email que o DocFlow usa para enviar (SMTP). Fica guardado neste computador,
    com a senha protegida."""

    def __init__(self, parent: QWidget | None, sender) -> None:
        super().__init__(parent)
        self.sender = sender
        self.setWindowTitle("Email de envio")
        self.setMinimumWidth(520)
        atual = load_email_settings()

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        intro = QLabel(
            "Com o email do escritório cadastrado aqui, o DocFlow envia as cobranças e a mala direta "
            "sozinho, com um clique - sem abrir o seu programa de email."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        form.setSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.provedor_combo = QComboBox()
        self.provedor_combo.addItem("Escolha para preencher o servidor...", None)
        for nome, dados in PROVEDORES_SMTP.items():
            self.provedor_combo.addItem(nome, dados)
        self.provedor_combo.addItem("Outro (preencher à mão)", None)
        self.provedor_combo.currentIndexChanged.connect(self._aplicar_provedor)
        form.addRow("Provedor", self.provedor_combo)

        self.remetente_nome_edit = QLineEdit(atual["remetente_nome"])
        self.remetente_nome_edit.setPlaceholderText("Ex: Métodos Contabilidade")
        form.addRow("Nome do remetente", self.remetente_nome_edit)
        self.remetente_email_edit = QLineEdit(atual["remetente_email"])
        self.remetente_email_edit.setPlaceholderText("Ex: contato@escritorio.com.br")
        form.addRow("Email", self.remetente_email_edit)
        self.senha_edit = QLineEdit()
        self.senha_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.senha_edit.setPlaceholderText("Deixe vazio para manter a senha salva" if atual["senha"] else "Senha do email")
        form.addRow("Senha", self.senha_edit)

        servidor = QHBoxLayout()
        self.host_edit = QLineEdit(atual["host"])
        self.host_edit.setPlaceholderText("smtp.seuprovedor.com.br")
        servidor.addWidget(self.host_edit, 1)
        servidor.addWidget(QLabel("porta"))
        self.porta_spin = QSpinBox()
        self.porta_spin.setRange(1, 65535)
        self.porta_spin.setValue(int(atual["porta"]))
        servidor.addWidget(self.porta_spin)
        form.addRow("Servidor (SMTP)", servidor)
        self.seguranca_combo = QComboBox()
        for chave, texto in SEGURANCA_LABELS.items():
            self.seguranca_combo.addItem(texto, chave)
        self.seguranca_combo.setCurrentIndex(max(self.seguranca_combo.findData(atual["seguranca"]), 0))
        form.addRow("Segurança", self.seguranca_combo)
        self.usuario_edit = QLineEdit(atual["usuario"])
        self.usuario_edit.setPlaceholderText("Normalmente o próprio email")
        form.addRow("Usuário", self.usuario_edit)
        layout.addLayout(form)

        dica = QLabel(
            "Gmail e Microsoft 365 costumam bloquear a senha normal: crie uma <b>senha de app</b> na conta "
            "(Segurança > Senhas de app) e use ela aqui."
        )
        dica.setObjectName("Muted")
        dica.setWordWrap(True)
        layout.addWidget(dica)

        botoes = QHBoxLayout()
        testar = make_button("Enviar email de teste")
        testar.clicked.connect(self.testar)
        botoes.addWidget(testar)
        botoes.addStretch(1)
        cancelar = make_button("Cancelar", "quiet")
        cancelar.clicked.connect(self.reject)
        botoes.addWidget(cancelar)
        salvar = make_button("Salvar", "primary")
        salvar.clicked.connect(self.salvar)
        botoes.addWidget(salvar)
        layout.addLayout(botoes)

    def _aplicar_provedor(self) -> None:
        dados = self.provedor_combo.currentData()
        if not dados:
            return
        host, porta, seguranca = dados
        self.host_edit.setText(host)
        self.porta_spin.setValue(porta)
        self.seguranca_combo.setCurrentIndex(self.seguranca_combo.findData(seguranca))

    def values(self) -> dict:
        return {
            "host": self.host_edit.text(),
            "porta": self.porta_spin.value(),
            "seguranca": self.seguranca_combo.currentData(),
            "usuario": self.usuario_edit.text() or self.remetente_email_edit.text(),
            "senha": self.senha_edit.text(),
            "remetente_nome": self.remetente_nome_edit.text(),
            "remetente_email": self.remetente_email_edit.text(),
        }

    def salvar(self) -> None:
        try:
            save_email_settings(self.values())
        except ValidationError as exc:
            QMessageBox.critical(self, "Email de envio", str(exc))
            return
        self.accept()

    def testar(self) -> None:
        try:
            salvo = save_email_settings(self.values())
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                destino = self.sender.testar(salvo)
            finally:
                QApplication.restoreOverrideCursor()
        except ValidationError as exc:
            QMessageBox.critical(self, "Email de envio", str(exc))
            return
        QMessageBox.information(self, "Email de envio", f"Email de teste enviado para {destino}. Confira a caixa de entrada.")


class WhatsAppSequenceDialog(QDialog):
    """Passa pelas conversas uma a uma: abre o WhatsApp com a mensagem pronta (no grupo, a
    mensagem vai copiada para colar), a pessoa confere e envia la, volta aqui e clica em
    'Enviei' - o envio fica registrado e a proxima ja abre."""

    def __init__(self, parent: QWidget | None, services, itens: list[dict]) -> None:
        super().__init__(parent)
        self.services = services
        self.itens = [item for item in itens if item.get("whatsapp_link")]
        self.posicao = 0
        self.enviados = 0
        self.pulados = 0
        self.setWindowTitle("Enviar pelo WhatsApp")
        self.setMinimumSize(560, 520)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        topo = QHBoxLayout()
        self.progresso_label = QLabel("")
        self.progresso_label.setStyleSheet("font-weight: 600;")
        topo.addWidget(self.progresso_label)
        topo.addStretch(1)
        self.contagem_label = QLabel("")
        self.contagem_label.setObjectName("Muted")
        topo.addWidget(self.contagem_label)
        layout.addLayout(topo)
        self.barra = QProgressBar()
        self.barra.setRange(0, max(len(self.itens), 1))
        self.barra.setTextVisible(False)
        self.barra.setMaximumHeight(8)
        layout.addWidget(self.barra)

        card = Card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 14, 18, 14)
        self.empresa_label = QLabel("")
        self.empresa_label.setStyleSheet("font-weight: 600; font-size: 12pt;")
        self.empresa_label.setWordWrap(True)
        card_layout.addWidget(self.empresa_label)
        self.numero_label = QLabel("")
        self.numero_label.setObjectName("Muted")
        card_layout.addWidget(self.numero_label)
        self.mensagem = QTextEdit()
        self.mensagem.setReadOnly(True)
        card_layout.addWidget(self.mensagem, 1)
        self.grupo_label = QLabel("")
        self.grupo_label.setWordWrap(True)
        self.grupo_label.setStyleSheet(f"color: {tokens()['warning']}; font-weight: 600;")
        card_layout.addWidget(self.grupo_label)
        layout.addWidget(card, 1)

        passos = QLabel(
            "<b>1.</b> Abrir conversa  ·  <b>2.</b> Conferir e apertar enviar no WhatsApp  ·  "
            "<b>3.</b> Voltar e clicar em <b>Enviei</b>"
        )
        passos.setObjectName("Muted")
        passos.setWordWrap(True)
        layout.addWidget(passos)
        self.auto_check = QCheckBox("Ao clicar em Enviei, já abrir a próxima conversa")
        self.auto_check.setChecked(True)
        layout.addWidget(self.auto_check)

        botoes = QHBoxLayout()
        parar = make_button("Parar", "quiet")
        parar.clicked.connect(self.accept)
        botoes.addWidget(parar)
        botoes.addStretch(1)
        self.pular_button = make_button("Pular")
        self.pular_button.clicked.connect(self.skip)
        botoes.addWidget(self.pular_button)
        self.abrir_button = make_button("Abrir conversa", "primary")
        self.abrir_button.clicked.connect(self.open_current)
        botoes.addWidget(self.abrir_button)
        self.enviei_button = make_button("Enviei ✓", "primary")
        self.enviei_button.clicked.connect(self.mark_sent)
        botoes.addWidget(self.enviei_button)
        layout.addLayout(botoes)
        self._show_current()

    def _show_current(self) -> None:
        total = len(self.itens)
        self.barra.setValue(self.posicao)
        self.contagem_label.setText(f"{self.enviados} enviada(s) · {self.pulados} pulada(s)")
        self.grupo_label.clear()
        if self.posicao >= total:
            self.progresso_label.setText("Pronto!")
            self.empresa_label.setText(
                f"{self.enviados} mensagem(ns) enviada(s) e registrada(s)." if total else "Nenhuma empresa com WhatsApp para enviar."
            )
            self.numero_label.setText("")
            self.mensagem.clear()
            for botao in (self.pular_button, self.abrir_button, self.enviei_button):
                botao.setEnabled(False)
            return
        item = self.itens[self.posicao]
        self.progresso_label.setText(f"Conversa {self.posicao + 1} de {total}")
        self.empresa_label.setText(f'{item["codigo_empresa"]} - {item["nome_empresa"]}')
        self.numero_label.setText(f'{item["whatsapp_destino"]}  ·  {item["envio_nome"]}  ·  competência {item["competencia"]}')
        self.mensagem.setPlainText(item["mensagem_whatsapp"])
        self.abrir_button.setText("Abrir grupo" if item.get("whatsapp_e_grupo") else "Abrir conversa")
        self.abrir_button.setVisible(True)
        self.enviei_button.setVisible(False)
        self.abrir_button.setFocus()

    def open_current(self) -> None:
        if abrir_whatsapp(self.itens[self.posicao]):
            self.grupo_label.setText("Mensagem copiada! No grupo, clique na caixa de texto, cole (Ctrl+V) e envie.")
        self.abrir_button.setVisible(False)
        self.enviei_button.setVisible(True)
        self.enviei_button.setFocus()

    def mark_sent(self) -> None:
        try:
            registrar_itens(self.services, [self.itens[self.posicao]], CANAL_WHATSAPP)
        except ValidationError as exc:
            QMessageBox.critical(self, "WhatsApp", str(exc))
            return
        self.enviados += 1
        self._next()

    def skip(self) -> None:
        self.pulados += 1
        self._next()

    def _next(self) -> None:
        self.posicao += 1
        self._show_current()
        if self.posicao < len(self.itens) and self.auto_check.isChecked():
            self.open_current()


class _CanalLista(QWidget):
    """Uma das divisoes de 'Quem recebe': tabela de empresas a esquerda e, a direita, a
    mensagem exatamente como a empresa selecionada recebe."""

    def __init__(self, colunas: list[str], vazio: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.linhas: list[dict] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        self.acoes = ToolbarRow()
        layout.addWidget(self.acoes)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.table = make_readonly_table(colunas, stretch_column=0)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        splitter.addWidget(self.table)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText(vazio)
        splitter.addWidget(self.preview)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

    def selecionadas(self) -> list[dict]:
        return [self.linhas[i] for i in selected_keys(self.table) if i is not None and i < len(self.linhas)]

    def atual(self) -> dict | None:
        indice = selected_key(self.table)
        return self.linhas[indice] if indice is not None and indice < len(self.linhas) else None


class QuemRecebePanel(QWidget):
    """O envio aplicado numa competencia, dividido em quem recebe por email, quem recebe por
    WhatsApp e quem fica de fora (e por que). Daqui se envia, se inclui e se tira empresas."""

    def __init__(self, services, on_changed, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.on_changed = on_changed
        self.envio: dict | None = None
        self.dados: dict | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)

        topo = QHBoxLayout()
        topo.addWidget(QLabel("Competência"))
        self.competencia_combo = QComboBox()
        self.competencia_combo.setMinimumWidth(110)
        self.competencia_combo.currentIndexChanged.connect(self._load)
        topo.addWidget(self.competencia_combo)
        self.quando_label = QLabel("")
        self.quando_label.setObjectName("Muted")
        self.quando_label.setWordWrap(True)
        topo.addWidget(self.quando_label, 1)
        layout.addLayout(topo)

        kpis = QHBoxLayout()
        kpis.setSpacing(8)
        t = tokens()
        self.kpi_email = KpiCard("Recebem por email", t["accent"])
        self.kpi_whatsapp = KpiCard("Recebem por WhatsApp", t["success"])
        self.kpi_ja = KpiCard("Já receberam")
        self.kpi_fora = KpiCard("Ficam de fora")
        for kpi in (self.kpi_email, self.kpi_whatsapp, self.kpi_ja, self.kpi_fora):
            kpis.addWidget(kpi)
        layout.addLayout(kpis)

        lista = ToolbarRow()
        incluir = make_button("Incluir empresas...")
        incluir.setToolTip("Põe empresas neste envio (ou devolve as que foram tiradas).")
        incluir.clicked.connect(self.include_companies)
        lista.add(incluir)
        tirar = make_button("Tirar deste envio", "quiet")
        tirar.setToolTip("Tira as empresas selecionadas só deste envio (Ctrl/Shift para várias).")
        tirar.clicked.connect(self.remove_companies)
        lista.add(tirar)
        lista.add_stretch()
        self.busca_edit = QLineEdit()
        self.busca_edit.setPlaceholderText("Buscar empresa, email ou número...")
        self.busca_edit.setClearButtonEnabled(True)
        self.busca_edit.setMinimumWidth(220)
        self.busca_edit.textChanged.connect(self._fill)
        lista.add(self.busca_edit)
        layout.addWidget(lista)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        layout.addWidget(self.tabs, 1)

        self.email = _CanalLista(["Empresa", "Email", "Situação"], "Clique numa empresa para ver o email que ela recebe.")
        self.enviar_emails_button = make_button("Enviar emails agora", "primary")
        self.enviar_emails_button.setToolTip("Envia pelo email do escritório cadastrado no DocFlow e registra cada envio.")
        self.enviar_emails_button.clicked.connect(self.send_emails)
        self.email.acoes.add(self.enviar_emails_button)
        rascunho = make_button("Abrir no meu email")
        rascunho.setToolTip("Abre o rascunho no seu programa de email para você mesmo enviar.")
        rascunho.clicked.connect(self.open_email)
        self.email.acoes.add(rascunho)
        marcar_email = make_button("Marcar como enviado", "quiet")
        marcar_email.clicked.connect(lambda: self.mark_selected(self.email))
        self.email.acoes.add(marcar_email)
        self.email.acoes.add_stretch()
        self.email.table.itemSelectionChanged.connect(lambda: self._preview(self.email))
        self.email.table.doubleClicked.connect(lambda _i: self.open_email())
        self.tabs.addTab(self.email, "Email")

        self.whatsapp = _CanalLista(
            ["Empresa", "WhatsApp", "Situação"], "Clique numa empresa para ver a mensagem de WhatsApp dela."
        )
        self.sequencia_button = make_button("Enviar em sequência", "primary")
        self.sequencia_button.setToolTip("Abre uma conversa (ou grupo) por vez com a mensagem pronta; você confere e envia.")
        self.sequencia_button.clicked.connect(self.send_whatsapp)
        self.whatsapp.acoes.add(self.sequencia_button)
        abrir = make_button("Abrir conversa")
        abrir.clicked.connect(self.open_whatsapp)
        self.whatsapp.acoes.add(abrir)
        copiar = make_button("Copiar mensagem", "quiet")
        copiar.clicked.connect(self.copy_whatsapp)
        self.whatsapp.acoes.add(copiar)
        marcar_whatsapp = make_button("Marcar como enviado", "quiet")
        marcar_whatsapp.clicked.connect(lambda: self.mark_selected(self.whatsapp))
        self.whatsapp.acoes.add(marcar_whatsapp)
        self.whatsapp.acoes.add_stretch()
        self.whatsapp.table.itemSelectionChanged.connect(lambda: self._preview(self.whatsapp))
        self.whatsapp.table.doubleClicked.connect(lambda _i: self.open_whatsapp())
        self.tabs.addTab(self.whatsapp, "WhatsApp")

        self.fora = _CanalLista(["Empresa", "Por que fica de fora"], "Quem não recebe nesta competência e o motivo.")
        devolver = make_button("Incluir de volta")
        devolver.setToolTip("Volta as empresas selecionadas que foram tiradas deste envio.")
        devolver.clicked.connect(self.return_companies)
        self.fora.acoes.add(devolver)
        self.fora_hint = QLabel("Sem email nem WhatsApp? Cadastre na tela Empresas, em Contato para cobrança.")
        self.fora_hint.setObjectName("Muted")
        self.fora.acoes.add(self.fora_hint)
        self.fora.acoes.add_stretch()
        self.fora.table.itemSelectionChanged.connect(lambda: self._preview(self.fora))
        self.tabs.addTab(self.fora, "Fica de fora")

    # Dados -----------------------------------------------------------------------------

    def set_envio(self, envio: dict | None, competencia: tuple[int, int] | None = None) -> None:
        self.envio = envio
        servico = self.services.envio_programado_service
        self.competencia_combo.blockSignals(True)
        self.competencia_combo.clear()
        if envio:
            hoje = date.today()
            atual = servico.competencia_do_envio(envio, hoje.year, hoje.month)
            competencias = servico.competencias_para_conferir(envio, hoje)
            for ano, mes in competencias:
                self.competencia_combo.addItem(f"{mes:02d}/{ano}", (ano, mes))
            indice = self.competencia_combo.findData(competencia) if competencia else -1
            if indice < 0:
                # Abre na competencia deste mes, se o envio cobra; senao na proxima.
                indice = next((i for i, c in enumerate(competencias) if c >= atual), max(len(competencias) - 1, 0))
            self.competencia_combo.setCurrentIndex(indice)
        self.competencia_combo.blockSignals(False)
        self._load()

    def competencia(self) -> tuple[int, int] | None:
        return self.competencia_combo.currentData()

    def reload(self) -> None:
        self._load()

    def _load(self) -> None:
        competencia = self.competencia()
        if not self.envio or not competencia:
            self.dados = None
            self.quando_label.setText("")
            self._fill()
            return
        self.dados = self.services.envio_programado_service.conferencia(self.envio["id"], *competencia)
        quando = date.fromisoformat(self.dados["data_envio"])
        hoje = date.today()
        if quando > hoje:
            prazo = f"sai a partir de {quando.strftime('%d/%m/%Y')}"
        elif (quando.year, quando.month) == (hoje.year, hoje.month):
            prazo = f"está para enviar desde {quando.strftime('%d/%m/%Y')}"
        else:
            prazo = f"era para ter saído em {quando.strftime('%d/%m/%Y')}"
        desligado = "" if self.envio["ativo"] else "  ·  Envio desativado: nada sai sozinho."
        self.quando_label.setText(f"Este envio {prazo}.{desligado}")
        self._fill()

    def _linhas_por_aba(self) -> tuple[list[dict], list[dict], list[dict]]:
        linhas = (self.dados or {}).get("linhas", [])
        busca = self.busca_edit.text().strip().casefold()
        if busca:
            linhas = [
                l for l in linhas
                if busca in f'{l["codigo_empresa"]} {l["nome_empresa"]} {l["contato"]}'.casefold()
            ]
        recebem = (CONF_VAI_RECEBER, CONF_JA_RECEBEU)
        email = [l for l in linhas if l["situacao"] in recebem and l["canal"] == CANAL_EMAIL]
        whatsapp = [l for l in linhas if l["situacao"] in recebem and l["canal"] == CANAL_WHATSAPP]
        fora = [l for l in linhas if l["situacao"] not in recebem]
        return email, whatsapp, fora

    def _fill(self) -> None:
        email, whatsapp, fora = self._linhas_por_aba()
        t = tokens()
        cores = {CONF_VAI_RECEBER: t["success"], CONF_JA_RECEBEU: t["muted"]}

        def situacao(l: dict) -> str:
            return "Vai receber" if l["situacao"] == CONF_VAI_RECEBER else "Já recebeu ✓"

        for aba, linhas in ((self.email, email), (self.whatsapp, whatsapp)):
            aba.linhas = linhas
            fill_table(
                aba.table,
                [(i, [f'{l["codigo_empresa"]} - {l["nome_empresa"]}', l["contato"] or "-", situacao(l)]) for i, l in enumerate(linhas)],
                colors={(i, 2): cores[l["situacao"]] for i, l in enumerate(linhas)},
            )
            aba.preview.clear()
        self.fora.linhas = fora
        fill_table(
            self.fora.table,
            [(i, [f'{l["codigo_empresa"]} - {l["nome_empresa"]}', self._motivo(l)]) for i, l in enumerate(fora)],
            colors={(i, 1): t["danger"] for i, l in enumerate(fora) if l["situacao"] == CONF_SEM_CONTATO},
        )
        self.fora.preview.clear()

        resumo = (self.dados or {}).get("resumo", {})
        por_canal = (self.dados or {}).get("por_canal", {})
        self.kpi_email.set_value(str(por_canal.get(CANAL_EMAIL, 0)))
        self.kpi_whatsapp.set_value(str(por_canal.get(CANAL_WHATSAPP, 0)))
        self.kpi_ja.set_value(str(resumo.get(CONF_JA_RECEBEU, 0)))
        self.kpi_fora.set_value(
            str(sum(resumo.get(s, 0) for s in (CONF_JA_ENTREGOU, CONF_SEM_CONTATO, CONF_FORA)))
        )
        pendentes_email = sum(1 for l in email if l["situacao"] == CONF_VAI_RECEBER)
        pendentes_whatsapp = len(self._pendentes_whatsapp())
        self.tabs.setTabText(0, f"Email ({len(email)})")
        self.tabs.setTabText(1, f"WhatsApp ({len(whatsapp)})")
        self.tabs.setTabText(2, f"Fica de fora ({len(fora)})")
        cco = (self.dados or {}).get("modo") == MODO_CCO
        if cco:
            self.enviar_emails_button.setText(f"Enviar email em cópia oculta ({pendentes_email} empresa(s))")
        else:
            self.enviar_emails_button.setText(f"Enviar {pendentes_email} email(s) agora")
        self.enviar_emails_button.setEnabled(pendentes_email > 0)
        self.sequencia_button.setText(f"Enviar em sequência ({pendentes_whatsapp})")
        self.sequencia_button.setEnabled(pendentes_whatsapp > 0)

    @staticmethod
    def _motivo(linha: dict) -> str:
        if linha["situacao"] == CONF_JA_ENTREGOU:
            return "Já entregou o documento" + (f' ({linha["motivo"]})' if linha["motivo"] else "")
        return linha["motivo"] or linha["situacao_label"]

    def _pendentes_whatsapp(self) -> list[dict]:
        return [
            l["item"] for l in (self.dados or {}).get("linhas", [])
            if l["situacao"] == CONF_VAI_RECEBER and l["canal"] == CANAL_WHATSAPP and l["item"]
        ]

    def _preview(self, aba: _CanalLista) -> None:
        linha = aba.atual()
        if not linha:
            aba.preview.clear()
            return
        item = linha["item"]
        if aba is self.fora or not item:
            aba.preview.setPlainText(
                f'{linha["codigo_empresa"]} - {linha["nome_empresa"]}\n\nNão recebe nesta competência: {self._motivo(linha)}.'
            )
            return
        if item.get("modo") == MODO_CCO:
            cabecalho = (
                f'Email único em cópia oculta\nPara: {item["para"] or "(falta o email do escritório - aba Mensagem)"}\n'
                f'Cco: {len(item["cco"])} endereço(s), entre eles {linha["contato"]}\nAssunto: {item["assunto"]}'
            )
            texto = item["corpo"]
        elif aba is self.whatsapp:
            cabecalho = f'WhatsApp: {item["whatsapp_destino"]}'
            if item.get("whatsapp_e_grupo"):
                cabecalho += "  (grupo - a mensagem é copiada para você colar)"
            texto = item["mensagem_whatsapp"]
        else:
            cabecalho = f'Para: {", ".join(item["destinatarios"]) or "-"}\nAssunto: {item["assunto"]}'
            texto = item["corpo"]
        aba.preview.setPlainText(f"{cabecalho}\n\n{texto}")

    # Acoes -----------------------------------------------------------------------------

    def send_emails(self) -> None:
        if not self.dados:
            return
        selecionadas = [l["empresa_id"] for l in self.email.selecionadas() if l["situacao"] == CONF_VAI_RECEBER]
        pendentes = [l for l in self.email.linhas if l["situacao"] == CONF_VAI_RECEBER]
        quantas = len(selecionadas) or len(pendentes)
        remetente = self.services.email_sender_service.remetente() or "o email do escritório"
        alvo = "as empresas selecionadas" if selecionadas else "todas as empresas pendentes"
        if self.dados["modo"] == MODO_CCO:
            pergunta = (f"Enviar agora UM email, de {remetente}, com {quantas} empresa(s) em cópia oculta "
                        f"({alvo}), competência {self.dados['competencia']}?")
        else:
            pergunta = f"Enviar agora {quantas} email(s), de {remetente}, para {alvo}? Competência {self.dados['competencia']}."
        if QMessageBox.question(self, "Enviar emails", pergunta) != QMessageBox.StandardButton.Yes:
            return
        if enviar_emails_agora(self, self.services, self.envio, self.competencia(), selecionadas or None):
            self.on_changed()

    def open_email(self) -> None:
        if not self.dados:
            return
        if self.dados["modo"] == MODO_CCO:
            item = self.dados.get("item_cco")
            if not item:
                QMessageBox.information(self, "Email", "Ninguém recebe por email nesta competência.")
                return
            if not item["para"]:
                QMessageBox.warning(self, "Email", "Preencha o email do escritório em Para, na aba Mensagem.")
                return
            pendentes = [e for e in item["empresas"] if not e["ja_enviado"]]
            cco = [email for e in pendentes for email in e["emails"]]
            if not cco:
                QMessageBox.information(self, "Email", "Todas as empresas já receberam esta competência.")
                return
            if abrir_rascunho_cco(self, item["para"], cco, item["assunto"], item["corpo"]):
                self._ask_registrar([item], f"Rascunho aberto com {len(pendentes)} empresa(s) em cópia oculta.")
            return
        linha = next((l for l in self.email.selecionadas() if l["item"]), None)
        if not linha:
            QMessageBox.information(self, "Email", "Selecione uma empresa na lista.")
            return
        item = linha["item"]
        try:
            open_bcc_email_draft(item["destinatarios"], item["assunto"], item["corpo"])
        except ValidationError as exc:
            QMessageBox.critical(self, "Email", str(exc))
            return
        self._ask_registrar([item], f'Rascunho aberto para {linha["nome_empresa"]}.', canal=CANAL_EMAIL)

    def send_whatsapp(self) -> None:
        itens = self._pendentes_whatsapp()
        escolhidas = {l["empresa_id"] for l in self.whatsapp.selecionadas()}
        if escolhidas and any(item["empresa_id"] in escolhidas for item in itens):
            itens = [item for item in itens if item["empresa_id"] in escolhidas]
        WhatsAppSequenceDialog(self, self.services, itens).exec()
        self.on_changed()

    def open_whatsapp(self) -> None:
        linha = self.whatsapp.atual()
        if not linha or not linha["item"]:
            QMessageBox.information(self, "WhatsApp", "Selecione uma empresa na lista.")
            return
        item = linha["item"]
        copiou = abrir_whatsapp(item)
        aviso = "O grupo foi aberto e a mensagem está copiada: cole (Ctrl+V) e envie." if copiou else "A conversa foi aberta no WhatsApp."
        if linha["situacao"] == CONF_VAI_RECEBER:
            self._ask_registrar([item], aviso, canal=CANAL_WHATSAPP)

    def copy_whatsapp(self) -> None:
        linha = self.whatsapp.atual()
        if linha and linha["item"]:
            QGuiApplication.clipboard().setText(linha["item"]["mensagem_whatsapp"])

    def mark_selected(self, aba: _CanalLista) -> None:
        linhas = [l for l in aba.selecionadas() if l["situacao"] == CONF_VAI_RECEBER]
        if not linhas:
            QMessageBox.information(self, "Envios", "Selecione empresas que ainda vão receber.")
            return
        pergunta = f"Marcar {len(linhas)} empresa(s) como enviada(s) na competência {self.dados['competencia']}?"
        if QMessageBox.question(self, "Envios", pergunta) != QMessageBox.StandardButton.Yes:
            return
        try:
            # Na copia oculta registra so as empresas escolhidas, nao o email inteiro.
            registrar_itens(self.services, [l["item_empresa"] for l in linhas])
        except ValidationError as exc:
            QMessageBox.critical(self, "Envios", str(exc))
        self.on_changed()

    def _ask_registrar(self, itens: list[dict], aviso: str, canal: str | None = None) -> None:
        if QMessageBox.question(self, "Envios", f"{aviso}\n\nDepois de enviar, registrar como enviado?") != QMessageBox.StandardButton.Yes:
            return
        try:
            registrar_itens(self.services, itens, canal)
        except ValidationError as exc:
            QMessageBox.critical(self, "Envios", str(exc))
        self.on_changed()

    # Quem entra e quem sai -------------------------------------------------------------

    def include_companies(self) -> None:
        if not self.envio:
            return
        servico = self.services.envio_programado_service
        if self.envio["tipo_documento_id"] is not None:
            tiradas = set(self.envio["empresa_ids_excluidas_lista"])
            candidatas = [e for e in self.services.empresa_service.list_empresas() if e["id"] in tiradas]
            if not candidatas:
                QMessageBox.information(
                    self,
                    "Incluir empresas",
                    f'Este envio vai para quem tem o documento "{self.envio["nome_tipo"]}". Para incluir outra '
                    "empresa, cadastre o documento para ela na tela Documentos.",
                )
                return
        else:
            na_lista = set(self.envio["empresa_ids_lista"])
            candidatas = [
                e for e in self.services.empresa_service.list_empresas(active_only=True)
                if na_lista and e["id"] not in na_lista
            ]
            if not candidatas:
                QMessageBox.information(self, "Incluir empresas", "Todas as empresas ativas já estão neste envio.")
                return
        dialog = CompanyMultiSelectDialog(self, candidatas, [], title=f'Incluir em "{self.envio["nome"]}"')
        if dialog.exec() and dialog.selected_company_ids:
            self._apply(lambda: servico.incluir_empresas(self.envio["id"], dialog.selected_company_ids))

    def remove_companies(self) -> None:
        aba = self.tabs.currentWidget()
        ids = [l["empresa_id"] for l in aba.selecionadas()] if aba is not self.fora else []
        if not self.envio or not ids:
            QMessageBox.information(self, "Tirar do envio", "Selecione na lista (Email ou WhatsApp) as empresas que vão sair.")
            return
        texto = aba.selecionadas()[0]["nome_empresa"] if len(ids) == 1 else f"{len(ids)} empresas"
        detalhe = " Ela continua com o documento; só deixa de receber esta cobrança." if self.envio["tipo_documento_id"] else ""
        if QMessageBox.question(self, "Tirar do envio", f'Tirar {texto} de "{self.envio["nome"]}"?{detalhe}') != QMessageBox.StandardButton.Yes:
            return
        self._apply(lambda: self.services.envio_programado_service.remover_empresas(self.envio["id"], ids))

    def return_companies(self) -> None:
        ids = [l["empresa_id"] for l in self.fora.selecionadas() if l["motivo"] == MOTIVO_TIRADA]
        if not self.envio or not ids:
            QMessageBox.information(
                self, "Incluir de volta", "Selecione empresas com o motivo \"Tirada deste envio\"."
            )
            return
        self._apply(lambda: self.services.envio_programado_service.incluir_empresas(self.envio["id"], ids))

    def _apply(self, acao) -> None:
        try:
            acao()
        except ValidationError as exc:
            QMessageBox.critical(self, "Envios", str(exc))
            return
        self.on_changed()
