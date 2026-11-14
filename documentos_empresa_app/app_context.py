from __future__ import annotations

from dataclasses import dataclass

from documentos_empresa_app.database.connection import DatabaseManager
from documentos_empresa_app.database.repositories import (
    CobrancaRepository,
    CollectionConfigRepository,
    DeliveryMethodRepository,
    DocumentoRepository,
    EmpresaRepository,
    EnvioProgramadoRepository,
    LogRepository,
    ImagemEmailRepository,
    ModeloMensagemRepository,
    PeriodoRepository,
    RememberedSessionRepository,
    RodadaRepository,
    SituacaoCobrancaRepository,
    SocioRepository,
    StatusRepository,
    TipoRepository,
    UsuarioRepository,
    VerificacaoRepository,
)
from documentos_empresa_app.database.schema import initialize_schema
from documentos_empresa_app.services.audit_service import AuditService
from documentos_empresa_app.services.auth_service import AuthService
from documentos_empresa_app.services.cobranca_service import CobrancaService
from documentos_empresa_app.services.collection_service import CollectionService
from documentos_empresa_app.services.database_maintenance_service import DatabaseMaintenanceService
from documentos_empresa_app.services.delivery_method_service import DeliveryMethodService
from documentos_empresa_app.services.documento_service import DocumentoService
from documentos_empresa_app.services.email_campaign_service import EmailCampaignService
from documentos_empresa_app.services.email_sender_service import EmailSenderService
from documentos_empresa_app.services.empresa_service import EmpresaService
from documentos_empresa_app.services.envio_programado_service import EnvioProgramadoService
from documentos_empresa_app.services.import_service import ImportService
from documentos_empresa_app.services.log_service import LogService
from documentos_empresa_app.services.panorama_service import PanoramaService
from documentos_empresa_app.services.pending_report_service import PendingReportService
from documentos_empresa_app.services.periodo_service import PeriodoService
from documentos_empresa_app.services.rodada_service import RodadaService
from documentos_empresa_app.services.session_service import SessionService
from documentos_empresa_app.services.socios_service import SociosService
from documentos_empresa_app.services.whatsapp_service import WhatsAppService
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
    panorama_service: PanoramaService
    collection_service: CollectionService
    session_service: SessionService
    email_campaign_service: EmailCampaignService
    cobranca_service: CobrancaService
    rodada_service: RodadaService
    envio_programado_service: EnvioProgramadoService
    audit_service: AuditService
    whatsapp_service: WhatsAppService
    email_sender_service: EmailSenderService
    socios_service: SociosService


def build_application_services(
    database_conninfo: str,
    session_service: SessionService | None = None,
) -> ApplicationServices:
    db_manager = DatabaseManager(database_conninfo)
    initialize_schema(db_manager)
    database_maintenance_service = DatabaseMaintenanceService(db_manager)

    session = session_service or SessionService()

    empresa_repository = EmpresaRepository(db_manager)
    collection_config_repository = CollectionConfigRepository(db_manager)
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
        documento_repository,
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
    panorama_service = PanoramaService(
        empresa_repository,
        documento_repository,
        periodo_repository,
        status_repository,
    )
    collection_service = CollectionService(
        collection_config_repository,
        empresa_repository,
        documento_repository,
        periodo_repository,
        status_repository,
    )
    import_service = ImportService(
        empresa_service,
        tipo_service,
        documento_service,
        periodo_service,
        status_service,
        delivery_method_service=delivery_method_service,
    )
    auth_service = AuthService(usuario_repository, remembered_session_repository)
    user_service = UserService(
        usuario_repository,
        session,
        audit_service=audit_service,
        auth_service=auth_service,
    )
    log_service = LogService(log_repository, session)
    email_campaign_service = EmailCampaignService(session, empresa_repository)
    cobranca_service = CobrancaService(
        CobrancaRepository(db_manager),
        VerificacaoRepository(db_manager),
        empresa_repository,
        documento_repository,
        periodo_repository,
        status_repository,
        status_service,
        collection_service,
        audit_service=audit_service,
        session_service=session,
        situacao_repository=SituacaoCobrancaRepository(db_manager),
    )
    rodada_service = RodadaService(
        RodadaRepository(db_manager),
        empresa_repository,
        audit_service=audit_service,
        session_service=session,
    )
    envio_programado_service = EnvioProgramadoService(
        EnvioProgramadoRepository(db_manager),
        empresa_repository,
        tipo_repository,
        audit_service=audit_service,
        session_service=session,
        modelo_repository=ModeloMensagemRepository(db_manager),
        imagem_repository=ImagemEmailRepository(db_manager),
    )

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
        panorama_service=panorama_service,
        collection_service=collection_service,
        session_service=session,
        email_campaign_service=email_campaign_service,
        cobranca_service=cobranca_service,
        rodada_service=rodada_service,
        envio_programado_service=envio_programado_service,
        audit_service=audit_service,
        whatsapp_service=WhatsAppService(),
        email_sender_service=EmailSenderService(),
        socios_service=SociosService(
            SocioRepository(db_manager),
            empresa_repository,
            periodo_repository,
            audit_service=audit_service,
            session_service=session,
        ),
    )

