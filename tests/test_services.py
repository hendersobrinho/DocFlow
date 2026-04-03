from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from documentos_empresa_app.database.connection import DatabaseManager
from documentos_empresa_app.database.repositories import (
    DocumentoRepository,
    EmpresaRepository,
    LogRepository,
    PeriodoRepository,
    StatusRepository,
    TipoRepository,
    UsuarioRepository,
)
from documentos_empresa_app.database.schema import initialize_schema
from documentos_empresa_app.services.audit_service import AuditService
from documentos_empresa_app.services.auth_service import AuthService
from documentos_empresa_app.services.documento_service import DocumentoService
from documentos_empresa_app.services.empresa_service import EmpresaService
from documentos_empresa_app.services.import_service import ImportService
from documentos_empresa_app.services.log_service import LogService
from documentos_empresa_app.services.periodo_service import PeriodoService
from documentos_empresa_app.services.session_service import SessionService
from documentos_empresa_app.services.status_service import StatusService
from documentos_empresa_app.services.tipo_service import TipoService
from documentos_empresa_app.services.user_service import UserService
from documentos_empresa_app.utils.common import ValidationError


class ApplicationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "test_app.db"

        db_manager = DatabaseManager(db_path)
        initialize_schema(db_manager)

        self.empresa_repository = EmpresaRepository(db_manager)
        self.tipo_repository = TipoRepository(db_manager)
        self.documento_repository = DocumentoRepository(db_manager)
        self.periodo_repository = PeriodoRepository(db_manager)
        self.status_repository = StatusRepository(db_manager)
        self.usuario_repository = UsuarioRepository(db_manager)
        self.log_repository = LogRepository(db_manager)

        self.session_service = SessionService()
        self.audit_service = AuditService(self.log_repository, self.session_service)

        self.empresa_service = EmpresaService(
            self.empresa_repository,
            audit_service=self.audit_service,
            session_service=self.session_service,
        )
        self.tipo_service = TipoService(self.tipo_repository)
        self.documento_service = DocumentoService(
            self.documento_repository,
            self.empresa_repository,
            self.tipo_repository,
            audit_service=self.audit_service,
            session_service=self.session_service,
        )
        self.periodo_service = PeriodoService(self.periodo_repository)
        self.status_service = StatusService(
            self.empresa_repository,
            self.documento_repository,
            self.periodo_repository,
            self.status_repository,
            audit_service=self.audit_service,
            session_service=self.session_service,
        )
        self.import_service = ImportService(
            self.empresa_service,
            self.tipo_service,
            self.documento_service,
        )
        self.auth_service = AuthService(self.usuario_repository)
        self.user_service = UserService(
            self.usuario_repository,
            self.session_service,
            audit_service=self.audit_service,
        )
        self.log_service = LogService(self.log_repository, self.session_service)

        admin_user = self.auth_service.authenticate("admin", "admin")
        self.session_service.login(admin_user)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_initial_types_are_seeded(self) -> None:
        tipos = [item["nome_tipo"] for item in self.tipo_service.list_tipos()]
        self.assertIn("Extratos CC", tipos)
        self.assertIn("Contratos", tipos)

    def test_generate_year_does_not_duplicate_months(self) -> None:
        first_run = self.periodo_service.generate_year(2026)
        second_run = self.periodo_service.generate_year(2026)

        self.assertEqual(first_run["created"], 12)
        self.assertEqual(second_run["created"], 0)
        self.assertEqual(second_run["existing"], 12)

    def test_closure_hides_future_periods(self) -> None:
        empresa_id = self.empresa_service.create_empresa(101, "Empresa Teste")
        tipo_id = self.tipo_service.get_or_create_tipo("Documentos Financeiros")["id"]
        documento_id = self.documento_service.create_documento(empresa_id, tipo_id, "Banco X")
        self.periodo_service.generate_year(2026)

        periodos = self.periodo_service.list_periodos()
        jan = next(item for item in periodos if item["ano"] == 2026 and item["mes"] == 1)
        apr = next(item for item in periodos if item["ano"] == 2026 and item["mes"] == 4)
        jun = next(item for item in periodos if item["ano"] == 2026 and item["mes"] == 6)

        self.status_service.update_status(documento_id, jun["id"], "Recebido")
        self.status_service.update_status(documento_id, apr["id"], "Encerrado")

        view = self.status_service.build_control_view(empresa_id, jan["id"], jun["id"])
        documentos = view["groups"][0]["documentos"]
        availability = [cell["available"] for cell in documentos[0]["cells"]]

        self.assertEqual(availability, [True, True, True, True, False, False])
        self.assertEqual(documentos[0]["cells"][3]["status"], "Encerrado")
        self.assertEqual(documentos[0]["cells"][5]["status"], "")

        may = next(item for item in periodos if item["ano"] == 2026 and item["mes"] == 5)
        later_view = self.status_service.build_control_view(empresa_id, may["id"], jun["id"])
        self.assertEqual(later_view["groups"], [])

    def test_empresa_service_accepts_integer_like_numeric_codes(self) -> None:
        empresa_id = self.empresa_service.create_empresa("101.0", "Empresa Decimal")
        empresa = self.empresa_service.get_empresa(empresa_id)

        self.assertEqual(empresa["codigo_empresa"], 101)

    def test_empresa_service_saves_delivery_contact_fields(self) -> None:
        empresa_id = self.empresa_service.create_empresa(
            102,
            "Empresa Campos",
            meios_recebimento=["Email", "Onvio"],
            email_contato="contato@empresa.com",
            nome_contato="Maria Silva",
        )

        empresa = self.empresa_service.get_empresa(empresa_id)

        self.assertEqual(empresa["meios_recebimento"], "Email, Onvio")
        self.assertEqual(empresa["email_contato"], "contato@empresa.com")
        self.assertEqual(empresa["nome_contato"], "Maria Silva")

    def test_empresa_service_preserves_legacy_delivery_methods(self) -> None:
        empresa_id = self.empresa_service.create_empresa(
            104,
            "Empresa Meio Legado",
            meios_recebimento=["Portal", "email", "portal"],
        )

        empresa = self.empresa_service.get_empresa(empresa_id)

        self.assertEqual(empresa["meios_recebimento"], "Portal, Email")

    def test_empresa_service_rejects_invalid_optional_email(self) -> None:
        with self.assertRaises(ValidationError):
            self.empresa_service.create_empresa(
                103,
                "Empresa Email Invalido",
                meios_recebimento=["Email"],
                email_contato="email_invalido",
            )

    def test_sparse_period_range_still_blocks_more_than_twelve_months(self) -> None:
        start_id = self.periodo_repository.create(2026, 1)
        end_id = self.periodo_repository.create(2027, 12)

        with self.assertRaises(ValidationError):
            self.periodo_service.get_periods_between(start_id, end_id)

    def test_import_service_wraps_excel_open_errors(self) -> None:
        with patch("documentos_empresa_app.services.import_service.load_workbook", side_effect=OSError("boom")):
            with self.assertRaises(ValidationError):
                self.import_service.import_empresas("arquivo_invalido.xlsx")

    def test_alias_type_name_is_normalized_to_existing_canonical_type(self) -> None:
        tipo = self.tipo_service.get_or_create_tipo("Extrato CC")

        self.assertEqual(tipo["nome_tipo"], "Extratos CC")

    def test_duplicate_type_aliases_are_merged_without_losing_status(self) -> None:
        empresa_id = self.empresa_service.create_empresa(501, "Empresa Alias")
        canonical_type_id = self.tipo_service.get_or_create_tipo("Extratos CC")["id"]
        alias_type_id = self.tipo_repository.create("Extrato CC")

        canonical_document_id = self.documento_repository.create(empresa_id, canonical_type_id, "Banco XP")
        alias_document_id = self.documento_repository.create(empresa_id, alias_type_id, "Banco XP")

        self.periodo_service.generate_year(2026)
        periodos = self.periodo_service.list_periodos()
        jan = next(item for item in periodos if item["ano"] == 2026 and item["mes"] == 1)
        feb = next(item for item in periodos if item["ano"] == 2026 and item["mes"] == 2)

        self.status_service.update_status(canonical_document_id, jan["id"], "Recebido")
        self.status_service.update_status(alias_document_id, feb["id"], "Pendente")

        initialize_schema(self.empresa_repository.db_manager)

        tipos = self.tipo_service.list_tipos()
        nomes = [tipo["nome_tipo"] for tipo in tipos]
        self.assertEqual(nomes.count("Extratos CC"), 1)
        self.assertNotIn("Extrato CC", nomes)

        documentos = self.documento_service.list_documentos_empresa(empresa_id)
        self.assertEqual(len([doc for doc in documentos if doc["nome_documento"] == "Banco XP"]), 1)

        view = self.status_service.build_control_view(empresa_id, jan["id"], feb["id"])
        self.assertEqual(len(view["groups"]), 1)
        self.assertEqual(view["groups"][0]["tipo_nome"], "Extratos CC")
        self.assertEqual(view["groups"][0]["documentos"][0]["cells"][0]["status"], "Recebido")
        self.assertEqual(view["groups"][0]["documentos"][0]["cells"][1]["status"], "Pendente")

    def test_default_admin_user_can_authenticate(self) -> None:
        user = self.auth_service.authenticate("admin", "admin")

        self.assertEqual(user["username"], "admin")
        self.assertEqual(user["tipo_usuario"], "admin")
        self.assertEqual(user["ativa"], 1)

    def test_inactive_user_cannot_login(self) -> None:
        user_id = self.user_service.create_user("maria", "123456", "comum", ativo=True)
        self.user_service.update_user(user_id, "maria", "comum", False)

        with self.assertRaises(ValidationError):
            self.auth_service.authenticate("maria", "123456")

    def test_logs_are_created_for_empresa_documento_e_status(self) -> None:
        empresa_id = self.empresa_service.create_empresa(777, "HND TEC")
        tipo_id = self.tipo_service.get_or_create_tipo("Extratos CC")["id"]
        documento_id = self.documento_service.create_documento(empresa_id, tipo_id, "Banco do Brasil")
        self.periodo_service.generate_year(2026)
        periodo = next(
            item for item in self.periodo_service.list_periodos() if item["ano"] == 2026 and item["mes"] == 3
        )

        self.status_service.update_status(documento_id, periodo["id"], "Recebido")

        logs = self.log_service.list_logs(limit=20)
        actions = [log["acao"] for log in logs]
        descriptions = [log["descricao"] for log in logs]

        self.assertIn("CADASTRO_EMPRESA", actions)
        self.assertIn("CADASTRO_DOCUMENTO", actions)
        self.assertIn("ALTERACAO_STATUS", actions)
        self.assertTrue(any("Banco do Brasil" in description for description in descriptions))
        self.assertTrue(any("HND TEC" in description for description in descriptions))

    def test_status_closure_logs_removed_future_statuses(self) -> None:
        empresa_id = self.empresa_service.create_empresa(778, "Empresa Encerramento")
        tipo_id = self.tipo_service.get_or_create_tipo("Extratos CC")["id"]
        documento_id = self.documento_service.create_documento(empresa_id, tipo_id, "Banco Futuro")
        self.periodo_service.generate_year(2026)
        periodos = self.periodo_service.list_periodos()
        abril = next(item for item in periodos if item["ano"] == 2026 and item["mes"] == 4)
        junho = next(item for item in periodos if item["ano"] == 2026 and item["mes"] == 6)

        self.status_service.update_status(documento_id, junho["id"], "Recebido")
        self.status_service.update_status(documento_id, abril["id"], "Encerrado")

        logs = self.log_service.list_logs(limit=20, empresa_id=empresa_id)
        future_logs = [log for log in logs if log["periodo_ano"] == 2026 and log["periodo_mes"] == 6]

        self.assertTrue(future_logs)
        self.assertTrue(any('de "Recebido" para "vazio"' in log["descricao"] for log in future_logs))

    def test_company_creation_rolls_back_if_audit_log_fails(self) -> None:
        with patch.object(self.audit_service, "log", side_effect=RuntimeError("falha no log")):
            with self.assertRaises(RuntimeError):
                self.empresa_service.create_empresa(779, "Empresa Sem Log")

        self.assertIsNone(self.empresa_service.get_empresa_by_code(779))

    def test_log_filters_by_empresa_e_periodo(self) -> None:
        empresa_a_id = self.empresa_service.create_empresa(801, "Empresa A")
        empresa_b_id = self.empresa_service.create_empresa(802, "Empresa B")
        tipo_id = self.tipo_service.get_or_create_tipo("Extratos CC")["id"]
        documento_a_id = self.documento_service.create_documento(empresa_a_id, tipo_id, "Doc A")
        documento_b_id = self.documento_service.create_documento(empresa_b_id, tipo_id, "Doc B")

        self.periodo_service.generate_year(2026)
        periodos = self.periodo_service.list_periodos()
        jan = next(item for item in periodos if item["ano"] == 2026 and item["mes"] == 1)
        feb = next(item for item in periodos if item["ano"] == 2026 and item["mes"] == 2)

        self.status_service.update_status(documento_a_id, jan["id"], "Recebido")
        self.status_service.update_status(documento_b_id, feb["id"], "Pendente")

        company_logs = self.log_service.list_logs(limit=50, empresa_id=empresa_a_id)
        self.assertTrue(company_logs)
        self.assertTrue(all(log["empresa_id"] == empresa_a_id for log in company_logs))

        period_logs = self.log_service.list_logs(limit=50, periodo_ano=2026, periodo_mes=2)
        self.assertTrue(period_logs)
        self.assertTrue(all(log["periodo_ano"] == 2026 and log["periodo_mes"] == 2 for log in period_logs))
        self.assertTrue(any("Empresa B" in log["descricao"] for log in period_logs))


if __name__ == "__main__":
    unittest.main()
