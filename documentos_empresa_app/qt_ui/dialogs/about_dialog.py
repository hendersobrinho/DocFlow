from __future__ import annotations

import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from documentos_empresa_app import __version__
from documentos_empresa_app.qt_ui.icons import app_icon
from documentos_empresa_app.qt_ui.theme import tokens
from documentos_empresa_app.qt_ui.widgets.common import make_button
from documentos_empresa_app.utils.common import APP_NAME
from documentos_empresa_app.utils.resources import iter_icon_candidates

CONTACT_EMAIL = "hnd.lab.dev@gmail.com"
DEVELOPER_NAME = "Henderson Pereira S. Júnior"
SITE_DEVELOPER = "www.henderlab.com.br"
SITE_DEVELOPER_URL = "https://www.henderlab.com.br"


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Sobre o {APP_NAME}")
        self.setWindowIcon(app_icon())
        self.setFixedWidth(430)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)

        header = QHBoxLayout()
        icon_path = next((p for p in iter_icon_candidates() if p.suffix.lower() == ".png"), None)
        if icon_path:
            icon_label = QLabel()
            icon_label.setPixmap(
                QPixmap(str(icon_path)).scaled(
                    56, 56, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
            )
            header.addWidget(icon_label)

        title_block = QVBoxLayout()
        title_label = QLabel(APP_NAME)
        title_label.setObjectName("PageTitle")
        title_block.addWidget(title_label)
        version_label = QLabel(f"Versao {__version__}")
        version_label.setObjectName("Muted")
        title_block.addWidget(version_label)
        header.addLayout(title_block)
        header.addStretch(1)
        layout.addLayout(header)
        layout.addSpacing(10)

        layout.addWidget(QLabel("Controle mensal de documentos empresariais."))
        layout.addWidget(QLabel(f"Desenvolvido por: {DEVELOPER_NAME}."))
        layout.addWidget(QLabel(f"Contato: {CONTACT_EMAIL}"))

        site_label = QLabel(
            f'Site org: <a style="color: {tokens()["accent"]};" href="{SITE_DEVELOPER_URL}">{SITE_DEVELOPER}</a>'
        )
        site_label.setOpenExternalLinks(False)
        site_label.linkActivated.connect(lambda _url: webbrowser.open(SITE_DEVELOPER_URL))
        layout.addWidget(site_label)
        layout.addSpacing(12)

        buttons = QHBoxLayout()
        copy_button = make_button("Copiar email")
        copy_button.clicked.connect(self._copy_email)
        buttons.addWidget(copy_button)
        buttons.addStretch(1)
        close_button = make_button("Fechar", "quiet")
        close_button.clicked.connect(self.accept)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

    def _copy_email(self) -> None:
        QGuiApplication.clipboard().setText(CONTACT_EMAIL)
