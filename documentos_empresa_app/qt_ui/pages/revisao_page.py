from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.dialogs.agent_chat_dialog import AgentChatDialog
from documentos_empresa_app.qt_ui.widgets.common import Card, PageHeader, make_button
from documentos_empresa_app.qt_ui.widgets.company_selector import CompanySelector
from documentos_empresa_app.utils.common import ValidationError
from documentos_empresa_app.utils.document_agent_diagnostics import get_document_agent_log_path
from documentos_empresa_app.utils.helpers import open_file_in_default_app

ORIGEM_LABELS = {
    "regex_cnpj": "CNPJ local",
    "llm": "IA (Haiku)",
    "nenhuma": "Sem sugestao",
}


class _ClassificationWorker(QObject):
    """Classifica arquivos em thread de fundo — sem acesso a banco."""

    finished = Signal(list)
    failed = Signal(str)
    progress = Signal(int, int)

    def __init__(self, service, files, cnpj_index, known_names) -> None:
        super().__init__()
        self.service = service
        self.files = files
        self.cnpj_index = cnpj_index
        self.known_names = known_names

    def run(self) -> None:
        results = []
        try:
            for position, file_path in enumerate(self.files, start=1):
                if QThread.currentThread().isInterruptionRequested():
                    return
                results.append(self.service.classify_file(file_path, self.cnpj_index, self.known_names))
                self.progress.emit(position, len(self.files))
        except Exception as exc:  # pragma: no cover - salvaguarda da thread
            self.failed.emit(str(exc))
            return
        self.finished.emit(results)


