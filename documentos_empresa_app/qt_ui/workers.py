from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QWidget

from documentos_empresa_app.qt_ui.widgets.busy_dialog import BusyDialog


class CallableWorker(QObject):
    """Executa uma funcao sem argumentos em thread de fundo e emite o resultado."""

    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, func: Callable[[], Any]) -> None:
        super().__init__()
        self._func = func

    def run(self) -> None:
        try:
            result = self._func()
        except Exception as exc:  # pragma: no cover - salvaguarda da thread
            self.failed.emit(str(exc))
            return
        self.finished.emit(result)


class BlockingTaskRunner(QObject):
    """Roda uma funcao demorada em QThread mostrando um BusyDialog com barra de
    progresso indeterminada, para nao travar a interface sem feedback visual.

    O metodo `run` bloqueia o codigo chamador (via QDialog.exec) ate a tarefa
    terminar, mas a interface continua respondendo/pintando normalmente porque o
    trabalho pesado roda em outra thread - so o fluxo do chamador espera o resultado.
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._parent = parent
        self._thread: QThread | None = None
        self._worker: CallableWorker | None = None
        self._dialog: BusyDialog | None = None
        self._on_success: Callable[[Any], None] | None = None
        self._on_error: Callable[[str], None] | None = None

    def run(
        self,
        message: str,
        func: Callable[[], Any],
        on_success: Callable[[Any], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self._on_success = on_success
        self._on_error = on_error
        self._dialog = BusyDialog(message, self._parent)
        self._thread = QThread(self._parent)
        self._worker = CallableWorker(func)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        # Conectar direto a um metodo vinculado de self (nao a uma lambda) e essencial:
        # sinais de outra thread para uma lambda "solta" nao sao enfileirados para a
        # thread principal no PySide, rodam direto na thread de fundo e travam ao
        # chamar accept() num QDialog fora da thread da GUI.
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.failed.connect(self._on_worker_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)

        self._thread.start()
        self._dialog.exec()

    def _on_worker_finished(self, result: Any) -> None:
        if self._dialog is not None:
            self._dialog.accept()
        if self._on_success is not None:
            self._on_success(result)

    def _on_worker_failed(self, message: str) -> None:
        if self._dialog is not None:
            self._dialog.accept()
        if self._on_error is not None:
            self._on_error(message)
