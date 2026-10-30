from __future__ import annotations

import webbrowser

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from documentos_empresa_app import __version__
from documentos_empresa_app.qt_ui.brand import LOGO_HORIZONTAL_COR, LOGO_HORIZONTAL_NEGATIVO, TAGLINE, brand_pixmap
from documentos_empresa_app.qt_ui.icons import app_icon
from documentos_empresa_app.qt_ui.theme import ThemeManager, tokens
from documentos_empresa_app.qt_ui.widgets.common import make_button
from documentos_empresa_app.utils.common import APP_NAME

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

        dark = ThemeManager.instance().mode == "dark"
        logo = QLabel()
        pixmap = brand_pixmap(LOGO_HORIZONTAL_NEGATIVO if dark else LOGO_HORIZONTAL_COR, 46)
        if pixmap.isNull():
            logo.setText(APP_NAME)
            logo.setObjectName("PageTitle")
        else:
            logo.setPixmap(pixmap)
        layout.addWidget(logo)
        version_label = QLabel(f"Versão {__version__}")
        version_label.setObjectName("Muted")
        layout.addWidget(version_label)
        layout.addSpacing(10)

        tagline = QLabel(TAGLINE + ".")
        tagline.setWordWrap(True)
        layout.addWidget(tagline)
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
