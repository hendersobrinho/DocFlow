from __future__ import annotations

from datetime import date
import unittest

from psycopg.conninfo import make_conninfo

from documentos_empresa_app.app_context import build_application_services

from tests.postgres_support import create_test_database_manager, get_test_database_url


class ViradaDeAnoTests(unittest.TestCase):
    """Os meses do ano atual existem sempre; de novembro em diante, os do ano seguinte tambem."""

    def setUp(self) -> None:
        db_manager = create_test_database_manager(self)
        conninfo = make_conninfo(get_test_database_url(), options=f"-c search_path={db_manager.schema},public")
        self.services = build_application_services(conninfo)
        self.addCleanup(self.services.database_maintenance_service.db_manager.close)

    def _anos(self) -> list[int]:
        return self.services.periodo_service.list_available_years()

    def test_october_creates_only_the_current_year(self) -> None:
        criados = self.services.periodo_service.ensure_operational_years(date(2026, 10, 22))
        self.assertEqual(criados, [2026])
        self.assertEqual(self._anos(), [2026])

    def test_november_also_creates_next_year_once(self) -> None:
        periodo = self.services.periodo_service
        self.assertEqual(periodo.ensure_operational_years(date(2026, 11, 3)), [2026, 2027])
        self.assertEqual(periodo.ensure_operational_years(date(2026, 11, 4)), [])  # ja existe: nada
        self.assertEqual(sorted(self._anos()), [2026, 2027])
        self.assertEqual(len([p for p in periodo.list_periodos() if p["ano"] == 2027]), 12)


class CacheDeLeituraTests(unittest.TestCase):
    """O cache da fila/plano nunca devolve dado velho depois de uma gravacao."""

    def setUp(self) -> None:
        db_manager = create_test_database_manager(self)
        conninfo = make_conninfo(get_test_database_url(), options=f"-c search_path={db_manager.schema},public")
        self.services = build_application_services(conninfo)
        self.addCleanup(self.services.database_maintenance_service.db_manager.close)
        self.services.session_service.login(self.services.auth_service.authenticate("admin", "admin"))
        self.services.periodo_service.generate_year(date.today().year - 1)

    def test_plan_reflects_a_new_document_right_away(self) -> None:
        cobranca = self.services.cobranca_service
        antes = sum(cobranca.proximas_acoes(somente_ativas=False)["resumo"].values())
        empresa_id = self.services.empresa_service.create_empresa(1, "Padaria")
        tipo_id = self.services.tipo_service.get_or_create_tipo("Extratos CC")["id"]
        self.services.documento_service.create_documento(empresa_id, tipo_id, "Itau CC", ["Email"])

        depois = sum(cobranca.proximas_acoes(somente_ativas=False)["resumo"].values())
        self.assertGreater(depois, antes)

    def test_changing_the_returned_plan_does_not_change_the_cache(self) -> None:
        empresa_id = self.services.empresa_service.create_empresa(1, "Padaria")
        tipo_id = self.services.tipo_service.get_or_create_tipo("Extratos CC")["id"]
        self.services.documento_service.create_documento(empresa_id, tipo_id, "Itau CC", ["Email"])
        cobranca = self.services.cobranca_service

        plano = cobranca.proximas_acoes()
        plano["empresas"][0].pop("empresa_id")  # o MCP faz isso antes de responder
        self.assertIn("empresa_id", cobranca.proximas_acoes()["empresas"][0])


if __name__ == "__main__":
    unittest.main()
