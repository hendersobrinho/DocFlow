from __future__ import annotations

import os
import unittest

from psycopg.conninfo import make_conninfo

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402
import shiboken6  # noqa: E402

from documentos_empresa_app.app_context import build_application_services  # noqa: E402
from documentos_empresa_app.qt_ui.pages.documentos_page import DocumentosPage  # noqa: E402

from tests.postgres_support import create_test_database_manager, get_test_database_url  # noqa: E402

APP = QApplication.instance() or QApplication([])


class DocumentosPageTests(unittest.TestCase):
    def setUp(self) -> None:
        db_manager = create_test_database_manager(self)
        conninfo = make_conninfo(get_test_database_url(), options=f"-c search_path={db_manager.schema},public")
        self.services = build_application_services(conninfo)
        self.addCleanup(self.services.database_maintenance_service.db_manager.close)
        self.services.session_service.login(self.services.auth_service.authenticate("admin", "admin"))
        self.empresa_id = self.services.empresa_service.create_empresa(5, "Padaria")
        # Como na janela: salvar avisa as telas, e a de Documentos recarrega (inclusive o seletor).
        self.page = DocumentosPage(self.services, lambda: self.page.refresh_data())
        # Destroi a tela antes de fechar o banco (cleanups rodam do ultimo para o primeiro):
        # widget esquecido vivo ate o fim do processo pode derrubar o Python ao sair.
        self.addCleanup(shiboken6.delete, self.page)
        self.page.refresh_data()
        self.page.company_selector.set_company(self.empresa_id)

    def _novo(self, nome: str) -> None:
        self.page.start_new()
        self.page.tipo_combo.setCurrentIndex(0)
        self.page.nome_combo.setCurrentText(nome)

    def test_new_document_is_saved_and_stays_open(self) -> None:
        self._novo("Bradesco")
        self.page.save_document()  # antes: "Documento nao encontrado" depois de gravar

        docs = self.services.documento_service.list_documentos_empresa(self.empresa_id)
        self.assertEqual([d["nome_documento"] for d in docs], ["Bradesco"])
        self.assertEqual(self.page.editing_document_id, docs[0]["id"])
        self.assertFalse(self.page.creating)

    def test_reselecting_the_same_company_keeps_the_new_document_form(self) -> None:
        self._novo("Itaú")
        # O campo do codigo perdendo o foco seleciona a mesma empresa de novo.
        self.page.company_selector.set_company(self.empresa_id)
        self.assertTrue(self.page.creating)

        self.page.save_document()
        nomes = [d["nome_documento"] for d in self.services.documento_service.list_documentos_empresa(self.empresa_id)]
        self.assertEqual(nomes, ["Itaú"])

    def test_choosing_another_company_closes_the_form(self) -> None:
        outra = self.services.empresa_service.create_empresa(6, "Clinica")
        self.page.refresh_data()
        self._novo("Sicoob")
        self.page.dirty = False
        self.page.company_selector.set_company(outra)
        self.assertFalse(self.page.creating)


if __name__ == "__main__":
    unittest.main()
