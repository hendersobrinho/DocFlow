from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from documentos_empresa_app.database.connection import DatabaseManager
from documentos_empresa_app.database.repositories import (
    CollectionConfigRepository,
    DeliveryMethodRepository,
    DocumentoPendenteRevisaoRepository,
    DocumentoRepository,
    EmpresaRepository,
    LogRepository,
    PeriodoRepository,
    RememberedSessionRepository,
    StatusRepository,
    TipoRepository,
    UserPreferenceRepository,
    UsuarioRepository,
)
from documentos_empresa_app.database.schema import initialize_schema
from documentos_empresa_app.services.agent_config_service import (
    AgentConfigService,
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_MODELS,
)
from documentos_empresa_app.services.anthropic_chat_service import AnthropicChatService
from documentos_empresa_app.services.anthropic_competence_suggestion import AnthropicCompetenceSuggestionClient
from documentos_empresa_app.services.anthropic_document_classifier import AnthropicDocumentClassifierClient
from documentos_empresa_app.services.audit_service import AuditService
from documentos_empresa_app.services.auth_service import AuthService
from documentos_empresa_app.services.batch_organize_service import BatchOrganizeService
from documentos_empresa_app.services.collection_service import CollectionService
from documentos_empresa_app.services.database_maintenance_service import DatabaseMaintenanceService
from documentos_empresa_app.services.delivery_method_service import DeliveryMethodService
from documentos_empresa_app.services.document_agent_service import DocumentAgentService
from documentos_empresa_app.services.document_classification_service import DocumentClassificationService
from documentos_empresa_app.services.document_extraction_service import DocumentExtractionService
from documentos_empresa_app.services.document_organizer_service import DocumentOrganizerService
from documentos_empresa_app.services.documento_service import DocumentoService
from documentos_empresa_app.services.email_campaign_service import EmailCampaignService
from documentos_empresa_app.services.empresa_service import EmpresaService
from documentos_empresa_app.services.import_service import ImportService
from documentos_empresa_app.services.llm_types import CompetenceSuggestionClient, DocumentChatClient
from documentos_empresa_app.services.log_service import LogService
from documentos_empresa_app.services.openai_chat_service import OpenAIChatService
from documentos_empresa_app.services.openai_competence_suggestion import OpenAICompetenceSuggestionClient
from documentos_empresa_app.services.openai_document_classifier import OpenAIDocumentClassifierClient
from documentos_empresa_app.services.panorama_service import PanoramaService
from documentos_empresa_app.services.pending_report_service import PendingReportService
from documentos_empresa_app.services.periodo_service import PeriodoService
from documentos_empresa_app.services.session_service import SessionService
from documentos_empresa_app.services.status_service import StatusService
from documentos_empresa_app.services.tipo_service import TipoService
from documentos_empresa_app.services.user_service import UserService
from documentos_empresa_app.utils.helpers import (
    load_agent_confidence_threshold,
    load_agent_custom_instructions,
    load_agent_model,
    load_agent_provider,
    load_document_agent_inbox_folder,
    resolve_agent_api_key,
)


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
    document_agent_service: DocumentAgentService
    document_organizer_service: DocumentOrganizerService
    batch_organize_service: BatchOrganizeService
    agent_config_service: AgentConfigService
    document_chat_service: DocumentChatClient | None
    competence_suggestion_client: CompetenceSuggestionClient | None
    email_campaign_service: EmailCampaignService


