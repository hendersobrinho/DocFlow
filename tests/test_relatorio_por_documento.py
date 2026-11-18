import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from psycopg.conninfo import make_conninfo
from PySide6.QtWidgets import QApplication

from documentos_empresa_app.app_context import build_application_services
from tests.postgres_support import create_test_database_manager, get_test_database_url


class RelatorioPorDocumentoTests(unittest.TestCase):
    """Modelo alternativo do relatorio: cada documento uma vez, com os meses que faltam na frente."""

    def setUp(self) -> None:
        self.app = QApplication.instance() or QApplication([])
        db = create_test_database_manager(self)
        conninfo = make_conninfo(get_test_database_url(), options=f"-c search_path={db.schema},public")
        self.services = build_application_services(conninfo)
        self.addCleanup(self.services.database_maintenance_service.db_manager.close)
        self.services.session_service.login(self.services.auth_service.authenticate("admin", "admin"))
        self.services.periodo_service.generate_year(2026)
        self.periodos = {
            p["mes"]: p["id"] for p in self.services.periodo_service.list_periodos() if p["ano"] == 2026
        }
        empresa = self.services.empresa_service.create_empresa(10, "Clinica Sorriso")
        tipo = self.services.tipo_service.get_or_create_tipo("Contabil")["id"]
        balancete = self.services.documento_service.create_documento(empresa, tipo, "Balancete")
        caixa = self.services.documento_service.create_documento(empresa, tipo, "Caixa")
        for mes in range(1, 9):
            self.services.status_service.update_status(balancete, self.periodos[mes], "Pendente")
            self.services.status_service.update_status(caixa, self.periodos[mes], "Recebido")

    def test_dialogo_gera_por_documento_e_lembra_a_escolha(self) -> None:
        from documentos_empresa_app.qt_ui.pages import panorama_page

        salvos = {}
        with mock.patch.object(panorama_page, "load_ui_state", side_effect=lambda k, d=None: salvos.get(k, d)), \
                mock.patch.object(panorama_page, "save_ui_state", side_effect=salvos.__setitem__):
            dialogo = panorama_page.ExportReportDialog(self.services, self.periodos[8], [])
            self.addCleanup(dialogo.deleteLater)
            self.assertTrue(dialogo.agrupar_competencia.isChecked())  # padrao: o modelo de sempre
            dialogo.start_combo.setCurrentIndex(dialogo.start_combo.findData(self.periodos[1]))
            dialogo.agrupar_documento.setChecked(True)
            # As outras opcoes da janela nao mudam quando escolhe o modelo.
            self.assertTrue(dialogo.kind_situacao.isChecked())
            self.assertTrue(dialogo.scope_all.isChecked())
            html = dialogo._printable()["html"]
            self.assertEqual(salvos["relatorio:agrupar"], "documento")
            de_novo = panorama_page.ExportReportDialog(self.services, self.periodos[8], [])
            self.addCleanup(de_novo.deleteLater)
            self.assertTrue(de_novo.agrupar_documento.isChecked())
        self.assertIn("Balancete", html)
        self.assertIn("01/2026 a 08/2026", html)
        self.assertEqual(html.count("Balancete"), 1)


if __name__ == "__main__":
    unittest.main()
