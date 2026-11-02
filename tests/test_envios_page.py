from __future__ import annotations

import os
import unittest
from datetime import date
from unittest import mock

from psycopg.conninfo import make_conninfo

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from documentos_empresa_app.app_context import build_application_services  # noqa: E402
from documentos_empresa_app.qt_ui.pages import envios_page  # noqa: E402
from documentos_empresa_app.qt_ui.pages.envios_page import PUBLICO_ESCOLHIDAS, EnvioDialog, EnviosPage  # noqa: E402
from documentos_empresa_app.qt_ui.widgets import envios as envios_widgets  # noqa: E402
from documentos_empresa_app.qt_ui.widgets.envios import WhatsAppSequenceDialog  # noqa: E402

from tests.postgres_support import create_test_database_manager, get_test_database_url  # noqa: E402

APP = QApplication.instance() or QApplication([])
SIM = QMessageBox.StandardButton.Yes


def _url(chamada) -> str:
    return chamada[0][0].toString(QUrl.ComponentFormattingOption.FullyEncoded)


class EnviosPageTests(unittest.TestCase):
    def setUp(self) -> None:
        db_manager = create_test_database_manager(self)
        conninfo = make_conninfo(get_test_database_url(), options=f"-c search_path={db_manager.schema},public")
        self.services = build_application_services(conninfo)
        self.addCleanup(self.services.database_maintenance_service.db_manager.close)
        self.services.session_service.login(self.services.auth_service.authenticate("admin", "admin"))
        self.empresa_id = self.services.empresa_service.create_empresa(1, "Padaria")
        self.services.empresa_service.set_whatsapp(self.empresa_id, "27 98888-7777")
        self.services.empresa_service.set_whatsapp_envios(self.empresa_id, True)

    def _aviso(self) -> dict:
        return self.services.envio_programado_service.criar(
            {"nome": "Aviso", "meses": [date.today().month], "enviar_em": "mesmo_mes", "dia_envio": 1,
             "assunto": "A", "corpo": "Oi {empresa}", "corpo_whatsapp": "Oi"}
        )

    def test_dialog_builds_a_mailing_for_chosen_companies(self) -> None:
        dialog = EnvioDialog(None, self.services.tipo_service.list_tipos(), self.services.empresa_service.list_empresas())
        dialog.nome_edit.setText("Aviso")
        dialog.publico_combo.setCurrentIndex(dialog.publico_combo.findData(PUBLICO_ESCOLHIDAS))
        dialog.empresa_ids = [self.empresa_id]
        dialog.assunto_edit.setText("Aviso")
        dialog.corpo_edit.setPlainText("Oi {empresa}")
        dialog.whatsapp_edit.setPlainText("Oi pelo zap")
        valores = dialog.values()
        self.assertEqual((valores["tipo_documento_id"], valores["empresa_ids"], valores["enviar_em"]), (None, [self.empresa_id], "mes_seguinte"))
        self.assertIn("é cobrada a partir de", dialog.exemplo_label.text())
        envio = self.services.envio_programado_service.criar(valores)
        self.assertEqual((envio["empresa_ids_lista"], envio["corpo_whatsapp"]), ([self.empresa_id], "Oi pelo zap"))

    def test_list_shows_pending_and_whatsapp_tab_opens_the_conversation(self) -> None:
        self._aviso()
        page = EnviosPage(self.services, lambda: None)
        self.assertEqual(page.pendentes, {page.envios[0]["id"]: 1})
        painel = page.quem_recebe
        self.assertEqual((painel.kpi_email.value_label.text(), painel.kpi_whatsapp.value_label.text()), ("0", "1"))
        self.assertEqual(painel.tabs.tabText(1), "WhatsApp (1)")
        painel.whatsapp.table.selectRow(0)
        self.assertIn("Oi", painel.whatsapp.preview.toPlainText())
        with mock.patch.object(envios_widgets.QDesktopServices, "openUrl") as abrir, \
                mock.patch.object(QMessageBox, "question", return_value=SIM):
            painel.open_whatsapp()
        self.assertEqual(_url(abrir.call_args), "https://wa.me/5527988887777?text=Oi")
        self.assertEqual(page.pendentes, {})
        self.assertEqual(self.services.envio_programado_service.historico()[0]["canal"], "whatsapp")

    def test_whatsapp_sequence_handles_groups(self) -> None:
        outra = self.services.empresa_service.create_empresa(2, "Oficina")
        self.services.empresa_service.set_whatsapp_envios(outra, True, "https://chat.whatsapp.com/AbCdEfGhIjKlMnOp")
        self._aviso()
        page = EnviosPage(self.services, lambda: None)
        painel = page.quem_recebe
        self.assertIn("(2)", painel.sequencia_button.text())

        itens = painel._pendentes_whatsapp()
        dialog = WhatsAppSequenceDialog(page, self.services, itens)
        with mock.patch.object(envios_widgets.QDesktopServices, "openUrl") as abrir:
            dialog.open_current()
            dialog.mark_sent()  # registra e ja abre a proxima (o grupo)
            self.assertIn("copiada", dialog.grupo_label.text())
            self.assertEqual(QGuiApplication.clipboard().text(), "Oi")
            dialog.skip()
        self.assertEqual(_url(abrir.call_args_list[1]), "https://chat.whatsapp.com/AbCdEfGhIjKlMnOp")
        self.assertEqual((dialog.enviados, dialog.pulados), (1, 1))
        self.assertIn("Pronto", dialog.progresso_label.text())
        page.refresh_data()
        self.assertEqual(page.quem_recebe.kpi_ja.value_label.text(), "1")

    def test_companies_can_be_taken_out_and_returned(self) -> None:
        tipo = self.services.tipo_service.get_or_create_tipo("Informe de Rendimentos")["id"]
        self.services.periodo_service.generate_year(date.today().year)
        self.services.documento_service.create_documento(self.empresa_id, tipo, "Bradesco")
        self.services.envio_programado_service.criar(
            {"nome": "Informe", "tipo_documento_id": tipo, "meses": "mensal", "dia_envio": 1,
             "assunto": "Informe", "corpo": "Falta {documentos}"}
        )
        page = EnviosPage(self.services, lambda: None)
        painel = page.quem_recebe
        painel.whatsapp.table.selectRow(0)
        painel.tabs.setCurrentWidget(painel.whatsapp)
        with mock.patch.object(QMessageBox, "question", return_value=SIM):
            painel.remove_companies()
        self.assertEqual(painel.tabs.tabText(2), "Fica de fora (1)")
        self.assertEqual(painel.fora.linhas[0]["motivo"], "Tirada deste envio")
        self.assertIn("menos 1", page.subtitulo_label.text())
        painel.fora.table.selectRow(0)
        painel.return_companies()
        self.assertEqual(painel.tabs.tabText(1), "WhatsApp (1)")

    def test_message_tab_saves_text_and_templates(self) -> None:
        self._aviso()
        page = EnviosPage(self.services, lambda: None)
        aba = page.mensagem
        aba.corpo_edit.setPlainText("Novo texto para {empresa}")
        self.assertTrue(aba.dirty)
        with mock.patch.object(envios_page.QInputDialog, "getText", return_value=("Aviso padrão", True)), \
                mock.patch.object(QMessageBox, "information"):
            aba.salvar_modelo()
        self.assertTrue(aba.save())
        self.assertEqual(page.envio_atual()["corpo"], "Novo texto para {empresa}")

        modelo = self.services.envio_programado_service.listar_modelos()[0]
        aba.corpo_edit.setPlainText("outro")
        aba.carregar_modelo(modelo)
        self.assertEqual(aba.corpo_edit.toPlainText(), "Novo texto para {empresa}")
        aba._montar_menu_modelos()
        self.assertIn("Aviso padrão", [a.text().strip() for a in aba.modelos_menu.actions()])

    def test_new_mailing_sends_by_email_through_the_office_login(self) -> None:
        segunda = self.services.empresa_service.create_empresa(2, "Oficina", "of@x.com")
        page = EnviosPage(self.services, lambda: None)
        self.assertEqual(page.detalhe.currentIndex(), 0)  # sem envio: tela vazia
        with mock.patch.object(envios_page.QInputDialog, "getText", return_value=("Distribuição de lucros", True)), \
                mock.patch.object(QMessageBox, "information"):
            page.new_mailing()
        envio = page.envio_atual()
        self.assertEqual(sorted(envio["empresa_ids_lista"]), sorted([self.empresa_id, segunda]))
        page.mensagem.para_edit.setText("contato@escritorio.com")
        self.assertTrue(page.mensagem.save())
        painel = page.quem_recebe
        self.assertEqual((painel.kpi_email.value_label.text(), painel.kpi_whatsapp.value_label.text()), ("1", "1"))

        enviados = []
        sender = mock.Mock()
        sender.configurado.return_value = True
        sender.remetente.return_value = "envios@escritorio.com"
        sender.enviar_lote.side_effect = lambda mensagens, on_progress=None: enviados.extend(mensagens) or [{"ok": True}] * len(mensagens)
        self.services.email_sender_service = sender
        with mock.patch.object(QMessageBox, "question", return_value=SIM), \
                mock.patch.object(QMessageBox, "information"):
            painel.send_emails()
        self.assertEqual([(m["para"], m["cco"]) for m in enviados], [(["contato@escritorio.com"], ["of@x.com"])])
        self.assertEqual(painel.kpi_ja.value_label.text(), "1")


if __name__ == "__main__":
    unittest.main()
