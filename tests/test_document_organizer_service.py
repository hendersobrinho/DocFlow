from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from documentos_empresa_app.database.connection import DatabaseManager
from documentos_empresa_app.database.repositories import (
    DocumentoPendenteRevisaoRepository,
    EmpresaRepository,
    LogRepository,
)
from documentos_empresa_app.database.schema import initialize_schema
from documentos_empresa_app.services.audit_service import AuditService
from documentos_empresa_app.services.document_organizer_service import (
    DocumentOrganizerService,
    OrganizeNeedsInput,
    OrganizeProposal,
    resolve_organize_target,
)
from documentos_empresa_app.services.session_service import SessionService
from documentos_empresa_app.utils.common import ValidationError


class ResolveOrganizeTargetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.company_dir = Path(self.temp_dir.name) / "1. METODOS"
        self.company_dir.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _touch(self, relative_path: str) -> Path:
        path = self.company_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"conteudo")
        return path

    def test_layout_year_direct(self) -> None:
        self._touch("2026/Sicoob CC 03-2026.pdf")
        result = resolve_organize_target(self.company_dir, 4, 2026, bank_key="sicoob")
        self.assertIsInstance(result, OrganizeProposal)
        self.assertEqual(result.destination_dir, self.company_dir / "2026")
        self.assertEqual(result.new_filename, "Sicoob CC 04-2026.pdf")

    def test_layout_month_folder_inside_year(self) -> None:
        self._touch("2026/03 - Marco/Sicoob CC.pdf")
        result = resolve_organize_target(
            self.company_dir, 4, 2026, bank_key="sicoob", original_filename="extrato.pdf"
        )
        # Sem competencia numerica no nome do irmao ("Sicoob CC.pdf"), a inferencia de nome
        # nao acha padrao dentro da pasta do mes anterior (04 nem existe ainda) - o leaf cai
        # na pasta do ano, que tambem nao tem irmao com padrao numerico. Sem conflito real
        # (nenhum candidato usavel), o nome e sintetizado em vez de perguntar.
        self.assertIsInstance(result, OrganizeProposal)
        self.assertTrue(result.filename_is_synthesized)
        self.assertEqual(result.new_filename, "Sicoob 04-2026.pdf")

    def test_layout_extratos_bancarios_com_subpasta_tipo(self) -> None:
        self._touch("2026/Extratos Bancarios/Conta Corrente/Sicoob CC 03-2026.pdf")
        result = resolve_organize_target(self.company_dir, 4, 2026, bank_key="sicoob", doc_type="cc")
        self.assertIsInstance(result, OrganizeProposal)
        self.assertEqual(
            result.destination_dir, self.company_dir / "2026" / "Extratos Bancarios" / "Conta Corrente"
        )
        self.assertEqual(result.new_filename, "Sicoob CC 04-2026.pdf")

    def test_ano_ausente_propoe_criar_pasta_com_nome_sintetizado(self) -> None:
        result = resolve_organize_target(
            self.company_dir, 4, 2026, bank_key="sicoob", doc_type="cc", original_filename="extrato.pdf"
        )
        self.assertIsInstance(result, OrganizeProposal)
        self.assertEqual(result.destination_dir, self.company_dir / "2026")
        self.assertEqual(result.new_folders, [self.company_dir / "2026"])
        self.assertTrue(result.filename_is_synthesized)
        self.assertEqual(result.new_filename, "Sicoob CC 04-2026.pdf")

    def test_pasta_ano_vazia_propoe_nome_sintetizado(self) -> None:
        (self.company_dir / "2026").mkdir()
        result = resolve_organize_target(self.company_dir, 4, 2026, original_filename="extrato.pdf")
        self.assertIsInstance(result, OrganizeProposal)
        self.assertTrue(result.filename_is_synthesized)
        self.assertEqual(result.new_filename, "Documento 04-2026.pdf")
        self.assertEqual(result.new_folders, [])

    def test_pasta_com_templates_conflitantes_pede_input(self) -> None:
        year_dir = self.company_dir / "2026"
        year_dir.mkdir()
        (year_dir / "Sicoob CC 01-2026.pdf").write_bytes(b"a")
        (year_dir / "Extrato Itau 02-2026.pdf").write_bytes(b"b")

        result = resolve_organize_target(self.company_dir, 4, 2026)
        self.assertIsInstance(result, OrganizeNeedsInput)
        self.assertEqual(result.reason, "pasta_sem_padrao")


class DocumentOrganizerServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "test_organizer.db"
        db_manager = DatabaseManager(db_path)
        initialize_schema(db_manager)

        self.empresa_repository = EmpresaRepository(db_manager)
        self.pendente_repository = DocumentoPendenteRevisaoRepository(db_manager)
        self.log_repository = LogRepository(db_manager)
        self.session_service = SessionService()
        self.audit_service = AuditService(self.log_repository, self.session_service)

        self.organizer_service = DocumentOrganizerService(
            self.empresa_repository,
            self.pendente_repository,
            audit_service=self.audit_service,
            session_service=self.session_service,
        )

        self.company_dir = Path(self.temp_dir.name) / "1. METODOS"
        self.company_dir.mkdir()
        self.inbox_dir = Path(self.temp_dir.name) / "inbox"
        self.inbox_dir.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _create_empresa(self, diretorio: str | None = None) -> dict:
        empresa_id = self.empresa_repository.create(1, "Acme Ltda")
        if diretorio:
            self.empresa_repository.update_directory(empresa_id, diretorio)
        return self.empresa_repository.get_by_id(empresa_id)

    def _create_pendente(self, file_path: Path, empresa: dict | None = None) -> int:
        return self.pendente_repository.create(
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

    def test_propose_needs_input_when_empresa_sem_pasta(self) -> None:
        empresa = self._create_empresa()
        file_path = self.inbox_dir / "extrato.pdf"
        file_path.write_bytes(b"conteudo")
        pendente_id = self._create_pendente(file_path, empresa)

        result = self.organizer_service.propose(pendente_id, empresa["id"], 4, 2026)

        self.assertIsInstance(result, OrganizeNeedsInput)
        self.assertEqual(result.reason, "empresa_sem_pasta")

    def test_propose_resolves_via_empresas_root_dir_when_no_diretorio(self) -> None:
        empresa = self._create_empresa()  # sem diretorio_documentos configurado
        root_dir = Path(self.temp_dir.name) / "raiz_empresas"
        root_dir.mkdir()
        empresa_folder = root_dir / "1. Acme Ltda"
        (empresa_folder / "2026").mkdir(parents=True)
        (empresa_folder / "2026" / "Sicoob CC 03-2026.pdf").write_bytes(b"conteudo")

        file_path = self.inbox_dir / "extrato.pdf"
        file_path.write_bytes(b"conteudo")
        pendente_id = self._create_pendente(file_path, empresa)

        result = self.organizer_service.propose(
            pendente_id, empresa["id"], 4, 2026, banco="Sicoob", empresas_root_dir=str(root_dir)
        )

        self.assertIsInstance(result, OrganizeProposal)
        self.assertEqual(result.new_filename, "Sicoob CC 04-2026.pdf")
        self.assertEqual(result.company_dir, empresa_folder)

    def test_propose_proposes_creating_company_folder_when_root_has_no_match(self) -> None:
        empresa = self._create_empresa()  # sem diretorio_documentos
        root_dir = Path(self.temp_dir.name) / "raiz_vazia"
        root_dir.mkdir()

        file_path = self.inbox_dir / "extrato.pdf"
        file_path.write_bytes(b"conteudo")
        pendente_id = self._create_pendente(file_path, empresa)

        result = self.organizer_service.propose(
            pendente_id, empresa["id"], 4, 2026, empresas_root_dir=str(root_dir)
        )

        self.assertIsInstance(result, OrganizeProposal)
        self.assertEqual(result.company_dir, root_dir / "1. Acme Ltda")
        self.assertIn(root_dir / "1. Acme Ltda", result.new_folders)
        self.assertTrue(result.filename_is_synthesized)

    def test_propose_new_company_folder_matches_sibling_convention(self) -> None:
        empresa = self._create_empresa()  # sem diretorio_documentos
        root_dir = Path(self.temp_dir.name) / "raiz_com_convencao"
        (root_dir / "2 - Beta Ltda").mkdir(parents=True)
        (root_dir / "3 - Gamma Ltda").mkdir(parents=True)

        file_path = self.inbox_dir / "extrato.pdf"
        file_path.write_bytes(b"conteudo")
        pendente_id = self._create_pendente(file_path, empresa)

        result = self.organizer_service.propose(
            pendente_id, empresa["id"], 4, 2026, empresas_root_dir=str(root_dir)
        )

        self.assertIsInstance(result, OrganizeProposal)
        self.assertEqual(result.company_dir, root_dir / "1 - Acme Ltda")

    def test_propose_still_asks_when_diretorio_documentos_configured_but_missing(self) -> None:
        missing_dir = Path(self.temp_dir.name) / "pasta_que_sumiu"
        empresa = self._create_empresa(diretorio=str(missing_dir))

        file_path = self.inbox_dir / "extrato.pdf"
        file_path.write_bytes(b"conteudo")
        pendente_id = self._create_pendente(file_path, empresa)

        result = self.organizer_service.propose(pendente_id, empresa["id"], 4, 2026)

        self.assertIsInstance(result, OrganizeNeedsInput)
        self.assertEqual(result.reason, "empresa_sem_pasta")

    def test_propose_still_asks_when_explicit_override_is_missing(self) -> None:
        empresa = self._create_empresa()
        missing_override = Path(self.temp_dir.name) / "pasta_escolhida_inexistente"

        file_path = self.inbox_dir / "extrato.pdf"
        file_path.write_bytes(b"conteudo")
        pendente_id = self._create_pendente(file_path, empresa)

        result = self.organizer_service.propose(
            pendente_id, empresa["id"], 4, 2026, diretorio_documentos=str(missing_override)
        )

        self.assertIsInstance(result, OrganizeNeedsInput)
        self.assertEqual(result.reason, "empresa_sem_pasta")

    def test_execute_logs_newly_created_folders(self) -> None:
        empresa = self._create_empresa()  # sem diretorio_documentos
        root_dir = Path(self.temp_dir.name) / "raiz_vazia"
        root_dir.mkdir()

        file_path = self.inbox_dir / "extrato.pdf"
        file_path.write_bytes(b"conteudo")
        pendente_id = self._create_pendente(file_path, empresa)

        proposal = self.organizer_service.propose(
            pendente_id, empresa["id"], 4, 2026, empresas_root_dir=str(root_dir)
        )
        self.assertIsInstance(proposal, OrganizeProposal)

        destino = self.organizer_service.execute(pendente_id, empresa["id"], proposal)

        self.assertTrue(destino.exists())
        for folder in proposal.new_folders:
            self.assertTrue(folder.is_dir())

        logs = self.log_repository.list_recent(limit=5)
        self.assertTrue(logs)
        self.assertIn("Foram criadas a(s) pasta(s)", logs[0]["descricao"])

    def test_propose_diretorio_override_takes_priority_over_root(self) -> None:
        empresa = self._create_empresa()
        root_dir = Path(self.temp_dir.name) / "raiz_empresas"
        (root_dir / "1. Acme Ltda" / "2026").mkdir(parents=True)
        (root_dir / "1. Acme Ltda" / "2026" / "Sicoob CC 03-2026.pdf").write_bytes(b"conteudo")

        override_dir = Path(self.temp_dir.name) / "pasta_escolhida_na_tela"
        (override_dir / "2026").mkdir(parents=True)
        (override_dir / "2026" / "Boleto Condominio 03-2026.pdf").write_bytes(b"conteudo")

        file_path = self.inbox_dir / "extrato.pdf"
        file_path.write_bytes(b"conteudo")
        pendente_id = self._create_pendente(file_path, empresa)

        result = self.organizer_service.propose(
            pendente_id,
            empresa["id"],
            4,
            2026,
            diretorio_documentos=str(override_dir),
            empresas_root_dir=str(root_dir),
        )

        self.assertIsInstance(result, OrganizeProposal)
        self.assertEqual(result.new_filename, "Boleto Condominio 04-2026.pdf")
        self.assertEqual(result.company_dir, override_dir)

    def test_propose_does_not_write_to_database(self) -> None:
        empresa = self._create_empresa()
        root_dir = Path(self.temp_dir.name) / "raiz_empresas"
        (root_dir / "1. Acme Ltda" / "2026").mkdir(parents=True)
        (root_dir / "1. Acme Ltda" / "2026" / "Sicoob CC 03-2026.pdf").write_bytes(b"conteudo")

        file_path = self.inbox_dir / "extrato.pdf"
        file_path.write_bytes(b"conteudo")
        pendente_id = self._create_pendente(file_path, empresa)

        result = self.organizer_service.propose(
            pendente_id, empresa["id"], 4, 2026, banco="Sicoob", empresas_root_dir=str(root_dir)
        )
        self.assertIsInstance(result, OrganizeProposal)

        reloaded_empresa = self.empresa_repository.get_by_id(empresa["id"])
        self.assertIsNone(reloaded_empresa.get("diretorio_documentos"))

    def test_propose_raises_for_unknown_pendente(self) -> None:
        empresa = self._create_empresa(diretorio=str(self.company_dir))
        with self.assertRaises(ValidationError):
            self.organizer_service.propose(999999, empresa["id"], 4, 2026)

    def test_propose_raises_for_unknown_empresa(self) -> None:
        file_path = self.inbox_dir / "extrato.pdf"
        file_path.write_bytes(b"conteudo")
        pendente_id = self._create_pendente(file_path)
        with self.assertRaises(ValidationError):
            self.organizer_service.propose(pendente_id, 999999, 4, 2026)

    def test_propose_resolves_target_using_empresa_directory(self) -> None:
        empresa = self._create_empresa(diretorio=str(self.company_dir))
        (self.company_dir / "2026").mkdir()
        (self.company_dir / "2026" / "Sicoob CC 03-2026.pdf").write_bytes(b"conteudo")

        file_path = self.inbox_dir / "extrato.pdf"
        file_path.write_bytes(b"conteudo")
        pendente_id = self._create_pendente(file_path, empresa)

        result = self.organizer_service.propose(pendente_id, empresa["id"], 4, 2026, banco="Sicoob")

        self.assertIsInstance(result, OrganizeProposal)
        self.assertEqual(result.new_filename, "Sicoob CC 04-2026.pdf")
        self.assertEqual(result.destination_dir, self.company_dir / "2026")

    def test_execute_moves_file_creates_folder_and_marks_resolved(self) -> None:
        empresa = self._create_empresa(diretorio=str(self.company_dir))
        (self.company_dir / "2026").mkdir()
        (self.company_dir / "2026" / "Sicoob CC 03-2026.pdf").write_bytes(b"conteudo")

        file_path = self.inbox_dir / "extrato.pdf"
        file_path.write_bytes(b"conteudo")
        pendente_id = self._create_pendente(file_path, empresa)

        proposal = self.organizer_service.propose(pendente_id, empresa["id"], 4, 2026, banco="Sicoob")
        self.assertIsInstance(proposal, OrganizeProposal)

        destino = self.organizer_service.execute(pendente_id, empresa["id"], proposal)

        self.assertEqual(destino, self.company_dir / "2026" / "Sicoob CC 04-2026.pdf")
        self.assertTrue(destino.exists())
        self.assertFalse(file_path.exists())

        pendente = self.pendente_repository.get_by_id(pendente_id)
        self.assertEqual(pendente["status"], "resolvido")

    def test_execute_caches_directory_when_resolved_via_root(self) -> None:
        empresa = self._create_empresa()  # sem diretorio_documentos
        root_dir = Path(self.temp_dir.name) / "raiz_empresas"
        empresa_folder = root_dir / "1. Acme Ltda"
        (empresa_folder / "2026").mkdir(parents=True)
        (empresa_folder / "2026" / "Sicoob CC 03-2026.pdf").write_bytes(b"conteudo")

        file_path = self.inbox_dir / "extrato.pdf"
        file_path.write_bytes(b"conteudo")
        pendente_id = self._create_pendente(file_path, empresa)

        proposal = self.organizer_service.propose(
            pendente_id, empresa["id"], 4, 2026, banco="Sicoob", empresas_root_dir=str(root_dir)
        )
        self.assertIsInstance(proposal, OrganizeProposal)

        self.organizer_service.execute(pendente_id, empresa["id"], proposal)

        reloaded_empresa = self.empresa_repository.get_by_id(empresa["id"])
        self.assertEqual(reloaded_empresa["diretorio_documentos"], str(empresa_folder))

    def test_execute_does_not_overwrite_existing_diretorio_documentos(self) -> None:
        empresa = self._create_empresa(diretorio=str(self.company_dir))
        (self.company_dir / "2026").mkdir()
        (self.company_dir / "2026" / "Sicoob CC 03-2026.pdf").write_bytes(b"conteudo")

        file_path = self.inbox_dir / "extrato.pdf"
        file_path.write_bytes(b"conteudo")
        pendente_id = self._create_pendente(file_path, empresa)

        proposal = self.organizer_service.propose(pendente_id, empresa["id"], 4, 2026, banco="Sicoob")
        self.organizer_service.execute(pendente_id, empresa["id"], proposal)

        reloaded_empresa = self.empresa_repository.get_by_id(empresa["id"])
        self.assertEqual(reloaded_empresa["diretorio_documentos"], str(self.company_dir))

    def test_execute_resolves_name_collision(self) -> None:
        empresa = self._create_empresa(diretorio=str(self.company_dir))
        year_dir = self.company_dir / "2026"
        year_dir.mkdir()
        (year_dir / "Sicoob CC 03-2026.pdf").write_bytes(b"conteudo")
        (year_dir / "Sicoob CC 04-2026.pdf").write_bytes(b"arquivo ja existente")

        file_path = self.inbox_dir / "extrato.pdf"
        file_path.write_bytes(b"conteudo novo")
        pendente_id = self._create_pendente(file_path, empresa)

        proposal = self.organizer_service.propose(pendente_id, empresa["id"], 4, 2026, banco="Sicoob")
        destino = self.organizer_service.execute(pendente_id, empresa["id"], proposal)

        self.assertEqual(destino.name, "Sicoob CC 04-2026 (1).pdf")
        self.assertTrue(destino.exists())

    def test_execute_creates_missing_year_folder(self) -> None:
        empresa = self._create_empresa(diretorio=str(self.company_dir))
        file_path = self.inbox_dir / "extrato.pdf"
        file_path.write_bytes(b"conteudo")
        pendente_id = self._create_pendente(file_path, empresa)

        # Monta manualmente a proposta - testa execute() isoladamente, sem depender
        # de propose()/resolve_organize_target (que hoje tambem chegaria numa proposta
        # assim para esse caso, ver ResolveOrganizeTargetTests acima).
        proposal = OrganizeProposal(
            destination_dir=self.company_dir / "2026",
            new_filename="Sicoob CC 04-2026.pdf",
            based_on_sibling=None,
            company_dir=self.company_dir,
        )
        destino = self.organizer_service.execute(pendente_id, empresa["id"], proposal)

        self.assertTrue(destino.exists())
        self.assertTrue((self.company_dir / "2026").is_dir())

    def test_execute_raises_when_source_file_missing(self) -> None:
        empresa = self._create_empresa(diretorio=str(self.company_dir))
        file_path = self.inbox_dir / "extrato.pdf"
        file_path.write_bytes(b"conteudo")
        pendente_id = self._create_pendente(file_path, empresa)
        file_path.unlink()

        proposal = OrganizeProposal(
            destination_dir=self.company_dir / "2026",
            new_filename="Sicoob CC 04-2026.pdf",
            based_on_sibling=None,
            company_dir=self.company_dir,
        )
        with self.assertRaises(ValidationError):
            self.organizer_service.execute(pendente_id, empresa["id"], proposal)


if __name__ == "__main__":
    unittest.main()
