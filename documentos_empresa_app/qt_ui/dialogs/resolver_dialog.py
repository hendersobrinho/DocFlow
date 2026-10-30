"""Janela unica para uma pessoa resolver um ou varios documentos na mao: chegou, chegou
errado, nao chegou, cliente prometeu, precisa de uma pessoa ou devolver para o Claude -
sempre com observacao e, quando faz sentido, o arquivo."""

from __future__ import annotations

from datetime import date, timedelta
from html import escape

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.icons import app_icon
from documentos_empresa_app.qt_ui.theme import tokens
from documentos_empresa_app.qt_ui.widgets.common import make_button
from documentos_empresa_app.services.cobranca_service import MOTIVOS_PESSOA, MOTIVOS_PROBLEMA
from documentos_empresa_app.utils.common import APP_NAME, ValidationError

OPCAO_RECEBIDO = "recebido"
OPCAO_PROBLEMA = "documento_com_problema"
OPCAO_NAO_CHEGOU = "nao_encontrado"
OPCAO_PROMESSA = "promessa"
OPCAO_PESSOA = "pessoa"
OPCAO_DEVOLVER = "devolver"

# Motivos que uma pessoa escolhe ao mandar para "Precisa de atencao" (os de baixa e de
# limite sao gerados pelo sistema).
MOTIVOS_PESSOA_MANUAL = {k: v for k, v in MOTIVOS_PESSOA.items() if k in ("cliente_respondeu", "sem_canal", "outro")}

BOTAO_CONFIRMAR = {
    OPCAO_RECEBIDO: "Dar baixa",
    OPCAO_PROBLEMA: "Registrar problema",
    OPCAO_NAO_CHEGOU: "Mandar para cobrança",
    OPCAO_PROMESSA: "Registrar promessa",
    OPCAO_PESSOA: "Mandar para uma pessoa",
    OPCAO_DEVOLVER: "Devolver para o Claude",
}


