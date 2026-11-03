from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLineEdit, QWidget

from documentos_empresa_app import __version__
from documentos_empresa_app.qt_ui.brand import TAGLINE
from documentos_empresa_app.qt_ui.dialogs.database_connection_dialog import prompt_database_connection_qt
from documentos_empresa_app.qt_ui.widgets.brand_dialog import BrandDialog, add_password_toggle
from documentos_empresa_app.qt_ui.widgets.common import make_button
from documentos_empresa_app.utils.common import APP_TITLE
from documentos_empresa_app.utils.helpers import ValidationError, load_login_preferences, save_login_preferences


class LoginWindow(BrandDialog):
    def __init__(self, services, parent: QWidget | None = None) -> None:
        super().__init__("", TAGLINE, panel_width=360, parent=parent)
        self.services = services
        self.authenticated_user: dict | None = None
        # Trocou a conexao pelo botao: quem abriu reconecta e mostra o login de novo.
        self.change_database_requested = False

        self.setWindowTitle(f"{APP_TITLE} - Entrar")
        self.setFixedSize(820, 520)

        self.add_heading("Entrar", "Use o seu usuário e senha do DocFlow.")

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Seu usuário")
        self.add_field("Usuário", self.username_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Sua senha")
        add_password_toggle(self.password_edit)
        self.add_field("Senha", self.password_edit)

        self.remember_check = QCheckBox("Manter conectado neste computador")
        self.add_widget(self.remember_check)
        self.form_layout.addSpacing(10)
        self.add_message_area()
        self.form_layout.addSpacing(6)

        self.login_button = make_button("Entrar", "primary")
        self.login_button.setDefault(True)
        self.login_button.clicked.connect(self.login)
        self.add_widget(self.login_button)

        exit_row = QHBoxLayout()
        exit_row.addStretch(1)
        database_button = make_button("Configurar banco de dados...", "quiet")
        database_button.setToolTip("Apontar para outro servidor/banco PostgreSQL (ex: computador reaproveitado).")
        database_button.clicked.connect(self.change_database)
        exit_row.addWidget(database_button)
        exit_button = make_button("Sair do DocFlow", "quiet")
        exit_button.clicked.connect(self.reject)
        exit_row.addWidget(exit_button)
        exit_row.addStretch(1)
        self.form_layout.addLayout(exit_row)
        self.form_layout.addStretch(1)

        db_manager = services.database_maintenance_service.db_manager
        self.add_footer(f"Banco: {db_manager.display_name}   ·   versão {__version__}")

        for edit in (self.username_edit, self.password_edit):
            edit.textEdited.connect(lambda _text: self.clear_message())

        preferences = load_login_preferences()
        self.username_edit.setText(preferences["username"])
        self.remember_check.setChecked(bool(preferences["remember_credential"]))
        if preferences["username"]:
            self.password_edit.setFocus()
        else:
            self.username_edit.setFocus()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.login()
            return
        super().keyPressEvent(event)

    def change_database(self) -> None:
        if prompt_database_connection_qt(self) is None:
            return
        self.change_database_requested = True
        self.reject()

    def login(self) -> None:
        previous_preferences = load_login_preferences()
        try:
            user = self.services.auth_service.authenticate(
                self.username_edit.text(), self.password_edit.text()
            )
        except ValidationError as exc:
            self.show_message(str(exc))
            self.password_edit.clear()
            self.password_edit.setFocus()
            return

        self.services.auth_service.revoke_remembered_session(previous_preferences["remembered_token"])

        remembered_token = None
        if self.remember_check.isChecked():
            remembered_token = self.services.auth_service.create_remembered_session(user["id"])

        save_login_preferences(
            user["username"],
            remember_credential=self.remember_check.isChecked(),
            remembered_token=remembered_token,
        )

        self.services.session_service.login(user, remembered_token=remembered_token)
        self.authenticated_user = user
        self.accept()
