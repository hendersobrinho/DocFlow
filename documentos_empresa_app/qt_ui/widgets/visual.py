"""Pecas visuais desenhadas a mao (QPainter), usadas nas telas de acompanhamento:

- PillDelegate: o texto de uma celula vira uma "pilula" colorida (status, acao, situacao);
- ProgressDelegate: barra de progresso segmentada dentro da celula (recebido/pendente/...);
- PipelineBar: o funil da cobranca (Verificar > Cobrar > Recobrar > Aguardando > Pessoa),
  com contagem em cada etapa e clique para filtrar;
- YearMap: mapa de calor documento x mes, o "panorama" de uma empresa.

Tudo le as cores de theme.tokens() na hora de pintar, entao segue o modo claro/escuro."""

from __future__ import annotations

from functools import lru_cache
from typing import Callable

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.theme import status_colors, tokens
from documentos_empresa_app.utils.common import ValidationError, format_utc_timestamp

PROGRESS_ROLE = Qt.ItemDataRole.UserRole + 7


def mix(color: str, other: str, amount: float) -> QColor:
    """Mistura duas cores (amount=0 -> color, 1 -> other). Usado para fundos suaves."""
    a, b = QColor(color), QColor(other)
    return QColor(
        round(a.red() + (b.red() - a.red()) * amount),
        round(a.green() + (b.green() - a.green()) * amount),
        round(a.blue() + (b.blue() - a.blue()) * amount),
    )


def soft_pair(color: str) -> tuple[QColor, QColor]:
    """(fundo, texto) de uma pilula na cor dada, no tema atual."""
    t = tokens()
    dark = QColor(t["window"]).lightness() < 128
    background = mix(color, t["surface"], 0.78 if dark else 0.86)
    # No escuro o texto clareia um pouco; no claro escurece, para manter o contraste.
    foreground = mix(color, "#FFFFFF", 0.25) if dark else mix(color, t["text"], 0.25)
    return background, foreground


# Celulas ---------------------------------------------------------------------------


class _PaintedCellDelegate(QStyledItemDelegate):
    """Base: pinta o fundo normal da celula (selecao, linha alternada) sem o texto."""

    def _paint_background(self, painter: QPainter, option: QStyleOptionViewItem, index) -> QStyleOptionViewItem:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        style = opt.widget.style() if opt.widget else None
        if style:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        opt.text = text
        return opt


