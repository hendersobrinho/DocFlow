from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from documentos_empresa_app.database.connection import DatabaseManager
from documentos_empresa_app.database.repositories import (
    DocumentoPendenteRevisaoRepository,
    DocumentoRepository,
    EmpresaRepository,
    LogRepository,
    TipoRepository,
)
from documentos_empresa_app.database.schema import initialize_schema
from documentos_empresa_app.services.audit_service import AuditService
from documentos_empresa_app.services.batch_organize_service import BatchOrganizeService
from documentos_empresa_app.services.document_extraction_service import DocumentExtractionError
from documentos_empresa_app.services.document_organizer_service import DocumentOrganizerService
from documentos_empresa_app.services.documento_service import DocumentoService
from documentos_empresa_app.services.llm_types import CompetenceSuggestion, LLMCompetenceSuggestionError
from documentos_empresa_app.services.session_service import SessionService
from documentos_empresa_app.services.tipo_service import TipoService
from documentos_empresa_app.utils.common import ValidationError


class _FakeExtractionService:
    def __init__(self, text: str = "texto do documento", error: Exception | None = None) -> None:
        self.text = text
        self.error = error
        self.calls: list[Path] = []

    def extract_text(self, file_path: Path) -> str:
        self.calls.append(file_path)
        if self.error:
            raise self.error
        return self.text


class _FakeDocumentAgentService:
    def __init__(self, extraction_service: _FakeExtractionService) -> None:
        self.extraction_service = extraction_service


class _FakeCompetenceSuggestionClient:
    def __init__(self, suggestion: CompetenceSuggestion | None = None, error: Exception | None = None) -> None:
        self.suggestion = suggestion
        self.error = error
        self.calls: list[tuple[str, list[dict]]] = []

    def suggest(self, document_text: str, registered_documents: list[dict]) -> CompetenceSuggestion:
        self.calls.append((document_text, registered_documents))
        if self.error:
            raise self.error
        return self.suggestion


class BatchOrganizeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "test_batch.db"
        db_manager = DatabaseManager(db_path)
        initialize_schema(db_manager)

        self.empresa_repository = EmpresaRepository(db_manager)
        self.pendente_repository = DocumentoPendenteRevisaoRepository(db_manager)
        self.tipo_repository = TipoRepository(db_manager)
        self.documento_repository = DocumentoRepository(db_manager)
        log_repository = LogRepository(db_manager)
        session_service = SessionService()
        audit_service = AuditService(log_repository, session_service)

        self.tipo_service = TipoService(self.tipo_repository)
        self.documento_service = DocumentoService(
            self.documento_repository, self.empresa_repository, self.tipo_repository
        )

        self.document_organizer_service = DocumentOrganizerService(
            self.empresa_repository, self.pendente_repository, audit_service=audit_service,
            session_service=session_service,
        )

        self.company_dir = Path(self.temp_dir.name) / "1. Acme"
        (self.company_dir / "2026").mkdir(parents=True)
        (self.company_dir / "2026" / "Sicoob CC 03-2026.pdf").write_bytes(b"conteudo")
        self.inbox_dir = Path(self.temp_dir.name) / "inbox"
        self.inbox_dir.mkdir()

        self.extraction_service = _FakeExtractionService()
        self.document_agent_service = _FakeDocumentAgentService(self.extraction_service)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _create_empresa(self, diretorio: str | None = None) -> dict:
        empresa_id = self.empresa_repository.create(1, "Acme Ltda")
        if diretorio:
            self.empresa_repository.update_directory(empresa_id, diretorio)
        return self.empresa_repository.get_by_id(empresa_id)

    def _create_pendente(self, file_path: Path, empresa: dict | None = None) -> dict:
        pendente_id = self.pendente_repository.create(
            str(file_path),
            file_path.name,
            None,
            empresa["id"] if empresa else None,
            empresa["nome_empresa"] if empresa else None,
            None,
            None,
            "nenhuma",
            None,
        )
        return self.pendente_repository.get_by_id(pendente_id)

    def _make_service(self, client=None) -> BatchOrganizeService:
        return BatchOrganizeService(
            self.document_agent_service,
            self.document_organizer_service,
            self.documento_service,
            competence_suggestion_client=client,
        )

    def _register_documento(
        self,
        empresa_id: int,
        nome_tipo: str = "Extratos Bancarios",
        nome_documento: str = "Extrato Sicoob CC",
    ) -> dict:
        tipo_id = self.tipo_service.create_tipo(nome_tipo, "mensal")
        documento_id = self.documento_service.create_documento(empresa_id, tipo_id, nome_documento)
        return self.documento_service.get_documento(documento_id)

    def test_eligible_pendentes_filters_out_missing_empresa(self) -> None:
        file_path = self.inbox_dir / "sem_empresa.pdf"
        file_path.write_bytes(b"conteudo")
        pendente_sem_empresa = self._create_pendente(file_path)

        empresa = self._create_empresa(diretorio=str(self.company_dir))
        file_path2 = self.inbox_dir / "com_empresa.pdf"
        file_path2.write_bytes(b"conteudo")
        pendente_com_empresa = self._create_pendente(file_path2, empresa)

        service = self._make_service()
        eligible = service.eligible_pendentes([pendente_sem_empresa, pendente_com_empresa])

        self.assertEqual([p["id"] for p in eligible], [pendente_com_empresa["id"]])

    def test_build_rows_without_client_returns_error(self) -> None:
        empresa = self._create_empresa(diretorio=str(self.company_dir))
        file_path = self.inbox_dir / "extrato.pdf"
        file_path.write_bytes(b"conteudo")
        pendente = self._create_pendente(file_path, empresa)

        service = self._make_service(client=None)
        rows = service.build_rows([pendente], empresas_root_dir=None)

        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0].proposal)
        self.assertIsNone(rows[0].suggestion)
        self.assertEqual(rows[0].error, "Sugestao de competencia por IA nao configurada.")

    def test_build_rows_handles_extraction_failure(self) -> None:
        empresa = self._create_empresa(diretorio=str(self.company_dir))
        file_path = self.inbox_dir / "extrato.pdf"
        file_path.write_bytes(b"conteudo")
        pendente = self._create_pendente(file_path, empresa)

        self.extraction_service.error = DocumentExtractionError("arquivo corrompido")
        client = _FakeCompetenceSuggestionClient()
        service = self._make_service(client=client)

        rows = service.build_rows([pendente], empresas_root_dir=None)

        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0].proposal)
        self.assertIn("Falha ao ler o documento", rows[0].error)

    def test_build_rows_handles_suggestion_failure(self) -> None:
        empresa = self._create_empresa(diretorio=str(self.company_dir))
        file_path = self.inbox_dir / "extrato.pdf"
        file_path.write_bytes(b"conteudo")
        pendente = self._create_pendente(file_path, empresa)

        client = _FakeCompetenceSuggestionClient(error=LLMCompetenceSuggestionError("falhou"))
        service = self._make_service(client=client)

        rows = service.build_rows([pendente], empresas_root_dir=None)

        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0].proposal)
        self.assertIn("Falha na sugestao de competencia", rows[0].error)

    def test_build_rows_happy_path_returns_proposal(self) -> None:
        empresa = self._create_empresa(diretorio=str(self.company_dir))
        documento = self._register_documento(empresa["id"])
        file_path = self.inbox_dir / "extrato.pdf"
        file_path.write_bytes(b"conteudo")
        pendente = self._create_pendente(file_path, empresa)

        client = _FakeCompetenceSuggestionClient(
            suggestion=CompetenceSuggestion(
                mes=4, ano=2026, documento_empresa_id=documento["id"], banco="Sicoob", tipo_conta="cc"
            )
        )
        service = self._make_service(client=client)

        rows = service.build_rows([pendente], empresas_root_dir=None)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertIsNone(row.error)
        self.assertIsNone(row.needs_input_message)
        self.assertIsNotNone(row.proposal)
        self.assertEqual(row.proposal.new_filename, "Sicoob CC 04-2026.pdf")
        self.assertEqual(row.suggestion.mes, 4)

    def test_build_rows_reports_needs_input(self) -> None:
        empresa = self._create_empresa()  # sem diretorio_documentos, sem pasta raiz
        documento = self._register_documento(empresa["id"])
        file_path = self.inbox_dir / "extrato.pdf"
        file_path.write_bytes(b"conteudo")
        pendente = self._create_pendente(file_path, empresa)

        client = _FakeCompetenceSuggestionClient(
            suggestion=CompetenceSuggestion(
                mes=4, ano=2026, documento_empresa_id=documento["id"], banco=None, tipo_conta=None
            )
        )
        service = self._make_service(client=client)

        rows = service.build_rows([pendente], empresas_root_dir=None)

        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0].proposal)
        self.assertIsNotNone(rows[0].needs_input_message)

    def test_build_rows_reports_needs_input_when_document_not_recognized(self) -> None:
        empresa = self._create_empresa(diretorio=str(self.company_dir))
        file_path = self.inbox_dir / "desconhecido.pdf"
        file_path.write_bytes(b"conteudo")
        pendente = self._create_pendente(file_path, empresa)

        client = _FakeCompetenceSuggestionClient(
            suggestion=CompetenceSuggestion(mes=4, ano=2026, documento_empresa_id=None, banco=None, tipo_conta=None)
        )
        service = self._make_service(client=client)

        def _propose_should_not_be_called(*args, **kwargs):
            raise AssertionError("propose() nao deveria ser chamado quando o documento nao e reconhecido")

        self.document_organizer_service.propose = _propose_should_not_be_called

        rows = service.build_rows([pendente], empresas_root_dir=None)

        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0].proposal)
        self.assertIsNotNone(rows[0].needs_input_message)

    def test_build_rows_reports_validation_error_from_propose(self) -> None:
        empresa = self._create_empresa(diretorio=str(self.company_dir))
        documento = self._register_documento(empresa["id"])
        file_path = self.inbox_dir / "extrato.pdf"
        file_path.write_bytes(b"conteudo")
        pendente = self._create_pendente(file_path, empresa)
        self.pendente_repository.mark_ignored(pendente["id"])  # ja nao esta mais "pendente"

        client = _FakeCompetenceSuggestionClient(
            suggestion=CompetenceSuggestion(
                mes=4, ano=2026, documento_empresa_id=documento["id"], banco="Sicoob", tipo_conta="cc"
            )
        )
        service = self._make_service(client=client)

        rows = service.build_rows([pendente], empresas_root_dir=None)

        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0].proposal)
        self.assertIsNotNone(rows[0].error)

    def test_execute_row_raises_without_proposal(self) -> None:
        empresa = self._create_empresa(diretorio=str(self.company_dir))
        file_path = self.inbox_dir / "extrato.pdf"
        file_path.write_bytes(b"conteudo")
        pendente = self._create_pendente(file_path, empresa)

        service = self._make_service()
        rows = service.build_rows([pendente], empresas_root_dir=None)

        with self.assertRaises(ValidationError):
            service.execute_row(rows[0])

    def test_execute_row_moves_file_and_resolves_pendente(self) -> None:
        empresa = self._create_empresa(diretorio=str(self.company_dir))
        documento = self._register_documento(empresa["id"])
        file_path = self.inbox_dir / "extrato.pdf"
        file_path.write_bytes(b"conteudo")
        pendente = self._create_pendente(file_path, empresa)

        client = _FakeCompetenceSuggestionClient(
            suggestion=CompetenceSuggestion(
                mes=4, ano=2026, documento_empresa_id=documento["id"], banco="Sicoob", tipo_conta="cc"
            )
        )
        service = self._make_service(client=client)
        rows = service.build_rows([pendente], empresas_root_dir=None)

        destino = service.execute_row(rows[0])

        self.assertEqual(destino, self.company_dir / "2026" / "Sicoob CC 04-2026.pdf")
        self.assertTrue(destino.exists())
        self.assertFalse(file_path.exists())

        reloaded_pendente = self.pendente_repository.get_by_id(pendente["id"])
        self.assertEqual(reloaded_pendente["status"], "resolvido")


if __name__ == "__main__":
    unittest.main()
