from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem, QWidget

from documentos_empresa_app.utils.helpers import load_ui_state, save_ui_state

ROW_KEY_ROLE = Qt.ItemDataRole.UserRole
TOOLTIP_MIN_LENGTH = 24
_DATA_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})")
_COMPETENCIA_RE = re.compile(r"^(\d{2})/(\d{4})")
_PEDACOS_RE = re.compile(r"(\d+)")


def natural_key(text: str) -> tuple:
    """Chave de ordenacao "como gente": 7 antes de 11, datas dd/mm/aaaa e competencias
    mm/aaaa em ordem de calendario, texto sem diferenciar maiusculas."""
    texto = str(text or "").strip()
    data = _DATA_RE.match(texto)
    if data:
        texto = f"{data.group(3)}{data.group(2)}{data.group(1)}{texto[10:]}"
    else:
        competencia = _COMPETENCIA_RE.match(texto)
        if competencia:
            texto = f"{competencia.group(2)}{competencia.group(1)}{texto[7:]}"
    return tuple((0, int(p), "") if p.isdigit() else (1, 0, p.casefold()) for p in _PEDACOS_RE.split(texto) if p)


class NaturalItem(QTableWidgetItem):
    def __lt__(self, other: QTableWidgetItem) -> bool:  # noqa: D105 - ordenacao do Qt
        return natural_key(self.text()) < natural_key(other.text())


def remember_sort(
    table: QTableWidget,
    key: str,
    default_column: int = 0,
    default_order: Qt.SortOrder = Qt.SortOrder.AscendingOrder,
) -> None:
    """Liga a ordenacao por clique no cabecalho e guarda a escolha (coluna e direcao) neste
    computador: a grade abre do jeito que foi deixada da ultima vez."""
    salvo = load_ui_state(f"ordem:{key}")
    coluna, ordem = default_column, default_order
    if isinstance(salvo, list) and len(salvo) == 2 and 0 <= int(salvo[0]) < table.columnCount():
        coluna = int(salvo[0])
        ordem = Qt.SortOrder.DescendingOrder if int(salvo[1]) else Qt.SortOrder.AscendingOrder
    header = table.horizontalHeader()
    header.setSectionsClickable(True)
    header.setSortIndicatorShown(True)
    header.setSortIndicator(coluna, ordem)
    table.setSortingEnabled(True)
    header.sortIndicatorChanged.connect(
        lambda c, o: save_ui_state(f"ordem:{key}", [int(c), 1 if o == Qt.SortOrder.DescendingOrder else 0])
    )


def make_readonly_table(
    headers: list[str],
    stretch_column: int,
    parent: QWidget | None = None,
    sort_key: str | None = None,
    sortable: bool = True,
) -> QTableWidget:
    """Tabela so de leitura, selecao por linha inteira, uma coluna esticada e as demais no
    tamanho do conteudo - o padrao das listas da Ficha e de Cobrancas. Clicar no cabecalho
    ordena, e a ordem escolhida fica guardada (sort_key; sem ele, os titulos das colunas)."""
    table = QTableWidget(0, len(headers), parent)
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setWordWrap(False)
    header = table.horizontalHeader()
    # "Ajustar ao conteudo" mede cada celula; numa lista de centenas de linhas isso pesa a
    # cada atualizacao. Medir as 120 primeiras linhas ja da a largura certa.
    header.setResizeContentsPrecision(120)
    for column in range(len(headers)):
        mode = QHeaderView.ResizeMode.Stretch if column == stretch_column else QHeaderView.ResizeMode.ResizeToContents
        header.setSectionResizeMode(column, mode)
    if sortable:
        remember_sort(table, sort_key or "|".join(headers))
    return table


def fill_table(table: QTableWidget, rows: list[tuple[object, list[str]]], colors: dict[tuple[int, int], str] | None = None) -> None:
    """Preenche a tabela. Cada linha e (chave, valores); a chave fica guardada na primeira
    coluna para recuperar o registro selecionado. colors: (linha, coluna) -> cor do texto."""
    table.setUpdatesEnabled(False)  # uma pintura so no fim, nao uma por celula
    # Ordenar enquanto preenche embaralha as linhas: desliga e religa no fim (reordena uma vez).
    ordenavel = table.isSortingEnabled()
    table.setSortingEnabled(False)
    try:
        table.setRowCount(0)
        table.setRowCount(len(rows))
        for row_index, (key, values) in enumerate(rows):
            for column, value in enumerate(values):
                item = NaturalItem(value)
                if len(value) > TOOLTIP_MIN_LENGTH:  # dica so onde o texto pode ficar cortado
                    item.setToolTip(value)
                if column == 0:
                    item.setData(ROW_KEY_ROLE, key)
                color = (colors or {}).get((row_index, column))
                if color:
                    item.setForeground(QColor(color))
                table.setItem(row_index, column, item)
    finally:
        table.setSortingEnabled(ordenavel)
        table.setUpdatesEnabled(True)


def selected_key(table: QTableWidget):
    rows = table.selectionModel().selectedRows()
    if not rows:
        return None
    item = table.item(rows[0].row(), 0)
    return item.data(ROW_KEY_ROLE) if item is not None else None


def selected_keys(table: QTableWidget) -> list:
    """Chaves de todas as linhas selecionadas (para tabelas com selecao multipla)."""
    keys = []
    for index in sorted(table.selectionModel().selectedRows(), key=lambda i: i.row()):
        item = table.item(index.row(), 0)
        if item is not None:
            keys.append(item.data(ROW_KEY_ROLE))
    return keys
