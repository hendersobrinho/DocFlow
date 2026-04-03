from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from documentos_empresa_app.database.connection import DatabaseManager
from documentos_empresa_app.database.repositories import (
    DeliveryMethodRepository,
    DocumentoRepository,
    EmpresaRepository,
    LogRepository,
    PeriodoRepository,
    RememberedSessionRepository,
    StatusRepository,
    TipoRepository,
    UsuarioRepository,
)
from documentos_empresa_app.database.schema import initialize_schema
from documentos_empresa_app.services.audit_service import AuditService
from documentos_empresa_app.services.auth_service import AuthService
from documentos_empresa_app.services.database_maintenance_service import DatabaseMaintenanceService
from documentos_empresa_app.services.delivery_method_service import DeliveryMethodService
from documentos_empresa_app.services.documento_service import DocumentoService
from documentos_empresa_app.services.empresa_service import EmpresaService
from documentos_empresa_app.services.import_service import ImportService
from documentos_empresa_app.services.log_service import LogService
from documentos_empresa_app.services.pending_report_service import PendingReportService
from documentos_empresa_app.services.periodo_service import PeriodoService
from documentos_empresa_app.services.session_service import SessionService
from documentos_empresa_app.services.status_service import StatusService
from documentos_empresa_app.services.tipo_service import TipoService
from documentos_empresa_app.services.user_service import UserService


@dataclass(slots=True)
class ApplicationServices:
    empresa_service: EmpresaService
    delivery_method_service: DeliveryMethodService
    tipo_service: TipoService
    documento_service: DocumentoService
    periodo_service: PeriodoService
    status_service: StatusService
    import_service: ImportService
    database_maintenance_service: DatabaseMaintenanceService
    auth_service: AuthService
    user_service: UserService
    log_service: LogService
    pending_report_service: PendingReportService
    session_service: SessionService


def build_application_services(db_path: str | Path, session_service: SessionService | None = None) -> ApplicationServices:
    db_manager = DatabaseManager(db_path)
    initialize_schema(db_manager)

    session = session_service or SessionService()

    empresa_repository = EmpresaRepository(db_manager)
    delivery_method_repository = DeliveryMethodRepository(db_manager)
    tipo_repository = TipoRepository(db_manager)
    documento_repository = DocumentoRepository(db_manager)
    periodo_repository = PeriodoRepository(db_manager)
    status_repository = StatusRepository(db_manager)
    usuario_repository = UsuarioRepository(db_manager)
    remembered_session_repository = RememberedSessionRepository(db_manager)
    log_repository = LogRepository(db_manager)

    audit_service = AuditService(log_repository, session)
    empresa_service = EmpresaService(empresa_repository, audit_service=audit_service, session_service=session)
    delivery_method_service = DeliveryMethodService(
        delivery_method_repository,
        empresa_repository,
        audit_service=audit_service,
        session_service=session,
    )
    tipo_service = TipoService(tipo_repository)
    documento_service = DocumentoService(
        documento_repository,
        empresa_repository,
        tipo_repository,
        audit_service=audit_service,
        session_service=session,
    )
    periodo_service = PeriodoService(periodo_repository)
    pending_report_service = PendingReportService(
        empresa_repository,
        documento_repository,
        periodo_repository,
        status_repository,
    )
    status_service = StatusService(
        empresa_repository,
        documento_repository,
        periodo_repository,
        status_repository,
        audit_service=audit_service,
        session_service=session,
    )
    import_service = ImportService(empresa_service, tipo_service, documento_service)
    database_maintenance_service = DatabaseMaintenanceService(db_manager)
    auth_service = AuthService(usuario_repository, remembered_session_repository)
    user_service = UserService(
        usuario_repository,
        session,
        audit_service=audit_service,
        auth_service=auth_service,
    )
    log_service = LogService(log_repository, session)

    return ApplicationServices(
        empresa_service=empresa_service,
        delivery_method_service=delivery_method_service,
        tipo_service=tipo_service,
        documento_service=documento_service,
        periodo_service=periodo_service,
        status_service=status_service,
        import_service=import_service,
        database_maintenance_service=database_maintenance_service,
        auth_service=auth_service,
        user_service=user_service,
        log_service=log_service,
        pending_report_service=pending_report_service,
        session_service=session,
    )
