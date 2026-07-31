from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QTransform
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

MAX_BUBBLE_WIDTH = 360
SPINNER_SIZE = 20
SPINNER_INTERVAL_MS = 35
SPINNER_STEP_DEGREES = 8


class SpinningIcon(QLabel):
    """Reaproveita a logo do agente como spinner - roda um QPixmap raster
    (renderizado uma vez a partir do QIcon svg) num QTimer simples. So gira de fato
    enquanto a chamada a IA roda numa QThread de fundo - numa chamada sincrona no
    thread da UI o timer nunca teria chance de disparar."""

    def __init__(self, icon: QIcon, size: int = SPINNER_SIZE, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._base_pixmap = icon.pixmap(size, size)
        self._angle = 0
        self.setFixedSize(size, size)

        self._timer = QTimer(self)
        self._timer.setInterval(SPINNER_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._render_frame()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        self._angle = (self._angle + SPINNER_STEP_DEGREES) % 360
        self._render_frame()

    def _render_frame(self) -> None:
        rotated = self._base_pixmap.transformed(
            QTransform().rotate(self._angle), Qt.TransformationMode.SmoothTransformation
        )
        x = (rotated.width() - self._base_pixmap.width()) // 2
        y = (rotated.height() - self._base_pixmap.height()) // 2
        self.setPixmap(rotated.copy(x, y, self._base_pixmap.width(), self._base_pixmap.height()))


class ThinkingIndicator(QWidget):
    """Linha "esta pensando..." com a logo girando, mostrada do lado esquerdo (igual
    uma mensagem do agente) enquanto se espera a resposta da IA."""

    def __init__(self, icon: QIcon, label_text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._spinner = SpinningIcon(icon)
        layout.addWidget(self._spinner)

        label = QLabel(label_text)
        label.setObjectName("ChatSystemMessage")
        layout.addWidget(label)

    def stop(self) -> None:
        self._spinner.stop()


class ChatBubble(QFrame):
    def __init__(self, text: str, role: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ChatBubbleUser" if role == "user" else "ChatBubbleAgent")
        self.setMaximumWidth(MAX_BUBBLE_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Minimum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(label)


class ChatTranscript(QScrollArea):
    """Lista de mensagens em formato de balao de conversa - usuario e agente em lados
    opostos, mensagens de sistema (cancelamento/erro/confirmacao) centralizadas e sem
    balao. Widgets simples empilhados num QVBoxLayout - conversas por documento sao
    curtas, nao precisa de model/view nem virtualizacao."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        self.setWidget(content)
        self._layout = QVBoxLayout(content)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(10)
        self._layout.addStretch(1)
        self._thinking_widget: ThinkingIndicator | None = None
        self._thinking_row: QHBoxLayout | None = None

    def add_user_message(self, text: str) -> None:
        self._add_row(ChatBubble(text, "user"), align_right=True)

    def add_agent_message(self, text: str) -> None:
        self._add_row(ChatBubble(text, "agent"), align_right=False)

    def show_thinking(self, icon: QIcon, label_text: str) -> None:
        self.hide_thinking()
        self._thinking_widget = ThinkingIndicator(icon, label_text)
        self._thinking_row = self._add_row(self._thinking_widget, align_right=False)

    def hide_thinking(self) -> None:
        if self._thinking_widget is None:
            return
        self._thinking_widget.stop()
        self._remove_row(self._thinking_row)
        self._thinking_widget = None
        self._thinking_row = None

    def add_system_message(self, text: str) -> None:
        label = QLabel(text)
        label.setObjectName("ChatSystemMessage")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(label)
        row.addStretch(1)
        self._insert_row(row)

    def clear(self) -> None:
        self.hide_thinking()
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
                continue
            layout = item.layout()
            if layout is not None:
                self._clear_layout(layout)

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _add_row(self, widget: QWidget, *, align_right: bool) -> QHBoxLayout:
        row = QHBoxLayout()
        if align_right:
            row.addStretch(1)
            row.addWidget(widget)
        else:
            row.addWidget(widget)
            row.addStretch(1)
        self._insert_row(row)
        return row

    def _insert_row(self, row: QHBoxLayout) -> None:
        self._layout.insertLayout(self._layout.count() - 1, row)
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _remove_row(self, row: QHBoxLayout) -> None:
        for i in range(self._layout.count()):
            item = self._layout.itemAt(i)
            if item.layout() is row:
                self._layout.takeAt(i)
                self._clear_layout(row)
                row.deleteLater()
                break

    def _scroll_to_bottom(self) -> None:
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())
