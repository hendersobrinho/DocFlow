from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from documentos_empresa_app.database.connection import DatabaseManager
from documentos_empresa_app.database.repositories import (
    DocumentoPendenteRevisaoRepository,
    EmpresaRepository,
    LogRepository,
)
from documentos_empresa_app.database.schema import initialize_schema
from documentos_empresa_app.services.llm_types import LLMSuggestion
from documentos_empresa_app.services.audit_service import AuditService
from documentos_empresa_app.services.document_agent_service import DocumentAgentService
from documentos_empresa_app.services.document_classification_service import (
    ClassificationResult,
    DocumentClassificationService,
)
from documentos_empresa_app.services.document_extraction_service import (
    DocumentExtractionError,
    DocumentExtractionService,
)
from documentos_empresa_app.services.empresa_service import EmpresaService
from documentos_empresa_app.services.session_service import SessionService
from documentos_empresa_app.utils import document_agent_diagnostics
from documentos_empresa_app.utils.common import ValidationError

try:
    from openpyxl import Workbook
except ImportError:  # pragma: no cover - depende do ambiente local
    Workbook = None

try:
    import pypdf  # noqa: F401

    HAS_PYPDF = True
except ImportError:  # pragma: no cover - depende do ambiente local
    HAS_PYPDF = False


class DocumentExtractionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = DocumentExtractionService()
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_is_supported(self) -> None:
        self.assertTrue(self.service.is_supported(Path("nota.pdf")))
        self.assertTrue(self.service.is_supported(Path("nota.xlsx")))
        self.assertFalse(self.service.is_supported(Path("nota.txt")))

    def test_extract_text_raises_for_unsupported_extension(self) -> None:
        file_path = Path(self.temp_dir.name) / "arquivo.txt"
        file_path.write_text("conteudo")
        with self.assertRaises(DocumentExtractionError):
            self.service.extract_text(file_path)

    @unittest.skipIf(Workbook is None, "openpyxl indisponivel neste ambiente")
    def test_extract_spreadsheet_text(self) -> None:
        file_path = Path(self.temp_dir.name) / "boleto.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["CNPJ", "12.345.678/0001-90"])
        sheet.append(["Empresa", "Acme Ltda"])
        workbook.save(file_path)

        text = self.service.extract_text(file_path)
        self.assertIn("12.345.678/0001-90", text)
        self.assertIn("Acme Ltda", text)


class DocumentClassificationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.empresa = {"id": 1, "nome_empresa": "Acme Ltda", "cnpj": "12345678000190"}
        self.index = {"12345678000190": self.empresa}

    def test_regex_match_free_path(self) -> None:
        service = DocumentClassificationService(llm_client=None)
        text = "Documento referente ao CNPJ 12.345.678/0001-90 emitido em 2026."
        result = service.classify(text, self.index, ["Acme Ltda"])

        self.assertEqual(result.origem, "regex_cnpj")
        self.assertEqual(result.matched_empresa, self.empresa)
        self.assertEqual(result.cnpj_extraido, "12345678000190")

    def test_no_match_without_llm_client(self) -> None:
        service = DocumentClassificationService(llm_client=None)
        result = service.classify("documento sem cnpj conhecido", self.index, ["Acme Ltda"])

        self.assertIsNone(result.matched_empresa)
        self.assertEqual(result.origem, "nenhuma")
        self.assertIn("nao configurada", result.motivo)

    def test_llm_high_confidence_match(self) -> None:
        fake_client = _FakeLLMClient(
            LLMSuggestion(
                suggested_company_name="Acme Ltda",
                suggested_cnpj="12.345.678/0001-90",
                suggested_document_type="Boleto",
                confidence=0.9,
            )
        )
        service = DocumentClassificationService(llm_client=fake_client, confidence_threshold=0.75)
        result = service.classify("documento sem cnpj no texto", self.index, ["Acme Ltda"])

        self.assertEqual(result.origem, "llm")
        self.assertEqual(result.matched_empresa, self.empresa)
        self.assertEqual(result.tipo_documento_sugerido, "Boleto")

    def test_llm_low_confidence_goes_to_review(self) -> None:
        fake_client = _FakeLLMClient(
            LLMSuggestion(
                suggested_company_name="Acme Ltda",
                suggested_cnpj="12.345.678/0001-90",
                suggested_document_type="Boleto",
                confidence=0.3,
            )
        )
        service = DocumentClassificationService(llm_client=fake_client, confidence_threshold=0.75)
        result = service.classify("documento sem cnpj no texto", self.index, ["Acme Ltda"])

        self.assertIsNone(result.matched_empresa)
        self.assertEqual(result.origem, "llm")

    def test_llm_suggests_unknown_company_goes_to_review(self) -> None:
        fake_client = _FakeLLMClient(
            LLMSuggestion(
                suggested_company_name="Empresa Desconhecida",
                suggested_cnpj="99.999.999/0001-99",
                suggested_document_type="Extrato",
                confidence=0.95,
            )
        )
        service = DocumentClassificationService(llm_client=fake_client, confidence_threshold=0.75)
        result = service.classify("documento sem cnpj conhecido", self.index, ["Acme Ltda"])

        self.assertIsNone(result.matched_empresa)
        self.assertEqual(result.empresa_sugerida_nome, "Empresa Desconhecida")


