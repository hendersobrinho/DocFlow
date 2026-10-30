from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QGridLayout, QWidget


class CheckChoices(QWidget):
    """Grade de caixas de marcar para escolher varias opcoes de uma lista curta (ex: meios
    de recebimento) - mais direto que um campo de adicionar/remover."""

    changed = Signal()

    def __init__(self, columns: int = 3, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.columns = columns
        self.checks: dict[str, QCheckBox] = {}
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setHorizontalSpacing(16)
        self._layout.setVerticalSpacing(6)

    def set_options(self, options: list[str], selected: list[str] | None = None) -> None:
        selected = selected or []
        for check in self.checks.values():
            check.deleteLater()
        self.checks = {}
        values = list(dict.fromkeys([*options, *[value for value in selected if value not in options]]))
        for index, value in enumerate(values):
            check = QCheckBox(value)
            check.setChecked(value in selected)
            check.toggled.connect(lambda _checked: self.changed.emit())
            self.checks[value] = check
            self._layout.addWidget(check, index // self.columns, index % self.columns)

    def set_selected(self, selected: list[str]) -> None:
        missing = [value for value in selected if value not in self.checks]
        if missing:
            self.set_options(list(self.checks), selected)
            return
        for value, check in self.checks.items():
            check.blockSignals(True)
            check.setChecked(value in selected)
            check.blockSignals(False)

    def selected(self) -> list[str]:
        return [value for value, check in self.checks.items() if check.isChecked()]
