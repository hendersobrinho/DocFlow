from __future__ import annotations

from documentos_empresa_app.database.repositories import LogRepository
from documentos_empresa_app.services.session_service import SessionService
from documentos_empresa_app.utils.common import ValidationError


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

    def _ensure_admin(self) -> None:
        if not self.session_service.is_admin():
            raise ValidationError("Apenas usuarios admin podem visualizar os logs.")
