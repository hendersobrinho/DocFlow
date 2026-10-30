from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
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

    def show_message(self, text: str) -> None:
        self.panel.set_footer(text)
        QApplication.processEvents()

    def show_animated(self) -> None:
        self.setWindowOpacity(0.0)
        self.show()
        self._fade_animation.start()
        QApplication.processEvents()

    def finish(self, window: QWidget | None = None) -> None:
        if window is not None:
            window.show()
        self.close()
