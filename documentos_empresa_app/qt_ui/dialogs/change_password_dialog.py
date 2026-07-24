from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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
from documentos_empresa_app.utils.common import APP_NAME, APP_TITLE, ValidationError


class ChangePasswordDialog(QDialog):
    """Forca a troca da senha padrao do administrador no primeiro login -
    a senha inicial ("admin") e publica (esta na documentacao do sistema),
    entao deixar como esta e um risco de seguranca (LGPD: seguranca no
    tratamento de dados pessoais)."""

    def __init__(self, services, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.password_changed = False

        self.setWindowTitle(f"{APP_TITLE} - Troca de senha obrigatoria")
        self.setWindowIcon(app_icon())
        self.setFixedWidth(420)
        self.setModal(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)

        card = Card()
        outer.addWidget(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)

        title = QLabel("Troque a senha padrao")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        subtitle = QLabel(
            "Este usuario ainda esta com a senha padrao de instalacao. Por seguranca, "
            "defina uma senha propria antes de continuar."
        )
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        layout.addSpacing(8)

        layout.addWidget(QLabel("Senha atual"))
        self.current_password_edit = QLineEdit()
        self.current_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.current_password_edit)

        layout.addWidget(QLabel("Nova senha"))
        self.new_password_edit = QLineEdit()
        self.new_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.new_password_edit)

        layout.addWidget(QLabel("Confirme a nova senha"))
        self.confirm_password_edit = QLineEdit()
        self.confirm_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.confirm_password_edit)
        layout.addSpacing(8)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        exit_button = make_button("Sair", "quiet")
        exit_button.clicked.connect(self.reject)
        buttons.addWidget(exit_button)
        confirm_button = make_button("Trocar senha", "primary")
        confirm_button.setDefault(True)
        confirm_button.clicked.connect(self.change_password)
        buttons.addWidget(confirm_button)
        layout.addLayout(buttons)

        self.current_password_edit.setFocus()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.change_password()
            return
        super().keyPressEvent(event)

    def change_password(self) -> None:
        new_password = self.new_password_edit.text()
        if new_password != self.confirm_password_edit.text():
            QMessageBox.critical(self, APP_NAME, "A confirmacao nao corresponde a nova senha.")
            return

        try:
            self.services.user_service.change_own_password(
                self.current_password_edit.text(), new_password
            )
        except ValidationError as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))
            self.current_password_edit.clear()
            return

        self.password_changed = True
        self.accept()
