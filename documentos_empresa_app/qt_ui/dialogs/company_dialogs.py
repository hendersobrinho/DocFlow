from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.widgets.common import make_button


class _CompanyTableDialog(QDialog):
    """Base para dialogos de escolha de empresa com busca."""

    def __init__(
        self,
        parent: QWidget | None,
        companies: list[dict],
        title: str,
        multi_select: bool,
        initial_search: str = "",
    ) -> None:
        super().__init__(parent)
        self.companies = companies
        self.setWindowTitle(title)
        self.resize(680, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Buscar por codigo ou nome...")
        self.search_edit.setText(initial_search)
        self.search_edit.textChanged.connect(self._populate)
        layout.addWidget(self.search_edit)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Codigo", "Nome", "Situacao"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
            if multi_select
            else QAbstractItemView.SelectionMode.SingleSelection
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.doubleClicked.connect(lambda _index: self.accept())
        layout.addWidget(self.table, 1)

        self.button_row = QHBoxLayout()
        self.button_row.addStretch(1)
        cancel_button = make_button("Cancelar", "quiet")
        cancel_button.clicked.connect(self.reject)
        self.button_row.addWidget(cancel_button)
        confirm_button = make_button("Selecionar", "primary")
        confirm_button.clicked.connect(self.accept)
        self.button_row.addWidget(confirm_button)
        layout.addLayout(self.button_row)

        self._populate()
        self.search_edit.setFocus()

    def _populate(self) -> None:
        search = self.search_edit.text().strip().casefold()
        self.table.setRowCount(0)

        ranked: list[tuple[int, str, dict]] = []
        for company in self.companies:
            name = company["nome_empresa"].casefold()
            code = str(company["codigo_empresa"]).casefold()
            full = f"{code} {name}"
            if search:
                if name.startswith(search) or code.startswith(search):
                    rank = 0
                elif search in name:
                    rank = 1
                elif search in full:
                    rank = 2
                else:
                    continue
            else:
                rank = 3
            ranked.append((rank, name, company))

        ranked.sort(key=lambda item: (item[0], item[1], item[2]["codigo_empresa"]))

        for _rank, _name, company in ranked:
            row = self.table.rowCount()
            self.table.insertRow(row)
            code_item = QTableWidgetItem(str(company["codigo_empresa"]))
            code_item.setData(Qt.ItemDataRole.UserRole, company["id"])
            self.table.setItem(row, 0, code_item)
            self.table.setItem(row, 1, QTableWidgetItem(company["nome_empresa"]))
            self.table.setItem(row, 2, QTableWidgetItem("Ativa" if company["ativa"] else "Inativa"))

        if self.table.rowCount():
            self.table.selectRow(0)

    def _selected_ids(self) -> list[int]:
        ids: list[int] = []
        for index in self.table.selectionModel().selectedRows():
            item = self.table.item(index.row(), 0)
            if item is not None:
                ids.append(int(item.data(Qt.ItemDataRole.UserRole)))
        return ids


class CompanyListDialog(_CompanyTableDialog):
    def __init__(
        self,
        parent: QWidget | None,
        companies: list[dict],
        initial_search: str = "",
        title: str = "Empresas cadastradas",
    ) -> None:
        super().__init__(parent, companies, title, multi_select=False, initial_search=initial_search)
        self.selected_company_id: int | None = None

    def accept(self) -> None:
        ids = self._selected_ids()
        if not ids:
            return
        self.selected_company_id = ids[0]
        super().accept()


class CompanyMultiSelectDialog(_CompanyTableDialog):
    def __init__(
        self,
        parent: QWidget | None,
        companies: list[dict],
        selected_company_ids: list[int] | None = None,
        title: str = "Selecionar empresas",
    ) -> None:
        super().__init__(parent, companies, title, multi_select=True)
        self.selected_company_ids: list[int] = list(selected_company_ids or [])

        select_all_button = make_button("Selecionar todas", "secondary" and None)
        select_all_button.clicked.connect(self.table.selectAll)
        self.button_row.insertWidget(0, select_all_button)
        clear_button = make_button("Limpar", "quiet")
        clear_button.clicked.connect(self.table.clearSelection)
        self.button_row.insertWidget(1, clear_button)

        preset = set(self.selected_company_ids)
        if preset:
            selection_model = self.table.selectionModel()
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if item is not None and int(item.data(Qt.ItemDataRole.UserRole)) in preset:
                    self.table.selectRow(row) if not selection_model.hasSelection() else None
                    index = self.table.model().index(row, 0)
                    selection_model.select(
                        index,
                        selection_model.SelectionFlag.Select | selection_model.SelectionFlag.Rows,
                    )

    def accept(self) -> None:
        self.selected_company_ids = self._selected_ids()
        super().accept()
