from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QVBoxLayout, QWidget

from documentos_empresa_app.qt_ui.icons import app_icon
from documentos_empresa_app.utils.common import APP_NAME


class BusyDialog(QDialog):
    """Dialogo modal com barra de progresso indeterminada, usado para dar feedback
    visual durante operacoes demoradas que rodam em uma QThread de fundo (backup,
    restauracao, importacao de planilha, exportacao de relatorio, etc.)."""

    def __init__(self, message: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.setModal(True)
        self.setFixedWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(14)

        self.message_label = QLabel(message)
        self.message_label.setWordWrap(True)
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.message_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        layout.addWidget(self.progress_bar)

    def set_message(self, message: str) -> None:
        self.message_label.setText(message)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        event.ignore()
