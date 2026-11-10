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
        # Preferencias de tela em memoria: o teste nao mexe na configuracao deste computador.
        self.estado: dict = {}
        for nome, func in (
            ("load_ui_state", lambda k, d=None: self.estado.get(k, d)),
            ("save_ui_state", lambda k, v: self.estado.__setitem__(k, v)),
        ):
            patcher = mock.patch(f"documentos_empresa_app.qt_ui.pages.panorama_page.{nome}", func)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.page = PanoramaPage(self.services, self._on_changed)
        self.page.refresh_data()
        self.page.table.selectRow(0)

    def _on_changed(self) -> None:
        self.changed += 1
        self.page.refresh_data()

    def _status(self, documento_id: int, col: int) -> str:
        doc = next(d for d in self.page.year_map.documentos if d["documento_id"] == documento_id)
        return doc["celulas"][col]["status"]

    def test_remembers_last_chosen_period(self) -> None:
        combo = self.page.period_combo
        escolhida = combo.findText(f"03/{date.today().year}")
        combo.setCurrentIndex(escolhida)
        self.assertEqual(self.estado["panorama:competencia"], f"03/{date.today().year}")

        outra = PanoramaPage(self.services, lambda: None)  # como se abrisse o sistema de novo
        self.addCleanup(outra.deleteLater)
        outra.refresh_data()
        self.assertEqual(outra.period_combo.currentText(), f"03/{date.today().year}")

    def test_typing_marks_like_the_spreadsheet(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        self.page.show()
        self.page.activateWindow()
        QTest.qWaitForWindowActive(self.page)  # atalhos so disparam com a janela ativa
        mapa = self.page.year_map
        ultimo = len(mapa.periodos) - 1
        mapa.set_selected(self.itau, mapa.periodos[ultimo]["periodo_id"])
        mapa.setFocus()
        coluna_itau = next(i for i, d in enumerate(mapa.documentos) if d["documento_id"] == self.itau)
        outro = mapa.documentos[1 - coluna_itau]["documento_id"]
        seta = Qt.Key.Key_Down if coluna_itau == 0 else Qt.Key.Key_Up

        for tecla, documento, esperado in (("O", self.itau, "Recebido"), ("P", self.itau, "Pendente"), ("X", self.itau, "Nao cobrar")):
            QTest.keyClick(self.page.year_map, tecla)
            self.assertEqual(self._status(documento, ultimo), esperado, tecla)

        QTest.keyClick(self.page.year_map, seta)  # anda para o outro documento, mesmo mes
        QTest.keyClick(self.page.year_map, "O")
        QTest.keyClick(self.page.year_map, "K")  # "OK" inteiro: o K nao faz nada
        self.assertEqual(self._status(outro, ultimo), "Recebido")
        self.assertEqual(self._status(self.itau, ultimo), "Nao cobrar")

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

    def test_fill_handle_drags_the_status_like_excel(self) -> None:
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest

        self.page.resize(1200, 800)
        self.page.show()
        mapa = self.page.year_map
        if len(mapa.periodos) < 4:
            self.skipTest("precisa de pelo menos 4 meses no mapa")
        linha = next(i for i, d in enumerate(mapa.documentos) if d["documento_id"] == self.itau)
        mapa.set_selected(self.itau, mapa.periodos[0]["periodo_id"])
        self.page.mark_selection("Recebido")
        mapa = self.page.year_map
        self.assertIsNotNone(mapa._handle_rect())  # quadradinho marcado: a alca aparece

        def centro(rect) -> QPoint:
            return rect.center().toPoint()

        QTest.mousePress(mapa, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, centro(mapa._handle_rect()))
        QTest.mouseMove(mapa, centro(mapa._cell_rect(linha, 3)))
        self.assertEqual(len(mapa._fill_cells()), 3)
        QTest.mouseRelease(mapa, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, centro(mapa._cell_rect(linha, 3)))
        self.assertEqual([self._status(self.itau, c) for c in range(4)], ["Recebido"] * 4)
        outro = next(d for d in self.page.year_map.documentos if d["documento_id"] == self.bb)
        self.assertEqual(outro["celulas"][1]["status"], "")  # a outra linha nao muda

        # Na diagonal nao preenche nada; Encerrado nao tem alca.
        mapa = self.page.year_map
        mapa.set_selected(self.itau, mapa.periodos[0]["periodo_id"])
        mapa._filling, mapa._fill_target = True, (1 - linha, 2)
        self.assertEqual(mapa._fill_cells(), [])
        mapa._filling = False

    def test_copy_and_paste_like_a_spreadsheet(self) -> None:
        mapa = self.page.year_map
        if len(mapa.periodos) < 3:
            self.skipTest("precisa de pelo menos 3 meses no mapa")
        p = [periodo["periodo_id"] for periodo in mapa.periodos]
        mapa.selection = {(self.itau, p[0]), (self.itau, p[1])}
        self.page.mark_selection("Recebido")
        mapa = self.page.year_map
        mapa.set_selected(self.itau, p[1])
        self.page.mark_selection("Nao cobrar")

        # Copia a linha do Itau (2 meses) e cola na do BB.
        mapa = self.page.year_map
        mapa.selection = {(self.itau, p[0]), (self.itau, p[1])}
        texto = mapa.copy_selection()
        self.assertEqual(texto, "Recebido\tNão cobrar")
        mapa.set_selected(self.bb, p[0])
        self.page.paste_cells(texto)
        self.assertEqual([self._status(self.bb, c) for c in range(3)], ["Recebido", "Nao cobrar", ""])

        # Um valor so (de uma planilha: "OK") vai para todos os selecionados; vazio nao mexe.
        mapa = self.page.year_map
        mapa.selection = {(self.bb, p[1]), (self.bb, p[2])}
        self.page.paste_cells("OK\r\n")
        self.assertEqual([self._status(self.bb, c) for c in range(3)], ["Recebido"] * 3)
        mapa = self.page.year_map
        mapa.set_selected(self.itau, p[1])
        self.page.paste_cells("\tx")  # a primeira coluna vazia nao mexe no p[1]
        self.assertEqual([self._status(self.itau, c) for c in range(3)], ["Recebido", "Nao cobrar", "Nao cobrar"])

        with mock.patch.object(QMessageBox, "warning") as aviso:
            self.page.paste_cells("talvez")
        aviso.assert_called_once()

    def test_ctrl_z_undoes_the_last_marks(self) -> None:
        mapa = self.page.year_map
        if len(mapa.periodos) < 3:
            self.skipTest("precisa de pelo menos 3 meses no mapa")
        p = [periodo["periodo_id"] for periodo in mapa.periodos]
        mapa.set_selected(self.itau, p[0])
        self.page.mark_selection("Pendente")
        mapa = self.page.year_map
        mapa.set_selected(self.itau, p[0])
        self.page.fill_cells("Pendente", [(self.itau, p[1]), (self.itau, p[2])])
        mapa = self.page.year_map
        mapa.selection = {(self.itau, p[0]), (self.itau, p[1])}
        self.page.paste_cells("Recebido")
        self.assertEqual([self._status(self.itau, c) for c in range(3)], ["Recebido", "Recebido", "Pendente"])

        self.page.undo_last()  # desfaz o colar
        self.assertEqual([self._status(self.itau, c) for c in range(3)], ["Pendente"] * 3)
        self.page.undo_last()  # desfaz o arrastar
        self.assertEqual([self._status(self.itau, c) for c in range(3)], ["Pendente", "", ""])
        self.page.undo_last()  # desfaz a primeira marcacao
        self.assertEqual(self._status(self.itau, 0), "")
        self.page.undo_last()  # nada mais
        self.assertIn("Nada para desfazer", self.page.selection_label.text())

        # Encerrado apaga os meses seguintes; o Ctrl+Z traz tudo de volta.
        mapa = self.page.year_map
        mapa.selection = {(self.bb, p[1]), (self.bb, p[2])}
        self.page.mark_selection("Recebido")
        mapa = self.page.year_map
        mapa.set_selected(self.bb, p[0])
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.page.mark_selection("Encerrado")
        self.assertEqual([self._status(self.bb, c) for c in range(3)][0], "Encerrado")
        self.page.undo_last()
        self.assertEqual([self._status(self.bb, c) for c in range(3)], ["", "Recebido", "Recebido"])

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
