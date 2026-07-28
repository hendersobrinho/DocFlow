from __future__ import annotations

import html
from pathlib import Path
import shutil

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.icons import app_icon
from documentos_empresa_app.qt_ui.widgets.common import make_button
from documentos_empresa_app.qt_ui.dialogs.organize_confirmation_dialog import (
    OrganizeConfirmationDialog,
    apply_confirmation_overrides,
)
from documentos_empresa_app.services.document_extraction_service import DocumentExtractionError
from documentos_empresa_app.services.document_organizer_service import OrganizeNeedsInput
from documentos_empresa_app.services.llm_types import ChatReply, LLMChatError, ProposedFileCopy, ProposedOrganize
from documentos_empresa_app.utils.common import APP_NAME, ValidationError
from documentos_empresa_app.utils.file_naming import resolve_unique_path


class AgentChatDialog(QDialog):
    def __init__(
        self,
        services,
        pendente: dict,
        empresa_id: int | None = None,
        diretorio_documentos: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.services = services
        self.pendente = pendente
        self.empresa_id = empresa_id
        self.diretorio_documentos_override = diretorio_documentos
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

        self._handle_reply(reply)

    def _handle_reply(self, reply: ChatReply) -> None:
        if reply.text:
            self._append_message("Agente", reply.text)

        if reply.proposed_copy is not None:
            self._confirm_and_execute_copy(reply.proposed_copy)
            return

        if reply.proposed_organize is not None:
            self._confirm_and_execute_organize(reply.proposed_organize)
            return

        self.input_edit.setEnabled(True)
        self.send_button.setEnabled(True)
        self.input_edit.setFocus()

    def _confirm_and_execute_copy(self, proposed_copy: ProposedFileCopy) -> None:
        source = Path(self.pendente["caminho_arquivo_original"])
        destination_dir = Path(proposed_copy.destination_folder).expanduser()
        destination_name = proposed_copy.new_filename or source.name

        confirmed = (
            QMessageBox.question(
                self,
                APP_NAME,
                (
                    f'A IA quer copiar o arquivo "{source.name}" para:\n\n'
                    f"{destination_dir / destination_name}\n\nConfirma a copia?"
                ),
            )
            == QMessageBox.StandardButton.Yes
        )

        if not confirmed:
            result_message = "O usuario cancelou a copia do arquivo."
            self._append_system_message("Copia cancelada.")
        else:
            try:
                destino = self._copy_file(source, destination_dir, destination_name)
            except OSError as exc:
                result_message = f"Falha ao copiar o arquivo: {exc}"
                self._append_system_message(result_message)
            else:
                result_message = f"Arquivo copiado com sucesso para {destino}."
                self._append_system_message(f"Arquivo copiado para {destino}.")

        try:
            follow_up = self.services.document_chat_service.resolve_proposed_copy(
                self.document_text, self.history, proposed_copy, result_message
            )
        except LLMChatError as exc:
            self._append_system_message(str(exc))
        else:
            if follow_up.text:
                self._append_message("Agente", follow_up.text)

        self.input_edit.setEnabled(True)
        self.send_button.setEnabled(True)
        self.input_edit.setFocus()

    def _resolve_target_empresa_id(self) -> int | None:
        if self.empresa_id is not None:
            return self.empresa_id
        return self.pendente.get("empresa_sugerida_id")

    def _confirm_and_execute_organize(self, proposed_organize: ProposedOrganize) -> None:
        empresa_id = self._resolve_target_empresa_id()
        if empresa_id is None:
            result_message = (
                "Nao sei para qual empresa organizar este documento - selecione a empresa "
                "sugerida na tela de Revisao antes de pedir para organizar."
            )
            self._append_system_message(result_message)
            self._follow_up_organize(proposed_organize, result_message)
            return

        try:
            proposal = self.services.document_organizer_service.propose(
                self.pendente["id"],
                empresa_id,
                proposed_organize.mes,
                proposed_organize.ano,
                banco=proposed_organize.banco,
                tipo_conta=proposed_organize.tipo_conta,
                diretorio_documentos=self.diretorio_documentos_override,
                empresas_root_dir=self.services.user_service.get_own_empresas_root_folder(),
            )
        except ValidationError as exc:
            result_message = str(exc)
            self._append_system_message(result_message)
            self._follow_up_organize(proposed_organize, result_message)
            return

        if isinstance(proposal, OrganizeNeedsInput):
            self._append_system_message(proposal.message)
            self._follow_up_organize(proposed_organize, proposal.message)
            return

        dialog = OrganizeConfirmationDialog(
            documento_nome=self.pendente["nome_arquivo"],
            new_folders=proposal.new_folders,
            new_filename=proposal.new_filename,
            based_on_sibling=proposal.based_on_sibling,
            filename_is_synthesized=proposal.filename_is_synthesized,
            parent=self,
        )
        confirmed = dialog.exec() == QDialog.DialogCode.Accepted

        if not confirmed:
            result_message = "O usuario cancelou a organizacao do arquivo."
            self._append_system_message("Organizacao cancelada.")
        else:
            apply_confirmation_overrides(proposal, dialog)
            try:
                destino = self.services.document_organizer_service.execute(
                    self.pendente["id"], empresa_id, proposal
                )
            except ValidationError as exc:
                result_message = f"Falha ao organizar o arquivo: {exc}"
                self._append_system_message(result_message)
            else:
                result_message = f"Arquivo organizado com sucesso em {destino}."
                self._append_system_message(f"Arquivo organizado em {destino}.")

        self._follow_up_organize(proposed_organize, result_message)

    def _follow_up_organize(self, proposed_organize: ProposedOrganize, result_message: str) -> None:
        try:
            follow_up = self.services.document_chat_service.resolve_proposed_organize(
                self.document_text, self.history, proposed_organize, result_message
            )
        except LLMChatError as exc:
            self._append_system_message(str(exc))
        else:
            if follow_up.text:
                self._append_message("Agente", follow_up.text)

        self.input_edit.setEnabled(True)
        self.send_button.setEnabled(True)
        self.input_edit.setFocus()

    def _copy_file(self, source: Path, destination_dir: Path, filename: str) -> Path:
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination_path = resolve_unique_path(destination_dir, filename)
        shutil.copy2(source, destination_path)
        return destination_path

    def _append_message(self, author: str, text: str) -> None:
        self.transcript.append(f"<b>{html.escape(author)}:</b> {html.escape(text)}")

    def _append_system_message(self, text: str) -> None:
        self.transcript.append(f"<i>{html.escape(text)}</i>")
