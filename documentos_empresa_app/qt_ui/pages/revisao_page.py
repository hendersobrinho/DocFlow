from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
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

from documentos_empresa_app.qt_ui.dialogs.organize_confirmation_dialog import (
    OrganizeConfirmationDialog,
    apply_confirmation_overrides,
)
from documentos_empresa_app.qt_ui.widgets.common import Card, PageHeader, make_button
from documentos_empresa_app.qt_ui.widgets.company_selector import CompanySelector
from documentos_empresa_app.services.batch_organize_service import BatchOrganizeRow
from documentos_empresa_app.utils.common import ValidationError
from documentos_empresa_app.utils.document_agent_diagnostics import get_document_agent_log_path
from documentos_empresa_app.utils.helpers import open_file_in_default_app

ORIGEM_LABELS = {
    "regex_cnpj": "CNPJ local",
    "llm": "IA (Haiku)",
    "nenhuma": "Sem sugestao",
}

COL_CHECK = 0
COL_ARQUIVO = 1
COL_CNPJ = 2
COL_EMPRESA = 3
COL_TIPO = 4
COL_CONFIANCA = 5
COL_ORIGEM = 6
COL_MOTIVO = 7
COL_CRIADO_EM = 8
COL_COMPETENCIA = 9
COL_DESTINO = 10
COL_SITUACAO = 11
COL_EDITAR = 12


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


class _BatchOrganizeWorker(QObject):
    """Monta as propostas de organizacao em thread de fundo - chama IA e le arquivos do disco."""

    finished = Signal(list)
    failed = Signal(str)

    def __init__(self, service, pendentes: list[dict], empresas_root_dir: str | None) -> None:
        super().__init__()
        self.service = service
        self.pendentes = pendentes
        self.empresas_root_dir = empresas_root_dir

    def run(self) -> None:
        try:
            rows = self.service.build_rows(self.pendentes, empresas_root_dir=self.empresas_root_dir)
        except Exception as exc:  # pragma: no cover - salvaguarda da thread
            self.failed.emit(str(exc))
            return
        self.finished.emit(rows)


