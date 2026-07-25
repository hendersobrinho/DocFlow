from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QProgressBar, QVBoxLayout, QWidget

from documentos_empresa_app.qt_ui.theme import ThemeManager
from documentos_empresa_app.utils.common import APP_NAME
from documentos_empresa_app.utils.resources import get_icons_directory

WIDTH = 420
HEIGHT = 260
LOGO_SIZE = 68


class SplashScreen(QWidget):
    """Tela de carregamento exibida enquanto o app inicializa (banco, licenca, etc.)."""

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.SplashScreen,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(WIDTH, HEIGHT)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)

        card = QFrame()
        card.setObjectName("SplashCard")
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(32, 30, 32, 26)
        layout.setSpacing(6)
        layout.addStretch(1)

        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        pixmap = self._load_logo_pixmap()
        if not pixmap.isNull():
            logo_label.setPixmap(pixmap)
        layout.addWidget(logo_label)
        layout.addSpacing(14)

        title_label = QLabel(APP_NAME)
        title_label.setObjectName("SplashTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(title_label)

        self.status_label = QLabel("Iniciando...")
        self.status_label.setObjectName("SplashStatus")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.status_label)
        layout.addSpacing(16)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("SplashProgress")
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        layout.addWidget(self.progress_bar)

        layout.addStretch(1)

        self._apply_style(card)
        self._center_on_screen()

        self._fade_animation = QPropertyAnimation(self, b"windowOpacity")
        self._fade_animation.setDuration(260)
        self._fade_animation.setStartValue(0.0)
        self._fade_animation.setEndValue(1.0)
        self._fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _load_logo_pixmap(self) -> QPixmap:
        path = get_icons_directory() / "icon.png"
        if not path.exists():
            return QPixmap()
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return pixmap
        return pixmap.scaled(
            LOGO_SIZE,
            LOGO_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _apply_style(self, card: QFrame) -> None:
        t = ThemeManager.instance().tokens
        card.setStyleSheet(
            f"""
            QFrame#SplashCard {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {t["surface"]}, stop:1 {t["window"]});
                border: 1px solid {t["border_strong"]};
                border-radius: 18px;
            }}
            QLabel#SplashTitle {{
                color: {t["text"]};
                font-family: "Segoe UI";
                font-size: 17pt;
                font-weight: 700;
            }}
            QLabel#SplashStatus {{
                color: {t["muted"]};
                font-family: "Segoe UI";
                font-size: 9.5pt;
            }}
            QProgressBar#SplashProgress {{
                background: {t["border"]};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar#SplashProgress::chunk {{
                background: {t["accent"]};
                border-radius: 3px;
            }}
            """
        )

    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        x = geometry.x() + (geometry.width() - self.width()) // 2
        y = geometry.y() + (geometry.height() - self.height()) // 2
        self.move(x, y)

    def show_message(self, text: str) -> None:
        self.status_label.setText(text)
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