class OptionCard(QFrame):
    """Cartao clicavel com um radio, uma explicacao e campos extras que so aparecem quando
    o cartao esta escolhido."""

    def __init__(self, title: str, description: str, extra: QWidget | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("OptionCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        self.radio = QRadioButton(title)
        self.radio.setStyleSheet("font-weight: 600; background: transparent;")
        layout.addWidget(self.radio)
        self.description = QLabel(description)
        self.description.setObjectName("Muted")
        self.description.setWordWrap(True)
        self.description.setContentsMargins(24, 0, 0, 0)
        layout.addWidget(self.description)
        self.extra = extra
        if extra is not None:
            extra.setContentsMargins(24, 6, 0, 0)
            layout.addWidget(extra)
            extra.setVisible(False)
        self.radio.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked: bool) -> None:
        self.setProperty("selected", "true" if checked else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        if self.extra is not None:
            self.extra.setVisible(checked)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.radio.setChecked(True)
        super().mousePressEvent(event)


class ResolverDialog(QDialog):
    """itens: dicts com documento_id, periodo_id, nome_documento, competencia e empresa.
    permitir_devolver: mostra a opcao "Devolver para o Claude" (casos que estao com uma
    pessoa). opcao_inicial: qual cartao ja vem marcado."""

    def __init__(
        self,
        services,
        itens: list[dict],
        *,
        permitir_devolver: bool = False,
        opcao_inicial: str | None = None,
        pasta_inicial: str | None = None,
        arquivo_inicial: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.services = services
        self.itens = itens
        self.pasta_inicial = pasta_inicial
        self.resultado: str | None = None
        self.setWindowTitle(f"{APP_NAME} - Resolver documento")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(640, 800)

        regras = services.collection_service.get_followup_rules()
        t = tokens()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        titulo = QLabel("Resolver documento" if len(itens) == 1 else f"Resolver {len(itens)} documentos")
        titulo.setStyleSheet("font-size: 14pt; font-weight: 700;")
        layout.addWidget(titulo)
        lista = "<br>".join(
            f'<b>{escape(i["nome_documento"])}</b> ({i["competencia"]}) '
            f'<span style="color:{t["muted"]};">- {escape(i.get("empresa") or "")}</span>'
            for i in itens[:6]
        )
        if len(itens) > 6:
            lista += f"<br>... e mais {len(itens) - 6}"
        alvo = QLabel(lista)
        alvo.setWordWrap(True)
        layout.addWidget(alvo)

        pergunta = QLabel("O que aconteceu?")
        pergunta.setStyleSheet("font-weight: 600; margin-top: 4px;")
        layout.addWidget(pergunta)

        # Campos extras de cada opcao.
        self.problema_combo = QComboBox()
        for key, label in MOTIVOS_PROBLEMA.items():
            self.problema_combo.addItem(label, key)
        problema_extra = self._row("O que está errado", self.problema_combo)

        self.promessa_date = QDateEdit()
        self.promessa_date.setCalendarPopup(True)
        self.promessa_date.setDisplayFormat("dd/MM/yyyy")
        sugestao = date.today() + timedelta(days=max(regras["dias_entre_cobrancas"], 1))
        self.promessa_date.setDate(QDate(sugestao.year, sugestao.month, sugestao.day))
        self.promessa_date.setMinimumDate(QDate.currentDate())
        promessa_extra = self._row("Aguardar até", self.promessa_date)

        self.pessoa_combo = QComboBox()
        for key, label in MOTIVOS_PESSOA_MANUAL.items():
            self.pessoa_combo.addItem(label, key)
        pessoa_extra = self._row("Motivo", self.pessoa_combo)

        problema_destino = (
            "O caso vai para Precisa de atenção para alguém decidir."
            if regras["problema_vai_para_pessoa"]
            else "O documento volta para a fila de cobrança, pedindo o certo."
        )
        opcoes = [
            (OPCAO_RECEBIDO, "Chegou e está certo", "Marca como Recebido (dá baixa). Anexe o arquivo se tiver.", None),
            (OPCAO_PROBLEMA, "Chegou, mas está errado", f"Fica anotado o que veio errado. {problema_destino}", problema_extra),
            (OPCAO_NAO_CHEGOU, "Não chegou", "Você procurou e não está lá. O documento vai para a fila de cobrança.", None),
            (OPCAO_PROMESSA, "O cliente prometeu enviar", "Não cobra de novo até a data. Depois, volta a ser verificado.", promessa_extra),
            (OPCAO_PESSOA, "Precisa de uma pessoa", "Tira do fluxo do Claude e coloca em Precisa de atenção.", pessoa_extra),
        ]
        if permitir_devolver:
            opcoes.append(
                (
                    OPCAO_DEVOLVER,
                    "Devolver para o Claude",
                    "O que travava foi resolvido. O documento volta a ser verificado e cobrado normalmente.",
                    None,
                )
            )

        cards_widget = QWidget()
        cards_layout = QVBoxLayout(cards_widget)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(6)
        self.group = QButtonGroup(self)
        self.cards: dict[str, OptionCard] = {}
        for key, title, description, extra in opcoes:
            card = OptionCard(title, description, extra)
            self.group.addButton(card.radio)
            card.radio.toggled.connect(lambda checked, k=key: checked and self._on_option(k))
            self.cards[key] = card
            cards_layout.addWidget(card)
        cards_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(cards_widget)
        layout.addWidget(scroll, 1)

        form = QFormLayout()
        form.setSpacing(8)
        self.arquivo_row = QWidget()
        arquivo_layout = QHBoxLayout(self.arquivo_row)
        arquivo_layout.setContentsMargins(0, 0, 0, 0)
        self.arquivo_edit = QLineEdit(arquivo_inicial or "")
        self.arquivo_edit.setPlaceholderText("Opcional: onde o documento está salvo")
        arquivo_layout.addWidget(self.arquivo_edit, 1)
        procurar = make_button("Procurar...")
        procurar.clicked.connect(self._procurar_arquivo)
        arquivo_layout.addWidget(procurar)
        self.arquivo_label = QLabel("Arquivo")
        form.addRow(self.arquivo_label, self.arquivo_row)
        self.observacao_edit = QPlainTextEdit()
        self.observacao_edit.setPlaceholderText("Opcional: o que você viu, combinou ou fez. Fica no histórico do documento.")
        self.observacao_edit.setMaximumHeight(80)
        form.addRow("Observação", self.observacao_edit)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancelar = make_button("Cancelar", "quiet")
        cancelar.clicked.connect(self.reject)
        buttons.addWidget(cancelar)
        self.confirmar = make_button("Confirmar", "primary")
        self.confirmar.clicked.connect(self._confirmar)
        buttons.addWidget(self.confirmar)
        layout.addLayout(buttons)

        inicial = opcao_inicial if opcao_inicial in self.cards else None
        if inicial:
            self.cards[inicial].radio.setChecked(True)
        else:
            self._on_option(None)

    @staticmethod
    def _row(label: str, widget: QWidget) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(label))
        layout.addWidget(widget, 1)
        return row

    def _opcao(self) -> str | None:
        return next((k for k, c in self.cards.items() if c.radio.isChecked()), None)

    def _on_option(self, key: str | None) -> None:
        com_arquivo = key in (OPCAO_RECEBIDO, OPCAO_PROBLEMA)
        self.arquivo_row.setVisible(com_arquivo)
        self.arquivo_label.setVisible(com_arquivo)
        self.confirmar.setEnabled(key is not None)
        self.confirmar.setText(BOTAO_CONFIRMAR.get(key, "Confirmar"))

    def _procurar_arquivo(self) -> None:
        inicio = self.arquivo_edit.text() or self.pasta_inicial or ""
        caminho, _ = QFileDialog.getOpenFileName(self, "Escolher o arquivo do documento", inicio)
        if caminho:
            self.arquivo_edit.setText(caminho)

    def _confirmar(self) -> None:
        opcao = self._opcao()
        if opcao is None:
            return
        pares = [(i["documento_id"], i["periodo_id"]) for i in self.itens]
        observacao = self.observacao_edit.toPlainText().strip() or None
        arquivo = self.arquivo_edit.text().strip() or None
        service = self.services.cobranca_service
        try:
            if opcao in (OPCAO_RECEBIDO, OPCAO_PROBLEMA, OPCAO_NAO_CHEGOU):
                service.resolver_manual(
                    pares,
                    opcao,
                    motivo=self.problema_combo.currentData() if opcao == OPCAO_PROBLEMA else None,
                    arquivo=arquivo if opcao != OPCAO_NAO_CHEGOU else None,
                    observacao=observacao,
                )
            elif opcao == OPCAO_PROMESSA:
                prazo = self.promessa_date.date().toPython()
                service.registrar_promessa(pares, prazo.isoformat(), observacao)
            elif opcao == OPCAO_PESSOA:
                service.encaminhar_para_pessoa(pares, self.pessoa_combo.currentData(), observacao)
            else:
                service.devolver_para_fluxo(pares, observacao)
        except ValidationError as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))
            return
        self.resultado = opcao
        self.accept()