class RevisaoPage(QWidget):
    def __init__(self, services, on_data_changed, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.on_data_changed = on_data_changed
        self.pendentes_by_id: dict[int, dict] = {}
        self._chosen_target_folder: str | None = None
        self._classify_worker_thread: QThread | None = None
        self._batch_worker_thread: QThread | None = None
        self._batch_rows_by_pendente_id: dict[int, BatchOrganizeRow] = {}
        self._batch_run_token: int = 0

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

        root_card = Card()
        root_layout = QHBoxLayout(root_card)
        root_layout.setContentsMargins(18, 14, 18, 14)
        root_layout.setSpacing(8)
        layout.addWidget(root_card)

        root_layout.addWidget(QLabel("Pasta raiz das empresas:"))
        self.empresas_root_edit = QLineEdit(self.services.user_service.get_own_empresas_root_folder() or "")
        self.empresas_root_edit.setReadOnly(True)
        self.empresas_root_edit.setToolTip(
            "Pasta que contem todas as subpastas de empresa (ex: Empresas/1. METODOS, "
            "Empresas/6. CLINRIM). O agente usa essa pasta pra localizar a empresa certa pelo "
            "codigo quando ela ainda nao tem uma pasta configurada individualmente."
        )
        root_layout.addWidget(self.empresas_root_edit, 1)
        self.choose_empresas_root_button = make_button("Escolher pasta...")
        self.choose_empresas_root_button.clicked.connect(self.choose_empresas_root_folder)
        root_layout.addWidget(self.choose_empresas_root_button)

        batch_card = Card()
        batch_layout = QHBoxLayout(batch_card)
        batch_layout.setContentsMargins(18, 14, 18, 14)
        batch_layout.setSpacing(8)
        layout.addWidget(batch_card)

        batch_layout.addWidget(QLabel("Empresa:"))
        self.company_filter_combo = QComboBox()
        self.company_filter_combo.setMinimumWidth(220)
        self.company_filter_combo.currentIndexChanged.connect(self._on_company_filter_changed)
        batch_layout.addWidget(self.company_filter_combo)
        self.organize_ai_button = make_button("Organizar selecionados com IA")
        self.organize_ai_button.setEnabled(False)
        self.organize_ai_button.clicked.connect(self.organize_selected_with_ai)
        batch_layout.addWidget(self.organize_ai_button)
        self.confirm_batch_button = make_button("Confirmar organizacao", "primary")
        self.confirm_batch_button.setEnabled(False)
        self.confirm_batch_button.clicked.connect(self.confirm_batch_organization)
        batch_layout.addWidget(self.confirm_batch_button)
        self.batch_status_label = QLabel("")
        self.batch_status_label.setObjectName("Muted")
        batch_layout.addWidget(self.batch_status_label, 1)

        self.status_label = QLabel("Pronto para processar.")
        self.status_label.setObjectName("Muted")
        layout.addWidget(self.status_label)

        selection_hint = QLabel(
            "Clique numa linha para revisar um documento por vez; marque as caixas para "
            "organizar varios da mesma empresa com IA."
        )
        selection_hint.setObjectName("Muted")
        selection_hint.setWordWrap(True)
        layout.addWidget(selection_hint)

        self.table = QTableWidget(0, 13)
        self.table.setHorizontalHeaderLabels(
            [
                "",
                "Arquivo",
                "CNPJ extraido",
                "Empresa sugerida",
                "Tipo",
                "Confianca",
                "Origem",
                "Motivo",
                "Criado em",
                "Competencia sugerida",
                "Destino proposto",
                "Situacao (lote)",
                "",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        for col in (
            COL_CHECK, COL_CNPJ, COL_EMPRESA, COL_TIPO, COL_CONFIANCA, COL_ORIGEM, COL_MOTIVO,
            COL_CRIADO_EM, COL_COMPETENCIA, COL_EDITAR,
        ):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_ARQUIVO, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(COL_ARQUIVO, 220)
        header.setSectionResizeMode(COL_DESTINO, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_SITUACAO, QHeaderView.ResizeMode.Stretch)
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
        folder_block.setSpacing(4)
        folder_title = QLabel("Pasta de destino (opcional)")
        folder_title.setObjectName("Muted")
        folder_block.addWidget(folder_title)
        folder_row = QHBoxLayout()
        folder_row.setSpacing(6)
        self.target_folder_label = QLabel()
        self.target_folder_label.setObjectName("Muted")
        folder_row.addWidget(self.target_folder_label, 1)
        self.choose_target_button = make_button("Escolher pasta...")
        self.choose_target_button.clicked.connect(self.choose_target_folder)
        folder_row.addWidget(self.choose_target_button)
        folder_block.addLayout(folder_row)
        folder_block.addStretch(1)
        resolve_layout.addLayout(folder_block, 1)
        self._set_target_folder_display("Nenhuma pasta escolhida - usa a pasta padrao da empresa.")

        action_block = QVBoxLayout()
        self.confirm_button = make_button("Confirmar", "primary")
        self.confirm_button.clicked.connect(self.confirm_selected)
        action_block.addWidget(self.confirm_button)
        self.ignore_button = make_button("Ignorar", "danger")
        self.ignore_button.clicked.connect(self.ignore_selected)
        action_block.addWidget(self.ignore_button)
        action_block.addStretch(1)
        resolve_layout.addLayout(action_block)

        self._set_resolution_enabled(False)

    def refresh_data(self) -> None:
        self.inbox_edit.setText(self.services.user_service.get_own_inbox_folder() or "")
        self.empresas_root_edit.setText(self.services.user_service.get_own_empresas_root_folder() or "")
        self.company_selector.refresh_companies()

        self._batch_run_token += 1
        self.table.setRowCount(0)
        self.pendentes_by_id = {}
        self._batch_rows_by_pendente_id = {}

        pendentes = self.services.document_agent_service.list_pendentes()
        eligible_ids = {
            pendente["id"] for pendente in self.services.batch_organize_service.eligible_pendentes(pendentes)
        }

        for pendente in pendentes:
            self.pendentes_by_id[pendente["id"]] = pendente
            row = self.table.rowCount()
            self.table.insertRow(row)

            checkbox = QCheckBox()
            eligible = pendente["id"] in eligible_ids
            checkbox.setEnabled(eligible)
            if not eligible:
                checkbox.setToolTip("Documento sem empresa sugerida - nao e possivel organizar em lote.")
            checkbox.stateChanged.connect(self._on_batch_checkbox_toggled)
            self.table.setCellWidget(row, COL_CHECK, self._wrap_checkbox_for_cell(checkbox))

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
            for offset, value in enumerate(values):
                col = offset + 1
                item = QTableWidgetItem(str(value))
                if col == COL_ARQUIVO:
                    item.setData(Qt.ItemDataRole.UserRole, pendente["id"])
                if col == COL_MOTIVO:
                    item.setToolTip(str(value))
                self.table.setItem(row, col, item)

            self._set_batch_columns(row, competencia="-", destino="-", situacao="-")

        self._populate_company_filter()

        self._chosen_target_folder = None
        self._set_target_folder_display("Nenhuma pasta escolhida - usa a pasta padrao da empresa.")
        self._set_resolution_enabled(False)

        self.organize_ai_button.setEnabled(False)
        self.confirm_batch_button.setEnabled(False)
        self.batch_status_label.setText("")

    def choose_inbox_folder(self) -> None:
        current = self.inbox_edit.text().strip()
        initial = current if current and Path(current).is_dir() else str(Path.home())
        selected = QFileDialog.getExistingDirectory(self, "Escolha a pasta de entrada dos documentos", initial)
        if not selected:
            return
        self.inbox_edit.setText(selected)
        self.services.user_service.set_own_inbox_folder(selected)

    def choose_empresas_root_folder(self) -> None:
        current = self.empresas_root_edit.text().strip()
        initial = current if current and Path(current).is_dir() else str(Path.home())
        selected = QFileDialog.getExistingDirectory(self, "Escolha a pasta raiz das empresas", initial)
        if not selected:
            return
        self.empresas_root_edit.setText(selected)
        self.services.user_service.set_own_empresas_root_folder(selected)

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

        self._classify_worker_thread = QThread(self)
        self._classify_worker = _ClassificationWorker(service, files, cnpj_index, known_names)
        self._classify_worker.moveToThread(self._classify_worker_thread)
        self._classify_worker_thread.started.connect(self._classify_worker.run)
        self._classify_worker.progress.connect(
            lambda done, total: self.status_label.setText(f"Processando documento {done} de {total}...")
        )
        self._classify_worker.finished.connect(self._on_worker_finished)
        self._classify_worker.failed.connect(self._on_worker_failed)
        self._classify_worker.finished.connect(self._classify_worker_thread.quit)
        self._classify_worker.failed.connect(self._classify_worker_thread.quit)
        self._classify_worker_thread.finished.connect(self._classify_worker.deleteLater)
        self._classify_worker_thread.start()

    def shutdown(self) -> None:
        """Aguarda as threads de fundo antes da janela fechar — destruir
        uma QThread em execucao aborta o processo inteiro."""
        if self._classify_worker_thread is not None and self._classify_worker_thread.isRunning():
            self._classify_worker_thread.requestInterruption()
            self._classify_worker_thread.quit()
            self._classify_worker_thread.wait(15000)
        if self._batch_worker_thread is not None and self._batch_worker_thread.isRunning():
            self._batch_worker_thread.quit()
            self._batch_worker_thread.wait(15000)

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

        pendente_id = self._pendente_id_for_row(rows[0].row())
        pendente = self.pendentes_by_id.get(pendente_id) if pendente_id is not None else None
        self._set_resolution_enabled(True)
        self._chosen_target_folder = None
        self._set_target_folder_display("Nenhuma pasta escolhida - usa a pasta padrao da empresa.")
        if pendente and pendente.get("empresa_sugerida_id"):
            self.company_selector.set_company(pendente["empresa_sugerida_id"])
        else:
            self.company_selector.clear_selection()

    def choose_target_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Escolha a pasta de destino do documento")
        if not selected:
            return
        self._chosen_target_folder = selected
        self._set_target_folder_display(selected)

    def _set_target_folder_display(self, text: str) -> None:
        self.target_folder_label.setToolTip(text)
        elided = self.target_folder_label.fontMetrics().elidedText(text, Qt.TextElideMode.ElideMiddle, 260)
        self.target_folder_label.setText(elided)

    def _pendente_id_for_row(self, row: int) -> int | None:
        item = self.table.item(row, COL_ARQUIVO)
        if item is None:
            return None
        return int(item.data(Qt.ItemDataRole.UserRole))

    def _row_for_pendente_id(self, pendente_id: int) -> int | None:
        for row in range(self.table.rowCount()):
            if self._pendente_id_for_row(row) == pendente_id:
                return row
        return None

    def _selected_pendente_id(self) -> int | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return self._pendente_id_for_row(rows[0].row())

    def _wrap_checkbox_for_cell(self, checkbox: QCheckBox) -> QWidget:
        """Centraliza o checkbox numa celula da tabela - um QCheckBox "cru" esticado pra
        preencher a celula so responde a clique perto do proprio indicador (a area vazia
        ao redor nao ativa o toggle), o que faz parecer que so a primeira marcacao funciona.
        Um container com layout centralizado devolve um alvo de clique pequeno e previsivel."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(checkbox)
        return container

    def _checkbox_for_row(self, row: int) -> QCheckBox | None:
        container = self.table.cellWidget(row, COL_CHECK)
        if container is None:
            return None
        return container.findChild(QCheckBox)

    def _checked_pendente_ids(self) -> list[int]:
        ids = []
        for row in range(self.table.rowCount()):
            checkbox = self._checkbox_for_row(row)
            if checkbox is not None and checkbox.isChecked():
                pendente_id = self._pendente_id_for_row(row)
                if pendente_id is not None:
                    ids.append(pendente_id)
        return ids

    def _on_batch_checkbox_toggled(self, _state: int) -> None:
        self.organize_ai_button.setEnabled(bool(self._checked_pendente_ids()))

    def _set_batch_columns(self, row: int, *, competencia: str, destino: str, situacao: str) -> None:
        self.table.setItem(row, COL_COMPETENCIA, QTableWidgetItem(competencia))
        self.table.setItem(row, COL_DESTINO, QTableWidgetItem(destino))
        self._set_situacao(row, situacao)

    def _set_situacao(self, row: int, text: str) -> None:
        item = QTableWidgetItem(text)
        item.setToolTip(text)
        self.table.setItem(row, COL_SITUACAO, item)

    def _populate_company_filter(self) -> None:
        entries: list[tuple[str, int]] = []
        seen: set[int] = set()
        for pendente in self.pendentes_by_id.values():
            empresa_id = pendente.get("empresa_sugerida_id")
            if empresa_id is None or empresa_id in seen:
                continue
            seen.add(empresa_id)
            entries.append((pendente.get("empresa_sugerida_nome") or f"Empresa {empresa_id}", empresa_id))
        entries.sort(key=lambda item: item[0].lower())

        self.company_filter_combo.blockSignals(True)
        self.company_filter_combo.clear()
        self.company_filter_combo.addItem("Todas as empresas", None)
        for nome, empresa_id in entries:
            self.company_filter_combo.addItem(nome, empresa_id)
        self.company_filter_combo.blockSignals(False)
        self._apply_company_filter()

    def _on_company_filter_changed(self, _index: int) -> None:
        self._apply_company_filter()

    def _apply_company_filter(self) -> None:
        selected_empresa_id = self.company_filter_combo.currentData()
        for row in range(self.table.rowCount()):
            pendente_id = self._pendente_id_for_row(row)
            pendente = self.pendentes_by_id.get(pendente_id) if pendente_id is not None else None
            hide = (
                selected_empresa_id is not None
                and pendente is not None
                and pendente.get("empresa_sugerida_id") != selected_empresa_id
            )
            self.table.setRowHidden(row, hide)

    def organize_selected_with_ai(self) -> None:
        ids = self._checked_pendente_ids()
        if not ids:
            return

        pendentes = [self.pendentes_by_id[pid] for pid in ids if pid in self.pendentes_by_id]
        eligible = self.services.batch_organize_service.eligible_pendentes(pendentes)
        eligible_ids = {p["id"] for p in eligible}
        ineligible = [p for p in pendentes if p["id"] not in eligible_ids]

        for pendente in ineligible:
            row = self._row_for_pendente_id(pendente["id"])
            if row is None:
                continue
            self._set_situacao(row, "Sem empresa sugerida - nao e possivel organizar em lote.")
            checkbox = self._checkbox_for_row(row)
            if checkbox is not None:
                checkbox.setChecked(False)
                checkbox.setEnabled(False)

        if not eligible:
            self.batch_status_label.setText(
                "Nenhum documento selecionado tem empresa sugerida para organizar em lote."
            )
            return

        empresas_root_dir = self.services.user_service.get_own_empresas_root_folder()
        self.organize_ai_button.setEnabled(False)
        self.batch_status_label.setText(f"Analisando {len(eligible)} documento(s)...")
        self._start_batch_worker(eligible, empresas_root_dir)

    def _start_batch_worker(self, pendentes: list[dict], empresas_root_dir: str | None) -> None:
        run_token = self._batch_run_token
        self._batch_worker_thread = QThread(self)
        self._batch_worker = _BatchOrganizeWorker(
            self.services.batch_organize_service, pendentes, empresas_root_dir
        )
        self._batch_worker.moveToThread(self._batch_worker_thread)
        self._batch_worker_thread.started.connect(self._batch_worker.run)
        self._batch_worker.finished.connect(lambda rows: self._on_batch_rows_loaded(rows, run_token))
        self._batch_worker.failed.connect(self._on_batch_loading_failed)
        self._batch_worker.finished.connect(self._batch_worker_thread.quit)
        self._batch_worker.failed.connect(self._batch_worker_thread.quit)
        self._batch_worker_thread.finished.connect(self._batch_worker.deleteLater)
        self._batch_worker_thread.start()

    def _on_batch_loading_failed(self, message: str) -> None:
        self.organize_ai_button.setEnabled(bool(self._checked_pendente_ids()))
        self.batch_status_label.setText(f"Falha ao analisar os documentos: {message}")

    def _on_batch_rows_loaded(self, rows: list[BatchOrganizeRow], run_token: int) -> None:
        self.organize_ai_button.setEnabled(bool(self._checked_pendente_ids()))
        if run_token != self._batch_run_token:
            return

        valid_count = 0
        for row_data in rows:
            self._batch_rows_by_pendente_id[row_data.pendente_id] = row_data
            table_row = self._row_for_pendente_id(row_data.pendente_id)
            if table_row is None:
                continue

            competencia_text = (
                f"{row_data.suggestion.mes:02d}/{row_data.suggestion.ano}" if row_data.suggestion else "-"
            )
            if row_data.proposal is not None:
                valid_count += 1
                destino_text = str(row_data.proposal.destination_dir / row_data.proposal.new_filename)
                notes = []
                if row_data.proposal.new_folders:
                    notes.append(f"cria {len(row_data.proposal.new_folders)} pasta(s) nova(s)")
                if row_data.proposal.filename_is_synthesized:
                    notes.append("nome padrao (sem exemplo)")
                situacao_text = "Pronto para confirmar" + (f" ({'; '.join(notes)})" if notes else "")
            else:
                destino_text = "-"
                situacao_text = row_data.needs_input_message or row_data.error or "Nao foi possivel propor um destino."
                checkbox = self._checkbox_for_row(table_row)
                if checkbox is not None:
                    checkbox.setChecked(False)
                    checkbox.setEnabled(False)

            self._set_batch_columns(
                table_row, competencia=competencia_text, destino=destino_text, situacao=situacao_text
            )

            if row_data.proposal is not None:
                edit_button = make_button("Editar nome...")
                edit_button.clicked.connect(
                    lambda _checked=False, pid=row_data.pendente_id: self._open_edit_dialog_for_row(pid)
                )
                self.table.setCellWidget(table_row, COL_EDITAR, edit_button)
            else:
                self.table.removeCellWidget(table_row, COL_EDITAR)

        self.batch_status_label.setText(f"{len(rows)} documento(s) analisado(s), {valid_count} com destino proposto.")
        self.confirm_batch_button.setEnabled(valid_count > 0)

    def _open_edit_dialog_for_row(self, pendente_id: int) -> None:
        row_data = self._batch_rows_by_pendente_id.get(pendente_id)
        if row_data is None or row_data.proposal is None:
            return

        dialog = OrganizeConfirmationDialog(
            documento_nome=row_data.nome_arquivo,
            new_folders=row_data.proposal.new_folders,
            new_filename=row_data.proposal.new_filename,
            based_on_sibling=row_data.proposal.based_on_sibling,
            filename_is_synthesized=row_data.proposal.filename_is_synthesized,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        apply_confirmation_overrides(row_data.proposal, dialog)
        table_row = self._row_for_pendente_id(pendente_id)
        if table_row is not None:
            destino_text = str(row_data.proposal.destination_dir / row_data.proposal.new_filename)
            self.table.setItem(table_row, COL_DESTINO, QTableWidgetItem(destino_text))

    def confirm_batch_organization(self) -> None:
        ids = self._checked_pendente_ids()
        rows_to_execute = [
            (pid, self._batch_rows_by_pendente_id[pid])
            for pid in ids
            if pid in self._batch_rows_by_pendente_id and self._batch_rows_by_pendente_id[pid].proposal is not None
        ]
        if not rows_to_execute:
            return

        organized = 0
        failed = 0
        for pendente_id, row_data in rows_to_execute:
            table_row = self._row_for_pendente_id(pendente_id)
            try:
                destino = self.services.batch_organize_service.execute_row(row_data)
            except ValidationError as exc:
                failed += 1
                if table_row is not None:
                    self._set_situacao(table_row, f"Falha: {exc}")
            else:
                organized += 1
                if table_row is not None:
                    self._set_situacao(table_row, f"Organizado em {destino}")

            if table_row is not None:
                checkbox = self._checkbox_for_row(table_row)
                if checkbox is not None:
                    checkbox.setChecked(False)
                    checkbox.setEnabled(False)

        summary = f"{organized} documento(s) organizado(s) com sucesso."
        if failed:
            summary += f" {failed} falharam."
        QMessageBox.information(self, "Revisao de documentos", summary)
        self.on_data_changed()

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

    def selected_chat_context(self) -> tuple[dict, int | None, str | None] | None:
        """Documento, empresa e pasta escolhidos atualmente na tela de revisao - usado pela
        bolha flutuante de chat na janela principal pra abrir a conversa ja com esse contexto."""
        pendente_id = self._selected_pendente_id()
        if pendente_id is None:
            return None
        pendente = self.pendentes_by_id.get(pendente_id)
        if not pendente:
            return None
        return pendente, self.company_selector.get_selected_company_id(), self._chosen_target_folder

    def _set_resolution_enabled(self, enabled: bool) -> None:
        self.choose_target_button.setEnabled(enabled)
        self.confirm_button.setEnabled(enabled)
        self.ignore_button.setEnabled(enabled)
