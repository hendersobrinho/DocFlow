from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem, QWidget

ROW_KEY_ROLE = Qt.ItemDataRole.UserRole
TOOLTIP_MIN_LENGTH = 24


def make_readonly_table(headers: list[str], stretch_column: int, parent: QWidget | None = None) -> QTableWidget:
    """Tabela so de leitura, selecao por linha inteira, uma coluna esticada e as demais no
    tamanho do conteudo - o padrao das listas da Ficha e de Cobrancas."""
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
    return table


def fill_table(table: QTableWidget, rows: list[tuple[object, list[str]]], colors: dict[tuple[int, int], str] | None = None) -> None:
    """Preenche a tabela. Cada linha e (chave, valores); a chave fica guardada na primeira
    coluna para recuperar o registro selecionado. colors: (linha, coluna) -> cor do texto."""
    table.setUpdatesEnabled(False)  # uma pintura so no fim, nao uma por celula
    try:
        table.setRowCount(0)
        table.setRowCount(len(rows))
        for row_index, (key, values) in enumerate(rows):
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if len(value) > TOOLTIP_MIN_LENGTH:  # dica so onde o texto pode ficar cortado
                    item.setToolTip(value)
                if column == 0:
                    item.setData(ROW_KEY_ROLE, key)
                color = (colors or {}).get((row_index, column))
                if color:
                    item.setForeground(QColor(color))
                table.setItem(row_index, column, item)
    finally:
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
