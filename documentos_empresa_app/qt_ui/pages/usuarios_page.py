from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.theme import tokens
from documentos_empresa_app.qt_ui.widgets.common import Card, PageHeader, ToolbarRow, make_button
from documentos_empresa_app.qt_ui.widgets.tables import fill_table, make_readonly_table, selected_key
from documentos_empresa_app.utils.common import ValidationError, format_utc_timestamp

PROFILE_LABELS = {"admin": "Administrador", "comum": "Usuário comum"}
PROFILE_HINTS = {
    "admin": "Pode tudo, inclusive cadastrar usuários, mudar configurações, restaurar backup e ver o histórico.",
    "comum": "Usa o dia a dia: empresas, documentos, controle mensal e cobranças. Não mexe em usuários nem "
    "configurações.",
}


class UsuariosPage(QWidget):
    """Quem pode entrar no sistema: lista de usuarios e, ao lado, o cadastro do usuario
    escolhido ou de um usuario novo."""

    def __init__(self, services, on_data_changed, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.on_data_changed = on_data_changed
        self.editing_user_id: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(PageHeader("Usuários", "Quem pode entrar no DocFlow e o que cada pessoa pode fazer."))

        toolbar = ToolbarRow()
        toolbar.add_stretch()
        new_button = make_button("Novo usuário", "primary")
        new_button.clicked.connect(self.start_new)
        toolbar.add(new_button)
        layout.addWidget(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)
        self.table = make_readonly_table(["Usuário", "Perfil", "Situação", "Criado em"], stretch_column=0)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        splitter.addWidget(self.table)

        self.detail_stack = QStackedWidget()
        empty = QLabel("Clique num usuário para editar\nou em Novo usuário.")
        empty.setObjectName("Muted")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_card = Card()
        QVBoxLayout(empty_card).addWidget(empty)
        self.detail_stack.addWidget(empty_card)
        self.detail_stack.addWidget(self._build_form())
        splitter.addWidget(self.detail_stack)
        splitter.setSizes([600, 520])

    def _build_form(self) -> QWidget:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 14)
        layout.setSpacing(10)
        self.form_title = QLabel()
        self.form_title.setStyleSheet("font-size: 13pt; font-weight: 600;")
        layout.addWidget(self.form_title)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Nome usado para entrar")
        form.addRow("Usuário", self.username_edit)
        self.tipo_combo = QComboBox()
        for key, label in PROFILE_LABELS.items():
            self.tipo_combo.addItem(label, key)
        self.tipo_combo.currentIndexChanged.connect(self._update_profile_hint)
        form.addRow("Perfil", self.tipo_combo)
        self.profile_hint = QLabel()
        self.profile_hint.setObjectName("Muted")
        self.profile_hint.setWordWrap(True)
        form.addRow("", self.profile_hint)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Senha", self.password_edit)
        self.password_confirm_edit = QLineEdit()
        self.password_confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Repita a senha", self.password_confirm_edit)
        self.active_check = QCheckBox("Pode entrar no sistema (ativo)")
        form.addRow("", self.active_check)
        layout.addLayout(form)
        layout.addStretch(1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = make_button("Descartar", "quiet")
        cancel.clicked.connect(self._discard)
        actions.addWidget(cancel)
        self.save_button = make_button("Salvar", "primary")
        self.save_button.clicked.connect(self.save_user)
        actions.addWidget(self.save_button)
        layout.addLayout(actions)
        return card

    # Dados -------------------------------------------------------------------------

    def refresh_data(self) -> None:
        try:
            users = self.services.user_service.list_users()
        except ValidationError:
            return
        muted = tokens()["muted"]
        rows = []
        colors = {}
        for index, user in enumerate(users):
            rows.append(
                (
                    user["id"],
                    [
                        user["username"],
                        PROFILE_LABELS.get(user["tipo_usuario"], user["tipo_usuario"]),
                        "Ativo" if user["ativa"] else "Inativo",
                        format_utc_timestamp(user.get("criado_em"), with_time=False),
                    ],
                )
            )
            if not user["ativa"]:
                for column in range(4):
                    colors[(index, column)] = muted
        self.table.blockSignals(True)
        fill_table(self.table, rows, colors)
        self.table.blockSignals(False)

    def _on_selection_changed(self) -> None:
        user_id = selected_key(self.table)
        if user_id is None:
            return
        try:
            user = self.services.user_service.get_user(user_id)
        except ValidationError as exc:
            QMessageBox.critical(self, "Usuários", str(exc))
            return
        self.editing_user_id = user_id
        self.detail_stack.setCurrentIndex(1)
        self.form_title.setText(user["username"])
        self.username_edit.setText(user["username"])
        self.tipo_combo.setCurrentIndex(max(0, self.tipo_combo.findData(user["tipo_usuario"])))
        self._clear_passwords("Deixe em branco para manter a senha atual")
        self.active_check.setChecked(bool(user["ativa"]))
        self.save_button.setText("Salvar alterações")
        self._update_profile_hint()

    # Acoes -------------------------------------------------------------------------

    def start_new(self) -> None:
        self.table.clearSelection()
        self.editing_user_id = None
        self.detail_stack.setCurrentIndex(1)
        self.form_title.setText("Novo usuário")
        self.username_edit.clear()
        self.tipo_combo.setCurrentIndex(self.tipo_combo.findData("comum"))
        self._clear_passwords("Senha de acesso")
        self.active_check.setChecked(True)
        self.save_button.setText("Cadastrar usuário")
        self._update_profile_hint()
        self.username_edit.setFocus()

    def _clear_passwords(self, placeholder: str) -> None:
        self.password_edit.clear()
        self.password_confirm_edit.clear()
        self.password_edit.setPlaceholderText(placeholder)

    def _update_profile_hint(self) -> None:
        self.profile_hint.setText(PROFILE_HINTS.get(self.tipo_combo.currentData(), ""))

    def _discard(self) -> None:
        if self.editing_user_id is not None:
            self._on_selection_changed()
        else:
            self.detail_stack.setCurrentIndex(0)

    def save_user(self) -> None:
        password = self.password_edit.text()
        if password != self.password_confirm_edit.text():
            QMessageBox.warning(self, "Usuários", "As duas senhas digitadas não são iguais.")
            return
        try:
            if self.editing_user_id:
                self.services.user_service.update_user(
                    self.editing_user_id,
                    self.username_edit.text(),
                    self.tipo_combo.currentData(),
                    self.active_check.isChecked(),
                    password=password or None,
                )
                message = "Usuário atualizado."
            else:
                self.editing_user_id = self.services.user_service.create_user(
                    self.username_edit.text(),
                    password,
                    self.tipo_combo.currentData(),
                    ativo=self.active_check.isChecked(),
                )
                message = "Usuário cadastrado. No primeiro acesso ele já entra com a senha definida aqui."
        except ValidationError as exc:
            QMessageBox.critical(self, "Usuários", str(exc))
            return
        QMessageBox.information(self, "Usuários", message)
        self.on_data_changed()
        self.refresh_data()
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) == self.editing_user_id:
                self.table.selectRow(row)
                break
