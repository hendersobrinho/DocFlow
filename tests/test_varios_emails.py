from __future__ import annotations

import unittest
from unittest import mock

from psycopg.conninfo import make_conninfo

from documentos_empresa_app.app_context import build_application_services
from documentos_empresa_app.services.envio_programado_service import split_emails
from documentos_empresa_app.utils import helpers
from documentos_empresa_app.utils.common import ValidationError

from tests.postgres_support import create_test_database_manager, get_test_database_url


class VariosEmailsTests(unittest.TestCase):
    """A cobranca de uma empresa pode ir para mais de um email."""

    def setUp(self) -> None:
        db_manager = create_test_database_manager(self)
        conninfo = make_conninfo(get_test_database_url(), options=f"-c search_path={db_manager.schema},public")
        self.services = build_application_services(conninfo)
        self.addCleanup(self.services.database_maintenance_service.db_manager.close)
        self.services.session_service.login(self.services.auth_service.authenticate("admin", "admin"))
        self.empresas = self.services.empresa_service

    def test_company_keeps_every_email(self) -> None:
        empresa_id = self.empresas.create_empresa(1, "Padaria", "fin@pao.com; dono@pao.com  FIN@pao.com")
        email = self.empresas.get_empresa(empresa_id)["email_contato"]
        self.assertEqual(email, "fin@pao.com, dono@pao.com")
        # Os envios automaticos mandam para todos.
        self.assertEqual(split_emails(email), ["fin@pao.com", "dono@pao.com"])

        self.empresas.update_empresa(empresa_id, "Padaria", "fin@pao.com, rh@pao.com")
        self.assertEqual(self.empresas.get_empresa(empresa_id)["email_contato"], "fin@pao.com, rh@pao.com")

    def test_invalid_email_says_which_one(self) -> None:
        with self.assertRaises(ValidationError) as erro:
            self.empresas.create_empresa(2, "Clinica", "ok@clinica.com, clinica.com")
        self.assertIn('"clinica.com"', str(erro.exception))

    def test_mailing_list_gets_every_email_of_the_company(self) -> None:
        a = self.empresas.create_empresa(3, "A", "a1@x.com, a2@x.com")
        b = self.empresas.create_empresa(4, "B", "a2@x.com")
        emails, faltando, _ = self.services.email_campaign_service.build_recipients([a, b])
        self.assertEqual((emails, faltando), (["a1@x.com", "a2@x.com"], []))

    def test_email_draft_puts_every_email_in_to(self) -> None:
        with mock.patch.object(helpers.sys, "platform", "win32"), \
                mock.patch.object(helpers.os, "startfile", create=True) as abrir, \
                mock.patch.object(helpers, "get_default_email_handler", return_value="Outlook"):
            helpers.open_email_draft("fin@pao.com; dono@pao.com", "Assunto", "Corpo")
        self.assertTrue(abrir.call_args[0][0].startswith("mailto:fin@pao.com,dono@pao.com?"))


if __name__ == "__main__":
    unittest.main()
