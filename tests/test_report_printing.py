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
from documentos_empresa_app.services.report_html import PAGE_BACKGROUND, build_report_html


def _linhas(quantidade: int) -> list[dict]:
    return [
        {
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
            kind=kind, rows=linhas, companies_total=10, period_text="09/2026",
            company_label="Todas as empresas (10)", generated_at="10/11/2026 11:00",
        )

    def test_html_uses_the_brand_colors_and_all_statuses(self) -> None:
        html = self._html(_linhas(12))
        for texto in ("Situação da documentação", "#203461", "#4BBDCD", "Chegou", "Ainda não chegou", "Procurado e não encontrado"):
            self.assertIn(texto, html)

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
