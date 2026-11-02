from __future__ import annotations

import webbrowser

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.icons import app_icon
from documentos_empresa_app.qt_ui.widgets.common import make_button
from documentos_empresa_app.services.update_service import UpdateInfo, UpdateService, can_self_update
from documentos_empresa_app.utils.common import APP_NAME, ValidationError
from documentos_empresa_app.utils.diagnostics import get_diagnostics_logger


class _DownloadWorker(QObject):
    progress = Signal(int, int)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, service: UpdateService, info: UpdateInfo) -> None:
        super().__init__()
        self._service = service
        self._info = info

    def run(self) -> None:
        try:
            caminho = self._service.download(self._info, on_progress=lambda feito, total: self.progress.emit(feito, total))
        except ValidationError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:  # pragma: no cover - salvaguarda da thread
            get_diagnostics_logger().exception("ATUALIZACAO_ERRO_INESPERADO | erro=%s", exc)
            self.failed.emit("Erro inesperado ao baixar a atualização - veja o log de diagnóstico.")
            return
        self.finished.emit(caminho)


class UpdateDialog(QDialog):
    """Mostra a versao nova e o que mudou; "Atualizar agora" baixa o instalador, confere,
    fecha o DocFlow e instala - o sistema abre sozinho de novo no fim."""

    def __init__(self, service: UpdateService, info: UpdateInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.info = info
        self._thread: QThread | None = None
        self._worker: _DownloadWorker | None = None
        self.installing = False  # quem abriu fecha o DocFlow quando isto fica True
        self.setWindowTitle(f"Atualizar o {APP_NAME}")
        self.setWindowIcon(app_icon())
        self.resize(560, 460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(10)
        titulo = QLabel(f"Versão {info.versao} disponível")
        titulo.setObjectName("PageTitle")
        layout.addWidget(titulo)
        atual = QLabel(f"Você está na versão {service.current_version}. Seus dados não são alterados pela atualização.")
        atual.setObjectName("Muted")
        atual.setWordWrap(True)
        layout.addWidget(atual)

        self.notas = QTextBrowser()
        self.notas.setOpenExternalLinks(True)
        self.notas.setMarkdown(info.notas or "_Sem descrição nesta versão._")
        layout.addWidget(self.notas, 1)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        self.status_label = QLabel(
            "Ao atualizar, o DocFlow fecha, instala a versão nova e abre de novo sozinho."
            if can_self_update()
            else "Você está rodando pelo código-fonte: baixe o instalador pela página da versão."
        )
        self.status_label.setObjectName("Muted")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        botoes = QHBoxLayout()
        self.pagina_button = make_button("Ver no GitHub", "quiet")
        self.pagina_button.clicked.connect(lambda: webbrowser.open(info.pagina))
        self.pagina_button.setEnabled(bool(info.pagina))
        botoes.addWidget(self.pagina_button)
        botoes.addStretch(1)
        self.depois_button = make_button("Depois")
        self.depois_button.clicked.connect(self.reject)
        botoes.addWidget(self.depois_button)
        self.atualizar_button = make_button("Atualizar agora", "primary")
        self.atualizar_button.clicked.connect(self.start_update)
        self.atualizar_button.setEnabled(can_self_update())
        botoes.addWidget(self.atualizar_button)
        layout.addLayout(botoes)

    def start_update(self) -> None:
        self.atualizar_button.setEnabled(False)
        self.depois_button.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.status_label.setText("Baixando a atualização...")
        self._thread = QThread(self)
        self._worker = _DownloadWorker(self.service, self.info)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_downloaded)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()

    def _on_progress(self, feito: int, total: int) -> None:
        if total > 0:
            self.progress.setRange(0, 1000)
            self.progress.setValue(int(feito * 1000 / total))
            self.status_label.setText(f"Baixando a atualização... {feito / 1048576:.0f} de {total / 1048576:.0f} MB")

    def _on_failed(self, message: str) -> None:
        self.progress.setVisible(False)
        self.status_label.setText(message)
        self.atualizar_button.setEnabled(True)
        self.depois_button.setEnabled(True)
        QMessageBox.warning(self, APP_NAME, message)

    def _on_downloaded(self, caminho) -> None:
        self.progress.setRange(0, 1000)
        self.progress.setValue(1000)
        self.status_label.setText("Instalando... o DocFlow vai fechar e abrir de novo.")
        try:
            self.service.install(caminho)
        except OSError as exc:
            self._on_failed(f"Não foi possível iniciar o instalador: {exc}")
            return
        self.installing = True
        self.accept()
