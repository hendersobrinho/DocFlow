"""Identidade visual do DocFlow (docflow-identidade/LEIA-ME.md): cores da marca, fontes,
logos em SVG e o painel de marca usado nas telas de entrada (carregamento, banco, login).

O simbolo e um D (o escritorio) abracando um documento; as "trilhas" que entram no D sao o
fluxo levando cada arquivo para o lugar certo. O BrandPanel desenha isso animado."""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QFontMetricsF,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QSizePolicy, QWidget

from documentos_empresa_app.utils.resources import get_runtime_base_path

# Cores da marca ---------------------------------------------------------------------

NAVY = "#203461"         # base, fundos, o D
CIANO = "#4BBDCD"        # identificado, ativo, foco (texto em cima: navy)
LARANJA = "#F9B259"      # pendencia, destaque pontual (texto em cima: navy)
NAVY_900 = "#0F1A33"
NAVY_800 = "#16254A"
NAVY_600 = "#2E4A85"
NAVY_300 = "#8C9BC0"
NEVOA = "#F2F5FA"
LINHA = "#DCE3EE"
GRAFITE = "#1B2335"
CINZA = "#5E6B82"

TAGLINE = "Controle e organização de documentos para escritórios contábeis"

# Fontes -----------------------------------------------------------------------------

FONT_UI = "Inter"            # interface
FONT_BRAND = "Sora"          # marca e titulos
FONT_MONO = "JetBrains Mono"  # CNPJ, competencias, numeros
FONT_UI_FALLBACK = "Segoe UI"

# Fontes estaticas (um arquivo por peso): o Qt nao aplica o peso em fonte variavel, entao
# os pesos usados foram gerados a partir das variaveis do Google Fonts (licenca OFL ao lado).


def assets_dir(*parts: str) -> Path:
    return get_runtime_base_path().joinpath("assets", *parts)


@lru_cache(maxsize=1)
def load_brand_fonts() -> tuple[str, ...]:
    """Registra as fontes da marca (ficam em assets/fonts, licenca OFL). Chamado uma vez;
    sem os arquivos, o tema cai para Segoe UI / a fonte do sistema."""
    families: list[str] = []
    for path in sorted(assets_dir("fonts").glob("*.ttf")):
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id >= 0:
            families.extend(QFontDatabase.applicationFontFamilies(font_id))
    return tuple(families)


def brand_font(size_pt: float, weight: QFont.Weight = QFont.Weight.Normal, family: str = FONT_BRAND) -> QFont:
    font = QFont(family)
    font.setPointSizeF(size_pt)
    font.setWeight(weight)
    if family == FONT_BRAND:
        font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 98)  # tracking -2% do wordmark
    return font


# Logos ------------------------------------------------------------------------------

SIMBOLO_COR = "docflow-simbolo-cor.svg"
SIMBOLO_NEGATIVO = "docflow-simbolo-negativo.svg"
LOGO_HORIZONTAL_COR = "docflow-logo-horizontal-cor.svg"
LOGO_HORIZONTAL_NEGATIVO = "docflow-logo-horizontal-negativo.svg"
LOGO_VERTICAL_COR = "docflow-logo-vertical-cor.svg"
LOGO_VERTICAL_NEGATIVO = "docflow-logo-vertical-negativo.svg"


@lru_cache(maxsize=64)
def _renderer(filename: str) -> QSvgRenderer | None:
    path = assets_dir("brand", filename)
    if not path.exists():
        return None
    renderer = QSvgRenderer(str(path))
    return renderer if renderer.isValid() else None


def brand_pixmap(filename: str, height: int, device_pixel_ratio: float | None = None) -> QPixmap:
    """Logo/simbolo da marca na altura pedida, nitido em tela de alta densidade (o SVG e
    desenhado na resolucao real da tela)."""
    renderer = _renderer(filename)
    if renderer is None or height <= 0:
        return QPixmap()
    if device_pixel_ratio is None:
        app = QApplication.instance()
        device_pixel_ratio = app.devicePixelRatio() if app else 1.0
    size = renderer.defaultSize()
    width = round(height * size.width() / max(size.height(), 1))
    pixmap = QPixmap(QSize(round(width * device_pixel_ratio), round(height * device_pixel_ratio)))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(device_pixel_ratio)
    return pixmap