class _FakeLLMClient:
    def __init__(self, suggestion: LLMSuggestion) -> None:
        self.suggestion = suggestion

    def suggest(self, document_text: str, known_company_names: list[str]) -> LLMSuggestion:
        return self.suggestion


class DocumentAgentServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "test_agent.db"
        db_manager = DatabaseManager(db_path)
        initialize_schema(db_manager)

        self.empresa_repository = EmpresaRepository(db_manager)
        self.pendente_repository = DocumentoPendenteRevisaoRepository(db_manager)
        self.log_repository = LogRepository(db_manager)
        self.session_service = SessionService()
        self.audit_service = AuditService(self.log_repository, self.session_service)
        self.empresa_service = EmpresaService(
            self.empresa_repository, audit_service=self.audit_service, session_service=self.session_service
        )

        self.agent_service = DocumentAgentService(
            DocumentExtractionService(),
            DocumentClassificationService(llm_client=None),
            self.pendente_repository,
            self.empresa_repository,
            self.empresa_service,
            audit_service=self.audit_service,
            session_service=self.session_service,
        )

        self.inbox_dir = Path(self.temp_dir.name) / "inbox"
        self.inbox_dir.mkdir()
        self.dest_dir = Path(self.temp_dir.name) / "dest"
        self.dest_dir.mkdir()

        # Isola o log de diagnostico do agente do config real do usuario.
        self.diagnostics_config_dir = Path(self.temp_dir.name) / "config"
        self.diagnostics_patcher = patch.multiple(
            "documentos_empresa_app.utils.document_agent_diagnostics",
            CONFIG_DIR=self.diagnostics_config_dir,
        )
        self.diagnostics_patcher.start()
        document_agent_diagnostics._reset_for_tests()

    def tearDown(self) -> None:
        document_agent_diagnostics._reset_for_tests()
        self.diagnostics_patcher.stop()
        self.temp_dir.cleanup()

    def _create_empresa(self, cnpj: str | None = None, diretorio: str | None = None) -> dict:
        empresa_id = self.empresa_repository.create(1, "Acme Ltda", cnpj=cnpj)
        if diretorio:
            self.empresa_repository.update_directory(empresa_id, diretorio)
        return self.empresa_repository.get_by_id(empresa_id)

    def test_scan_folder_skips_already_pending_files(self) -> None:
        file_path = self.inbox_dir / "boleto.pdf"
        file_path.write_bytes(b"conteudo")

        found = self.agent_service.scan_folder(self.inbox_dir)
        self.assertEqual(found, [file_path])

        self.pendente_repository.create(
            str(file_path), file_path.name, None, None, None, None, None, "nenhuma", "teste"
        )

        found_again = self.agent_service.scan_folder(self.inbox_dir)
        self.assertEqual(found_again, [])

    @unittest.skipIf(Workbook is None, "openpyxl indisponivel neste ambiente")
    def test_classify_file_logs_when_local_layer_finds_no_cnpj(self) -> None:
        file_path = self.inbox_dir / "planilha_sem_cnpj.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Documento sem nenhum CNPJ reconhecivel"])
        workbook.save(file_path)

        cnpj_index = self.agent_service.build_cnpj_index()
        known_names = self.agent_service.build_known_company_names()
        _returned_path, result, extraction_error = self.agent_service.classify_file(
            file_path, cnpj_index, known_names
        )

        self.assertIsNone(extraction_error)
        self.assertEqual(result.origem, "nenhuma")

        log_content = document_agent_diagnostics.get_document_agent_log_path().read_text(encoding="utf-8")
        self.assertIn("CNPJ_NAO_ENCONTRADO", log_content)
        self.assertIn(str(file_path), log_content)

    @unittest.skipIf(not HAS_PYPDF, "pypdf indisponivel neste ambiente")
    def test_classify_file_logs_extraction_failures(self) -> None:
        file_path = self.inbox_dir / "arquivo_corrompido.pdf"
        file_path.write_bytes(b"isto nao e um pdf valido")

        cnpj_index = self.agent_service.build_cnpj_index()
        known_names = self.agent_service.build_known_company_names()
        _returned_path, result, extraction_error = self.agent_service.classify_file(
            file_path, cnpj_index, known_names
        )

        self.assertIsNotNone(extraction_error)
        self.assertIsNone(result)

        log_content = document_agent_diagnostics.get_document_agent_log_path().read_text(encoding="utf-8")
        self.assertIn("EXTRACAO_FALHOU", log_content)

    def test_apply_result_moves_matched_file_with_directory(self) -> None:
        empresa = self._create_empresa(cnpj="12345678000190", diretorio=str(self.dest_dir))
        file_path = self.inbox_dir / "boleto.pdf"
        file_path.write_bytes(b"conteudo")

        result = ClassificationResult(
            matched_empresa=empresa,
            cnpj_extraido="12345678000190",
            origem="regex_cnpj",
            tipo_documento_sugerido=None,
            confianca=1.0,
            empresa_sugerida_nome=empresa["nome_empresa"],
            motivo=None,
        )
        outcome = self.agent_service.apply_result(file_path, result, None)

        self.assertEqual(outcome.outcome, "movido")
        self.assertFalse(file_path.exists())
        self.assertTrue((self.dest_dir / "boleto.pdf").exists())
        self.assertEqual(self.agent_service.list_pendentes(), [])

    def test_apply_result_queues_matched_file_without_directory(self) -> None:
        empresa = self._create_empresa(cnpj="12345678000190")
        file_path = self.inbox_dir / "boleto.pdf"
        file_path.write_bytes(b"conteudo")

        result = ClassificationResult(
            matched_empresa=empresa,
            cnpj_extraido="12345678000190",
            origem="regex_cnpj",
            tipo_documento_sugerido=None,
            confianca=1.0,
            empresa_sugerida_nome=empresa["nome_empresa"],
            motivo=None,
        )
        outcome = self.agent_service.apply_result(file_path, result, None)

        self.assertEqual(outcome.outcome, "pendente_revisao")
        self.assertTrue(file_path.exists())
        pendentes = self.agent_service.list_pendentes()
        self.assertEqual(len(pendentes), 1)
        self.assertEqual(pendentes[0]["empresa_sugerida_id"], empresa["id"])

    def test_apply_result_queues_unmatched_file_without_creating_company(self) -> None:
        file_path = self.inbox_dir / "boleto.pdf"
        file_path.write_bytes(b"conteudo")

        result = ClassificationResult(
            matched_empresa=None,
            cnpj_extraido="99999999000199",
            origem="nenhuma",
            tipo_documento_sugerido=None,
            confianca=None,
            empresa_sugerida_nome=None,
            motivo="Nao encontrado.",
        )
        empresas_before = len(self.empresa_repository.list_all())
        outcome = self.agent_service.apply_result(file_path, result, None)
        empresas_after = len(self.empresa_repository.list_all())

        self.assertEqual(outcome.outcome, "pendente_revisao")
        self.assertEqual(empresas_before, empresas_after)

    def test_resolve_pending_document_reuses_set_empresa_directory(self) -> None:
        empresa = self._create_empresa(cnpj="12345678000190")
        file_path = self.inbox_dir / "boleto.pdf"
        file_path.write_bytes(b"conteudo")

        pendente_id = self.pendente_repository.create(
            str(file_path), file_path.name, "12345678000190", empresa["id"],
            empresa["nome_empresa"], None, 1.0, "regex_cnpj", None,
        )

        self.agent_service.resolve_pending_document(pendente_id, empresa["id"], diretorio_documentos=str(self.dest_dir))

        self.assertFalse(file_path.exists())
        self.assertTrue((self.dest_dir / "boleto.pdf").exists())
        updated_empresa = self.empresa_repository.get_by_id(empresa["id"])
        self.assertEqual(updated_empresa["diretorio_documentos"], str(self.dest_dir))
        self.assertEqual(self.agent_service.list_pendentes(), [])

    def test_resolve_pending_document_without_directory_raises(self) -> None:
        empresa = self._create_empresa(cnpj="12345678000190")
        file_path = self.inbox_dir / "boleto.pdf"
        file_path.write_bytes(b"conteudo")

        pendente_id = self.pendente_repository.create(
            str(file_path), file_path.name, "12345678000190", empresa["id"],
            empresa["nome_empresa"], None, 1.0, "regex_cnpj", None,
        )

        with self.assertRaises(ValidationError):
            self.agent_service.resolve_pending_document(pendente_id, empresa["id"])

    def test_ignore_pending_document(self) -> None:
        file_path = self.inbox_dir / "boleto.pdf"
        file_path.write_bytes(b"conteudo")
        pendente_id = self.pendente_repository.create(
            str(file_path), file_path.name, None, None, None, None, None, "nenhuma", "teste"
        )

        self.agent_service.ignore_pending_document(pendente_id)

        self.assertEqual(self.agent_service.list_pendentes(), [])
        pendente = self.pendente_repository.get_by_id(pendente_id)
        self.assertEqual(pendente["status"], "ignorado")


if __name__ == "__main__":
    unittest.main()
