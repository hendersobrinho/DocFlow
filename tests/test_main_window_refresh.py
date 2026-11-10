import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from psycopg.conninfo import make_conninfo
from PySide6.QtWidgets import QApplication

from documentos_empresa_app.app_context import build_application_services
from tests.postgres_support import create_test_database_manager, get_test_database_url


class MainWindowRefreshTests(unittest.TestCase):
    """Botao Atualizar (F5): mostra o que o Claude gravou sem fechar o DocFlow."""

    def setUp(self) -> None:
        self.app = QApplication.instance() or QApplication([])
        db_manager = create_test_database_manager(self)
        conninfo = make_conninfo(get_test_database_url(), options=f"-c search_path={db_manager.schema},public")
        self.services = build_application_services(conninfo)
        self.claude = build_application_services(conninfo)
        for services in (self.services, self.claude):
            self.addCleanup(services.database_maintenance_service.db_manager.close)
        self.services.session_service.login(self.services.auth_service.authenticate("admin", "admin"))

    def test_refresh_button_flags_external_changes_and_clears_after_refresh(self) -> None:
        from documentos_empresa_app.qt_ui import main_window

        with mock.patch.object(main_window, "can_self_update", return_value=False):
            janela = main_window.MainWindow(self.services)
        self.addCleanup(janela.deleteLater)
        janela.novidades_timer.stop()
        janela.show()
        self.app.processEvents()

        janela.atualizar_tudo()
        self.assertEqual(janela.refresh_button.text(), "Atualizar (F5)")

        self.claude.empresa_service.create_empresa(777, "Cadastrada Pelo Claude")
        janela._verificar_novidades()
        self.assertIn("há novidades", janela.refresh_button.text())

        with mock.patch.object(janela, "refresh_all_tabs") as recarregar:
            janela.atualizar_tudo()
        recarregar.assert_called_once()
        self.assertEqual(janela.refresh_button.text(), "Atualizar (F5)")
        janela.close()


if __name__ == "__main__":
    unittest.main()
