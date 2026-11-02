from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

from openpyxl import Workbook
from openpyxl.styles import PatternFill
from openpyxl.styles.colors import Color

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "tratar_planilha_controle.py"
_spec = importlib.util.spec_from_file_location("tratar_planilha_controle", SCRIPT_PATH)
tratar = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = tratar  # dataclasses precisam achar o modulo
_spec.loader.exec_module(tratar)


def _preto(tint: float = 0.0) -> PatternFill:
    return PatternFill("solid", fgColor=Color(theme=1, tint=tint))


class CelulasPintadasDePretoTests(unittest.TestCase):
    """Na planilha de controle, celula pintada de preto e vazia = o documento nao existia ou ja
    tinha encerrado naquele mes: nao pode entrar na revisao/cobranca."""

    def _doc(self, valores: list[str], pretas: set[int], tint: float = 0.0):
        ws = Workbook().active
        for i, valor in enumerate(valores):
            cell = ws.cell(1, i + 1, valor or None)
            if i in pretas:
                cell.fill = _preto(tint)
        escuras = [tratar.celula_escura(ws.cell(1, i + 1)) for i in range(12)]
        doc = tratar.Documento(linha=1, original="Banco", envio_original="", obs_original="")
        for i, valor in enumerate(valores):
            if valor:
                doc.meses[i] = valor
        tratar.aplica_celulas_escuras(doc, valores, escuras)
        return doc

    def test_black_before_opening_becomes_nao_cobrar(self) -> None:
        valores = ["", "", "", "", "OK", "OK", "OK", "", "", "", "", ""]
        doc = self._doc(valores, {0, 1, 2, 3}, tint=0.25)
        self.assertEqual(doc.meses[:5], ["X", "X", "X", "X", "OK"])
        self.assertEqual(doc.meses[7], "")  # mes em branco sem pintura continua para cobrar

    def test_black_after_last_month_becomes_encerrado(self) -> None:
        valores = ["OK"] * 6 + [""] * 6
        doc = self._doc(valores, set(range(6, 12)))
        self.assertEqual(doc.meses[5:8], ["OK", "Encerrado", ""])

    def test_whole_row_black_is_never_charged(self) -> None:
        doc = self._doc([""] * 12, set(range(12)))
        self.assertEqual(doc.meses, ["X"] * 12)

    def test_written_value_in_painted_cell_is_kept(self) -> None:
        valores = ["OK", "OK", "P"] + [""] * 9
        doc = self._doc(valores, {0, 1, 2}, tint=0.25)
        self.assertEqual(doc.meses[:4], ["OK", "OK", "P", ""])

    def test_white_cell_is_not_dark(self) -> None:
        ws = Workbook().active
        ws["A1"].fill = PatternFill("solid", fgColor=Color(theme=0))
        self.assertFalse(tratar.celula_escura(ws["A1"]))
        self.assertFalse(tratar.celula_escura(ws["B1"]))


if __name__ == "__main__":
    unittest.main()
