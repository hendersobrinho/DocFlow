from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QWidget

from documentos_empresa_app.qt_ui.widgets.brand_dialog import BrandDialog, add_password_toggle
from documentos_empresa_app.qt_ui.widgets.common import make_button
from documentos_empresa_app.utils.common import APP_TITLE, ValidationError


class ChangePasswordDialog(BrandDialog):
    """Forca a troca da senha padrao do administrador no primeiro login -
    a senha inicial ("admin") e publica (esta na documentacao do sistema),
    entao deixar como esta e um risco de seguranca (LGPD: seguranca no
    tratamento de dados pessoais)."""

    def __init__(self, services, parent: QWidget | None = None) -> None:
        super().__init__(
            "Primeiro acesso",
            "A senha de instalação é conhecida por todos. Troque agora para proteger os dados dos seus clientes.",
            panel_width=320,
            parent=parent,
        )
        self.services = services
        self.password_changed = False

        self.setWindowTitle(f"{APP_TITLE} - Troca de senha obrigatória")
        self.setFixedSize(800, 560)
        self.setModal(True)

        self.add_heading("Troque a senha padrão", "Defina uma senha própria antes de continuar.")

        self.current_password_edit = self._password_field("Senha atual")
        self.new_password_edit = self._password_field("Nova senha")
        self.confirm_password_edit = self._password_field("Confirme a nova senha")
        self.add_message_area()
        self.form_layout.addStretch(1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        exit_button = make_button("Sair", "quiet")
        exit_button.clicked.connect(self.reject)
        buttons.addWidget(exit_button)
        confirm_button = make_button("Trocar senha", "primary")
        confirm_button.setDefault(True)
        confirm_button.setMinimumWidth(150)
        confirm_button.clicked.connect(self.change_password)
        buttons.addWidget(confirm_button)
        self.form_layout.addLayout(buttons)

        self.current_password_edit.setFocus()

    def _password_field(self, label: str) -> QLineEdit:
        edit = QLineEdit()
        edit.setEchoMode(QLineEdit.EchoMode.Password)
        add_password_toggle(edit)
        edit.textEdited.connect(lambda _text: self.clear_message())
        self.add_field(label, edit)
        return edit

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.change_password()
            return
        super().keyPressEvent(event)

    def change_password(self) -> None:
        new_password = self.new_password_edit.text()
        if new_password != self.confirm_password_edit.text():
            self.show_message("A confirmação não é igual à nova senha.")
            self.confirm_password_edit.setFocus()
            return

        try:
            self.services.user_service.change_own_password(
                self.current_password_edit.text(), new_password
            )
        except ValidationError as exc:
            self.show_message(str(exc))
            self.current_password_edit.clear()
            self.current_password_edit.setFocus()
            return

        self.password_changed = True
        self.accept()
