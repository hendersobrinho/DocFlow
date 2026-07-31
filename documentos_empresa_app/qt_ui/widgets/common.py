from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


def make_button(text: str, variant: str | None = None, parent: QWidget | None = None) -> QPushButton:
    button = QPushButton(text, parent)
    if variant:
        button.setProperty("variant", variant)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def make_icon_button(
    icon: QIcon,
    tooltip: str,
    size: int,
    variant: str,
    parent: QWidget | None = None,
) -> QPushButton:
    button = QPushButton(parent)
    button.setProperty("variant", variant)
    button.setIcon(icon)
    button.setIconSize(QSize(int(size * 0.65), int(size * 0.65)))
    button.setFixedSize(size, size)
    button.setToolTip(tooltip)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


class SinglePageStackedWidget(QStackedWidget):
    """QStackedWidget normal usa a maior largura/altura minima entre TODAS as paginas
    para o proprio tamanho minimo, mesmo as escondidas - isso trava o redimensionamento
    da janela (e do dock de chat) no tamanho da pagina mais larga (Panorama), mesmo
    quando outra pagina bem mais estreita esta visivel. Aqui o minimo/preferido segue
    so a pagina atual."""

    def sizeHint(self) -> QSize:
        current = self.currentWidget()
        return current.sizeHint() if current is not None else super().sizeHint()

    def minimumSizeHint(self) -> QSize:
        current = self.currentWidget()
        return current.minimumSizeHint() if current is not None else super().minimumSizeHint()


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")


class KpiCard(QFrame):
    """Card compacto de indicador para o dashboard."""

    def __init__(self, label: str, accent_color: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("KpiCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(2)

        self.value_label = QLabel("-")
        self.value_label.setObjectName("KpiValue")
        if accent_color:
            self.value_label.setStyleSheet(f"color: {accent_color};")
        layout.addWidget(self.value_label)

        self.caption_label = QLabel(label)
        self.caption_label.setObjectName("KpiLabel")
        self.caption_label.setWordWrap(True)
        layout.addWidget(self.caption_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)

    def set_accent(self, color: str | None) -> None:
        self.value_label.setStyleSheet(f"color: {color};" if color else "")


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("PageTitle")
        layout.addWidget(self.title_label)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("PageSubtitle")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setVisible(bool(subtitle))
        layout.addWidget(self.subtitle_label)

    def set_subtitle(self, subtitle: str) -> None:
        self.subtitle_label.setText(subtitle)
        self.subtitle_label.setVisible(bool(subtitle))


class ToolbarRow(QWidget):
    """Linha horizontal de controles com espacamento padrao."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.layout_ = QHBoxLayout(self)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.layout_.setSpacing(8)

    def add(self, widget: QWidget) -> QWidget:
        self.layout_.addWidget(widget)
        return widget

    def add_stretch(self) -> None:
        self.layout_.addStretch(1)
