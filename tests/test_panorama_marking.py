from __future__ import annotations

import os
from datetime import date
import unittest
from unittest import mock

from psycopg.conninfo import make_conninfo

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from documentos_empresa_app.app_context import build_application_services  # noqa: E402
from documentos_empresa_app.qt_ui.pages.panorama_page import PanoramaPage  # noqa: E402

from tests.postgres_support import create_test_database_manager, get_test_database_url  # noqa: E402

APP = QApplication.instance() or QApplication([])


class PanoramaMarkingTests(unittest.TestCase):
    """O mapa do Panorama substitui o Controle mensal: marca um ou varios quadradinhos."""

    def setUp(self) -> None:
        db_manager = create_test_database_manager(self)
        conninfo = make_conninfo(get_test_database_url(), options=f"-c search_path={db_manager.schema},public")
        self.services = build_application_services(conninfo)
        self.addCleanup(self.services.database_maintenance_service.db_manager.close)
        self.services.session_service.login(self.services.auth_service.authenticate("admin", "admin"))
        self.services.periodo_service.generate_year(date.today().year)
        empresa_id = self.services.empresa_service.create_empresa(1, "Padaria", "fin@pao.com")
        tipo_id = self.services.tipo_service.get_or_create_tipo("Extratos CC")["id"]
        self.itau = self.services.documento_service.create_documento(empresa_id, tipo_id, "Itau CC", ["Email"])
        self.bb = self.services.documento_service.create_documento(empresa_id, tipo_id, "BB CC", ["Email"])
        self.changed = 0
        self.page = PanoramaPage(self.services, self._on_changed)
        self.page.refresh_data()
        self.page.table.selectRow(0)

    def _on_changed(self) -> None:
        self.changed += 1
        self.page.refresh_data()

    def _status(self, documento_id: int, col: int) -> str:
        doc = next(d for d in self.page.year_map.documentos if d["documento_id"] == documento_id)
        return doc["celulas"][col]["status"]

    def test_mark_one_then_a_whole_month(self) -> None:
        mapa = self.page.year_map
        self.assertEqual({d["documento_id"] for d in mapa.documentos}, {self.itau, self.bb})
        ultimo = len(mapa.periodos) - 1
        periodo = mapa.periodos[ultimo]["periodo_id"]

        mapa.set_selected(self.itau, periodo)
        self.page.mark_selection("Recebido")
        self.assertEqual(self._status(self.itau, ultimo), "Recebido")
        self.assertEqual(self.page.year_map.selected_cells()[0]["documento_id"], self.itau)  # selecao mantida

        mapa.selection = {(d["documento_id"], periodo) for d in mapa.documentos}
        self.page.mark_selection("Pendente")
        self.assertEqual((self._status(self.itau, ultimo), self._status(self.bb, ultimo)), ("Pendente", "Pendente"))

    def test_closing_asks_first_and_blocks_following_months(self) -> None:
        mapa = self.page.year_map
        primeiro = mapa.periodos[0]["periodo_id"]
        mapa.set_selected(self.bb, primeiro)
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            self.page.mark_selection("Encerrado")
        self.assertEqual(self._status(self.bb, 0), "")

        mapa.set_selected(self.bb, primeiro)
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.page.mark_selection("Encerrado")
        bb = next(d for d in self.page.year_map.documentos if d["documento_id"] == self.bb)
        self.assertEqual(bb["celulas"][0]["status"], "Encerrado")
        if len(bb["celulas"]) > 1:
            self.assertFalse(bb["celulas"][1]["disponivel"])


if __name__ == "__main__":
    unittest.main()