class PillDelegate(_PaintedCellDelegate):
    """Desenha o texto da celula como uma pilula. 'color_for(texto)' devolve a cor base
    (ou None para texto comum); 'pair_for(texto)' pode devolver (fundo, texto) prontos."""

    def __init__(
        self,
        color_for: Callable[[str], str | None] | None = None,
        pair_for: Callable[[str], tuple[str, str] | None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.color_for = color_for
        self.pair_for = pair_for

    def _colors(self, text: str) -> tuple[QColor, QColor] | None:
        if self.pair_for:
            pair = self.pair_for(text)
            if pair:
                return QColor(pair[0]), QColor(pair[1])
        if self.color_for:
            color = self.color_for(text)
            if color:
                return soft_pair(color)
        return None

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        opt = self._paint_background(painter, option, index)
        text = opt.text
        colors = self._colors(text) if text and text not in ("-", "") else None
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(6, 5, -6, -5)
        if colors is None:
            painter.setPen(QColor(tokens()["muted"]))
            painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
            painter.restore()
            return
        background, foreground = colors
        font = QFont(opt.font)
        font.setWeight(QFont.Weight.DemiBold)
        metrics = QFontMetrics(font)
        width = min(metrics.horizontalAdvance(text) + 20, rect.width())
        pill = QRectF(rect.left(), rect.center().y() - 11, width, 22)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(pill, 11, 11)
        painter.setPen(foreground)
        painter.setFont(font)
        elided = metrics.elidedText(text, Qt.TextElideMode.ElideRight, int(pill.width()) - 16)
        painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, elided)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        base = super().sizeHint(option, index)
        return QSize(base.width() + 24, max(base.height(), 32))


class ProgressDelegate(_PaintedCellDelegate):
    """Barra segmentada. A celula guarda em PROGRESS_ROLE uma lista de (valor, cor) e o
    total; o texto da celula aparece a direita (ex: "3/5")."""

    BAR_WIDTH = 120

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        opt = self._paint_background(painter, option, index)
        data = index.data(PROGRESS_ROLE)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = tokens()
        rect = option.rect.adjusted(8, 0, -8, 0)
        bar = QRectF(rect.left(), rect.center().y() - 4, min(self.BAR_WIDTH, rect.width() - 44), 8)
        path = QPainterPath()
        path.addRoundedRect(bar, 4, 4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.fillPath(path, QColor(t["border"]))
        if data:
            segments, total = data
            painter.setClipPath(path)
            x = bar.left()
            for value, color in segments:
                if total <= 0 or value <= 0:
                    continue
                width = bar.width() * value / total
                painter.fillRect(QRectF(x, bar.top(), width, bar.height()), QColor(color))
                x += width
            painter.setClipping(False)
        painter.setPen(QColor(t["text"]))
        text_rect = QRect(int(bar.right()) + 8, rect.top(), rect.right() - int(bar.right()) - 8, rect.height())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, opt.text)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        base = super().sizeHint(option, index)
        return QSize(self.BAR_WIDTH + 64, max(base.height(), 32))


# Funil da cobranca -----------------------------------------------------------------


class StageCard(QFrame):
    clicked = Signal(str)

    def __init__(self, key: str, label: str, hint: str, color_token: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.key = key
        self.color_token = color_token
        self.selected = False
        self.count = 0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(96)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 12, 10)
        layout.setSpacing(0)
        top = QHBoxLayout()
        self.value_label = QLabel("0")
        top.addWidget(self.value_label)
        top.addStretch(1)
        layout.addLayout(top)
        self.title_label = QLabel(label)
        layout.addWidget(self.title_label)
        self.hint_label = QLabel(hint)
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)
        self.setToolTip(hint)
        self._restyle()

    @property
    def color(self) -> str:
        return tokens()[self.color_token]

    def set_count(self, count: int) -> None:
        self.count = count
        self.value_label.setText(str(count))
        self._restyle()

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self._restyle()

    def _restyle(self) -> None:
        t = tokens()
        active = self.count > 0
        number_color = self.color if active else t["muted"]
        self.value_label.setStyleSheet(f"font-size: 22pt; font-weight: 700; color: {number_color}; background: transparent;")
        self.title_label.setStyleSheet(f"font-weight: 600; color: {t['text']}; background: transparent;")
        self.hint_label.setStyleSheet(f"color: {t['muted']}; font-size: 8.5pt; background: transparent;")
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        t = tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        background = soft_pair(self.color)[0] if self.selected else QColor(t["surface"])
        border = QColor(self.color) if self.selected else QColor(t["border"])
        painter.setPen(QPen(border, 1.5 if self.selected else 1))
        painter.setBrush(background)
        painter.drawRoundedRect(rect, 12, 12)
        # Faixa colorida a esquerda: identifica a etapa mesmo com zero itens.
        stripe = QPainterPath()
        stripe.addRoundedRect(QRectF(rect.left(), rect.top(), 6, rect.height()), 3, 3)
        painter.fillPath(stripe, QColor(self.color if self.count else t["border_strong"]))
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.key)
        super().mousePressEvent(event)


