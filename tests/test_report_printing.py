from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

APP = QApplication.instance() or QApplication([])

from documentos_empresa_app.qt_ui.report_printing import save_html_as_pdf
from documentos_empresa_app.services.report_html import PAGE_BACKGROUND, build_report_html, intervalos_competencias


def _linhas(quantidade: int) -> list[dict]:
    return [
        {
            "empresa_id": numero // 3,
            "documento_id": numero,
            "codigo_empresa": 100 + numero // 3,
            "nome_empresa": f"Empresa {numero // 3}",
            "ano": 2026,
            "mes": 9,
            "tipo_documento": "Extratos CC",
            "nome_documento": f"Banco {numero}",
            "status": "Pendente" if numero % 4 == 0 else "Recebido",
        }
        for numero in range(quantidade)
    ]


class ReportPrintingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.pasta, True)

    def _html(self, linhas: list[dict], kind: str = "situacao") -> str:
        return build_report_html(
            kind=kind, rows=linhas, competencia="09/2026",
            company_label="Todas as empresas (10)", generated_at="10/11/2026 11:00",
        )

    def test_html_uses_the_brand_colors_and_all_statuses(self) -> None:
        html = self._html(_linhas(12))
        for texto in ("Situação da documentação", "#203461", "Chegou", "Pendente"):
            self.assertIn(texto, html)

    def test_months_in_a_row_become_a_range(self) -> None:
        self.assertEqual(intervalos_competencias([(2026, m) for m in range(1, 9)]), "01/2026 a 08/2026")
        self.assertEqual(
            intervalos_competencias([(2025, 11), (2025, 12), (2026, 1), (2026, 3), (2026, 6), (2026, 7)]),
            "11/2025 a 01/2026, 03/2026, 06/2026 a 07/2026",
        )
        self.assertEqual(intervalos_competencias([(2026, 3)]), "03/2026")

    def test_by_document_lists_each_document_once_with_its_months(self) -> None:
        def linha(doc_id, nome, mes, status="Pendente"):
            return {
                "empresa_id": 1, "documento_id": doc_id, "codigo_empresa": 10, "nome_empresa": "Clinica",
                "ano": 2026, "mes": mes, "tipo_documento": "Contabil", "nome_documento": nome, "status": status,
            }

        mes = [linha(1, "Balancete", 8), linha(2, "Caixa", 8, "Recebido")]
        anteriores = [linha(1, "Balancete", m) for m in range(1, 8)] + [linha(3, "Movimento", 2), linha(3, "Movimento", 5)]
        kwargs = dict(kind="situacao", rows=mes, pendentes_anteriores=anteriores, competencia="08/2026",
                      company_label="Todas", generated_at="18/11/2026 10:00")
        por_doc = build_report_html(**kwargs, agrupar="documento")
        self.assertEqual(por_doc.count("Balancete"), 1)
        self.assertIn("01/2026 a 08/2026", por_doc)
        self.assertIn("02/2026, 05/2026", por_doc)
        por_mes = build_report_html(**kwargs)  # o modelo de sempre continua igual
        self.assertEqual(por_mes.count("Balancete"), 8)

    def test_everything_missing_is_pendente_without_a_separate_not_found_column(self) -> None:
        def linha(emp, doc_id, nome, status):
            return {
                "empresa_id": emp, "documento_id": doc_id, "codigo_empresa": 10 + emp, "nome_empresa": f"Empresa {emp}",
                "ano": 2026, "mes": 9, "tipo_documento": "Contabil", "nome_documento": nome, "status": status,
            }

        # Empresa 1 mandou um e falta outro; empresa 2 nao mandou nada: os dois faltando sao Pendente.
        linhas = [linha(1, 1, "Balancete", "Recebido"), linha(1, 2, "Caixa", "Pendente"), linha(2, 3, "Extrato", "Pendente")]
        for agrupar in ("competencia", "documento"):
            html = build_report_html(
                kind="situacao", rows=linhas, competencia="09/2026", company_label="Todas",
                generated_at="18/11/2026 10:00", agrupar=agrupar,
            )
            self.assertNotIn("não encontrado", html)
            self.assertNotIn("Ainda não chegou", html)
            self.assertIn("documento(s) pendente(s)", html)
            self.assertIn("Extrato", html)

    def test_pdf_has_the_system_background_on_every_page(self) -> None:
        from PySide6.QtPdf import QPdfDocument

        destino = save_html_as_pdf(self._html(_linhas(150)), self.pasta / "relatorio.pdf")
        self.assertTrue(destino.exists())
        documento = QPdfDocument()
        documento.load(str(destino))
        self.assertGreater(documento.pageCount(), 1)
        esperado = (int(PAGE_BACKGROUND[1:3], 16), int(PAGE_BACKGROUND[3:5], 16), int(PAGE_BACKGROUND[5:7], 16))
        for pagina in range(documento.pageCount()):
            imagem = documento.render(pagina, documento.pagePointSize(pagina).toSize())
            # Canto da folha (dentro da margem): tem que ser o fundo do sistema, nao branco.
            cor = imagem.pixelColor(3, 3)
            self.assertEqual((cor.red(), cor.green(), cor.blue()), esperado, f"pagina {pagina + 1}")


if __name__ == "__main__":
    unittest.main()