class RevisaoPage(QWidget):
    def __init__(self, services, on_data_changed, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.on_data_changed = on_data_changed
        self.pendentes_by_id: dict[int, dict] = {}
        self._chosen_target_folder: str | None = None
        self._worker_thread: QThread | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        layout.addWidget(
            PageHeader(
                "Revisao de Documentos",
                "O agente le os arquivos da pasta de entrada, identifica a empresa pelo CNPJ e move "
                "automaticamente; o que nao for identificado fica aqui para revisao manual.",
            )
        )

        inbox_card = Card()
        inbox_layout = QHBoxLayout(inbox_card)
        inbox_layout.setContentsMargins(18, 14, 18, 14)
        inbox_layout.setSpacing(8)
        layout.addWidget(inbox_card)

        inbox_layout.addWidget(QLabel("Pasta de entrada:"))
        self.inbox_edit = QLineEdit(self.services.user_service.get_own_inbox_folder() or "")
        self.inbox_edit.setReadOnly(True)
        inbox_layout.addWidget(self.inbox_edit, 1)
        self.choose_inbox_button = make_button("Escolher pasta...")
        self.choose_inbox_button.clicked.connect(self.choose_inbox_folder)
        inbox_layout.addWidget(self.choose_inbox_button)
        self.process_button = make_button("Processar novos documentos", "primary")
        self.process_button.clicked.connect(self.process_new_documents)
        inbox_layout.addWidget(self.process_button)
        self.diagnostics_button = make_button("Ver log de diagnostico")
        self.diagnostics_button.setToolTip(
            "Abre o log tecnico das camadas sem IA (extracao de texto e casamento por CNPJ) - "
            "util para revisar padroes de falha e ajustar o codigo depois."
        )
        self.diagnostics_button.clicked.connect(self.open_diagnostics_log)
        inbox_layout.addWidget(self.diagnostics_button)

        self.status_label = QLabel("Pronto para processar.")
        self.status_label.setObjectName("Muted")
        layout.addWidget(self.status_label)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["Arquivo", "CNPJ extraido", "Empresa sugerida", "Tipo", "Confianca", "Origem", "Motivo", "Criado em"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 220)
        for col in (1, 2, 3, 4, 5, 7):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table, 1)

        resolve_card = Card()
        resolve_layout = QHBoxLayout(resolve_card)
        resolve_layout.setContentsMargins(18, 14, 18, 14)
        resolve_layout.setSpacing(14)
        layout.addWidget(resolve_card)

        self.company_selector = CompanySelector(
            self.services.empresa_service, active_only=True, title="Empresa de destino"
        )
        resolve_layout.addWidget(self.company_selector, 1)

        folder_block = QVBoxLayout()
        self.target_folder_label = QLabel("Nenhuma pasta escolhida.")
        self.target_folder_label.setObjectName("Muted")
        self.target_folder_label.setWordWrap(True)
        folder_block.addWidget(self.target_folder_label)
        self.choose_target_button = make_button("Escolher pasta...")
        self.choose_target_button.clicked.connect(self.choose_target_folder)
        folder_block.addWidget(self.choose_target_button)
        folder_block.addStretch(1)
        resolve_layout.addLayout(folder_block)

        action_block = QVBoxLayout()
        self.confirm_button = make_button("Confirmar", "primary")
        self.confirm_button.clicked.connect(self.confirm_selected)
        action_block.addWidget(self.confirm_button)
        self.ask_agent_button = make_button("Perguntar ao agente")
        self.ask_agent_button.clicked.connect(self.ask_agent)
        action_block.addWidget(self.ask_agent_button)
        self.ignore_button = make_button("Ignorar", "danger")
        self.ignore_button.clicked.connect(self.ignore_selected)
        action_block.addWidget(self.ignore_button)
        action_block.addStretch(1)
        resolve_layout.addLayout(action_block)

        self._set_resolution_enabled(False)

    def refresh_data(self) -> None:
        self.inbox_edit.setText(self.services.user_service.get_own_inbox_folder() or "")
        self.company_selector.refresh_companies()
        self.table.setRowCount(0)
        self.pendentes_by_id = {}

        for pendente in self.services.document_agent_service.list_pendentes():
            self.pendentes_by_id[pendente["id"]] = pendente
            row = self.table.rowCount()
            self.table.insertRow(row)
            confianca = pendente.get("confianca_sugestao")
            values = (
                pendente["nome_arquivo"],
                pendente.get("cnpj_extraido") or "-",
                pendente.get("empresa_sugerida_nome") or "-",
                pendente.get("tipo_documento_sugerido") or "-",
                f"{confianca:.0%}" if confianca is not None else "-",
                ORIGEM_LABELS.get(pendente.get("origem_sugestao"), pendente.get("origem_sugestao") or "-"),
                pendente.get("motivo") or "-",
                pendente.get("criado_em") or "-",
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, pendente["id"])
                if col == 6:
                    item.setToolTip(str(value))
                self.table.setItem(row, col, item)

        self._chosen_target_folder = None
        self.target_folder_label.setText("Nenhuma pasta escolhida.")
        self._set_resolution_enabled(False)

    def choose_inbox_folder(self) -> None:
        current = self.inbox_edit.text().strip()
        initial = current if current and Path(current).is_dir() else str(Path.home())
        selected = QFileDialog.getExistingDirectory(self, "Escolha a pasta de entrada dos documentos", initial)
        if not selected:
            return
        self.inbox_edit.setText(selected)
        self.services.user_service.set_own_inbox_folder(selected)

    def open_diagnostics_log(self) -> None:
        log_path = get_document_agent_log_path()
        if not log_path.exists():
            QMessageBox.information(
                self,
                "Revisao de documentos",
                "Nenhum log de diagnostico foi gerado ainda - ele so registra quando alguma camada "
                "sem IA (extracao de texto ou casamento por CNPJ) nao consegue organizar um documento.",
            )
            return
        try:
            open_file_in_default_app(log_path)
        except ValidationError as exc:
            QMessageBox.critical(self, "Revisao de documentos", str(exc))

    def process_new_documents(self) -> None:
        inbox_folder = self.inbox_edit.text().strip()
        if not inbox_folder or not Path(inbox_folder).is_dir():
            QMessageBox.warning(self, "Revisao de documentos", "Escolha uma pasta de entrada valida antes de processar.")
            return

        service = self.services.document_agent_service
        files = service.scan_folder(inbox_folder)
        if not files:
            self.status_label.setText("Nenhum documento novo encontrado na pasta de entrada.")
            return

        cnpj_index = service.build_cnpj_index()
        known_names = service.build_known_company_names()

        self.process_button.setEnabled(False)
        self.choose_inbox_button.setEnabled(False)
        self.status_label.setText(f"Processando {len(files)} documento(s)...")

        self._worker_thread = QThread(self)
        self._worker = _ClassificationWorker(service, files, cnpj_index, known_names)
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.progress.connect(
            lambda done, total: self.status_label.setText(f"Processando documento {done} de {total}...")
        )
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.failed.connect(self._on_worker_failed)
        self._worker.finished.connect(self._worker_thread.quit)
        self._worker.failed.connect(self._worker_thread.quit)
        self._worker_thread.finished.connect(self._worker.deleteLater)
        self._worker_thread.start()

    def shutdown(self) -> None:
        """Aguarda a thread de classificacao antes da janela fechar — destruir
        um QThread em execucao aborta o processo inteiro."""
        if self._worker_thread is not None and self._worker_thread.isRunning():
            self._worker_thread.requestInterruption()
            self._worker_thread.quit()
            self._worker_thread.wait(15000)

    def _on_worker_failed(self, message: str) -> None:
        self.process_button.setEnabled(True)
        self.choose_inbox_button.setEnabled(True)
        self.status_label.setText("Falha ao processar documentos.")
        QMessageBox.critical(self, "Revisao de documentos", f"Falha ao processar documentos: {message}")

    def _on_worker_finished(self, results: list) -> None:
        self.process_button.setEnabled(True)
        self.choose_inbox_button.setEnabled(True)

        service = self.services.document_agent_service
        moved = pending = errors = 0
        for file_path, classification_result, extraction_error in results:
            outcome = service.apply_result(file_path, classification_result, extraction_error)
            if outcome.outcome == "movido":
                moved += 1
            elif outcome.outcome == "erro":
                errors += 1
            else:
                pending += 1

        self.status_label.setText(
            f"{len(results)} documento(s) processados: {moved} movido(s), {pending} para revisao, {errors} com erro."
        )
        self.on_data_changed()

    def _on_selection_changed(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            self._set_resolution_enabled(False)
            return

        item = self.table.item(rows[0].row(), 0)
        pendente = self.pendentes_by_id.get(int(item.data(Qt.ItemDataRole.UserRole))) if item else None
        self._set_resolution_enabled(True)
        self._chosen_target_folder = None
        self.target_folder_label.setText("Nenhuma pasta escolhida.")
        if pendente and pendente.get("empresa_sugerida_id"):
            self.company_selector.set_company(pendente["empresa_sugerida_id"])
        else:
            self.company_selector.clear_selection()

    def choose_target_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Escolha a pasta de destino do documento")
        if not selected:
            return
        self._chosen_target_folder = selected
        self.target_folder_label.setText(selected)

    def _selected_pendente_id(self) -> int | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        return int(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def confirm_selected(self) -> None:
        pendente_id = self._selected_pendente_id()
        if pendente_id is None:
            return
        empresa_id = self.company_selector.get_selected_company_id()
        if not empresa_id:
            QMessageBox.warning(self, "Revisao de documentos", "Selecione a empresa de destino.")
            return

        try:
            self.services.document_agent_service.resolve_pending_document(
                pendente_id, empresa_id, diretorio_documentos=self._chosen_target_folder
            )
        except ValidationError as exc:
            QMessageBox.critical(self, "Revisao de documentos", str(exc))
            return

        QMessageBox.information(self, "Revisao de documentos", "Documento confirmado e movido com sucesso.")
        self.on_data_changed()

    def ignore_selected(self) -> None:
        pendente_id = self._selected_pendente_id()
        if pendente_id is None:
            return
        answer = QMessageBox.question(
            self,
            "Revisao de documentos",
            "Deseja ignorar este documento? Ele sai da fila de revisao sem ser movido.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self.services.document_agent_service.ignore_pending_document(pendente_id)
        except ValidationError as exc:
            QMessageBox.critical(self, "Revisao de documentos", str(exc))
            return

        self.on_data_changed()

    def ask_agent(self) -> None:
        pendente_id = self._selected_pendente_id()
        if pendente_id is None:
            return
        pendente = self.pendentes_by_id.get(pendente_id)
        if not pendente:
            return
        AgentChatDialog(self.services, pendente, self).exec()

    def _set_resolution_enabled(self, enabled: bool) -> None:
        self.choose_target_button.setEnabled(enabled)
        self.confirm_button.setEnabled(enabled)
        self.ask_agent_button.setEnabled(enabled)
        self.ignore_button.setEnabled(enabled)