class _Chevron(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(16)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(tokens()["border_strong"]), 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        cx, cy = self.width() / 2, self.height() / 2
        painter.drawPolyline([QPointF(cx - 3, cy - 7), QPointF(cx + 3, cy), QPointF(cx - 3, cy + 7)])
        painter.end()


class PipelineBar(QWidget):
    """Etapas lado a lado com setas entre elas. Cada etapa e (chave, titulo, dica, token de
    cor do tema). Clique numa etapa filtra por ela; clique de novo volta para tudo ("todas")."""

    changed = Signal(str)

    def __init__(self, stages: list[tuple[str, str, str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.cards: dict[str, StageCard] = {}
        self._current = "todas"
        for index, (key, label, hint, color) in enumerate(stages):
            if index:
                layout.addWidget(_Chevron())
            card = StageCard(key, label, hint, color)
            card.clicked.connect(self._on_clicked)
            self.cards[key] = card
            layout.addWidget(card, 1)

    def _on_clicked(self, key: str) -> None:
        self.select("todas" if key == self._current else key)
        self.changed.emit(self._current)

    def select(self, key: str) -> None:
        self._current = key if key in self.cards else "todas"
        for card_key, card in self.cards.items():
            card.set_selected(card_key == self._current)

    def current(self) -> str:
        return self._current

    def set_counts(self, counts: dict[str, int]) -> None:
        for key, card in self.cards.items():
            card.set_count(int(counts.get(key, 0)))

    def restyle(self) -> None:
        for card in self.cards.values():
            card._restyle()


# Mapa do ano -----------------------------------------------------------------------

# Marcas da situacao de cobranca desenhadas no canto da celula.
SITUACAO_MARK = {
    "precisa_pessoa": "danger",
    "documento_com_problema": "warning",
    "verificacao_falhou": "danger",
    "cobrado_aguardando": "accent",
    "promessa_envio": "accent",
    "nao_encontrado": "warning",
}


class YearMap(QWidget):
    """Grade documento x mes, agrupada por tipo de documento. Cada celula tem a cor do
    status (Recebido, Pendente...) e um ponto no canto quando ha uma situacao de cobranca.

    Selecao: clique seleciona uma celula; Ctrl+clique soma/tira; Shift+clique seleciona o
    retangulo desde a ultima celula; clique no mes seleciona a coluna; clique no nome do
    documento seleciona a linha. Celulas que nao se aplicam (fora da regra do documento ou
    depois de Encerrado) nao entram na selecao.

    Alca de preencher (como no Excel): com um quadradinho marcado selecionado, aparece uma
    alca no canto; arrastar para o lado (meses) ou para cima/baixo (documentos do mesmo mes)
    copia o status para os quadradinhos do caminho.

    Sinais: cell_clicked(documento_id, periodo_id, competencia) num clique simples;
    selection_changed(); context_menu_requested(posicao global) no botao direito;
    fill_requested(status, [(documento_id, periodo_id), ...]) ao soltar a alca;
    paste_requested(texto da area de transferencia) no Ctrl+V.

    Copiar e colar (como numa planilha): Ctrl+C copia os status selecionados para a area de
    transferencia (texto separado por tab, cola no Excel tambem); Ctrl+V cola a partir do
    quadradinho selecionado mais acima e a esquerda, no mesmo formato. Um status so copiado
    e colado em varios selecionados preenche todos."""

    cell_clicked = Signal(int, int, str)
    selection_changed = Signal()
    context_menu_requested = Signal(QPoint)
    fill_requested = Signal(str, list)
    paste_requested = Signal(str)

    LABEL_WIDTH = 220
    HEADER_HEIGHT = 30
    GROUP_HEIGHT = 24
    CELL_H = 30
    GAP = 4
    HANDLE = 7
    # Encerrado bloqueia os meses seguintes: nao faz sentido espalhar.
    FILL_STATUSES = ("Recebido", "Pendente", "Nao cobrar")

    def __init__(self, parent: QWidget | None = None, multi_select: bool = False) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.multi_select = multi_select
        self.periodos: list[dict] = []
        self.documentos: list[dict] = []
        self.situacao_labels: dict[str, str] = {}
        self.selection: set[tuple[int, int]] = set()
        self._anchor: tuple[int, int] | None = None  # (indice da linha de documento, coluna)
        self._hover: tuple[int, int] | None = None
        self._fill_target: tuple[int, int] | None = None  # celula ate onde a alca foi arrastada
        self._filling = False
        self._copied: set[tuple[int, int]] = set()  # (documento_id, periodo_id) do ultimo Ctrl+C
        self._rows: list[tuple[str, object]] = []  # ("grupo", tipo) | ("doc", indice)
        self._row_top: list[float] = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    # Dados -------------------------------------------------------------------------

    def set_data(self, mapa: dict, situacao_labels: dict[str, str] | None = None, keep_selection: bool = False) -> None:
        self.periodos = mapa.get("periodos", [])
        self.documentos = mapa.get("documentos", [])
        self.situacao_labels = situacao_labels or {}
        validas = {
            (doc["documento_id"], c["periodo_id"]) for doc in self.documentos for c in doc["celulas"] if c["disponivel"]
        }
        self.selection = (self.selection & validas) if keep_selection else set()
        self._copied &= validas
        if not keep_selection:
            self._anchor = None
        self._layout_rows()
        self.updateGeometry()
        self.update()
        self.selection_changed.emit()

    def _layout_rows(self) -> None:
        self._rows = []
        self._row_top = []
        y = float(self.HEADER_HEIGHT)
        tipo_atual = None
        com_grupos = len({d.get("tipo") for d in self.documentos}) > 1
        for index, doc in enumerate(self.documentos):
            if com_grupos and doc.get("tipo") != tipo_atual:
                tipo_atual = doc.get("tipo")
                self._rows.append(("grupo", tipo_atual))
                self._row_top.append(y)
                y += self.GROUP_HEIGHT
            self._rows.append(("doc", index))
            self._row_top.append(y)
            y += self.CELL_H + self.GAP
        self._height = int(y) + 4

    def set_selected(self, documento_id: int | None, periodo_id: int | None) -> None:
        self.selection = {(documento_id, periodo_id)} if documento_id is not None else set()
        self._anchor = next(
            (
                (doc_index, col)
                for doc_index, doc in enumerate(self.documentos)
                for col, celula in enumerate(doc["celulas"])
                if (doc["documento_id"], celula["periodo_id"]) == (documento_id, periodo_id)
            ),
            None,
        )
        self.update()
        self.selection_changed.emit()

    def selected_cells(self) -> list[dict]:
        """Celulas selecionadas, com o documento e a competencia junto."""
        resultado = []
        for doc in self.documentos:
            for col, celula in enumerate(doc["celulas"]):
                if (doc["documento_id"], celula["periodo_id"]) in self.selection:
                    resultado.append(
                        {
                            **celula,
                            "documento_id": doc["documento_id"],
                            "nome_documento": doc["nome_documento"],
                            "tipo": doc.get("tipo"),
                            "competencia": self.periodos[col]["competencia"],
                        }
                    )
        return resultado

    # Geometria ---------------------------------------------------------------------

    def sizeHint(self) -> QSize:
        width = self.LABEL_WIDTH + len(self.periodos) * (52 + self.GAP) + 8
        return QSize(width, max(getattr(self, "_height", 0), self.HEADER_HEIGHT + self.CELL_H + 8))

    def minimumSizeHint(self) -> QSize:
        return QSize(self.LABEL_WIDTH + 200, self.sizeHint().height())

    def _cell_width(self) -> float:
        if not self.periodos:
            return 52.0
        available = self.width() - self.LABEL_WIDTH - 8
        return max(34.0, min(72.0, available / len(self.periodos) - self.GAP))

    def _doc_row_top(self, doc_index: int) -> float:
        for (kind, value), top in zip(self._rows, self._row_top):
            if kind == "doc" and value == doc_index:
                return top
        return 0.0

    def _cell_rect(self, doc_index: int, col: int) -> QRectF:
        w = self._cell_width()
        return QRectF(self.LABEL_WIDTH + col * (w + self.GAP), self._doc_row_top(doc_index), w, self.CELL_H)

    def _hit(self, pos) -> tuple[str, int, int] | None:
        """('celula', doc, col) | ('mes', -1, col) | ('documento', doc, -1)."""
        x, y = pos.x(), pos.y()
        w = self._cell_width()
        col = int((x - self.LABEL_WIDTH) // (w + self.GAP)) if x >= self.LABEL_WIDTH else -1
        if col >= len(self.periodos) or (col >= 0 and x - self.LABEL_WIDTH - col * (w + self.GAP) > w):
            col = -2  # no espaco entre colunas ou depois da ultima
        if y < self.HEADER_HEIGHT:
            return ("mes", -1, col) if col >= 0 else None
        for (kind, value), top in zip(self._rows, self._row_top):
            if kind == "doc" and top <= y <= top + self.CELL_H:
                if x < self.LABEL_WIDTH - 8:
                    return ("documento", value, -1)
                return ("celula", value, col) if col >= 0 else None
        return None

    # Pintura -----------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        t = tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.documentos:
            painter.setPen(QColor(t["muted"]))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Nenhum documento para mostrar.")
            painter.end()
            return

        small = QFont(self.font())
        small.setPointSizeF(max(7.5, small.pointSizeF() - 1))
        bold = QFont(self.font())
        bold.setWeight(QFont.Weight.DemiBold)
        metrics = QFontMetrics(self.font())
        hover_col = self._hover[2] if self._hover and self._hover[0] == "mes" else None
        hover_doc = self._hover[1] if self._hover and self._hover[0] == "documento" else None

        # Meses: "01/26"; janeiro em destaque marca a virada do ano. Clicavel (coluna).
        painter.setFont(small)
        for col, periodo in enumerate(self.periodos):
            w = self._cell_width()
            header = QRectF(self.LABEL_WIDTH + col * (w + self.GAP), 4, w, self.HEADER_HEIGHT - 8)
            if self.multi_select and hover_col == col:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(t["accent_soft"]))
                painter.drawRoundedRect(header, 5, 5)
            painter.setPen(QColor(t["text"] if periodo["mes"] == 1 or hover_col == col else t["muted"]))
            painter.drawText(header, Qt.AlignmentFlag.AlignCenter, f'{periodo["mes"]:02d}/{str(periodo["ano"])[2:]}')

        for (kind, value), top in zip(self._rows, self._row_top):
            if kind == "grupo":
                painter.setFont(small)
                painter.setPen(QColor(t["muted"]))
                painter.drawText(
                    QRectF(0, top + 4, self.width(), self.GROUP_HEIGHT - 4),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    str(value or "").upper(),
                )
                continue
            doc = self.documentos[value]
            label_rect = QRectF(0, top, self.LABEL_WIDTH - 12, self.CELL_H)
            painter.setFont(bold if hover_doc == value and self.multi_select else self.font())
            painter.setPen(QColor(t["accent"] if hover_doc == value and self.multi_select else t["text"]))
            nome = metrics.elidedText(doc["nome_documento"], Qt.TextElideMode.ElideRight, int(label_rect.width()))
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, nome)

            for col, celula in enumerate(doc["celulas"]):
                self._paint_cell(painter, t, bold, value, col, doc, celula)
        self._paint_fill(painter, t)
        painter.end()

    # Alca de preencher ---------------------------------------------------------------

    def _fill_source(self) -> tuple[int, int] | None:
        """O quadradinho de onde a alca sai: selecao de um so, marcado com um status que pode
        ser copiado."""
        if not self.multi_select or len(self.selection) != 1 or self._anchor is None:
            return None
        doc_index, col = self._anchor
        if not (0 <= doc_index < len(self.documentos) and 0 <= col < len(self.periodos)):
            return None
        celula = self._celula(doc_index, col)
        if (self.documentos[doc_index]["documento_id"], celula["periodo_id"]) not in self.selection:
            return None
        if not celula["disponivel"] or celula["status"] not in self.FILL_STATUSES:
            return None
        return doc_index, col

    def _handle_rect(self) -> QRectF | None:
        origem = self._fill_source()
        if origem is None:
            return None
        rect = self._cell_rect(*origem)
        h = self.HANDLE
        return QRectF(rect.right() - h / 2 - 1, rect.bottom() - h / 2 - 1, h, h)

    def _on_handle(self, pos) -> bool:
        rect = self._handle_rect()
        return rect is not None and rect.adjusted(-4, -4, 4, 4).contains(QPointF(pos))

    def _fill_cells(self) -> list[tuple[int, int]]:
        """Quadradinhos (indice do documento, coluna) do caminho da alca, sem a origem e sem
        os que nao se aplicam."""
        origem = self._fill_source()
        if origem is None or self._fill_target is None:
            return []
        (d0, c0), (d1, c1) = origem, self._fill_target
        if d1 == d0:
            caminho = [(d0, c) for c in range(min(c0, c1), max(c0, c1) + 1)]
        elif c1 == c0:
            caminho = [(d, c0) for d in range(min(d0, d1), max(d0, d1) + 1)]
        else:
            return []
        return [(d, c) for d, c in caminho if (d, c) != origem and self._celula(d, c)["disponivel"]]

    def _paint_fill(self, painter: QPainter, t: dict) -> None:
        if self._copied:
            # Contorno tracejado no que foi copiado, como no Excel (some com Esc).
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(t["accent"]), 1.5, Qt.PenStyle.DashLine))
            for doc_index, doc in enumerate(self.documentos):
                for col, celula in enumerate(doc["celulas"]):
                    if (doc["documento_id"], celula["periodo_id"]) in self._copied:
                        painter.drawRoundedRect(self._cell_rect(doc_index, col).adjusted(-2, -2, 2, 2), 8, 8)
        handle = self._handle_rect()
        if handle is None:
            return
        if self._filling:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(t["accent"]), 1.5, Qt.PenStyle.DashLine))
            for doc_index, col in self._fill_cells():
                painter.drawRoundedRect(self._cell_rect(doc_index, col).adjusted(1, 1, -1, -1), 6, 6)
        painter.setPen(QPen(QColor(t["surface"]), 1.5))
        painter.setBrush(QColor(t["accent"]))
        painter.drawRect(handle)

    def _paint_cell(self, painter: QPainter, t: dict, bold: QFont, doc_index: int, col: int, doc: dict, celula: dict) -> None:
        rect = self._cell_rect(doc_index, col)
        key = (doc["documento_id"], celula["periodo_id"])
        if not celula["disponivel"] and celula["status"] != "Nao cobrar":
            painter.setPen(QPen(QColor(t["border"]), 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 6, 6)
            return
        if celula["status"]:
            background, foreground = status_colors(celula["status"])
            fill = QColor(background)
        else:
            fill = QColor(t["surface_alt"])
            foreground = t["muted"]
        painter.setPen(QPen(QColor(t["border"]), 1))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 6, 6)
        # Simbolo curto dentro da celula, para quem nao distingue bem as cores.
        symbol = STATUS_SYMBOLS.get(celula["status"], "")
        if symbol:
            painter.setFont(bold)
            painter.setPen(QColor(foreground))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, symbol)
        mark = SITUACAO_MARK.get(celula.get("situacao") or "")
        if mark and celula["status"] not in ("Recebido", "Encerrado"):
            painter.setPen(QPen(QColor(t["surface"]), 1.5))
            painter.setBrush(QColor(t[mark]))
            painter.drawEllipse(QPointF(rect.right() - 7, rect.top() + 7), 4.5, 4.5)
        hovered = self._hover == ("celula", doc_index, col)
        if key in self.selection or hovered:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(t["accent"]), 2.5 if key in self.selection else 1.5))
            painter.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), 7, 7)

    # Mouse -------------------------------------------------------------------------

    def _celula(self, doc_index: int, col: int) -> dict:
        return self.documentos[doc_index]["celulas"][col]

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        pos = event.position().toPoint()
        if self._filling:
            self._drag_fill(pos, event.globalPosition().toPoint())
            return
        if self._on_handle(pos):
            QToolTip.showText(
                event.globalPosition().toPoint(),
                "<b>Arraste para preencher</b><br>Para o lado: os próximos meses. Para cima/baixo: os outros documentos.",
                self,
            )
            self.setCursor(Qt.CursorShape.CrossCursor)
            return
        hit = self._hit(pos)
        if hit != self._hover:
            self._hover = hit
            self.update()
        if hit is None:
            QToolTip.hideText()
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        kind, doc_index, col = hit
        if kind == "mes":
            texto = f'<b>{self.periodos[col]["competencia"]}</b><br><i>Clique para selecionar o mês inteiro</i>'
        elif kind == "documento":
            doc = self.documentos[doc_index]
            texto = f'<b>{doc["nome_documento"]}</b><br><i>Clique para selecionar a linha inteira</i>'
        else:
            texto = self._tooltip(doc_index, col)
        if kind != "celula" and not self.multi_select:
            QToolTip.hideText()
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        QToolTip.showText(event.globalPosition().toPoint(), texto, self)

    def _tooltip(self, doc_index: int, col: int) -> str:
        doc = self.documentos[doc_index]
        celula = self._celula(doc_index, col)
        periodo = self.periodos[col]
        linhas = [f'<b>{doc["nome_documento"]}</b> - {periodo["competencia"]}']
        if not celula["disponivel"]:
            linhas.append(celula.get("aviso") or "Não se aplica neste mês.")
            return "<br>".join(linhas)
        status = {"Nao cobrar": "Não cobrar"}.get(celula["status"], celula["status"]) or "Sem marcação"
        linhas.append(f"Status: <b>{status}</b>")
        if celula.get("marcado_em"):
            linhas.append(f'marcado por {celula.get("marcado_por") or "Sistema"} em {format_utc_timestamp(str(celula["marcado_em"]))}')
        if celula.get("situacao"):
            linhas.append(f'Cobrança: {self.situacao_labels.get(celula["situacao"], celula["situacao"])}')
        linhas.append("<i>Clique para selecionar; botão direito para marcar</i>" if self.multi_select else "<i>Clique para ver o histórico</i>")
        return "<br>".join(linhas)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._hover = None
        self.update()
        super().leaveEvent(event)

    def _drag_fill(self, pos, global_pos) -> None:
        hit = self._hit(pos)
        if hit and hit[0] == "celula":
            self._fill_target = (hit[1], hit[2])
        self.update()
        quantos = len(self._fill_cells())
        origem = self._fill_source()
        if origem and quantos:
            status = self._celula(*origem)["status"]
            rotulo = {"Nao cobrar": "Não cobrar"}.get(status, status)
            QToolTip.showText(global_pos, f"Preencher <b>{quantos}</b> com <b>{rotulo}</b>", self)
        else:
            QToolTip.hideText()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        if not self._filling:
            super().mouseReleaseEvent(event)
            return
        self._filling = False
        QToolTip.hideText()
        origem = self._fill_source()
        caminho = self._fill_cells()
        self._fill_target = None
        self.update()
        if origem is None or not caminho:
            return
        status = self._celula(*origem)["status"]
        alvos = [(self.documentos[d]["documento_id"], self._celula(d, c)["periodo_id"]) for d, c in caminho]
        # A selecao vira o trecho preenchido, como no Excel.
        self.selection = set(alvos) | {(self.documentos[origem[0]]["documento_id"], self._celula(*origem)["periodo_id"])}
        self.selection_changed.emit()
        self.fill_requested.emit(status, alvos)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton and self._on_handle(event.position().toPoint()):
            self._filling = True
            self._fill_target = self._fill_source()
            return
        hit = self._hit(event.position().toPoint())
        if hit is None:
            return
        kind, doc_index, col = hit
        right = event.button() == Qt.MouseButton.RightButton
        mods = event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier) and self.multi_select
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier) and self.multi_select

        if kind == "celula":
            celula = self._celula(doc_index, col)
            key = (self.documentos[doc_index]["documento_id"], celula["periodo_id"])
            if not celula["disponivel"]:
                return
            if right and key in self.selection:
                pass  # botao direito sobre a selecao: mantem a selecao
            elif shift and self._anchor is not None:
                self._select_rect(self._anchor, (doc_index, col), add=ctrl)
            elif ctrl:
                self.selection ^= {key}
                self._anchor = (doc_index, col)
            else:
                self.selection = {key}
                self._anchor = (doc_index, col)
                if not right:
                    self.cell_clicked.emit(key[0], key[1], self.periodos[col]["competencia"])
        elif not self.multi_select:
            return
        elif kind == "mes":
            coluna = {
                (doc["documento_id"], doc["celulas"][col]["periodo_id"])
                for doc in self.documentos
                if doc["celulas"][col]["disponivel"]
            }
            self.selection = (self.selection | coluna) if ctrl else coluna
        else:
            doc = self.documentos[doc_index]
            linha = {(doc["documento_id"], c["periodo_id"]) for c in doc["celulas"] if c["disponivel"]}
            self.selection = (self.selection | linha) if ctrl else linha
        self.update()
        self.selection_changed.emit()
        if right and self.selection:
            self.context_menu_requested.emit(event.globalPosition().toPoint())

    def _select_rect(self, start: tuple[int, int], end: tuple[int, int], add: bool) -> None:
        (d1, c1), (d2, c2) = start, end
        area = {
            (self.documentos[d]["documento_id"], self.documentos[d]["celulas"][c]["periodo_id"])
            for d in range(min(d1, d2), max(d1, d2) + 1)
            for c in range(min(c1, c2), max(c1, c2) + 1)
            if self.documentos[d]["celulas"][c]["disponivel"]
        }
        self.selection = (self.selection | area) if add else area

    ARROW_STEPS = {
        Qt.Key.Key_Left: (0, -1),
        Qt.Key.Key_Right: (0, 1),
        Qt.Key.Key_Up: (-1, 0),
        Qt.Key.Key_Down: (1, 0),
    }

    # Copiar e colar ----------------------------------------------------------------

    def _selected_positions(self) -> list[tuple[int, int]]:
        return [
            (doc_index, col)
            for doc_index, doc in enumerate(self.documentos)
            for col, celula in enumerate(doc["celulas"])
            if (doc["documento_id"], celula["periodo_id"]) in self.selection
        ]

    def copy_selection(self) -> str:
        """Status selecionados como texto (linhas = documentos, colunas = meses, separados por
        tab). Quadradinho sem marcacao, ou fora da selecao, vai vazio. Tambem vai para a area
        de transferencia."""
        posicoes = self._selected_positions()
        if not posicoes:
            return ""
        docs = sorted({d for d, _c in posicoes})
        cols = range(min(c for _d, c in posicoes), max(c for _d, c in posicoes) + 1)
        selecionadas = set(posicoes)
        linhas = []
        for doc_index in docs:
            valores = []
            for col in cols:
                status = self._celula(doc_index, col)["status"] if (doc_index, col) in selecionadas else ""
                valores.append(STATUS_TEXT.get(status, ""))
            linhas.append("\t".join(valores))
        texto = "\n".join(linhas)
        QGuiApplication.clipboard().setText(texto)
        self._copied = set(self.selection)
        self.update()
        return texto

    def paste_plan(self, texto: str) -> list[tuple[int, int, str]]:
        """O que um Ctrl+V com este texto faria: [(documento_id, periodo_id, status)]. Vazio no
        texto nao mexe no quadradinho; os que nao se aplicam sao pulados."""
        posicoes = self._selected_positions()
        if not posicoes:
            raise ValidationError("Selecione o quadradinho onde colar.")
        linhas = str(texto or "").replace("\r\n", "\n").replace("\r", "\n").rstrip("\n").split("\n")
        grade = [[parse_status_text(valor) for valor in linha.split("\t")] for linha in linhas]
        if not any(status is not None for linha in grade for status in linha):
            raise ValidationError("Nada para colar: copie quadradinhos marcados (Ctrl+C) primeiro.")
        alvos: list[tuple[int, int, str]] = []
        if len(grade) == 1 and len(grade[0]) == 1:
            # Um status so: vai para todos os selecionados.
            for doc_index, col in posicoes:
                celula = self._celula(doc_index, col)
                if celula["disponivel"]:
                    alvos.append((self.documentos[doc_index]["documento_id"], celula["periodo_id"], grade[0][0]))
            return alvos
        d0 = min(d for d, _c in posicoes)
        c0 = min(c for d, c in posicoes if d == d0)
        for i, linha in enumerate(grade):
            for j, status in enumerate(linha):
                doc_index, col = d0 + i, c0 + j
                if status is None or doc_index >= len(self.documentos) or col >= len(self.periodos):
                    continue
                celula = self._celula(doc_index, col)
                if celula["disponivel"]:
                    alvos.append((self.documentos[doc_index]["documento_id"], celula["periodo_id"], status))
        return alvos

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self.multi_select and event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection()
            return
        if self.multi_select and event.matches(QKeySequence.StandardKey.Paste):
            self.paste_requested.emit(QGuiApplication.clipboard().text())
            return
        if event.key() == Qt.Key.Key_Escape and self._copied:
            self._copied = set()
            self.update()
            return
        if event.key() == Qt.Key.Key_Escape and self.selection:
            self.selection = set()
            self.update()
            self.selection_changed.emit()
            return
        step = self.ARROW_STEPS.get(event.key())
        if step and self.multi_select and self._anchor is not None:
            self._move_selection(*step)
            return
        super().keyPressEvent(event)

    def _move_selection(self, d_doc: int, d_col: int) -> None:
        """Setas andam como numa planilha: seleciona o proximo quadradinho que se aplica
        naquela direcao (pula os que nao se aplicam), para marcar so pelo teclado."""
        doc_index, col = self._anchor
        while True:
            doc_index, col = doc_index + d_doc, col + d_col
            if not (0 <= doc_index < len(self.documentos) and 0 <= col < len(self.periodos)):
                return
            celula = self._celula(doc_index, col)
            if celula["disponivel"]:
                break
        self.selection = {(self.documentos[doc_index]["documento_id"], celula["periodo_id"])}
        self._anchor = (doc_index, col)
        self.update()
        self.selection_changed.emit()


