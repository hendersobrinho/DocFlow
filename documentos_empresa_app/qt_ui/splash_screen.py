from __future__ import annotations

from PySide6.QtCore import QElapsedTimer, QEasingCurve, QPropertyAnimation, Qt, QThread
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from documentos_empresa_app.qt_ui.brand import TAGLINE, BrandPanel

WIDTH = 560
HEIGHT = 360


class SplashScreen(QWidget):
    """Tela de carregamento exibida enquanto o app inicializa (banco, sessao...): o painel
    da marca com as trilhas entrando no simbolo, a frase e o status com a barra em ciano."""

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.SplashScreen,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(WIDTH, HEIGHT)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.panel = BrandPanel("", TAGLINE, corner_radius=20, show_progress=True)
        self.panel.set_footer("Iniciando...")
        layout.addWidget(self.panel)

        self._center_on_screen()
        self._fade_animation = QPropertyAnimation(self, b"windowOpacity")
        self._fade_animation.setDuration(260)
        self._fade_animation.setStartValue(0.0)
        self._fade_animation.setEndValue(1.0)
        self._fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        x = geometry.x() + (geometry.width() - self.width()) // 2
        y = geometry.y() + (geometry.height() - self.height()) // 2
        self.move(x, y)

    def show_message(self, text: str, progress: float | None = None) -> None:
        """Atualiza o status (e a barra, de 0 a 1). Da um instante para a tela se desenhar
        antes do trabalho pesado seguinte - sem isso a janela congela no meio da animacao."""
        self.panel.set_footer(text)
        if progress is not None:
            self.panel.set_progress(progress)
        self._pump(40)

    def show_animated(self) -> None:
        if self.isVisible() and self.windowOpacity() > 0.99:
            return
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self._fade_animation.start()
        self._pump(self._fade_animation.duration())

    def finish(self, window: QWidget | None = None) -> None:
        self.panel.set_progress(1.0)
        self.panel.set_footer("Pronto!")
        self._pump(220)
        if window is not None:
            window.show()
            window.raise_()
            window.activateWindow()
        self.close()

    @staticmethod
    def _pump(milliseconds: int) -> None:
        relogio = QElapsedTimer()
        relogio.start()
        while relogio.elapsed() < milliseconds:
            QApplication.processEvents()
            QThread.msleep(10)
