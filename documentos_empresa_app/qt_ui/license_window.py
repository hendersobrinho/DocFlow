from __future__ import annotations

import json

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.icons import app_icon
from documentos_empresa_app.qt_ui.theme import tokens
from documentos_empresa_app.qt_ui.widgets.common import make_button
from documentos_empresa_app.services.license_service import LicenseError, LicenseService
from documentos_empresa_app.utils.common import APP_NAME, APP_TITLE


class LicenseWindow(QDialog):
    def __init__(
        self,
        license_service: LicenseService,
        status_message: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.license_service = license_service
        self.license_activated = False

        self.setWindowTitle(f"{APP_TITLE} - Licenca")
        self.setWindowIcon(app_icon())
        self.resize(620, 460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        instructions = QLabel(
            "Cole abaixo o conteudo do arquivo de licenca (JSON) ou importe o arquivo para ativar o sistema."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        if status_message:
            status_label = QLabel(status_message)
            status_label.setWordWrap(True)
            status_label.setStyleSheet(f'color: {tokens()["danger"]};')
            layout.addWidget(status_label)

        self.license_text = QPlainTextEdit()
        self.license_text.setPlaceholderText('{"payload": {...}, "signature": "..."}')
        layout.addWidget(self.license_text, 1)

        buttons = QHBoxLayout()
        import_button = make_button("Importar arquivo...")
        import_button.clicked.connect(self.import_file)
        buttons.addWidget(import_button)
        buttons.addStretch(1)
        cancel_button = make_button("Cancelar", "quiet")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(cancel_button)
        activate_button = make_button("Ativar licenca", "primary")
        activate_button.clicked.connect(self.activate)
        buttons.addWidget(activate_button)
        layout.addLayout(buttons)

    def import_file(self) -> None:
        file_path, _filter = QFileDialog.getOpenFileName(
            self,
            "Selecionar arquivo de licenca",
            "",
            "Arquivos JSON (*.json);;Todos os arquivos (*.*)",
        )
        if not file_path:
            return
        try:
            content = open(file_path, encoding="utf-8").read()
        except OSError:
            QMessageBox.critical(self, APP_NAME, "Nao foi possivel ler o arquivo selecionado.")
            return
        self.license_text.setPlainText(content)

    def activate(self) -> None:
        raw_text = self.license_text.toPlainText().strip()
        if not raw_text:
            QMessageBox.critical(self, APP_NAME, "Cole ou importe o conteudo da licenca para continuar.")
            return

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            QMessageBox.critical(self, APP_NAME, "O conteudo informado nao e um JSON valido.")
            return

        try:
            self.license_service.save(parsed)
        except LicenseError as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))
            return

        self.license_activated = True
        QMessageBox.information(self, APP_NAME, "Licenca ativada com sucesso.")
        self.accept()
