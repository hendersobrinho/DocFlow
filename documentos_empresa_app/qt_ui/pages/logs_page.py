from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import (
    QComboBox,
    QInputDialog,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.widgets.common import PageHeader, ToolbarRow, make_button
from documentos_empresa_app.qt_ui.widgets.tables import fill_table, make_readonly_table
from documentos_empresa_app.services.log_service import MIN_LOG_RETENTION_DAYS
from documentos_empresa_app.utils.common import MONTH_NAMES, ValidationError

LOG_LIMIT = 500

# Codigo gravado no log -> texto mostrado na tela. Codigos desconhecidos (de versoes
# antigas) aparecem como estao, so trocando "_" por espaco.
ACTION_LABELS = {
    "ALTERACAO_STATUS": "Status alterado",
    "COBRANCA_REGISTRADA": "Cobrança registrada",
    "VERIFICACAO_REGISTRADA": "Verificação registrada",
    "CADASTRO_EMPRESA": "Empresa cadastrada",
    "EDICAO_EMPRESA": "Empresa editada",
    "INATIVACAO_EMPRESA": "Empresa inativada",
    "REATIVACAO_EMPRESA": "Empresa reativada",
    "EXCLUSAO_EMPRESA": "Empresa excluída",
    "CADASTRO_DOCUMENTO": "Documento cadastrado",
    "EDICAO_DOCUMENTO": "Documento editado",
    "EXCLUSAO_DOCUMENTO": "Documento excluído",
    "CADASTRO_DOCUMENTO_PADRAO": "Nome padrão cadastrado",
    "EDICAO_DOCUMENTO_PADRAO": "Nome padrão editado",
    "EXCLUSAO_DOCUMENTO_PADRAO": "Nome padrão excluído",
    "ALTERACAO_TIPO_DOCUMENTO": "Tipo de documento alterado",
    "CADASTRO_MEIO_RECEBIMENTO": "Meio de recebimento cadastrado",
    "EDICAO_MEIO_RECEBIMENTO": "Meio de recebimento editado",
    "EXCLUSAO_MEIO_RECEBIMENTO": "Meio de recebimento excluído",
    "CRIACAO_USUARIO": "Usuário criado",
    "EDICAO_USUARIO": "Usuário editado",
    "INATIVACAO_USUARIO": "Usuário inativado",
    "REATIVACAO_USUARIO": "Usuário reativado",
    "ALTERACAO_SENHA_USUARIO": "Senha alterada",
}

ALL_COMPANIES = "Todas as empresas"
ALL = "Todos"


def action_label(code: str) -> str:
    return ACTION_LABELS.get(code, str(code).replace("_", " ").capitalize())


def format_log_moment(raw: str) -> str:
    try:
        return datetime.strptime(str(raw)[:19], "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return str(raw)


class LogsPage(QWidget):
    """Historico de acoes (auditoria): quem fez o que, quando, em qual empresa."""

    def __init__(self, services, on_data_changed, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.on_data_changed = on_data_changed
        self.company_map: dict[str, int] = {}
        self._syncing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(
            PageHeader("Histórico de ações", "Tudo o que foi feito no sistema, do mais recente para o mais antigo.")
        )

        toolbar = ToolbarRow()
        toolbar.add(QLabel("Empresa"))
        self.company_combo = QComboBox()
        self.company_combo.setMinimumWidth(240)
        self.company_combo.currentIndexChanged.connect(self._on_filter_changed)
        toolbar.add(self.company_combo)
        toolbar.add(QLabel("Ano"))
        self.year_combo = QComboBox()
        self.year_combo.setMinimumWidth(90)
        self.year_combo.currentIndexChanged.connect(self._on_year_changed)
        toolbar.add(self.year_combo)
        toolbar.add(QLabel("Mês"))
        self.month_combo = QComboBox()
        self.month_combo.setMinimumWidth(140)
        self.month_combo.currentIndexChanged.connect(self._on_filter_changed)
        toolbar.add(self.month_combo)
        clear_button = make_button("Limpar filtros", "quiet")
        clear_button.clicked.connect(self.clear_filters)
        toolbar.add(clear_button)
        toolbar.add_stretch()
        self.info_label = QLabel("")
        self.info_label.setObjectName("Muted")
        toolbar.add(self.info_label)
        layout.addWidget(toolbar)

        self.table = make_readonly_table(["Quando", "Quem", "O que", "Empresa", "Competência", "Detalhes"], stretch_column=5)
        layout.addWidget(self.table, 1)

        footer = ToolbarRow()
        footer.add_stretch()
        purge_button = make_button("Apagar registros antigos...", "quiet")
        purge_button.setToolTip(
            "Remove registros mais antigos que o prazo informado - a LGPD pede que dado pessoal "
            "não fique guardado indefinidamente sem necessidade."
        )
        purge_button.clicked.connect(self.purge_old_logs)
        footer.add(purge_button)
        layout.addWidget(footer)

    # Dados -------------------------------------------------------------------------

    def refresh_data(self) -> None:
        self._refresh_filter_options()
        self._load_logs()

    def _load_logs(self) -> None:
        month = self.month_combo.currentData()
        year = self.year_combo.currentData()
        try:
            logs = self.services.log_service.list_logs(
                limit=LOG_LIMIT,
                empresa_id=self.company_combo.currentData(),
                periodo_ano=year,
                periodo_mes=month,
            )
        except ValidationError:
            return

        if not logs:
            self.info_label.setText("Nenhum registro para esses filtros.")
        elif len(logs) >= LOG_LIMIT:
            self.info_label.setText(f"Mostrando os {LOG_LIMIT} mais recentes - use os filtros para refinar.")
        else:
            self.info_label.setText(f"{len(logs)} registro(s).")

        rows = []
        for log in logs:
            competencia = "-"
            if log["periodo_ano"] and log["periodo_mes"]:
                competencia = f'{int(log["periodo_mes"]):02d}/{int(log["periodo_ano"])}'
            rows.append(
                (
                    log["id"],
                    [
                        format_log_moment(log["data_hora"]),
                        log["username"],
                        action_label(log["acao"]),
                        log["empresa_nome"] or "-",
                        competencia,
                        log["descricao"],
                    ],
                )
            )
        fill_table(self.table, rows)

    def _refresh_filter_options(self) -> None:
        self._syncing = True
        selected_company = self.company_combo.currentData()
        selected_year = self.year_combo.currentData()

        self.company_combo.clear()
        self.company_combo.addItem(ALL_COMPANIES, None)
        companies = self.services.log_service.list_logged_companies()
        name_counts: dict[str, int] = {}
        for company in companies:
            base_name = company["nome_empresa"] or "Empresa removida"
            name_counts[base_name] = name_counts.get(base_name, 0) + 1
        for company in companies:
            if company["id"] is None:
                continue
            base_name = company["nome_empresa"] or "Empresa removida"
            label = base_name if name_counts[base_name] == 1 else f"{base_name} (ID {company['id']})"
            self.company_combo.addItem(label, company["id"])
        index = self.company_combo.findData(selected_company)
        self.company_combo.setCurrentIndex(index if index >= 0 else 0)

        self.year_combo.clear()
        self.year_combo.addItem(ALL, None)
        for year in self.services.log_service.list_log_years():
            self.year_combo.addItem(str(year), int(year))
        index = self.year_combo.findData(selected_year)
        self.year_combo.setCurrentIndex(index if index >= 0 else 0)
        self._sync_month_values()
        self._syncing = False

    def _sync_month_values(self) -> None:
        selected_month = self.month_combo.currentData()
        self.month_combo.blockSignals(True)
        self.month_combo.clear()
        self.month_combo.addItem(ALL, None)
        year = self.year_combo.currentData()
        if year is not None:
            try:
                months = self.services.log_service.list_log_months_by_year(int(year))
            except ValidationError:
                months = []
            for month in months:
                self.month_combo.addItem(f"{month:02d} - {MONTH_NAMES[month]}", int(month))
        index = self.month_combo.findData(selected_month)
        self.month_combo.setCurrentIndex(index if index >= 0 else 0)
        self.month_combo.blockSignals(False)

    def _on_year_changed(self, _index: int) -> None:
        if self._syncing:
            return
        self._sync_month_values()
        self._load_logs()

    def _on_filter_changed(self, _index: int) -> None:
        if not self._syncing:
            self._load_logs()

    def clear_filters(self) -> None:
        self._syncing = True
        self.company_combo.setCurrentIndex(0)
        self.year_combo.setCurrentIndex(0)
        self._sync_month_values()
        self._syncing = False
        self._load_logs()

    # Limpeza -----------------------------------------------------------------------

    def purge_old_logs(self) -> None:
        days, confirmed = QInputDialog.getInt(
            self,
            "Apagar registros antigos",
            f"Apagar registros com mais de quantos dias? (mínimo {MIN_LOG_RETENTION_DAYS})",
            365,
            MIN_LOG_RETENTION_DAYS,
            3650,
        )
        if not confirmed:
            return
        try:
            affected = self.services.log_service.count_logs_older_than(days)
        except ValidationError as exc:
            QMessageBox.critical(self, "Histórico de ações", str(exc))
            return
        if affected == 0:
            QMessageBox.information(self, "Histórico de ações", f"Nenhum registro com mais de {days} dia(s).")
            return
        answer = QMessageBox.question(
            self,
            "Histórico de ações",
            f"Isso apaga de vez {affected} registro(s) com mais de {days} dia(s). Continuar?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            removed = self.services.log_service.purge_logs_older_than(days)
        except ValidationError as exc:
            QMessageBox.critical(self, "Histórico de ações", str(exc))
            return
        QMessageBox.information(self, "Histórico de ações", f"{removed} registro(s) apagado(s).")
        self.refresh_data()
