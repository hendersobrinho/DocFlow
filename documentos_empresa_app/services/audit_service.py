from __future__ import annotations

from datetime import datetime

from documentos_empresa_app.database.repositories import LogRepository
from documentos_empresa_app.services.session_service import SessionService


class AuditService:
    def __init__(self, log_repository: LogRepository, session_service: SessionService) -> None:
        self.log_repository = log_repository
        self.session_service = session_service

    def log(
        self,
        acao: str,
        entidade: str,
        entidade_id: int | None,
        descricao: str,
        empresa_id: int | None = None,
        empresa_nome: str | None = None,
        periodo_ano: int | None = None,
        periodo_mes: int | None = None,
    ) -> None:
        self.log_repository.create(
            usuario_id=self.session_service.get_user_id(),
            acao=acao,
            entidade=entidade,
            entidade_id=entidade_id,
            empresa_id=empresa_id,
            empresa_nome=empresa_nome,
            periodo_ano=periodo_ano,
            periodo_mes=periodo_mes,
            descricao=descricao,
            data_hora=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
