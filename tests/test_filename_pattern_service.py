from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from documentos_empresa_app.services.filename_pattern_service import (
    find_period_span,
    has_conflicting_naming_templates,
    infer_filename_from_siblings,
    synthesize_default_filename,
)


class FindPeriodSpanTests(unittest.TestCase):
    def test_mm_hyphen_yyyy(self) -> None:
        span = find_period_span("Sicoob CC 04-2026.pdf", 4, 2026)
        self.assertEqual("Sicoob CC 04-2026.pdf"[span[0]:span[1]], "04-2026")

    def test_yyyy_hyphen_mm(self) -> None:
        span = find_period_span("Sicoob CC 2026-04.pdf", 4, 2026)
        self.assertEqual("Sicoob CC 2026-04.pdf"[span[0]:span[1]], "2026-04")

    def test_concatenated_mmyyyy(self) -> None:
        span = find_period_span("Sicoob CC 042026.pdf", 4, 2026)
        self.assertEqual("Sicoob CC 042026.pdf"[span[0]:span[1]], "042026")

    def test_concatenated_yyyymm(self) -> None:
        span = find_period_span("Sicoob CC 202604.pdf", 4, 2026)
        self.assertEqual("Sicoob CC 202604.pdf"[span[0]:span[1]], "202604")

    def test_different_separators(self) -> None:
        for sep in ("/", ".", "_", " "):
            filename = f"Sicoob CC 04{sep}2026.pdf"
            span = find_period_span(filename, 4, 2026)
            self.assertIsNotNone(span, msg=f"separador {sep!r} deveria casar")

    def test_returns_none_when_period_absent(self) -> None:
        self.assertIsNone(find_period_span("Sicoob CC 03-2026.pdf", 4, 2026))

    def test_returns_none_for_month_name_only(self) -> None:
        self.assertIsNone(find_period_span("Sicoob CC Marco 2026.pdf", 3, 2026))


class InferFilenameFromSiblingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _touch(self, name: str) -> None:
        (self.dir / name).write_bytes(b"conteudo")

    def test_empty_folder_returns_none(self) -> None:
        self.assertIsNone(infer_filename_from_siblings(self.dir, 4, 2026))

    def test_clones_pattern_from_single_sibling(self) -> None:
        self._touch("Sicoob CC 03-2026.pdf")
        result = infer_filename_from_siblings(self.dir, 4, 2026)
        self.assertIsNotNone(result)
        self.assertEqual(result.new_filename, "Sicoob CC 04-2026.pdf")
        self.assertEqual(result.based_on.name, "Sicoob CC 03-2026.pdf")
        self.assertEqual(result.old_period_text, "03-2026")
        self.assertEqual(result.new_period_text, "04-2026")

    def test_multiple_siblings_same_template_uses_most_recent(self) -> None:
        self._touch("Sicoob CC 01-2026.pdf")
        self._touch("Sicoob CC 02-2026.pdf")
        result = infer_filename_from_siblings(self.dir, 3, 2026)
        self.assertIsNotNone(result)
        self.assertEqual(result.new_filename, "Sicoob CC 03-2026.pdf")
        self.assertEqual(result.based_on.name, "Sicoob CC 02-2026.pdf")

    def test_conflicting_templates_returns_none(self) -> None:
        self._touch("Sicoob CC 02-2026.pdf")
        self._touch("Boleto Condominio 02-2026.pdf")
        self.assertIsNone(infer_filename_from_siblings(self.dir, 3, 2026))

    def test_bank_narrowing_resolves_ambiguity(self) -> None:
        self._touch("Sicoob CC 02-2026.pdf")
        self._touch("Boleto Condominio 02-2026.pdf")
        result = infer_filename_from_siblings(self.dir, 3, 2026, bank_key="sicoob")
        self.assertIsNotNone(result)
        self.assertEqual(result.new_filename, "Sicoob CC 03-2026.pdf")

    def test_doc_type_narrowing_resolves_ambiguity(self) -> None:
        self._touch("Sicoob CC 02-2026.pdf")
        self._touch("Sicoob Aplicacao 02-2026.pdf")
        result = infer_filename_from_siblings(self.dir, 3, 2026, doc_type="cc")
        self.assertIsNotNone(result)
        self.assertEqual(result.new_filename, "Sicoob CC 03-2026.pdf")

    def test_siblings_without_detectable_period_are_ignored(self) -> None:
        self._touch("Sicoob CC Marco 2026.pdf")
        self.assertIsNone(infer_filename_from_siblings(self.dir, 4, 2026))

    def test_sibling_with_ambiguous_period_count_is_ignored(self) -> None:
        self._touch("Sicoob CC 01-2026 e 02-2026.pdf")
        self.assertIsNone(infer_filename_from_siblings(self.dir, 3, 2026))

    def test_ignores_subdirectories(self) -> None:
        (self.dir / "subpasta").mkdir()
        self.assertIsNone(infer_filename_from_siblings(self.dir, 4, 2026))


class HasConflictingNamingTemplatesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _touch(self, name: str) -> None:
        (self.dir / name).write_bytes(b"conteudo")

    def test_empty_folder_is_not_conflicting(self) -> None:
        self.assertFalse(has_conflicting_naming_templates(self.dir))

    def test_missing_folder_is_not_conflicting(self) -> None:
        self.assertFalse(has_conflicting_naming_templates(self.dir / "nao_existe"))

    def test_single_template_is_not_conflicting(self) -> None:
        self._touch("Sicoob CC 01-2026.pdf")
        self._touch("Sicoob CC 02-2026.pdf")
        self.assertFalse(has_conflicting_naming_templates(self.dir))

    def test_two_distinct_templates_are_conflicting(self) -> None:
        self._touch("Sicoob CC 01-2026.pdf")
        self._touch("Boleto Condominio 02-2026.pdf")
        self.assertTrue(has_conflicting_naming_templates(self.dir))

    def test_siblings_without_detectable_period_are_not_conflicting(self) -> None:
        self._touch("Sicoob CC Marco 2026.pdf")
        self.assertFalse(has_conflicting_naming_templates(self.dir))


class SynthesizeDefaultFilenameTests(unittest.TestCase):
    def test_with_bank_and_type_and_extension(self) -> None:
        name = synthesize_default_filename(4, 2026, bank_key="sicoob", doc_type="cc", original_filename="scan.pdf")
        self.assertEqual(name, "Sicoob CC 04-2026.pdf")

    def test_aplicacao_label(self) -> None:
        name = synthesize_default_filename(
            4, 2026, bank_key="sicoob", doc_type="aplicacao", original_filename="scan.pdf"
        )
        self.assertEqual(name, "Sicoob Aplicacao 04-2026.pdf")

    def test_without_bank_uses_generic_label(self) -> None:
        name = synthesize_default_filename(4, 2026, original_filename="scan.pdf")
        self.assertEqual(name, "Documento 04-2026.pdf")

    def test_without_original_filename_has_no_extension(self) -> None:
        name = synthesize_default_filename(4, 2026, bank_key="sicoob")
        self.assertEqual(name, "Sicoob 04-2026")

    def test_preserves_original_extension(self) -> None:
        name = synthesize_default_filename(4, 2026, bank_key="sicoob", original_filename="foto.JPG")
        self.assertEqual(name, "Sicoob 04-2026.JPG")


if __name__ == "__main__":
    unittest.main()
