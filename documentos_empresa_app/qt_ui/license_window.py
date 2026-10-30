from __future__ import annotations

import json

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QPlainTextEdit,
    QWidget,
)

from documentos_empresa_app.qt_ui.widgets.brand_dialog import BrandDialog
from documentos_empresa_app.qt_ui.widgets.common import make_button
from documentos_empresa_app.services.license_service import LicenseError, LicenseService
from documentos_empresa_app.utils.common import APP_NAME, APP_TITLE


class LicenseWindow(BrandDialog):
    def __init__(
        self,
        license_service: LicenseService,
        status_message: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Ativar o DocFlow", "Cole a licença recebida ou importe o arquivo.", panel_width=300, parent=parent)
        self.license_service = license_service
        self.license_activated = False

        self.setWindowTitle(f"{APP_TITLE} - Licença")
        self.resize(900, 520)

        self.add_heading("Licença", "Cole abaixo o conteúdo do arquivo de licença (JSON) ou importe o arquivo.")
        if status_message:
            self.show_message(status_message)
        self.add_message_area()

        self.license_text = QPlainTextEdit()
        self.license_text.setPlaceholderText('{"payload": {...}, "signature": "..."}')
        self.license_text.setStyleSheet('font-family: "JetBrains Mono", "Consolas", monospace; font-size: 9pt;')
        self.add_widget(self.license_text, 1)
        self.form_layout.addSpacing(8)

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
        self.form_layout.addLayout(buttons)

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
            QMessageBox.critical(self, APP_NAME, "Não foi possível ler o arquivo selecionado.")
            return
        self.license_text.setPlainText(content)

    def activate(self) -> None:
        raw_text = self.license_text.toPlainText().strip()
        if not raw_text:
            self.show_message("Cole ou importe o conteúdo da licença para continuar.")
            return

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            self.show_message("O conteúdo informado não é um JSON válido.")
            return

        try:
            self.license_service.save(parsed)
        except LicenseError as exc:
            self.show_message(str(exc))
            return

        self.license_activated = True
        QMessageBox.information(self, APP_NAME, "Licenca ativada com sucesso.")
        self.accept()
