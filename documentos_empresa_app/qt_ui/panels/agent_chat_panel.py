from __future__ import annotations

from pathlib import Path
import shutil
from typing import Callable

from PySide6.QtCore import QThread
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.icons import agent_chat_icon
from documentos_empresa_app.qt_ui.widgets.chat_bubble import ChatTranscript
from documentos_empresa_app.qt_ui.widgets.common import make_button
from documentos_empresa_app.qt_ui.workers import CallableWorker
from documentos_empresa_app.qt_ui.dialogs.organize_confirmation_dialog import (
    OrganizeConfirmationDialog,
    apply_confirmation_overrides,
)
from documentos_empresa_app.services.document_extraction_service import DocumentExtractionError
from documentos_empresa_app.services.document_organizer_service import OrganizeNeedsInput
from documentos_empresa_app.services.llm_types import (
    ChatReply,
    ProposedCadastrarDocumento,
    ProposedDarBaixa,
    ProposedFileCopy,
    ProposedOrganize,
)
from documentos_empresa_app.utils.common import AGENT_NAME, APP_NAME, ValidationError
from documentos_empresa_app.utils.file_naming import resolve_unique_path


class AgentChatPanel(QWidget):
    """Painel fixo (dockado na janela principal) de chat com o agente de IA sobre um
    documento pendente. Uma unica instancia e reaproveitada entre documentos - ver
    `open_for_pendente`."""

    def __init__(self, services, on_action_completed, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.on_action_completed = on_action_completed
        self.pendente: dict | None = None
        self.empresa_id: int | None = None
        self.diretorio_documentos_override: str | None = None
        self.history: list[dict] = []
        self.document_text: str = ""
        self.registered_documents: list[dict] = []
        self.tipos_catalog: list[dict] = []
        self._chat_run_token: int = 0
        self._llm_thread: QThread | None = None
        self._llm_worker: CallableWorker | None = None
        self._llm_run_token: int = 0
        self._llm_success_callback: Callable[[object], None] | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.header_label = QLabel(
            f"Selecione um documento na tela de Revisao para conversar com o {AGENT_NAME}."
        )
        self.header_label.setObjectName("Muted")
        self.header_label.setWordWrap(True)
        layout.addWidget(self.header_label)

        self.transcript = ChatTranscript()
        layout.addWidget(self.transcript, 1)

        input_row = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.returnPressed.connect(self.send_message)
        input_row.addWidget(self.input_edit, 1)
        self.send_button = make_button("Enviar", "primary")
        self.send_button.clicked.connect(self.send_message)
        input_row.addWidget(self.send_button)
        layout.addLayout(input_row)

        self.input_edit.setEnabled(False)
        self.send_button.setEnabled(False)

    def open_for_pendente(
        self,
        pendente: dict,
        empresa_id: int | None = None,
        diretorio_documentos: str | None = None,
    ) -> None:
        self._chat_run_token += 1
        self.pendente = pendente
        self.empresa_id = empresa_id
        self.diretorio_documentos_override = diretorio_documentos
        self.history = []
        self.transcript.clear()
        self.header_label.setText(f'Documento: {pendente["nome_arquivo"]}')
        self.input_edit.clear()

        self.document_text = self._load_document_text()
        self.registered_documents, self.tipos_catalog = self._load_chat_catalogs()
        self._prepare_chat_state()

    def _load_chat_catalogs(self) -> tuple[list[dict], list[dict]]:
        empresa_id = self._resolve_target_empresa_id()
        registered_documents: list[dict] = []
        if empresa_id is not None:
            try:
                registered_documents = self.services.documento_service.list_documentos_empresa(empresa_id)
            except ValidationError:
                registered_documents = []
        tipos_catalog = self.services.tipo_service.list_tipos()
        return registered_documents, tipos_catalog

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
        self.input_edit.setEnabled(True)
        self.send_button.setEnabled(True)
        self._append_system_message(f"Pergunte o que quiser ao {AGENT_NAME} sobre este documento.")

    def send_message(self) -> None:
        user_message = self.input_edit.text().strip()
        if not user_message or self.services.document_chat_service is None:
            return

        self._append_message("Voce", user_message)
        self.input_edit.clear()

        service = self.services.document_chat_service
        history = self.history
        registered_documents = self.registered_documents
        tipos_catalog = self.tipos_catalog
        document_text = self.document_text
        self._run_llm_call(
            lambda: service.send_message(document_text, history, user_message, registered_documents, tipos_catalog),
            self._handle_reply,
        )

    def _run_llm_call(self, func: Callable[[], object], on_success: Callable[[object], None]) -> None:
        """Roda uma chamada a IA (inicial ou de follow-up) numa QThread de fundo, mostrando
        a logo girando enquanto espera - se rodasse direto na thread da UI a chamada de
        rede travaria a janela inteira e o spinner nunca teria chance de animar."""
        self._llm_run_token = self._chat_run_token
        self._llm_success_callback = on_success
        self.input_edit.setEnabled(False)
        self.send_button.setEnabled(False)
        self.transcript.show_thinking(agent_chat_icon(), f"{AGENT_NAME} esta pensando...")

        self._llm_thread = QThread(self)
        self._llm_worker = CallableWorker(func)
        self._llm_worker.moveToThread(self._llm_thread)
        self._llm_thread.started.connect(self._llm_worker.run)
        self._llm_worker.finished.connect(self._on_llm_finished)
        self._llm_worker.failed.connect(self._on_llm_failed)
        self._llm_worker.finished.connect(self._llm_thread.quit)
        self._llm_worker.failed.connect(self._llm_thread.quit)
        self._llm_thread.finished.connect(self._llm_worker.deleteLater)
        self._llm_thread.start()

    def _on_llm_finished(self, result: object) -> None:
        callback = self._llm_success_callback
        self._llm_success_callback = None
        stale = self._llm_run_token != self._chat_run_token
        self.transcript.hide_thinking()
        if stale or callback is None:
            return
        callback(result)

    def shutdown(self) -> None:
        """Aguarda a chamada de IA em andamento antes da janela fechar - destruir uma
        QThread em execucao aborta o processo inteiro (mesmo cuidado do RevisaoPage)."""
        if self._llm_thread is not None and self._llm_thread.isRunning():
            self._llm_thread.quit()
            self._llm_thread.wait(15000)

    def _on_llm_failed(self, message: str) -> None:
        self._llm_success_callback = None
        stale = self._llm_run_token != self._chat_run_token
        self.transcript.hide_thinking()
        if stale:
            return
        self._append_system_message(message)
        self.input_edit.setEnabled(True)
        self.send_button.setEnabled(True)
        self.input_edit.setFocus()

    def _handle_reply(self, reply: ChatReply) -> None:
        if reply.text:
            self._append_message("Agente", reply.text)

        if reply.proposed_copy is not None:
            self._confirm_and_execute_copy(reply.proposed_copy)
            return

        if reply.proposed_organize is not None:
            self._confirm_and_execute_organize(reply.proposed_organize)
            return

        if reply.proposed_cadastrar_documento is not None:
            self._confirm_and_execute_cadastrar_documento(reply.proposed_cadastrar_documento)
            return

        if reply.proposed_dar_baixa is not None:
            self._confirm_and_execute_dar_baixa(reply.proposed_dar_baixa)
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

        self.on_action_completed()
        self._follow_up(self.services.document_chat_service.resolve_proposed_copy, proposed_copy, result_message)

    def _resolve_target_empresa_id(self) -> int | None:
        if self.empresa_id is not None:
            return self.empresa_id
        if self.pendente is None:
            return None
        return self.pendente.get("empresa_sugerida_id")

    def _confirm_and_execute_organize(self, proposed_organize: ProposedOrganize) -> None:
        resolve = self.services.document_chat_service.resolve_proposed_organize
        empresa_id = self._resolve_target_empresa_id()
        if empresa_id is None:
            result_message = (
                "Nao sei para qual empresa organizar este documento - selecione a empresa "
                "sugerida na tela de Revisao antes de pedir para organizar."
            )
            self._append_system_message(result_message)
            self.on_action_completed()
            self._follow_up(resolve, proposed_organize, result_message)
            return

        documento_empresa = next(
            (doc for doc in self.registered_documents if doc["id"] == proposed_organize.documento_empresa_id), None
        )

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
                documento_empresa=documento_empresa,
            )
        except ValidationError as exc:
            result_message = str(exc)
            self._append_system_message(result_message)
            self.on_action_completed()
            self._follow_up(resolve, proposed_organize, result_message)
            return

        if isinstance(proposal, OrganizeNeedsInput):
            self._append_system_message(proposal.message)
            self.on_action_completed()
            self._follow_up(resolve, proposed_organize, proposal.message)
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

        self.on_action_completed()
        self._follow_up(resolve, proposed_organize, result_message)

    def _confirm_and_execute_cadastrar_documento(self, proposed: ProposedCadastrarDocumento) -> None:
        resolve = self.services.document_chat_service.resolve_proposed_cadastrar_documento
        empresa_id = self._resolve_target_empresa_id()
        if empresa_id is None:
            result_message = (
                "Nao sei para qual empresa cadastrar este documento - selecione a empresa "
                "sugerida na tela de Revisao antes de pedir para cadastrar."
            )
            self._append_system_message(result_message)
            self.on_action_completed()
            self._follow_up(resolve, proposed, result_message)
            return

        tipo = self.services.tipo_service.find_tipo_by_name(proposed.nome_tipo)
        if tipo is None and not proposed.regra_ocorrencia_novo_tipo:
            result_message = (
                f'Nao encontrei o tipo/categoria "{proposed.nome_tipo}" cadastrado. Para criar um '
                "tipo novo preciso saber a regra de ocorrencia (mensal, trimestral ou anual em "
                "janeiro) - pergunte ao usuario qual regra usar e proponha de novo."
            )
            self._append_system_message(result_message)
            self.on_action_completed()
            self._follow_up(resolve, proposed, result_message)
            return

        empresa = self.services.empresa_service.get_empresa(empresa_id)
        if tipo is None:
            confirm_text = (
                f'A IA quer cadastrar o documento "{proposed.nome_documento}" para '
                f'"{empresa["nome_empresa"]}", criando tambem um novo tipo/categoria '
                f'"{proposed.nome_tipo}" com ocorrencia {proposed.regra_ocorrencia_novo_tipo}.'
                "\n\nConfirma o cadastro?"
            )
        else:
            confirm_text = (
                f'A IA quer cadastrar o documento "{proposed.nome_documento}" para '
                f'"{empresa["nome_empresa"]}" no tipo "{tipo["nome_tipo"]}".\n\nConfirma o cadastro?'
            )
        confirmed = QMessageBox.question(self, APP_NAME, confirm_text) == QMessageBox.StandardButton.Yes

        if not confirmed:
            result_message = "O usuario cancelou o cadastro do documento."
            self._append_system_message("Cadastro cancelado.")
        else:
            try:
                if tipo is None:
                    tipo = self.services.tipo_service.get_or_create_tipo(
                        proposed.nome_tipo, proposed.regra_ocorrencia_novo_tipo
                    )
                self.services.documento_service.create_documento(
                    empresa_id, tipo["id"], proposed.nome_documento, proposed.meios_recebimento
                )
            except ValidationError as exc:
                result_message = f"Falha ao cadastrar o documento: {exc}"
                self._append_system_message(result_message)
            else:
                result_message = f'Documento "{proposed.nome_documento}" cadastrado com sucesso.'
                self._append_system_message(result_message)
                self.registered_documents = self.services.documento_service.list_documentos_empresa(empresa_id)

        self.on_action_completed()
        self._follow_up(resolve, proposed, result_message)

    def _confirm_and_execute_dar_baixa(self, proposed: ProposedDarBaixa) -> None:
        resolve = self.services.document_chat_service.resolve_proposed_dar_baixa
        empresa_id = self._resolve_target_empresa_id()
        if empresa_id is None:
            result_message = (
                "Nao sei para qual empresa dar baixa neste documento - selecione a empresa "
                "sugerida na tela de Revisao antes de pedir para dar baixa."
            )
            self._append_system_message(result_message)
            self.on_action_completed()
            self._follow_up(resolve, proposed, result_message)
            return

        try:
            documento = self.services.documento_service.get_documento(proposed.documento_empresa_id)
        except ValidationError as exc:
            result_message = f"Falha ao dar baixa: {exc}"
            self._append_system_message(result_message)
            self.on_action_completed()
            self._follow_up(resolve, proposed, result_message)
            return

        if documento["empresa_id"] != empresa_id:
            result_message = "Esse documento nao pertence a empresa deste chat."
            self._append_system_message(result_message)
            self.on_action_completed()
            self._follow_up(resolve, proposed, result_message)
            return

        try:
            periodo = self.services.periodo_service.get_or_create_periodo(proposed.ano, proposed.mes)
        except ValidationError as exc:
            result_message = f"Falha ao dar baixa: {exc}"
            self._append_system_message(result_message)
            self.on_action_completed()
            self._follow_up(resolve, proposed, result_message)
            return

        status_label = proposed.status or "(vazio)"
        confirmed = (
            QMessageBox.question(
                self,
                APP_NAME,
                (
                    f'A IA quer definir o status do documento "{documento["nome_documento"]}" '
                    f'({documento["nome_tipo"]}) para a competencia {proposed.mes:02d}/{proposed.ano} '
                    f'como "{status_label}".\n\nConfirma?'
                ),
            )
            == QMessageBox.StandardButton.Yes
        )

        if not confirmed:
            result_message = "O usuario cancelou a alteracao de status."
            self._append_system_message("Alteracao de status cancelada.")
        else:
            try:
                self.services.status_service.update_status(documento["id"], periodo["id"], proposed.status)
            except ValidationError as exc:
                result_message = f"Falha ao dar baixa: {exc}"
                self._append_system_message(result_message)
            else:
                result_message = (
                    f'Status atualizado para "{status_label}" na competencia '
                    f"{proposed.mes:02d}/{proposed.ano}."
                )
                self._append_system_message(result_message)

        self.on_action_completed()
        self._follow_up(resolve, proposed, result_message)

    def _follow_up(self, resolve_method, proposed, result_message: str) -> None:
        document_text = self.document_text
        history = self.history
        registered_documents = self.registered_documents
        tipos_catalog = self.tipos_catalog
        self._run_llm_call(
            lambda: resolve_method(
                document_text, history, proposed, result_message, registered_documents, tipos_catalog
            ),
            self._on_follow_up_finished,
        )

    def _on_follow_up_finished(self, follow_up: ChatReply) -> None:
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
        if author == "Voce":
            self.transcript.add_user_message(text)
        else:
            self.transcript.add_agent_message(text)

    def _append_system_message(self, text: str) -> None:
        self.transcript.add_system_message(text)
