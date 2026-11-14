import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from psycopg.conninfo import make_conninfo
from PySide6.QtWidgets import QApplication, QMessageBox

from documentos_empresa_app.app_context import build_application_services
from tests.postgres_support import create_test_database_manager, get_test_database_url

CPF_ANA = "529.982.247-25"


class SociosPageTests(unittest.TestCase):
    """Tela Socios (R$ 50 mil): o que o Claude achou nos extratos aparece para conferir e resolver."""

    def setUp(self) -> None:
        self.app = QApplication.instance() or QApplication([])
        db_manager = create_test_database_manager(self)
        conninfo = make_conninfo(get_test_database_url(), options=f"-c search_path={db_manager.schema},public")
        self.services = build_application_services(conninfo)
        self.addCleanup(self.services.database_maintenance_service.db_manager.close)
        self.services.session_service.login(self.services.auth_service.authenticate("admin", "admin"))
        self.services.periodo_service.generate_year(2026)
        self.marco = next(p["id"] for p in self.services.periodo_service.list_periodos() if (p["ano"], p["mes"]) == (2026, 3))
        self.empresa_id = self.services.empresa_service.create_empresa(10, "Clinica Sorriso")
        tipo = self.services.tipo_service.get_or_create_tipo("Extratos CC")["id"]
        self.itau = self.services.documento_service.create_documento(self.empresa_id, tipo, "Itau CC")

        from documentos_empresa_app.qt_ui.pages.socios_page import SociosPage

        self.changed = mock.Mock()
        self.page = SociosPage(self.services, self.changed)
        self.addCleanup(self.page.deleteLater)

    def test_cadastra_socio_pelo_formulario(self) -> None:
        self.page.refresh_data()
        self.page.socio_empresa.setCurrentIndex(self.page.socio_empresa.findData(self.empresa_id))
        self.page.socio_nome.setText("Ana Souza")
        self.page.socio_cpf.setText(CPF_ANA)
        self.page._salvar_socio()
        self.changed.assert_called_once()
        self.page.refresh_data()
        self.assertEqual(self.page.socio_table.rowCount(), 1)

        self.page.socio_busca.setText("529982")
        self.assertEqual(self.page.socio_table.rowCount(), 1)
        self.page.socio_busca.setText("Ninguem")
        self.assertEqual(self.page.socio_table.rowCount(), 0)

    def test_cpf_invalido_avisa_e_nao_grava(self) -> None:
        self.page.refresh_data()
        self.page.socio_empresa.setCurrentIndex(self.page.socio_empresa.findData(self.empresa_id))
        self.page.socio_nome.setText("Ana Souza")
        self.page.socio_cpf.setText("123.456.789-00")
        with mock.patch.object(QMessageBox, "warning") as aviso:
            self.page._salvar_socio()
        aviso.assert_called_once()
        self.assertEqual(self.services.socios_service.listar_socios(), [])

    def test_mostra_o_alerta_e_resolve(self) -> None:
        socios = self.services.socios_service
        socios.cadastrar_socio(self.empresa_id, "Ana Souza", CPF_ANA)
        self.services.status_service.update_status(self.itau, self.marco, "Recebido")
        socios.registrar_revisao(
            self.empresa_id, self.marco,
            [{"cpf": CPF_ANA, "valor": "30.000,00", "data": "10/03/2026", "descricao": "PIX ANA"},
             {"cpf": CPF_ANA, "valor": "25.000,00", "data": "20/03/2026", "descricao": "TED ANA"}],
            documento_id=self.itau,
        )
        self.page.refresh_data()
        self.assertEqual(self.page.alerta_table.rowCount(), 1)
        self.page.alerta_table.selectRow(0)
        self.assertIn("R$ 55.000,00", self.page.alerta_info.text())
        self.assertEqual(self.page.pagamentos_table.rowCount(), 2)
        self.assertTrue(self.page.resolver_button.isEnabled())

        self.page.revisao_periodo.setCurrentIndex(self.page.revisao_periodo.findData(self.marco))
        self.assertEqual(self.page.revisao_table.rowCount(), 1)

        with mock.patch(
            "documentos_empresa_app.qt_ui.pages.socios_page.QInputDialog.getMultiLineText",
            return_value=("IR retido no DARF", True),
        ):
            self.page._resolver("resolvido")
        alerta = socios.listar_alertas()[0]
        self.assertEqual((alerta["status"], alerta["observacao"]), ("resolvido", "IR retido no DARF"))
        self.page.refresh_data()  # filtro padrao e "A resolver": o resolvido sai da lista
        self.assertEqual(self.page.alerta_table.rowCount(), 0)


if __name__ == "__main__":
    unittest.main()
