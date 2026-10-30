from __future__ import annotations

import os
from datetime import date
import unittest
from unittest import mock

from psycopg.conninfo import make_conninfo

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from documentos_empresa_app.app_context import build_application_services  # noqa: E402
from documentos_empresa_app.qt_ui.dialogs import resolver_dialog  # noqa: E402
from documentos_empresa_app.qt_ui.dialogs.resolver_dialog import ResolverDialog  # noqa: E402

from tests.postgres_support import create_test_database_manager, get_test_database_url  # noqa: E402

APP = QApplication.instance() or QApplication([])


class ResolverDialogTests(unittest.TestCase):
    """A janela "Resolver documento" grava o que a pessoa escolheu, com observacao."""

    def setUp(self) -> None:
        db_manager = create_test_database_manager(self)
        conninfo = make_conninfo(get_test_database_url(), options=f"-c search_path={db_manager.schema},public")
        self.services = build_application_services(conninfo)
        self.addCleanup(self.services.database_maintenance_service.db_manager.close)
        self.services.session_service.login(self.services.auth_service.authenticate("admin", "admin"))
        ano = date.today().year - 1
        self.services.periodo_service.generate_year(ano)
        self.janeiro = next(
            p["id"] for p in self.services.periodo_service.list_periodos() if p["ano"] == ano and p["mes"] == 1
        )
        empresa_id = self.services.empresa_service.create_empresa(1, "Padaria", "fin@pao.com")
        tipo_id = self.services.tipo_service.get_or_create_tipo("Extratos CC")["id"]
        self.doc = self.services.documento_service.create_documento(empresa_id, tipo_id, "Itau CC", ["Email"])
        self.services.status_service.update_status(self.doc, self.janeiro, "Pendente")
        # Erro de validacao vira falha do teste em vez de abrir uma caixa de mensagem.
        patcher = mock.patch.object(
            resolver_dialog.QMessageBox, "critical", side_effect=lambda *a: self.fail(a[-1])
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _resolver(self, opcao: str, observacao: str = "anotado", configurar=None, devolver=False) -> None:
        item = {"documento_id": self.doc, "periodo_id": self.janeiro, "nome_documento": "Itau CC",
                "competencia": "01", "empresa": "Padaria"}
        dialog = ResolverDialog(self.services, [item], permitir_devolver=devolver)
        dialog.cards[opcao].radio.setChecked(True)
        dialog.observacao_edit.setPlainText(observacao)
        if configurar:
            configurar(dialog)
        dialog._confirmar()
        self.assertEqual(dialog.resultado, opcao)

    def _competencia(self) -> dict:
        return self.services.cobranca_service.registro_documento(self.doc)["competencias"][0]

    def test_each_option_records_the_right_situation(self) -> None:
        def escolher_motivo(dialog):
            dialog.problema_combo.setCurrentIndex(dialog.problema_combo.findData("competencia_errada"))
            dialog.arquivo_edit.setText("/tmp/itau.pdf")

        self._resolver("documento_com_problema", "veio agosto", escolher_motivo)
        competencia = self._competencia()
        self.assertEqual((competencia["situacao"], competencia["situacao_motivo"]),
                         ("documento_com_problema", "competencia_errada"))
        self.assertEqual(competencia["verificacoes"][0]["arquivo"], "/tmp/itau.pdf")
        self.assertEqual(competencia["verificacoes"][0]["observacao"], "veio agosto")

        self._resolver("pessoa", "cliente pediu ligacao")
        self.assertEqual(self._competencia()["situacao"], "precisa_pessoa")

        self._resolver("devolver", "liguei e combinamos", devolver=True)
        self.assertEqual(self._competencia()["situacao"], "a_verificar")

        self._resolver("promessa", "manda sexta")
        self.assertEqual(self._competencia()["situacao"], "promessa_envio")

        self._resolver("nao_encontrado")
        self.assertEqual(self._competencia()["situacao"], "nao_encontrado")

        self._resolver("recebido", "conferido")
        competencia = self._competencia()
        self.assertEqual((competencia["situacao"], competencia["status"]), ("recebido", "Recebido"))

    def test_return_to_claude_only_offered_when_allowed(self) -> None:
        item = {"documento_id": self.doc, "periodo_id": self.janeiro, "nome_documento": "Itau CC",
                "competencia": "01", "empresa": "Padaria"}
        self.assertNotIn("devolver", ResolverDialog(self.services, [item]).cards)
        self.assertIn("devolver", ResolverDialog(self.services, [item], permitir_devolver=True).cards)


if __name__ == "__main__":
    unittest.main()
