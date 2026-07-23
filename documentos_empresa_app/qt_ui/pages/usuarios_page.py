from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
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

from documentos_empresa_app.qt_ui.widgets.common import Card, PageHeader, make_button
from documentos_empresa_app.utils.common import ValidationError


class UsuariosPage(QWidget):
    def __init__(self, services, on_data_changed, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.on_data_changed = on_data_changed
        self.editing_user_id: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        layout.addWidget(PageHeader("Usuarios", "Gerencie quem pode acessar o sistema e o nivel de cada acesso."))

        form_card = Card()
        layout.addWidget(form_card)
        form_layout = QGridLayout(form_card)
        form_layout.setContentsMargins(18, 16, 18, 16)
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(6)

        form_layout.addWidget(QLabel("Nome de usuario"), 0, 0)
        self.username_edit = QLineEdit()
        form_layout.addWidget(self.username_edit, 1, 0)

        form_layout.addWidget(QLabel("Senha"), 0, 1)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addWidget(self.password_edit, 1, 1)

        form_layout.addWidget(QLabel("Tipo"), 0, 2)
        self.tipo_combo = QComboBox()
        self.tipo_combo.addItems(["comum", "admin"])
        form_layout.addWidget(self.tipo_combo, 1, 2)

        self.active_check = QCheckBox("Usuario ativo")
        self.active_check.setChecked(True)
        form_layout.addWidget(self.active_check, 1, 3)

        actions = QHBoxLayout()
        self.save_button = make_button("Cadastrar usuario", "primary")
        self.save_button.clicked.connect(self.save_user)
        actions.addWidget(self.save_button)
        clear_button = make_button("Limpar", "quiet")
        clear_button.clicked.connect(self.clear_form)
        actions.addWidget(clear_button)
        actions.addStretch(1)
        hint = QLabel("Ao editar, deixe a senha em branco para manter a atual.")
        hint.setObjectName("Muted")
        actions.addWidget(hint)
        form_layout.addLayout(actions, 2, 0, 1, 4)
        form_layout.setColumnStretch(0, 2)
        form_layout.setColumnStretch(1, 2)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Usuario", "Tipo", "Situacao", "Criado em"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 3):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table, 1)

    def refresh_data(self) -> None:
        try:
            users = self.services.user_service.list_users()
        except ValidationError:
            return

        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for user in users:
            row = self.table.rowCount()
            self.table.insertRow(row)
            name_item = QTableWidgetItem(user["username"])
            name_item.setData(Qt.ItemDataRole.UserRole, user["id"])
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem(user["tipo_usuario"]))
            self.table.setItem(row, 2, QTableWidgetItem("Ativo" if user["ativa"] else "Inativo"))
            self.table.setItem(row, 3, QTableWidgetItem(str(user.get("criado_em") or "-")))
        self.table.blockSignals(False)

    def _on_selection_changed(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        item = self.table.item(rows[0].row(), 0)
        if item is None:
            return
        user_id = int(item.data(Qt.ItemDataRole.UserRole))
        try:
            user = self.services.user_service.get_user(user_id)
        except ValidationError as exc:
            QMessageBox.critical(self, "Usuarios", str(exc))
            return

        self.editing_user_id = user_id
        self.username_edit.setText(user["username"])
        self.password_edit.clear()
        self.tipo_combo.setCurrentText(user["tipo_usuario"])
        self.active_check.setChecked(bool(user["ativa"]))
        self.save_button.setText("Salvar alteracoes")

    def clear_form(self) -> None:
        self.editing_user_id = None
        self.username_edit.clear()
        self.password_edit.clear()
        self.tipo_combo.setCurrentText("comum")
        self.active_check.setChecked(True)
        self.save_button.setText("Cadastrar usuario")
        self.table.clearSelection()

    def save_user(self) -> None:
        try:
            if self.editing_user_id:
                password = self.password_edit.text() or None
                self.services.user_service.update_user(
                    self.editing_user_id,
                    self.username_edit.text(),
                    self.tipo_combo.currentText(),
                    self.active_check.isChecked(),
                    password=password,
                )
                QMessageBox.information(self, "Usuarios", "Usuario atualizado com sucesso.")
            else:
                self.services.user_service.create_user(
                    self.username_edit.text(),
                    self.password_edit.text(),
                    self.tipo_combo.currentText(),
                    ativo=self.active_check.isChecked(),
                )
                QMessageBox.information(self, "Usuarios", "Usuario cadastrado com sucesso.")
        except ValidationError as exc:
            QMessageBox.critical(self, "Usuarios", str(exc))
            return

        self.clear_form()
        self.on_data_changed()
