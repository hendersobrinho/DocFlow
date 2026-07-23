from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QGridLayout,
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

from documentos_empresa_app.qt_ui.widgets.common import make_button
from documentos_empresa_app.utils.common import (
    TYPE_OCCURRENCE_CHOICES,
    TYPE_OCCURRENCE_MENSAL,
    ValidationError,
)


class DocumentTypeManagerDialog(QDialog):
    """Gerencia tipos de documento e a regra de ocorrencia de cada um."""

    def __init__(
        self,
        tipo_service,
        context_title: str = "Documentos",
        initial_tipo_id: int | None = None,
        allow_apply_to_document: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.tipo_service = tipo_service
        self.initial_tipo_id = initial_tipo_id
        self.allow_apply_to_document = allow_apply_to_document
        self.applied_type_id: int | None = None
        self.data_changed = False
        self.editing_tipo_id: int | None = None

        self.setWindowTitle(f"{context_title} - Tipos de documento")
        self.resize(620, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        help_label = QLabel(
            "Mensal: cobrado todo mes. Trimestral: cobrado em janeiro, abril, julho e outubro. "
            "Anual em janeiro: cobrado somente em janeiro. Nos demais meses o status vira 'Nao cobrar' automaticamente."
        )
        help_label.setWordWrap(True)
        help_label.setObjectName("Muted")
        layout.addWidget(help_label)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Nome", "Ocorrencia"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.doubleClicked.connect(lambda _index: self._apply_to_document())
        layout.addWidget(self.table, 1)

        editor = QGridLayout()
        editor.addWidget(QLabel("Nome do tipo"), 0, 0)
        self.nome_edit = QLineEdit()
        editor.addWidget(self.nome_edit, 1, 0)
        editor.addWidget(QLabel("Ocorrencia"), 0, 1)
        self.occurrence_combo = QComboBox()
        for value, label in TYPE_OCCURRENCE_CHOICES:
            self.occurrence_combo.addItem(label, value)
        editor.addWidget(self.occurrence_combo, 1, 1)
        editor.setColumnStretch(0, 1)
        layout.addLayout(editor)

        buttons = QHBoxLayout()
        self.save_button = make_button("Cadastrar tipo", "primary")
        self.save_button.clicked.connect(self._save)
        buttons.addWidget(self.save_button)
        clear_button = make_button("Limpar", "quiet")
        clear_button.clicked.connect(self._clear_editor)
        buttons.addWidget(clear_button)
        buttons.addStretch(1)
        self.apply_button = make_button("Usar no documento")
        self.apply_button.clicked.connect(self._apply_to_document)
        self.apply_button.setEnabled(False)
        if allow_apply_to_document:
            buttons.addWidget(self.apply_button)
        delete_button = make_button("Excluir tipo selecionado", "danger")
        delete_button.clicked.connect(self._delete)
        buttons.addWidget(delete_button)
        layout.addLayout(buttons)

        self._populate()

    def _populate(self) -> None:
        self.table.setRowCount(0)
        for tipo in self.tipo_service.list_tipos():
            row = self.table.rowCount()
            self.table.insertRow(row)
            name_item = QTableWidgetItem(tipo["nome_tipo"])
            name_item.setData(Qt.ItemDataRole.UserRole, tipo["id"])
            self.table.setItem(row, 0, name_item)
            label = next(
                (lbl for value, lbl in TYPE_OCCURRENCE_CHOICES if value == tipo.get("regra_ocorrencia")),
                tipo.get("regra_ocorrencia") or "Mensal",
            )
            self.table.setItem(row, 1, QTableWidgetItem(label))
            if self.initial_tipo_id and tipo["id"] == self.initial_tipo_id:
                self.table.selectRow(row)

    def _selected_tipo_id(self) -> int | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        return int(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def _on_selection_changed(self) -> None:
        tipo_id = self._selected_tipo_id()
        self.apply_button.setEnabled(self.allow_apply_to_document and tipo_id is not None)
        if tipo_id is None:
            return
        try:
            tipo = self.tipo_service.get_tipo(tipo_id)
        except ValidationError:
            return
        self.editing_tipo_id = tipo_id
        self.nome_edit.setText(tipo["nome_tipo"])
        index = self.occurrence_combo.findData(tipo.get("regra_ocorrencia") or TYPE_OCCURRENCE_MENSAL)
        self.occurrence_combo.setCurrentIndex(max(index, 0))
        self.save_button.setText("Salvar alteracoes")

    def _clear_editor(self) -> None:
        self.editing_tipo_id = None
        self.nome_edit.clear()
        self.occurrence_combo.setCurrentIndex(0)
        self.save_button.setText("Cadastrar tipo")
        self.table.clearSelection()

    def _save(self) -> None:
        try:
            if self.editing_tipo_id:
                self.tipo_service.update_tipo(
                    self.editing_tipo_id, self.nome_edit.text(), self.occurrence_combo.currentData()
                )
            else:
                self.tipo_service.create_tipo(self.nome_edit.text(), self.occurrence_combo.currentData())
        except ValidationError as exc:
            QMessageBox.critical(self, "Tipos de documento", str(exc))
            return
        self.data_changed = True
        self._clear_editor()
        self._populate()

    def _delete(self) -> None:
        tipo_id = self._selected_tipo_id()
        if tipo_id is None:
            QMessageBox.warning(self, "Tipos de documento", "Selecione um tipo para excluir.")
            return
        if QMessageBox.question(self, "Tipos de documento", "Deseja excluir o tipo selecionado?") != QMessageBox.StandardButton.Yes:
            return
        try:
            self.tipo_service.delete_tipo(tipo_id)
        except ValidationError as exc:
            QMessageBox.critical(self, "Tipos de documento", str(exc))
            return
        self.data_changed = True
        if self.initial_tipo_id == tipo_id:
            self.initial_tipo_id = None
        self._clear_editor()
        self._populate()

    def _apply_to_document(self) -> None:
        if not self.allow_apply_to_document:
            return
        tipo_id = self._selected_tipo_id()
        if tipo_id is None:
            return
        self.applied_type_id = tipo_id
        self.accept()


class DocumentNameManagerDialog(QDialog):
    """Gerencia os nomes padrao de documento do sistema por tipo."""

    def __init__(
        self,
        documento_service,
        tipo_service,
        context_title: str = "Documentos",
        initial_tipo_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.documento_service = documento_service
        self.tipo_service = tipo_service
        self.editing_name_id: int | None = None
        self.data_changed = False

        self.setWindowTitle(f"{context_title} - Nomes padrao")
        self.resize(620, 460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Nome", "Tipo"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table, 1)

        editor = QGridLayout()
        editor.addWidget(QLabel("Tipo"), 0, 0)
        self.tipo_combo = QComboBox()
        editor.addWidget(self.tipo_combo, 1, 0)
        editor.addWidget(QLabel("Nome padrao"), 0, 1)
        self.nome_edit = QLineEdit()
        editor.addWidget(self.nome_edit, 1, 1)
        editor.setColumnStretch(1, 1)
        layout.addLayout(editor)

        buttons = QHBoxLayout()
        self.save_button = make_button("Adicionar", "primary")
        self.save_button.clicked.connect(self._save)
        buttons.addWidget(self.save_button)
        clear_button = make_button("Limpar", "quiet")
        clear_button.clicked.connect(self._clear_editor)
        buttons.addWidget(clear_button)
        buttons.addStretch(1)
        delete_button = make_button("Excluir do sistema", "danger")
        delete_button.clicked.connect(self._delete)
        buttons.addWidget(delete_button)
        layout.addLayout(buttons)

        self._load_tipos(initial_tipo_id)
        self._populate()

    def _load_tipos(self, initial_tipo_id: int | None) -> None:
        self.tipo_combo.clear()
        for tipo in self.tipo_service.list_tipos():
            self.tipo_combo.addItem(tipo["nome_tipo"], tipo["id"])
        if initial_tipo_id is not None:
            index = self.tipo_combo.findData(initial_tipo_id)
            if index >= 0:
                self.tipo_combo.setCurrentIndex(index)

    def _populate(self) -> None:
        self.table.setRowCount(0)
        for entry in self.documento_service.list_system_document_names():
            row = self.table.rowCount()
            self.table.insertRow(row)
            name_item = QTableWidgetItem(entry["nome_documento"])
            name_item.setData(Qt.ItemDataRole.UserRole, entry["id"])
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem(entry["nome_tipo"]))

    def _on_selection_changed(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        item = self.table.item(rows[0].row(), 0)
        if item is None:
            return
        name_id = int(item.data(Qt.ItemDataRole.UserRole))
        try:
            entry = self.documento_service.get_system_document_name(name_id)
        except ValidationError:
            return
        self.editing_name_id = name_id
        self.nome_edit.setText(entry["nome_documento"])
        index = self.tipo_combo.findText(entry["nome_tipo"])
        if index >= 0:
            self.tipo_combo.setCurrentIndex(index)
        self.save_button.setText("Salvar alteracoes")

    def _clear_editor(self) -> None:
        self.editing_name_id = None
        self.nome_edit.clear()
        self.save_button.setText("Adicionar")
        self.table.clearSelection()

    def _save(self) -> None:
        tipo_id = self.tipo_combo.currentData()
        if tipo_id is None:
            QMessageBox.warning(self, "Nomes padrao", "Cadastre um tipo de documento antes.")
            return
        try:
            if self.editing_name_id:
                self.documento_service.update_system_document_name(
                    self.editing_name_id, tipo_id, self.nome_edit.text()
                )
            else:
                self.documento_service.create_system_document_name(tipo_id, self.nome_edit.text())
        except ValidationError as exc:
            QMessageBox.critical(self, "Nomes padrao", str(exc))
            return
        self.data_changed = True
        self._clear_editor()
        self._populate()

    def _delete(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(self, "Nomes padrao", "Selecione um nome para excluir.")
            return
        item = self.table.item(rows[0].row(), 0)
        name_id = int(item.data(Qt.ItemDataRole.UserRole))
        if QMessageBox.question(self, "Nomes padrao", "Deseja excluir o nome selecionado?") != QMessageBox.StandardButton.Yes:
            return
        try:
            self.documento_service.delete_system_document_name(name_id)
        except ValidationError as exc:
            QMessageBox.critical(self, "Nomes padrao", str(exc))
            return
        self.data_changed = True
        self._clear_editor()
        self._populate()


class DeliveryMethodsManagerDialog(QDialog):
    """Gerencia os meios de recebimento do sistema."""

    def __init__(self, delivery_method_service, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.delivery_method_service = delivery_method_service
        self.editing_method_id: int | None = None
        self.data_changed = False

        self.setWindowTitle("Meios de recebimento do sistema")
        self.resize(480, 440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        self.table = QTableWidget(0, 1)
        self.table.setHorizontalHeaderLabels(["Meio de recebimento"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table, 1)

        editor = QHBoxLayout()
        editor.addWidget(QLabel("Nome do meio"))
        self.nome_edit = QLineEdit()
        editor.addWidget(self.nome_edit, 1)
        layout.addLayout(editor)

        buttons = QHBoxLayout()
        self.save_button = make_button("Adicionar", "primary")
        self.save_button.clicked.connect(self._save)
        buttons.addWidget(self.save_button)
        clear_button = make_button("Limpar", "quiet")
        clear_button.clicked.connect(self._clear_editor)
        buttons.addWidget(clear_button)
        buttons.addStretch(1)
        delete_button = make_button("Excluir do sistema", "danger")
        delete_button.clicked.connect(self._delete)
        buttons.addWidget(delete_button)
        layout.addLayout(buttons)

        self._populate()

    def _populate(self) -> None:
        self.table.setRowCount(0)
        for method in self.delivery_method_service.list_methods():
            row = self.table.rowCount()
            self.table.insertRow(row)
            item = QTableWidgetItem(method["nome_meio"])
            item.setData(Qt.ItemDataRole.UserRole, method["id"])
            self.table.setItem(row, 0, item)

    def _on_selection_changed(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        item = self.table.item(rows[0].row(), 0)
        if item is None:
            return
        self.editing_method_id = int(item.data(Qt.ItemDataRole.UserRole))
        self.nome_edit.setText(item.text())
        self.save_button.setText("Renomear")

    def _clear_editor(self) -> None:
        self.editing_method_id = None
        self.nome_edit.clear()
        self.save_button.setText("Adicionar")
        self.table.clearSelection()

    def _save(self) -> None:
        try:
            if self.editing_method_id:
                affected = self.delivery_method_service.update_method(
                    self.editing_method_id, self.nome_edit.text()
                )
                if affected:
                    QMessageBox.information(
                        self, "Meios de recebimento", f"{affected} documento(s) atualizados com o novo nome."
                    )
            else:
                self.delivery_method_service.create_method(self.nome_edit.text())
        except ValidationError as exc:
            QMessageBox.critical(self, "Meios de recebimento", str(exc))
            return
        self.data_changed = True
        self._clear_editor()
        self._populate()

    def _delete(self) -> None:
        if self.editing_method_id is None:
            QMessageBox.warning(self, "Meios de recebimento", "Selecione um meio para excluir.")
            return
        method = self.delivery_method_service.get_method(self.editing_method_id)
        in_use = self.delivery_method_service.count_documents_using(method["nome_meio"])
        message = "Deseja excluir o meio selecionado do sistema?"
        if in_use:
            message = (
                f'O meio "{method["nome_meio"]}" ainda esta em uso por {in_use} documento(s). '
                "Ele sera removido apenas da lista do sistema. Continuar?"
            )
        if QMessageBox.question(self, "Meios de recebimento", message) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.delivery_method_service.delete_method(self.editing_method_id)
        except ValidationError as exc:
            QMessageBox.critical(self, "Meios de recebimento", str(exc))
            return
        self.data_changed = True
        self._clear_editor()
        self._populate()
