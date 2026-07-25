from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.icons import app_icon
from documentos_empresa_app.qt_ui.widgets.common import Card, make_button
from documentos_empresa_app.utils.common import APP_NAME, APP_TITLE
from documentos_empresa_app.utils.helpers import ValidationError, load_login_preferences, save_login_preferences


class LoginWindow(QDialog):
    def __init__(self, services, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.authenticated_user: dict | None = None

        self.setWindowTitle(f"{APP_TITLE} - Login")
        self.setWindowIcon(app_icon())
        self.setFixedWidth(420)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)

        card = Card()
        outer.addWidget(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)

        title = QLabel(APP_NAME)
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        subtitle = QLabel("Informe nome de usuario e senha para entrar no sistema.")
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        layout.addSpacing(8)

        layout.addWidget(QLabel("Nome de usuario"))
        self.username_edit = QLineEdit()
        layout.addWidget(self.username_edit)

        layout.addWidget(QLabel("Senha"))
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.password_edit)

        self.remember_check = QCheckBox("Lembrar credencial neste usuario do computador")
        layout.addWidget(self.remember_check)
        layout.addSpacing(8)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        exit_button = make_button("Sair", "quiet")
        exit_button.clicked.connect(self.reject)
        buttons.addWidget(exit_button)
        login_button = make_button("Entrar", "primary")
        login_button.setDefault(True)
        login_button.clicked.connect(self.login)
        buttons.addWidget(login_button)
        layout.addLayout(buttons)

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

    def login(self) -> None:
        previous_preferences = load_login_preferences()
        try:
            user = self.services.auth_service.authenticate(
                self.username_edit.text(), self.password_edit.text()
            )
        except ValidationError as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))
            self.password_edit.clear()
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