STATUS_SYMBOLS = {"Recebido": "✓", "Pendente": "!", "Encerrado": "–", "Nao cobrar": "·"}
# Texto do Ctrl+C e o que o Ctrl+V entende (as mesmas letras de marcar pelo teclado).
STATUS_TEXT = {"Recebido": "Recebido", "Pendente": "Pendente", "Encerrado": "Encerrado", "Nao cobrar": "Não cobrar"}
_STATUS_ALIASES = {
    "Recebido": ("recebido", "ok", "o", "r", "✓", "✔"),
    "Pendente": ("pendente", "p", "!"),
    "Encerrado": ("encerrado", "e", "–"),
    "Nao cobrar": ("nao cobrar", "não cobrar", "x", "n", "·"),
}
_STATUS_BY_TEXT = {alias: status for status, aliases in _STATUS_ALIASES.items() for alias in aliases}


def parse_status_text(valor: str) -> str | None:
    """'OK', 'Recebido', 'x', 'Não cobrar'... -> status; vazio -> None (nao mexe)."""
    texto = " ".join(str(valor or "").split()).casefold()
    if not texto:
        return None
    status = _STATUS_BY_TEXT.get(texto)
    if status is None:
        raise ValidationError(
            f'Não entendi "{valor.strip()}" para colar. Use Recebido (ou OK), Pendente, Não cobrar (ou X) ou Encerrado.'
        )
    return status


