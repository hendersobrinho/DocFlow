from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.icons import app_icon
from documentos_empresa_app.qt_ui.widgets.common import make_button
from documentos_empresa_app.services.document_extraction_service import DocumentExtractionError
from documentos_empresa_app.services.llm_types import LLMChatError
from documentos_empresa_app.utils.common import APP_NAME


class AgentChatDialog(QDialog):
    def __init__(self, services, pendente: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.pendente = pendente
        self.history: list[dict] = []

        self.setWindowTitle(f'{APP_NAME} - Chat sobre "{pendente["nome_arquivo"]}"')
        self.setWindowIcon(app_icon())
        self.resize(560, 620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        header = QLabel(f'Documento: {pendente["nome_arquivo"]}')
        header.setObjectName("Muted")
        header.setWordWrap(True)
        layout.addWidget(header)

        self.transcript = QTextEdit()
        self.transcript.setReadOnly(True)
        layout.addWidget(self.transcript, 1)

        input_row = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.returnPressed.connect(self.send_message)
        input_row.addWidget(self.input_edit, 1)
        self.send_button = make_button("Enviar", "primary")
        self.send_button.clicked.connect(self.send_message)
        input_row.addWidget(self.send_button)
        layout.addLayout(input_row)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_button = make_button("Fechar", "quiet")
        close_button.clicked.connect(self.accept)
        close_row.addWidget(close_button)
        layout.addLayout(close_row)

        self.document_text = self._load_document_text()
        self._prepare_chat_state()

    def _load_document_text(self) -> str:
        try:
            extraction_service = self.services.document_agent_service.extraction_service
            return extraction_service.extract_text(Path(self.pendente["caminho_arquivo_original"]))
        except (DocumentExtractionError, OSError) as exc:
            self._append_system_message(f"Nao foi possivel ler o texto do documento: {exc}")
            return ""

    def _prepare_chat_state(self) -> None:
        if self.services.document_chat_service is None:
            self._append_system_message(
                "Chat com IA nao configurado. Peca a um administrador para definir a API key da "
                "Anthropic na tela de Configuracoes."
            )
            self.input_edit.setEnabled(False)
            self.send_button.setEnabled(False)
            return
        self._append_system_message("Pergunte o que quiser sobre este documento.")

    def send_message(self) -> None:
        user_message = self.input_edit.text().strip()
        if not user_message or self.services.document_chat_service is None:
            return

        self.input_edit.setEnabled(False)
        self.send_button.setEnabled(False)
        self._append_message("Voce", user_message)
        self.input_edit.clear()

        try:
            reply = self.services.document_chat_service.send_message(
                self.document_text, self.history, user_message
            )
        except LLMChatError as exc:
            self._append_system_message(str(exc))
            self.input_edit.setEnabled(True)
            self.send_button.setEnabled(True)
            return

        self.history.append({"role": "user", "content": user_message})
        self.history.append({"role": "assistant", "content": reply})
        self._append_message("Agente", reply)
        self.input_edit.setEnabled(True)
        self.send_button.setEnabled(True)
        self.input_edit.setFocus()

    def _append_message(self, author: str, text: str) -> None:
        self.transcript.append(f"<b>{html.escape(author)}:</b> {html.escape(text)}")

    def _append_system_message(self, text: str) -> None:
        self.transcript.append(f"<i>{html.escape(text)}</i>")
