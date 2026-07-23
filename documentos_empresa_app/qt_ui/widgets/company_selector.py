from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QWidget,
)

from documentos_empresa_app.qt_ui.dialogs.company_dialogs import CompanyListDialog
from documentos_empresa_app.qt_ui.widgets.common import make_button


class CompanySelector(QGroupBox):
    """Seletor reutilizavel de empresa com busca por codigo e nome."""

    company_selected = Signal(dict)
    company_cleared = Signal()

    def __init__(
        self,
        empresa_service,
        active_only: bool = True,
        title: str = "Selecionar empresa",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, parent)
        self.empresa_service = empresa_service
        self.active_only = active_only
        self.selected_company_id: int | None = None
        self.companies: list[dict] = []
        self._syncing = False

        layout = QGridLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setHorizontalSpacing(10)

        layout.addWidget(QLabel("Codigo"), 0, 0)
        self.code_edit = QLineEdit()
        self.code_edit.setMaximumWidth(140)
        self.code_edit.editingFinished.connect(self._on_code_search)
        self.code_edit.textEdited.connect(self._on_typed)
        layout.addWidget(self.code_edit, 1, 0)

        layout.addWidget(QLabel("Buscar por nome"), 0, 1)
        self.name_combo = QComboBox()
        self.name_combo.setEditable(True)
        self.name_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.name_combo.lineEdit().textEdited.connect(self._on_name_typed)
        self.name_combo.activated.connect(self._on_name_selected)
        layout.addWidget(self.name_combo, 1, 1)
        layout.setColumnStretch(1, 1)

        browse_button = make_button("...", None)
        browse_button.setMaximumWidth(40)
        browse_button.clicked.connect(self.open_company_list)
        layout.addWidget(browse_button, 1, 2)

        self.status_label = QLabel("Nenhuma empresa selecionada.")
        self.status_label.setObjectName("Muted")
        layout.addWidget(self.status_label, 2, 0, 1, 3)

        self.refresh_companies()

    # API compativel com o seletor antigo

    def refresh_companies(self) -> None:
        self.companies = self.empresa_service.list_empresas(active_only=self.active_only)
        self._refresh_combo_values()
        if self.selected_company_id:
            company = next((c for c in self.companies if c["id"] == self.selected_company_id), None)
            if company:
                self._apply_selection(company)
                return
        self.clear_selection()

    def get_selected_company_id(self) -> int | None:
        return self.selected_company_id

    def clear_selection(self) -> None:
        had = self.selected_company_id is not None
        self.selected_company_id = None
        self._syncing = True
        self.code_edit.clear()
        self.name_combo.setCurrentText("")
        self._syncing = False
        self.status_label.setText("Nenhuma empresa selecionada.")
        if had:
            self.company_cleared.emit()

    def set_company(self, company_id: int | None) -> None:
        if company_id is None:
            self.clear_selection()
            return
        company = next((c for c in self.companies if c["id"] == company_id), None)
        if company:
            self._apply_selection(company)
        else:
            self.clear_selection()

    def open_company_list(self) -> None:
        self.refresh_companies()
        initial = self.name_combo.currentText().strip() or self.code_edit.text().strip()
        dialog = CompanyListDialog(self, self.companies, initial_search=initial)
        if dialog.exec() and dialog.selected_company_id is not None:
            self.set_company(dialog.selected_company_id)

    # Internos

    def _label(self, company: dict) -> str:
        status = "" if company["ativa"] else " [Inativa]"
        return f'{company["codigo_empresa"]} - {company["nome_empresa"]}{status}'

    def _refresh_combo_values(self, companies: list[dict] | None = None) -> None:
        current = self.name_combo.currentText()
        self._syncing = True
        self.name_combo.clear()
        for company in companies if companies is not None else self.companies:
            self.name_combo.addItem(self._label(company), company["id"])
        self.name_combo.setCurrentText(current)
        self._syncing = False

    def _on_typed(self, _text: str) -> None:
        if self._syncing:
            return
        if self.selected_company_id is not None:
            self.selected_company_id = None
            self._syncing = True
            self.name_combo.setCurrentText("")
            self._syncing = False
            self.company_cleared.emit()

    def _on_name_typed(self, text: str) -> None:
        if self._syncing:
            return
        if self.selected_company_id is not None:
            self.selected_company_id = None
            self._syncing = True
            self.code_edit.clear()
            self._syncing = False
            self.company_cleared.emit()
        search = text.strip().casefold()
        filtered = [c for c in self.companies if search in c["nome_empresa"].casefold()] if search else self.companies
        current = self.name_combo.lineEdit().text()
        cursor = self.name_combo.lineEdit().cursorPosition()
        self._refresh_combo_values(filtered)
        self._syncing = True
        self.name_combo.setCurrentText(current)
        self.name_combo.lineEdit().setCursorPosition(cursor)
        self._syncing = False

    def _on_code_search(self) -> None:
        raw_code = self.code_edit.text().strip()
        if not raw_code or self._syncing:
            return
        company = self.empresa_service.get_empresa_by_code(raw_code, active_only=self.active_only)
        if not company:
            had = self.selected_company_id is not None
            self.selected_company_id = None
            self.status_label.setText("Empresa nao encontrada para o codigo informado.")
            if had:
                self.company_cleared.emit()
            return
        self._apply_selection(company)

    def _on_name_selected(self, index: int) -> None:
        if self._syncing:
            return
        company_id = self.name_combo.itemData(index)
        if company_id is None:
            return
        company = next((c for c in self.companies if c["id"] == company_id), None)
        if company:
            self._apply_selection(company)

    def _apply_selection(self, company: dict) -> None:
        self.selected_company_id = company["id"]
        self._syncing = True
        self.code_edit.setText(str(company["codigo_empresa"]))
        self.name_combo.setCurrentText(self._label(company))
        self._syncing = False
        situacao = "ativa" if company["ativa"] else "inativa"
        self.status_label.setText(f'Empresa selecionada: {company["nome_empresa"]} ({situacao}).')
        self.company_selected.emit(company)