def paint_brand_svg(painter: QPainter, filename: str, rect: QRectF) -> None:
    """Desenha o SVG da marca dentro de rect, mantendo a proporcao (centralizado)."""
    renderer = _renderer(filename)
    if renderer is None:
        return
    size = renderer.defaultSize()
    scale = min(rect.width() / size.width(), rect.height() / size.height())
    w, h = size.width() * scale, size.height() * scale
    renderer.render(painter, QRectF(rect.x() + (rect.width() - w) / 2, rect.y() + (rect.height() - h) / 2, w, h))


# Painel de marca ----------------------------------------------------------------------


class BrandPanel(QWidget):
    """Fundo navy com o brilho radial da capa, as trilhas entrando no simbolo e, embaixo,
    titulo e frase. As trilhas andam devagar (animacao leve, ~30 fps) enquanto o painel
    estiver visivel; animated=False deixa estatico (testes, telas pequenas)."""

    def __init__(
        self,
        title: str = "",
        subtitle: str = TAGLINE,
        *,
        animated: bool = True,
        show_wordmark: bool = True,
        corner_radius: float = 0.0,
        show_progress: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.title = title
        self.subtitle = subtitle
        self.show_wordmark = show_wordmark
        self.corner_radius = corner_radius
        self.show_progress = show_progress
        self.footer_text = ""
        self._phase = 0.0
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(260, 260)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._animated = animated

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._animated:
            self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._timer.stop()
        super().hideEvent(event)

    def _tick(self) -> None:
        self._phase = (self._phase + 0.006) % 1.0
        self.update()

    def set_footer(self, text: str) -> None:
        """Linha de status no rodape (ex: "Conectando ao banco de dados...")."""
        self.footer_text = text
        self.update()

    def set_texts(self, title: str, subtitle: str | None = None) -> None:
        self.title = title
        if subtitle is not None:
            self.subtitle = subtitle
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        if self.corner_radius:
            clip = QPainterPath()
            clip.addRoundedRect(rect, self.corner_radius, self.corner_radius)
            painter.setClipPath(clip)
        painter.fillRect(rect, QColor(NAVY))

        # Brilho radial (como na capa), deslocado para cima e para a direita.
        glow = QRadialGradient(QPointF(rect.width() * 0.78, rect.height() * 0.22), rect.width() * 0.75)
        glow.setColorAt(0.0, QColor(46, 74, 133, 150))
        glow.setColorAt(0.55, QColor(46, 74, 133, 40))
        glow.setColorAt(1.0, QColor(32, 52, 97, 0))
        painter.fillRect(rect, glow)

        # Linhas discretas de "documento" ao fundo, a direita (textura da capa).
        painter.setPen(Qt.PenStyle.NoPen)
        linhas = [(0.58, 0.12, 0.36), (0.66, 0.17, 0.26)]
        if not (self.show_progress or self.footer_text):
            linhas += [(0.55, 0.86, 0.40), (0.68, 0.91, 0.22)]  # embaixo so sem a barra de status
        for i, (fx, fy, fw) in enumerate(linhas):
            painter.setBrush(QColor(255, 255, 255, 14 if i % 2 else 18))
            painter.drawRoundedRect(QRectF(rect.width() * fx, rect.height() * fy, rect.width() * fw, 8), 4, 4)

        # Simbolo + trilhas no centro do terco de cima.
        symbol_h = min(rect.height() * 0.24, rect.width() * 0.30, 150)
        symbol_w = symbol_h * 336 / 320
        center_y = rect.height() * (0.40 if (self.title or self.subtitle) else 0.5)
        symbol_rect = QRectF((rect.width() - symbol_w) / 2 + symbol_w * 0.12, center_y - symbol_h / 2, symbol_w, symbol_h)
        self._paint_tracks(painter, symbol_rect)
        paint_brand_svg(painter, SIMBOLO_NEGATIVO, symbol_rect)

        y = symbol_rect.bottom() + symbol_h * 0.34
        if self.show_wordmark:
            y = self._paint_wordmark(painter, rect, y, symbol_h)
        if self.title:
            painter.setFont(brand_font(max(11.0, symbol_h / 9.5), QFont.Weight.DemiBold))
            painter.setPen(QColor("#FFFFFF"))
            title_rect = QRectF(24, y, rect.width() - 48, symbol_h * 0.32)
            painter.drawText(title_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, self.title)
            y = title_rect.bottom() + 4
        if self.subtitle:
            font = QFont(FONT_UI)
            font.setPointSizeF(max(9.0, symbol_h / 15))
            painter.setFont(font)
            painter.setPen(QColor(200, 211, 235))
            painter.drawText(
                QRectF(32, y, rect.width() - 64, rect.height() - y - 16),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                self.subtitle,
            )
        if self.footer_text or self.show_progress:
            self._paint_footer(painter, rect)
        painter.end()

    def _paint_footer(self, painter: QPainter, rect: QRectF) -> None:
        """Status em texto e barra indeterminada em ciano no pe do painel."""
        bottom = rect.height() - 22
        if self.show_progress:
            track = QRectF(40, bottom, rect.width() - 80, 4)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 28))
            painter.drawRoundedRect(track, 2, 2)
            segment = track.width() * 0.28
            x = track.left() - segment + (track.width() + segment) * ((self._phase * 2.2) % 1.0)
            left, right = max(track.left(), x), min(track.right(), x + segment)
            if right > left:
                gradient = QLinearGradient(left, 0, right, 0)
                gradient.setColorAt(0.0, QColor(75, 189, 205, 40))
                gradient.setColorAt(1.0, QColor(CIANO))
                painter.setBrush(gradient)
                painter.drawRoundedRect(QRectF(left, track.top(), right - left, track.height()), 2, 2)
            bottom -= 12
        if self.footer_text:
            font = QFont(FONT_UI)
            font.setPointSizeF(9)
            painter.setFont(font)
            painter.setPen(QColor(NAVY_300))
            painter.drawText(QRectF(24, bottom - 22, rect.width() - 48, 18), Qt.AlignmentFlag.AlignHCenter, self.footer_text)

    def _paint_wordmark(self, painter: QPainter, rect: QRectF, y: float, symbol_h: float) -> float:
        """ "Doc" SemiBold branco + "Flow" Light ciano, como no logo."""
        size = max(16.0, symbol_h / 3.6)
        doc_font = brand_font(size, QFont.Weight.DemiBold)
        flow_font = brand_font(size, QFont.Weight.Light)
        doc_w = QFontMetricsF(doc_font).horizontalAdvance("Doc")
        flow_w = QFontMetricsF(flow_font).horizontalAdvance("Flow")
        height = QFontMetricsF(doc_font).height()
        x = (rect.width() - doc_w - flow_w) / 2
        painter.setFont(doc_font)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(QRectF(x, y, doc_w + 2, height), Qt.AlignmentFlag.AlignLeft, "Doc")
        painter.setFont(flow_font)
        painter.setPen(QColor(CIANO))
        painter.drawText(QRectF(x + doc_w, y, flow_w + 2, height), Qt.AlignmentFlag.AlignLeft, "Flow")
        return y + height + symbol_h * 0.12

    def _paint_tracks(self, painter: QPainter, symbol_rect: QRectF) -> None:
        """As duas trilhas da capa entrando no D: uma branca (o arquivo) e uma laranja (o
        dado extraido), com um brilho que corre da esquerda para o simbolo."""
        unit = symbol_rect.height() / 320
        left_end = symbol_rect.left() + 18 * unit
        tracks = (
            (symbol_rect.top() + 236 * unit, 22 * unit, QColor(255, 255, 255), 0.0),
            (symbol_rect.top() + 280 * unit, 22 * unit, QColor(LARANJA), 0.37),
        )
        start = max(0.0, symbol_rect.left() - symbol_rect.width() * 1.9)
        for y, thickness, color, offset in tracks:
            length = left_end - start
            gradient = QLinearGradient(start, y, left_end, y)
            transparent = QColor(color)
            transparent.setAlpha(0)
            gradient.setColorAt(0.0, transparent)
            soft = QColor(color)
            soft.setAlpha(110)
            gradient.setColorAt(0.75, soft)
            gradient.setColorAt(1.0, color)
            path = QPainterPath()
            path.addRoundedRect(QRectF(start, y - thickness / 2, length, thickness), thickness / 2, thickness / 2)
            painter.fillPath(path, gradient)
            # Pulso que corre pela trilha (o "arquivo chegando").
            t = (self._phase + offset) % 1.0
            eased = 1 - math.pow(1 - t, 2)
            px = start + length * eased
            pulse = QRadialGradient(QPointF(px, y), thickness * 2.4)
            glow = QColor(color)
            glow.setAlpha(int(140 * math.sin(math.pi * t)))
            pulse.setColorAt(0.0, glow)
            pulse.setColorAt(1.0, transparent)
            painter.setBrush(pulse)
            painter.drawEllipse(QPointF(px, y), thickness * 2.4, thickness * 2.4)