def status_icon(status: str, size: int = 18) -> QIcon:
    """Quadradinho na cor do status, igual ao do mapa - usado nos botoes e menus de marcar."""
    return _status_icon(status, size, tokens()["surface"])


@lru_cache(maxsize=64)
def _status_icon(status: str, size: int, _tema: str) -> QIcon:
    t = tokens()
    pixmap = QPixmap(size * 2, size * 2)  # 2x para ficar nitido em telas de alta densidade
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if status:
        background, foreground = status_colors(status)
    else:
        background, foreground = t["surface_alt"], t["muted"]
    painter.setPen(QPen(QColor(t["border_strong"]), 1))
    painter.setBrush(QColor(background))
    painter.drawRoundedRect(QRectF(1, 1, size - 2, size - 2), 4, 4)
    font = QFont()
    font.setBold(True)
    font.setPixelSize(int(size * 0.7))
    painter.setFont(font)
    painter.setPen(QColor(foreground))
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, STATUS_SYMBOLS.get(status, "×"))
    painter.end()
    return QIcon(pixmap)


class MapLegend(QWidget):
    """Legenda do YearMap: cores dos status e marcas de situacao."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(24)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        t = tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        x = 0.0
        y = self.height() / 2
        metrics = QFontMetrics(self.font())
        itens = [("box", status_colors("Recebido")[0], "Recebido"), ("box", status_colors("Pendente")[0], "Pendente"),
                 ("box", t["surface_alt"], "Sem marcação"), ("box", status_colors("Encerrado")[0], "Encerrado"),
                 ("dot", t["danger"], "Pessoa / falhou"), ("dot", t["warning"], "Não achado / problema"),
                 ("dot", t["accent"], "Cobrado")]
        for kind, color, label in itens:
            painter.setPen(QPen(QColor(t["border"]), 1))
            painter.setBrush(QColor(color))
            if kind == "box":
                painter.drawRoundedRect(QRectF(x, y - 7, 18, 14), 4, 4)
            else:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QPointF(x + 9, y), 5, 5)
            painter.setPen(QColor(t["muted"]))
            painter.drawText(QPointF(x + 24, y + metrics.ascent() / 2 - 1), label)
            x += 24 + metrics.horizontalAdvance(label) + 18
        painter.end()


def map_scroll_area(year_map: YearMap) -> QWidget:
    """Envolve o YearMap numa area com rolagem, encostado no topo e sem fundo proprio."""
    holder = QWidget()
    # Regra presa ao proprio holder: sem seletor ela descia ate o balao de dica (tooltip) do
    # mapa, que ficava transparente - preto no Windows, com o texto escuro ilegivel.
    holder.setObjectName("MapHolder")
    holder.setStyleSheet("#MapHolder { background: transparent; }")
    layout = QVBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(year_map)
    layout.addStretch(1)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setStyleSheet("QScrollArea { background: transparent; }")
    scroll.viewport().setAutoFillBackground(False)
    scroll.setWidget(holder)
    return scroll
