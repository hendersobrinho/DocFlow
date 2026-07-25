from __future__ import annotations

from datetime import datetime, timedelta

from documentos_empresa_app.database.repositories import LogRepository
from documentos_empresa_app.services.session_service import SessionService
from documentos_empresa_app.utils.common import ValidationError

MIN_LOG_RETENTION_DAYS = 30


class LogService:
    def __init__(self, log_repository: LogRepository, session_service: SessionService) -> None:
        self.log_repository = log_repository
        self.session_service = session_service

    def list_logs(
        self,
        limit: int = 500,
        empresa_id: int | None = None,
        periodo_ano: int | None = None,
        periodo_mes: int | None = None,
    ) -> list[dict]:
        self._ensure_admin()
        return self.log_repository.list_recent(
            limit=limit,
            empresa_id=empresa_id,
            periodo_ano=periodo_ano,
            periodo_mes=periodo_mes,
        )

    def list_logged_companies(self) -> list[dict]:
        self._ensure_admin()
        return self.log_repository.list_logged_companies()

    def list_log_years(self) -> list[int]:
        self._ensure_admin()
        return self.log_repository.list_log_years()

    def list_log_months_by_year(self, ano: int) -> list[int]:
        self._ensure_admin()
        return self.log_repository.list_log_months_by_year(ano)

    def count_logs_older_than(self, retention_days: int) -> int:
        """Numero de logs mais antigos que retention_days - usado pra mostrar o
        impacto antes de confirmar o expurgo."""
        self._ensure_admin()
        cutoff = self._cutoff_iso(retention_days)
        return self.log_repository.count_older_than(cutoff)

    def purge_logs_older_than(self, retention_days: int) -> int:
        """Apaga logs mais antigos que retention_days - a LGPD pede que dado
        pessoal (nomes de usuario, empresa) nao fique guardado indefinidamente
        sem necessidade. Retorna quantos registros foram removidos."""
        self._ensure_admin()
        if retention_days < MIN_LOG_RETENTION_DAYS:
            raise ValidationError(f"A retencao minima de logs e de {MIN_LOG_RETENTION_DAYS} dias.")
        cutoff = self._cutoff_iso(retention_days)
        return self.log_repository.delete_older_than(cutoff)

    def _cutoff_iso(self, retention_days: int) -> str:
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        return cutoff_date.strftime("%Y-%m-%d %H:%M:%S")

    def _ensure_admin(self) -> None:
        if not self.session_service.is_admin():
            raise ValidationError("Apenas usuarios admin podem visualizar os logs.")
