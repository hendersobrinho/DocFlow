from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QGroupBox,
    QListWidget,
    QWidget,
)

from documentos_empresa_app.qt_ui.dialogs.manager_dialogs import DeliveryMethodsManagerDialog
from documentos_empresa_app.qt_ui.widgets.common import make_button
from documentos_empresa_app.utils.common import DOCUMENT_DELIVERY_OPTIONS, parse_delivery_methods


class DeliveryMethodsField(QGroupBox):
    """Selecao multipla de meios de recebimento com gerenciador do sistema."""

    def __init__(self, delivery_method_service=None, parent: QWidget | None = None) -> None:
        super().__init__("Meios de recebimento", parent)
        self.delivery_method_service = delivery_method_service

        layout = QGridLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setHorizontalSpacing(8)

        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo.lineEdit().returnPressed.connect(self._add_current)
        layout.addWidget(self.combo, 0, 0)

        add_button = make_button("Adicionar")
        add_button.clicked.connect(self._add_current)
        layout.addWidget(add_button, 0, 1)

        self.manager_button = make_button("...")
        self.manager_button.setMaximumWidth(40)
        self.manager_button.clicked.connect(self._open_manager)
        layout.addWidget(self.manager_button, 0, 2)

        self.chosen_list = QListWidget()
        self.chosen_list.setMaximumHeight(96)
        self.chosen_list.itemDoubleClicked.connect(lambda item: self._remove_value(item.text()))
        layout.addWidget(self.chosen_list, 1, 0, 1, 2)

        self.remove_button = make_button("Remover", "quiet")
        self.remove_button.clicked.connect(self._remove_selected)
        layout.addWidget(self.remove_button, 1, 2, alignment=Qt.AlignmentFlag.AlignTop)
        layout.setColumnStretch(0, 1)

        self.refresh_available_values()

    def refresh_available_values(self) -> None:
        current = self.combo.currentText()
        self.combo.clear()
        if self.delivery_method_service is not None:
            values = [method["nome_meio"] for method in self.delivery_method_service.list_methods()]
        else:
            values = list(DOCUMENT_DELIVERY_OPTIONS)
        self.combo.addItems(values)
        self.combo.setCurrentText(current)

    def get_values(self) -> list[str]:
        pending = self.combo.currentText().strip()
        values = [self.chosen_list.item(i).text() for i in range(self.chosen_list.count())]
        if pending and pending.casefold() not in {v.casefold() for v in values}:
            values.append(pending)
        return values

    def set_values(self, raw) -> None:
        self.chosen_list.clear()
        for value in parse_delivery_methods(raw):
            self.chosen_list.addItem(value)
        self.combo.setCurrentText("")

    def clear(self) -> None:
        self.chosen_list.clear()
        self.combo.setCurrentText("")

    def set_editable(self, editable: bool) -> None:
        self.combo.setEnabled(editable)
        self.chosen_list.setEnabled(editable)
        self.remove_button.setEnabled(editable)

    def _add_current(self) -> None:
        value = self.combo.currentText().strip()
        if not value:
            return
        self._add_value(value)
        self.combo.setCurrentText("")

    def _add_value(self, value: str) -> None:
        existing = {self.chosen_list.item(i).text().casefold(): i for i in range(self.chosen_list.count())}
        if value.casefold() in existing:
            self.chosen_list.takeItem(existing[value.casefold()])
        else:
            self.chosen_list.addItem(value)

    def _remove_selected(self) -> None:
        for item in self.chosen_list.selectedItems():
            self.chosen_list.takeItem(self.chosen_list.row(item))

    def _remove_value(self, value: str) -> None:
        for i in range(self.chosen_list.count()):
            if self.chosen_list.item(i).text() == value:
                self.chosen_list.takeItem(i)
                return

    def _open_manager(self) -> None:
        if self.delivery_method_service is None:
            return
        dialog = DeliveryMethodsManagerDialog(
            self.delivery_method_service, allow_apply=self.combo.isEnabled(), parent=self
        )
        dialog.exec()
        if dialog.data_changed:
            self.refresh_available_values()
        if dialog.applied_value is not None:
            self._add_value(dialog.applied_value)
