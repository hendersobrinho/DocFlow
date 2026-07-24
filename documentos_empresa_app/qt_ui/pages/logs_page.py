from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.widgets.common import PageHeader, ToolbarRow, make_button
from documentos_empresa_app.services.log_service import MIN_LOG_RETENTION_DAYS
from documentos_empresa_app.utils.common import MONTH_NAMES, ValidationError


class LogsPage(QWidget):
    def __init__(self, services, on_data_changed, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.on_data_changed = on_data_changed
        self.company_map: dict[str, int] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        layout.addWidget(PageHeader("Logs", "Auditoria das acoes realizadas no sistema, da mais recente para a mais antiga."))

        toolbar = ToolbarRow()
        toolbar.add(QLabel("Empresa"))
        self.company_combo = QComboBox()
        self.company_combo.setMinimumWidth(240)
        toolbar.add(self.company_combo)
        toolbar.add(QLabel("Ano"))
        self.year_combo = QComboBox()
        self.year_combo.currentTextChanged.connect(lambda _text: self._sync_month_values())
        toolbar.add(self.year_combo)
        toolbar.add(QLabel("Mes"))
        self.month_combo = QComboBox()
        self.month_combo.setMinimumWidth(150)
        toolbar.add(self.month_combo)
        apply_button = make_button("Aplicar filtros", "primary")
        apply_button.clicked.connect(self.refresh_data)
        toolbar.add(apply_button)
        clear_button = make_button("Limpar filtros", "quiet")
        clear_button.clicked.connect(self.clear_filters)
        toolbar.add(clear_button)
        purge_button = make_button("Expurgar logs antigos...", "danger")
        purge_button.setToolTip(
            "Remove logs mais antigos que o prazo informado - a LGPD pede que dado pessoal "
            "(nome de usuarios, empresas) nao fique guardado indefinidamente sem necessidade."
        )
        purge_button.clicked.connect(self.purge_old_logs)
        toolbar.add(purge_button)
        toolbar.add_stretch()
        self.info_label = QLabel("")
        self.info_label.setObjectName("Muted")
        toolbar.add(self.info_label)
        layout.addWidget(toolbar)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Data/Hora", "Usuario", "Acao", "Empresa", "Periodo", "Descricao"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        for col in (0, 1, 2, 4):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(3, 220)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

    def refresh_data(self) -> None:
        self._refresh_filter_options()
        selected_month = self.month_combo.currentText()
        try:
            logs = self.services.log_service.list_logs(
                limit=500,
                empresa_id=self.company_map.get(self.company_combo.currentText()),
                periodo_ano=int(self.year_combo.currentText()) if self.year_combo.currentText() else None,
                periodo_mes=int(selected_month.split(" - ", 1)[0]) if selected_month else None,
            )
        except ValidationError:
            return

        self.info_label.setText(
            f"{len(logs)} log(s) encontrados." if logs else "Nenhum log encontrado para os filtros informados."
        )

        self.table.setRowCount(0)
        for log in logs:
            row = self.table.rowCount()
            self.table.insertRow(row)
            periodo = "-"
            if log["periodo_ano"] and log["periodo_mes"]:
                periodo = f'{int(log["periodo_mes"]):02d}/{int(log["periodo_ano"])}'
            values = (
                log["data_hora"],
                log["username"],
                log["acao"],
                log["empresa_nome"] or "-",
                periodo,
                log["descricao"],
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 5:
                    item.setToolTip(str(value))
                self.table.setItem(row, col, item)

    def purge_old_logs(self) -> None:
        days, confirmed = QInputDialog.getInt(
            self,
            "Expurgar logs antigos",
            f"Remover logs com mais de quantos dias? (minimo {MIN_LOG_RETENTION_DAYS})",
            365,
            MIN_LOG_RETENTION_DAYS,
            3650,
        )
        if not confirmed:
            return

        try:
            affected = self.services.log_service.count_logs_older_than(days)
        except ValidationError as exc:
            QMessageBox.critical(self, "Logs", str(exc))
            return

        if affected == 0:
            QMessageBox.information(self, "Logs", f"Nenhum log com mais de {days} dia(s) encontrado.")
            return

        answer = QMessageBox.question(
            self,
            "Logs",
            f"Isso vai apagar {affected} log(s) com mais de {days} dia(s), definitivamente. Continuar?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            removed = self.services.log_service.purge_logs_older_than(days)
        except ValidationError as exc:
            QMessageBox.critical(self, "Logs", str(exc))
            return

        QMessageBox.information(self, "Logs", f"{removed} log(s) removido(s).")
        self.refresh_data()

    def clear_filters(self) -> None:
        self.company_combo.setCurrentText("")
        self.year_combo.setCurrentText("")
        self.month_combo.setCurrentText("")
        self.refresh_data()

    def _refresh_filter_options(self) -> None:
        selected_company = self.company_combo.currentText()
        selected_year = self.year_combo.currentText()
        selected_month = self.month_combo.currentText()

        companies = self.services.log_service.list_logged_companies()
        self.company_map = {}
        name_counts: dict[str, int] = {}
        for company in companies:
            base_name = company["nome_empresa"] or "Empresa removida"
            name_counts[base_name] = name_counts.get(base_name, 0) + 1

        self.company_combo.blockSignals(True)
        self.company_combo.clear()
        self.company_combo.addItem("")
        for company in companies:
            if company["id"] is None:
                continue
            base_name = company["nome_empresa"] or "Empresa removida"
            label = base_name if name_counts[base_name] == 1 else f"{base_name} (ID {company['id']})"
            self.company_map[label] = company["id"]
            self.company_combo.addItem(label)
        self.company_combo.setCurrentText(selected_company if selected_company in self.company_map else "")
        self.company_combo.blockSignals(False)

        years = [str(year) for year in self.services.log_service.list_log_years()]
        self.year_combo.blockSignals(True)
        self.year_combo.clear()
        self.year_combo.addItem("")
        self.year_combo.addItems(years)
        self.year_combo.setCurrentText(selected_year if selected_year in years else "")
        self.year_combo.blockSignals(False)

        self._sync_month_values()
        index = self.month_combo.findText(selected_month)
        if index >= 0:
            self.month_combo.setCurrentIndex(index)

    def _sync_month_values(self) -> None:
        self.month_combo.blockSignals(True)
        self.month_combo.clear()
        self.month_combo.addItem("")
        year_text = self.year_combo.currentText()
        if year_text:
            try:
                months = self.services.log_service.list_log_months_by_year(int(year_text))
            except (ValueError, ValidationError):
                months = []
            for month in months:
                self.month_combo.addItem(f"{month:02d} - {MONTH_NAMES[month]}")
        self.month_combo.blockSignals(False)