def build_application_services(db_path: str | Path, session_service: SessionService | None = None) -> ApplicationServices:
    db_manager = DatabaseManager(db_path)
    initialize_schema(db_manager)
    database_maintenance_service = DatabaseMaintenanceService(db_manager)
    database_maintenance_service.optimize_database()

    session = session_service or SessionService()

    empresa_repository = EmpresaRepository(db_manager)
    collection_config_repository = CollectionConfigRepository(db_manager)
    delivery_method_repository = DeliveryMethodRepository(db_manager)
    tipo_repository = TipoRepository(db_manager)
    documento_repository = DocumentoRepository(db_manager)
    periodo_repository = PeriodoRepository(db_manager)
    status_repository = StatusRepository(db_manager)
    usuario_repository = UsuarioRepository(db_manager)
    user_preference_repository = UserPreferenceRepository(db_manager)
    remembered_session_repository = RememberedSessionRepository(db_manager)
    log_repository = LogRepository(db_manager)

    _migrate_legacy_inbox_folder(user_preference_repository, usuario_repository)

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
    )
    auth_service = AuthService(usuario_repository, remembered_session_repository)
    user_service = UserService(
        usuario_repository,
        user_preference_repository,
        session,
        audit_service=audit_service,
        auth_service=auth_service,
    )
    log_service = LogService(log_repository, session)
    agent_config_service = AgentConfigService(session)
    email_campaign_service = EmailCampaignService(session, empresa_repository)

    pendente_revisao_repository = DocumentoPendenteRevisaoRepository(db_manager)
    extraction_service = DocumentExtractionService()
    classification_service = DocumentClassificationService(llm_client=None)
    document_agent_service = DocumentAgentService(
        extraction_service,
        classification_service,
        pendente_revisao_repository,
        empresa_repository,
        empresa_service,
        audit_service=audit_service,
        session_service=session,
    )
    document_organizer_service = DocumentOrganizerService(
        empresa_repository,
        pendente_revisao_repository,
        audit_service=audit_service,
        session_service=session,
    )
    batch_organize_service = BatchOrganizeService(document_agent_service, document_organizer_service)

    services = ApplicationServices(
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
        document_agent_service=document_agent_service,
        document_organizer_service=document_organizer_service,
        batch_organize_service=batch_organize_service,
        agent_config_service=agent_config_service,
        document_chat_service=None,
        competence_suggestion_client=None,
        email_campaign_service=email_campaign_service,
    )
    refresh_agent_runtime(services)
    return services


def _migrate_legacy_inbox_folder(
    user_preference_repository: UserPreferenceRepository,
    usuario_repository: UsuarioRepository,
) -> None:
    """Migra a pasta de entrada global (config local antiga) para o admin mais antigo,
    na primeira vez que a preferencia por usuario e usada."""
    if user_preference_repository.count_all() > 0:
        return
    legacy_folder = load_document_agent_inbox_folder()
    if not legacy_folder:
        return
    admin_users = [user for user in usuario_repository.list_all() if user["tipo_usuario"] == "admin"]
    if not admin_users:
        return
    target_user = min(admin_users, key=lambda user: user["id"])
    user_preference_repository.set_pasta_entrada(target_user["id"], legacy_folder)


def refresh_agent_runtime(services: ApplicationServices) -> None:
    """Reconstroi os clientes de IA do agente a partir da config persistida (provedor,
    api key, modelo, limiar de confianca e prompt customizado), sem exigir reinicio do app."""
    provider = load_agent_provider()
    api_key = resolve_agent_api_key(provider)
    model = load_agent_model(provider) or DEFAULT_MODELS[provider]
    custom_instructions = load_agent_custom_instructions()
    threshold = load_agent_confidence_threshold()

    classification_service = services.document_agent_service.classification_service
    classification_service.confidence_threshold = (
        threshold if threshold is not None else DEFAULT_CONFIDENCE_THRESHOLD
    )

    if not api_key:
        classification_service.llm_client = None
        services.document_chat_service = None
        services.competence_suggestion_client = None
        services.batch_organize_service.competence_suggestion_client = None
        return

    if provider == "openai":
        classification_service.llm_client = OpenAIDocumentClassifierClient(
            api_key, model=model, custom_instructions=custom_instructions
        )
        services.document_chat_service = OpenAIChatService(
            api_key, model=model, custom_instructions=custom_instructions
        )
        services.competence_suggestion_client = OpenAICompetenceSuggestionClient(
            api_key, model=model, custom_instructions=custom_instructions
        )
        services.batch_organize_service.competence_suggestion_client = services.competence_suggestion_client
        return

    classification_service.llm_client = AnthropicDocumentClassifierClient(
        api_key, model=model, custom_instructions=custom_instructions
    )
    services.document_chat_service = AnthropicChatService(
        api_key, model=model, custom_instructions=custom_instructions
    )
    services.competence_suggestion_client = AnthropicCompetenceSuggestionClient(
        api_key, model=model, custom_instructions=custom_instructions
    )
    services.batch_organize_service.competence_suggestion_client = services.competence_suggestion_client
