import unittest

from documentos_empresa_app.app_context import build_application_services
from documentos_empresa_app.services.mudancas_service import MudancasService
from psycopg.conninfo import make_conninfo
from tests.postgres_support import create_test_database_manager, get_test_database_url


class MudancasServiceTests(unittest.TestCase):
    """O botao Atualizar avisa quando outro programa (o Claude pelo MCP) gravou no banco."""

    def setUp(self) -> None:
        db_manager = create_test_database_manager(self)
        conninfo = make_conninfo(get_test_database_url(), options=f"-c search_path={db_manager.schema},public")
        # Duas "instalacoes" no mesmo banco: a tela do DocFlow e o MCP do Claude.
        self.tela = build_application_services(conninfo)
        self.claude = build_application_services(conninfo)
        for services in (self.tela, self.claude):
            self.addCleanup(services.database_maintenance_service.db_manager.close)
        self.mudancas = MudancasService(self.tela.database_maintenance_service.db_manager)

    def test_external_write_is_noticed_and_own_write_is_not(self) -> None:
        self.assertIsNotNone(self.mudancas.assinatura())
        self.mudancas.marcar_visto()
        self.assertFalse(self.mudancas.ha_novidades())

        # A propria tela grava: ela ja se atualiza sozinha, entao nao ha "novidade".
        self.tela.empresa_service.create_empresa(501, "Gravada Pela Tela")
        self.assertFalse(self.mudancas.ha_novidades())
        self.assertFalse(self.mudancas.ha_novidades())

        # O Claude grava pelo outro programa: a tela precisa avisar.
        self.claude.empresa_service.create_empresa(502, "Gravada Pelo Claude")
        self.assertTrue(self.mudancas.ha_novidades())

        # Depois de atualizar, o aviso some.
        self.mudancas.invalidar_caches()
        self.mudancas.marcar_visto()
        self.assertFalse(self.mudancas.ha_novidades())

    def test_refresh_invalidates_read_caches(self) -> None:
        db_manager = self.tela.database_maintenance_service.db_manager
        antes = db_manager.write_generation
        self.mudancas.invalidar_caches()
        self.assertGreater(db_manager.write_generation, antes)


if __name__ == "__main__":
    unittest.main()
