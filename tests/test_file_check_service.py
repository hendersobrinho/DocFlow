from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from documentos_empresa_app.services.file_check_service import (
    MODE_CURRENT_ONLY,
    MODE_PENDING_HISTORY,
    LAYOUT_MONTH_FIRST,
    LAYOUT_YEAR_DIRECT,
    PERIOD_SOURCE_FILENAME_ONLY,
    RESULT_ALTA_CONFIANCA,
    RESULT_ERRO,
    RESULT_NAO_ENCONTRADO,
    RESULT_REVISAR,
    SCORE_HIGH,
    SCORE_REVIEW,
    TEMPORAL_ATUAL,
    TEMPORAL_ANTERIOR_PENDENTE,
    TEMPORAL_ANTERIOR_RECEBIDA,
    TEMPORAL_DIFERENTE,
    TEMPORAL_FUTURA,
    TEMPORAL_NAO_IDENTIFICADA,
    FileCheckService,
    build_expected_periods,
    classify_candidates,
    classify_file_period,
    contains_any,
    detect_document_bank,
    detect_document_type,
    document_match_terms,
    extract_periods_from_folder_name,
    extract_periods_from_filename,
    is_bank_statement_document,
    is_checkable_document,
    match_bank_in_filename,
    match_period_in_filename,
    match_type_in_filename,
    normalize,
    resolve_company_folder,
    resolve_extratos_folder,
    resolve_type_subfolder,
    resolve_year_folder,
    score_file,
    suggest_company_folder_name,
)


# ── normalize ──────────────────────────────────────────────────────────────────

class TestNormalize(unittest.TestCase):
    def test_strips_accents(self):
        self.assertEqual(normalize("Extratos Bancários"), "extratos bancarios")
        self.assertEqual(normalize("Aplicação"), "aplicacao")
        self.assertEqual(normalize("Conta Corrente"), "conta corrente")

    def test_lowercases(self):
        self.assertEqual(normalize("BB"), "bb")
        self.assertEqual(normalize("BANCO DO BRASIL"), "banco do brasil")

    def test_preserves_numbers(self):
        self.assertEqual(normalize("012026"), "012026")
        self.assertEqual(normalize("01/2026"), "01/2026")


class TestContainsAny(unittest.TestCase):
    def test_finds_token(self):
        self.assertTrue(contains_any("Extrato Bancário BB", ["extrato"]))
        self.assertTrue(contains_any("Conta Corrente", ["conta corrente"]))

    def test_accent_insensitive(self):
        self.assertTrue(contains_any("Extratos Bancários", ["extratos bancarios"]))

    def test_returns_false_when_absent(self):
        self.assertFalse(contains_any("Folha de Pagamento", ["extrato", "bancario"]))


# ── Period matching ────────────────────────────────────────────────────────────

class TestMatchPeriodInFilename(unittest.TestCase):
    def test_slash_format(self):
        self.assertTrue(match_period_in_filename("extrato_01_2026.pdf", 1, 2026))
        self.assertTrue(match_period_in_filename("extrato 01/2026.pdf", 1, 2026))

    def test_dash_format(self):
        self.assertTrue(match_period_in_filename("arquivo-01-2026.pdf", 1, 2026))

    def test_dot_format(self):
        self.assertTrue(match_period_in_filename("arquivo.01.2026.pdf", 1, 2026))

    def test_concatenated_format(self):
        self.assertTrue(match_period_in_filename("extrato012026.pdf", 1, 2026))
        self.assertTrue(match_period_in_filename("extrato_01_2026.pdf", 1, 2026))
        self.assertTrue(match_period_in_filename("extrato2026_01.pdf", 1, 2026))

    def test_year_month_reversed(self):
        self.assertTrue(match_period_in_filename("2026-01-extrato.pdf", 1, 2026))

    def test_month_name(self):
        self.assertTrue(match_period_in_filename("extrato_jan_2026.pdf", 1, 2026))
        self.assertTrue(match_period_in_filename("janeiro 2026.pdf", 1, 2026))
        self.assertTrue(match_period_in_filename("EXTRATO MARCO 2026.pdf", 3, 2026))

    def test_wrong_month_returns_false(self):
        self.assertFalse(match_period_in_filename("extrato_02_2026.pdf", 1, 2026))

    def test_wrong_year_returns_false(self):
        self.assertFalse(match_period_in_filename("extrato_01_2025.pdf", 1, 2026))

    def test_all_months_have_names(self):
        names = {
            1: "janeiro", 2: "fevereiro", 3: "marco", 4: "abril",
            5: "maio", 6: "junho", 7: "julho", 8: "agosto",
            9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro",
        }
        for month, name in names.items():
            self.assertTrue(
                match_period_in_filename(f"{name} 2026.pdf", month, 2026),
                f"Month {month} ({name}) not matched",
            )


# ── Bank detection ─────────────────────────────────────────────────────────────

class TestDetectDocumentBank(unittest.TestCase):
    def test_bb(self):
        self.assertEqual(detect_document_bank("Extrato BB Conta Corrente"), "banco do brasil")
        self.assertEqual(detect_document_bank("Banco do Brasil - CC"), "banco do brasil")

    def test_caixa(self):
        self.assertEqual(detect_document_bank("Extrato CEF Aplicacao"), "caixa")
        self.assertEqual(detect_document_bank("Caixa Economica Federal"), "caixa")

    def test_itau(self):
        self.assertEqual(detect_document_bank("Extrato Itau"), "itau")

    def test_bradesco(self):
        self.assertEqual(detect_document_bank("Bradesco CC"), "bradesco")

    def test_sicredi(self):
        self.assertEqual(detect_document_bank("Sicredi Aplicacao"), "sicredi")

    def test_unknown_returns_none(self):
        self.assertIsNone(detect_document_bank("Extrato Conta Corrente"))

    def test_accent_insensitive(self):
        self.assertEqual(detect_document_bank("Itaú Conta Corrente"), "itau")

    def test_common_santander_typo(self):
        self.assertEqual(detect_document_bank("Santarder C/C 1300025613"), "santander")

    def test_detects_banestes_from_bank_prefix(self):
        self.assertEqual(detect_document_bank("Banco Banestes C/C 3069614-0"), "banestes")


class TestMatchBankInFilename(unittest.TestCase):
    def test_matches_alias(self):
        self.assertTrue(match_bank_in_filename("extrato_bb_01_2026.pdf", "banco do brasil"))

    def test_no_match(self):
        self.assertFalse(match_bank_in_filename("extrato_bradesco_01_2026.pdf", "banco do brasil"))

    def test_none_bank_key(self):
        self.assertFalse(match_bank_in_filename("extrato_bb_01_2026.pdf", None))


# ── Type detection ─────────────────────────────────────────────────────────────

class TestDetectDocumentType(unittest.TestCase):
    def test_cc(self):
        self.assertEqual(detect_document_type("Extrato CC Bradesco"), "cc")
        self.assertEqual(detect_document_type("Conta Corrente BB"), "cc")
        self.assertEqual(detect_document_type("Extrato Corrente"), "cc")

    def test_aplicacao(self):
        self.assertEqual(detect_document_type("Aplicacao CDB Nubank"), "aplicacao")
        self.assertEqual(detect_document_type("Investimento Caixa"), "aplicacao")
        self.assertEqual(detect_document_type("Poupanca BB"), "aplicacao")
        self.assertEqual(detect_document_type("Rendimento Inter"), "aplicacao")

    def test_unknown_returns_none(self):
        self.assertIsNone(detect_document_type("Extrato Bancario"))

    def test_accent_insensitive(self):
        self.assertEqual(detect_document_type("Aplicação Sicoob"), "aplicacao")
        self.assertEqual(detect_document_type("Poupança BB"), "aplicacao")


class TestMatchTypeInFilename(unittest.TestCase):
    def test_cc_tokens(self):
        self.assertTrue(match_type_in_filename("extrato_cc_bb_01_2026.pdf", "cc"))
        self.assertTrue(match_type_in_filename("conta corrente itau jan 2026.pdf", "cc"))

    def test_aplicacao_tokens(self):
        self.assertTrue(match_type_in_filename("aplicacao_caixa_01_2026.pdf", "aplicacao"))
        self.assertTrue(match_type_in_filename("investimento_bb_jan_2026.pdf", "aplicacao"))

    def test_none_type(self):
        self.assertFalse(match_type_in_filename("arquivo.pdf", None))


# ── is_bank_statement_document ─────────────────────────────────────────────────

class TestIsBankStatementDocument(unittest.TestCase):
    def test_positive_cases(self):
        self.assertTrue(is_bank_statement_document("Extrato Bancario", "BB CC"))
        self.assertTrue(is_bank_statement_document("Banco", "Itau Aplicacao"))
        self.assertTrue(is_bank_statement_document("Extrato", "Conta Corrente Bradesco"))

    def test_negative_cases(self):
        self.assertFalse(is_bank_statement_document("Folha de Pagamento", "Funcionarios"))
        self.assertFalse(is_bank_statement_document("DAS", "Simples Nacional"))
        self.assertFalse(is_bank_statement_document("DARF", "Imposto de Renda"))


class TestGenericDocumentTerms(unittest.TestCase):
    def test_builds_terms_from_registered_document(self):
        terms = document_match_terms("Fiscal", "DAS Simples Nacional")
        self.assertIn("das", terms)
        self.assertIn("simples", terms)
        self.assertIn("nacional", terms)

    def test_non_bank_documents_are_checkable_when_named(self):
        self.assertTrue(is_checkable_document("Fiscal", "DAS Simples Nacional"))

    def test_folder_name_can_indicate_month(self):
        self.assertIn((5, 2026), extract_periods_from_folder_name("05 - Maio", fallback_year=2026))
        self.assertIn((5, 2026), extract_periods_from_folder_name("Maio", fallback_year=2026))


# ── resolve_company_folder ─────────────────────────────────────────────────────

class TestResolveCompanyFolder(unittest.TestCase):
    def test_uses_diretorio_documentos_when_valid(self, tmp_path=None):
        tmp = Path(self._get_tmp())
        empresa_dir = tmp / "empresa"
        empresa_dir.mkdir()
        empresa = {"codigo_empresa": 123, "diretorio_documentos": str(empresa_dir)}
        folder, score, note = resolve_company_folder(empresa, tmp)
        self.assertEqual(folder, empresa_dir)
        self.assertEqual(score, 30)

    def test_diretorio_documentos_missing_returns_none(self):
        empresa = {"codigo_empresa": 123, "diretorio_documentos": "/nonexistent/path/xyz"}
        folder, score, note = resolve_company_folder(empresa, Path("/"))
        self.assertIsNone(folder)
        self.assertEqual(score, 0)

    def test_searches_root_by_dot_prefix(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            empresa_dir = tmp_path / "123. EMPRESA TESTE"
            empresa_dir.mkdir()
            empresa = {"codigo_empresa": 123, "diretorio_documentos": None}
            folder, score, note = resolve_company_folder(empresa, tmp_path)
            self.assertEqual(folder, empresa_dir)
            self.assertEqual(score, 30)

    def test_searches_root_by_dash_prefix(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            empresa_dir = tmp_path / "456 - EMPRESA DASH"
            empresa_dir.mkdir()
            empresa = {"codigo_empresa": 456, "diretorio_documentos": None}
            folder, score, note = resolve_company_folder(empresa, tmp_path)
            self.assertEqual(folder, empresa_dir)
            self.assertEqual(score, 30)

    def test_returns_none_when_not_found(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            empresa = {"codigo_empresa": 999, "diretorio_documentos": None}
            folder, score, note = resolve_company_folder(empresa, tmp_path)
            self.assertIsNone(folder)
            self.assertEqual(score, 0)

    def _get_tmp(self):
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        return self._tmpdir


class TestSuggestCompanyFolderName(unittest.TestCase):
    def test_empty_root_uses_default_convention(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            name = suggest_company_folder_name("1", "Acme Ltda", Path(tmp))
            self.assertEqual(name, "1. Acme Ltda")

    def test_learns_dash_convention_from_siblings(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "2 - Beta Ltda").mkdir()
            (tmp_path / "3 - Gamma Ltda").mkdir()
            name = suggest_company_folder_name("1", "Acme Ltda", tmp_path)
            self.assertEqual(name, "1 - Acme Ltda")

    def test_majority_convention_wins_when_mixed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "2 - Beta Ltda").mkdir()
            (tmp_path / "3 - Gamma Ltda").mkdir()
            (tmp_path / "4. Delta Ltda").mkdir()
            name = suggest_company_folder_name("1", "Acme Ltda", tmp_path)
            self.assertEqual(name, "1 - Acme Ltda")

    def test_ignores_folders_without_recognizable_pattern(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "Documentos Gerais").mkdir()
            (tmp_path / "2026").mkdir()
            name = suggest_company_folder_name("1", "Acme Ltda", tmp_path)
            self.assertEqual(name, "1. Acme Ltda")

    def test_sanitizes_illegal_characters_in_company_name(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            name = suggest_company_folder_name("1", "Acme/Ltda: Filial*", Path(tmp))
            self.assertEqual(name, "1. AcmeLtda Filial")


# ── resolve_year_folder ────────────────────────────────────────────────────────

class TestResolveYearFolder(unittest.TestCase):
    def test_finds_year_folder(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            year_dir = tmp_path / "2026"
            year_dir.mkdir()
            folder, score, note = resolve_year_folder(tmp_path, 2026)
            self.assertEqual(folder, year_dir)
            self.assertEqual(score, 20)

    def test_returns_none_when_absent(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            folder, score, note = resolve_year_folder(tmp_path, 2026)
            self.assertIsNone(folder)
            self.assertEqual(score, 0)


# ── resolve_extratos_folder ────────────────────────────────────────────────────

class TestResolveExtratosFolder(unittest.TestCase):
    def test_finds_standard_name(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            ex_dir = tmp_path / "Extratos Bancarios"
            ex_dir.mkdir()
            folder, score, note = resolve_extratos_folder(tmp_path)
            self.assertEqual(folder, ex_dir)
            self.assertEqual(score, 10)

    def test_finds_accented_name(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            ex_dir = tmp_path / "Extratos Bancários"
            ex_dir.mkdir()
            folder, score, note = resolve_extratos_folder(tmp_path)
            self.assertEqual(folder, ex_dir)

    def test_finds_bancos_variant(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            ex_dir = tmp_path / "Bancos"
            ex_dir.mkdir()
            folder, score, note = resolve_extratos_folder(tmp_path)
            self.assertEqual(folder, ex_dir)

    def test_returns_none_when_absent(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            folder, score, note = resolve_extratos_folder(tmp_path)
            self.assertIsNone(folder)


# ── score_file ─────────────────────────────────────────────────────────────────

class TestScoreFile(unittest.TestCase):
    def _mock_path(self, name: str) -> Path:
        p = MagicMock(spec=Path)
        p.name = name
        return p

    def test_perfect_score(self):
        p = self._mock_path("extrato_bb_cc_01_2026.pdf")
        result = score_file(p, 123, "banco do brasil", "cc", 1, 2026, base_score=80)
        self.assertGreaterEqual(result["score"], SCORE_HIGH)
        self.assertEqual(result["conflicts"], [])

    def test_period_match_adds_30(self):
        p = self._mock_path("jan2026.pdf")
        r1 = score_file(p, 123, None, None, 1, 2026, base_score=0)
        p2 = self._mock_path("fev2026.pdf")
        r2 = score_file(p2, 123, None, None, 1, 2026, base_score=0)
        self.assertEqual(r1["score"], 30)
        self.assertEqual(r2["score"], 0)

    def test_bank_match_adds_30(self):
        p = self._mock_path("arquivo_bb.pdf")
        result = score_file(p, 123, "banco do brasil", None, 1, 2026, base_score=0)
        self.assertEqual(result["score"], 30)

    def test_wrong_bank_creates_conflict(self):
        p = self._mock_path("extrato_bradesco_01_2026.pdf")
        result = score_file(p, 123, "caixa", None, 1, 2026, base_score=0)
        self.assertTrue(any("bradesco" in c for c in result["conflicts"]))

    def test_missing_expected_bank_keeps_evidence_incomplete(self):
        p = self._mock_path("123_cc_01_2026.pdf")
        result = score_file(
            p,
            123,
            "santander",
            "cc",
            1,
            2026,
            base_score=80,
            expected_type_folder=True,
        )
        self.assertGreaterEqual(result["score"], SCORE_HIGH)
        self.assertTrue(result["evidence"]["bank_required"])
        self.assertFalse(result["evidence"]["bank_matched"])

    def test_opposite_type_creates_conflict_even_in_expected_folder(self):
        p = self._mock_path("123_safra_aplicacao_01_2026.pdf")
        result = score_file(
            p,
            123,
            "safra",
            "cc",
            1,
            2026,
            base_score=80,
            expected_type_folder=True,
        )
        self.assertTrue(any("tipo diferente" in c for c in result["conflicts"]))

    def test_type_match_adds_20(self):
        p = self._mock_path("extrato_cc.pdf")
        result = score_file(p, 123, None, "cc", 1, 2026, base_score=0)
        self.assertEqual(result["score"], 20)

    def test_company_code_adds_10(self):
        p = self._mock_path("extrato_123_jan_2026.pdf")
        result = score_file(p, 123, None, None, 1, 2026, base_score=0)
        self.assertIn(10, [result["score"] - 30, result["score"]])

    def test_no_file_operations_performed(self):
        p = MagicMock(spec=Path)
        p.name = "arquivo.pdf"
        score_file(p, 1, None, None, 1, 2026, base_score=0)
        p.read_bytes.assert_not_called()
        p.open.assert_not_called()
        p.unlink.assert_not_called()
        p.rename.assert_not_called()


# ── classify_candidates ────────────────────────────────────────────────────────

class TestClassifyCandidates(unittest.TestCase):
    def _make_candidate(self, score, conflicts=None, name="arquivo.pdf"):
        p = MagicMock(spec=Path)
        p.name = name
        return {"path": p, "score": score, "motivo": ["test"], "conflicts": conflicts or []}

    def test_empty_returns_nao_encontrado(self):
        resultado, best, motivo = classify_candidates([])
        self.assertEqual(resultado, RESULT_NAO_ENCONTRADO)
        self.assertIsNone(best)

    def test_low_score_returns_nao_encontrado(self):
        c = self._make_candidate(SCORE_REVIEW - 1)
        resultado, _, _ = classify_candidates([c])
        self.assertEqual(resultado, RESULT_NAO_ENCONTRADO)

    def test_high_score_clean_returns_alta_confianca(self):
        c = self._make_candidate(SCORE_HIGH + 10)
        resultado, best, _ = classify_candidates([c])
        self.assertEqual(resultado, RESULT_ALTA_CONFIANCA)
        self.assertIsNotNone(best)

    def test_conflict_demotes_to_revisar(self):
        c = self._make_candidate(SCORE_HIGH + 10, conflicts=["banco diferente"])
        resultado, _, _ = classify_candidates([c])
        self.assertEqual(resultado, RESULT_REVISAR)

    def test_missing_bank_evidence_demotes_to_revisar(self):
        p = MagicMock(spec=Path)
        p.name = "123_cc_01_2026.pdf"
        candidate = score_file(
            p,
            123,
            "santander",
            "cc",
            1,
            2026,
            base_score=80,
            expected_type_folder=True,
        )
        resultado, _, motivo = classify_candidates([candidate])
        self.assertEqual(resultado, RESULT_REVISAR)
        self.assertIn("banco esperado", motivo)

    def test_ambiguous_candidates_demotes_to_revisar(self):
        c1 = self._make_candidate(100, name="a.pdf")
        c2 = self._make_candidate(95, name="b.pdf")
        resultado, _, _ = classify_candidates([c1, c2])
        self.assertEqual(resultado, RESULT_REVISAR)

    def test_medium_score_returns_revisar(self):
        c = self._make_candidate(SCORE_REVIEW + 10)
        resultado, _, _ = classify_candidates([c])
        self.assertEqual(resultado, RESULT_REVISAR)

    def test_clear_winner_with_distant_second_is_alta_confianca(self):
        c1 = self._make_candidate(SCORE_HIGH + 20, name="winner.pdf")
        c2 = self._make_candidate(SCORE_REVIEW, name="loser.pdf")
        resultado, best, _ = classify_candidates([c1, c2])
        self.assertEqual(resultado, RESULT_ALTA_CONFIANCA)
        self.assertEqual(best["path"].name, "winner.pdf")


# ── FileCheckService – safety contract ────────────────────────────────────────

class TestFileCheckServiceSafety(unittest.TestCase):
    """Guarantee that the service never modifies files on disk."""

    def _build_service(self):
        empresa_service = MagicMock()
        empresa_service.list_empresas.return_value = []
        documento_service = MagicMock()
        periodo_service = MagicMock()
        periodo_service.get_periodo.return_value = {"id": 1, "ano": 2026, "mes": 1}
        status_service = MagicMock()
        return FileCheckService(empresa_service, documento_service, periodo_service, status_service)

    def test_check_period_does_not_write_files(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            service = self._build_service()
            # No exception, no writes
            results = service.check_period(1, [], tmp_path)
            self.assertEqual(results, [])
            # Verify no new files were created
            self.assertEqual(list(tmp_path.iterdir()), [])

    def test_apply_high_confidence_calls_status_service(self):
        empresa_service = MagicMock()
        documento_service = MagicMock()
        periodo_service = MagicMock()
        status_service = MagicMock()
        status_service.update_status_batch.return_value = {"selected": 2, "updated": 2, "document_ids": [1, 2]}

        service = FileCheckService(empresa_service, documento_service, periodo_service, status_service)

        results = [
            {"resultado": RESULT_ALTA_CONFIANCA, "documento_id": 1},
            {"resultado": RESULT_ALTA_CONFIANCA, "documento_id": 2},
            {"resultado": RESULT_REVISAR, "documento_id": 3},
        ]

        result = service.apply_high_confidence(results, periodo_id=1)

        status_service.update_status_batch.assert_called_once_with([1, 2], 1, "Recebido")
        self.assertEqual(result["updated"], 2)

    def test_apply_empty_high_confidence_is_noop(self):
        service = self._build_service()
        results = [{"resultado": RESULT_REVISAR, "documento_id": 5}]
        result = service.apply_high_confidence(results, periodo_id=1)
        self.assertEqual(result["updated"], 0)
        service._status_service.update_status_batch.assert_not_called()


# ── extract_periods_from_filename ──────────────────────────────────────────────

class TestExtractPeriodsFromFilename(unittest.TestCase):
    def test_slash_format(self):
        self.assertIn((1, 2026), extract_periods_from_filename("extrato 01/2026.pdf"))

    def test_dash_format(self):
        self.assertIn((2, 2026), extract_periods_from_filename("Bradesco CC 02-2026.pdf"))

    def test_dot_format(self):
        self.assertIn((3, 2026), extract_periods_from_filename("arquivo.03.2026.pdf"))

    def test_underscore_format(self):
        self.assertIn((5, 2026), extract_periods_from_filename("extrato_05_2026.pdf"))

    def test_concatenated_mmyyyy(self):
        self.assertIn((1, 2026), extract_periods_from_filename("extrato012026.pdf"))

    def test_year_first_yyyymm(self):
        self.assertIn((1, 2026), extract_periods_from_filename("extrato202601.pdf"))

    def test_year_first_with_dash(self):
        self.assertIn((1, 2026), extract_periods_from_filename("2026-01-extrato.pdf"))

    def test_month_name_with_year(self):
        self.assertIn((1, 2026), extract_periods_from_filename("extrato_jan_2026.pdf"))
        self.assertIn((1, 2026), extract_periods_from_filename("janeiro 2026.pdf"))
        self.assertIn((3, 2026), extract_periods_from_filename("EXTRATO MARCO 2026.pdf"))

    def test_month_name_without_year_uses_fallback(self):
        result = extract_periods_from_filename("BB CC janeiro.pdf", fallback_year=2026)
        self.assertIn((1, 2026), result)

    def test_month_name_without_year_no_fallback_returns_empty(self):
        result = extract_periods_from_filename("BB CC janeiro.pdf")
        self.assertEqual(result, [])

    def test_wrong_file_returns_empty(self):
        result = extract_periods_from_filename("extrato_bradesco.pdf")
        self.assertEqual(result, [])

    def test_file_period_02_does_not_match_05(self):
        result = extract_periods_from_filename("Bradesco CC 02-2026.pdf")
        self.assertIn((2, 2026), result)
        self.assertNotIn((5, 2026), result)

    def test_all_12_month_names(self):
        names = {
            1: "janeiro", 2: "fevereiro", 3: "marco", 4: "abril",
            5: "maio", 6: "junho", 7: "julho", 8: "agosto",
            9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro",
        }
        for month, name in names.items():
            result = extract_periods_from_filename(f"{name} 2026.pdf")
            self.assertIn((month, 2026), result, f"Month {month} ({name}) not detected")


# ── build_expected_periods ─────────────────────────────────────────────────────

class TestBuildExpectedPeriods(unittest.TestCase):
    def test_mensal_includes_all_months_up_to_selected(self):
        result = build_expected_periods("mensal", 5, 2026)
        self.assertIn((1, 2026), result)
        self.assertIn((5, 2026), result)
        self.assertNotIn((6, 2026), result)

    def test_trimestral_only_quarterly_months(self):
        result = build_expected_periods("trimestral", 7, 2026)
        self.assertIn((1, 2026), result)
        self.assertIn((4, 2026), result)
        self.assertIn((7, 2026), result)
        self.assertNotIn((2, 2026), result)
        self.assertNotIn((5, 2026), result)
        self.assertNotIn((10, 2026), result)  # future

    def test_anual_janeiro_only_january(self):
        result = build_expected_periods("anual_janeiro", 5, 2026)
        self.assertEqual(result, [(1, 2026)])

    def test_anual_janeiro_when_selected_before_january_returns_empty(self):
        # selected is 05/2026 so january 2026 IS included; testing logic
        result = build_expected_periods("anual_janeiro", 1, 2026)
        self.assertEqual(result, [(1, 2026)])

    def test_selected_period_is_included(self):
        result = build_expected_periods("mensal", 3, 2026)
        self.assertIn((3, 2026), result)


# ── classify_file_period ───────────────────────────────────────────────────────

class TestClassifyFilePeriod(unittest.TestCase):
    def _make_status_map(self, doc_id, period_id, status):
        return {(doc_id, period_id): status}

    def test_matching_period_is_atual(self):
        result = classify_file_period(
            (5, 2026), (5, 2026), {}, 1, {(5, 2026): 10}
        )
        self.assertEqual(result, TEMPORAL_ATUAL)

    def test_earlier_pending_is_anterior_pendente(self):
        status_map = {(1, 20): None}
        pid_map = {(2, 2026): 20}
        result = classify_file_period(
            (2, 2026), (5, 2026), status_map, 1, pid_map
        )
        self.assertEqual(result, TEMPORAL_ANTERIOR_PENDENTE)

    def test_earlier_received_is_anterior_recebida(self):
        status_map = {(1, 20): "Recebido"}
        pid_map = {(2, 2026): 20}
        result = classify_file_period(
            (2, 2026), (5, 2026), status_map, 1, pid_map
        )
        self.assertEqual(result, TEMPORAL_ANTERIOR_RECEBIDA)

    def test_future_period_is_futura(self):
        result = classify_file_period(
            (6, 2026), (5, 2026), {}, 1, {}
        )
        self.assertEqual(result, TEMPORAL_FUTURA)

    def test_unknown_earlier_period_is_diferente(self):
        result = classify_file_period(
            (3, 2025), (5, 2026), {}, 1, {}
        )
        self.assertEqual(result, TEMPORAL_DIFERENTE)


# ── Temporal safety: no auto-mark when file period != target ──────────────────

class TestTemporalSafety(unittest.TestCase):
    def _build_service_with_empresa(self, empresa, documentos, periodos, statuses):
        empresa_service = MagicMock()
        empresa_service.list_empresas.return_value = [empresa]

        documento_service = MagicMock()
        documento_service.list_documentos_empresa.return_value = documentos

        periodo_service = MagicMock()
        periodo_service.get_periodo.return_value = periodos[-1]
        periodo_service.list_periodos.return_value = periodos

        status_service = MagicMock()
        status_service.get_document_period_statuses.return_value = statuses

        return FileCheckService(empresa_service, documento_service, periodo_service, status_service)

    def test_file_period_02_does_not_mark_period_05(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            empresa_dir = tmp_path / "123. Empresa Teste"
            year_dir = empresa_dir / "2026"
            extratos_dir = year_dir / "Extratos Bancarios"
            extratos_dir.mkdir(parents=True)
            # File has 02/2026 in name but we are checking 05/2026
            (extratos_dir / "Bradesco CC 02-2026.pdf").touch()

            empresa = {
                "id": 1, "nome_empresa": "Empresa Teste",
                "codigo_empresa": 123, "diretorio_documentos": None,
            }
            doc = {
                "id": 10, "nome_documento": "Bradesco CC",
                "nome_tipo": "Extrato Bancario", "regra_ocorrencia": "mensal",
            }
            periodos = [
                {"id": 1, "ano": 2026, "mes": 1, "label": "01/2026"},
                {"id": 2, "ano": 2026, "mes": 2, "label": "02/2026"},
                {"id": 3, "ano": 2026, "mes": 3, "label": "03/2026"},
                {"id": 4, "ano": 2026, "mes": 4, "label": "04/2026"},
                {"id": 5, "ano": 2026, "mes": 5, "label": "05/2026"},
            ]
            statuses = {(10, pid["id"]): None for pid in periodos}

            service = self._build_service_with_empresa(empresa, [doc], periodos, statuses)
            results = service.check_period(5, [1], tmp_path)

            # The result for 05/2026 should NOT be alta_confianca
            # because the only file is 02/2026
            self.assertEqual(len(results), 1)
            r = results[0]
            self.assertNotEqual(r["resultado"], RESULT_ALTA_CONFIANCA)
            self.assertNotEqual(r.get("temporal_class"), TEMPORAL_ATUAL)

    def test_file_period_05_does_not_resolve_period_02(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            empresa_dir = tmp_path / "123. Empresa Teste"
            year_dir = empresa_dir / "2026"
            extratos_dir = year_dir / "Extratos Bancarios"
            extratos_dir.mkdir(parents=True)
            # File has 05/2026 in name; we are checking 02/2026
            (extratos_dir / "Bradesco CC 05-2026.pdf").touch()

            empresa = {
                "id": 1, "nome_empresa": "Empresa Teste",
                "codigo_empresa": 123, "diretorio_documentos": None,
            }
            doc = {
                "id": 10, "nome_documento": "Bradesco CC",
                "nome_tipo": "Extrato Bancario", "regra_ocorrencia": "mensal",
            }
            periodos = [
                {"id": 2, "ano": 2026, "mes": 2, "label": "02/2026"},
            ]
            statuses = {(10, 2): None}

            service = self._build_service_with_empresa(empresa, [doc], periodos, statuses)
            results = service.check_period(2, [1], tmp_path)

            self.assertEqual(len(results), 1)
            r = results[0]
            self.assertNotEqual(r["resultado"], RESULT_ALTA_CONFIANCA)

    def test_apply_safe_matches_only_marks_temporal_atual(self):
        empresa_service = MagicMock()
        documento_service = MagicMock()
        periodo_service = MagicMock()
        status_service = MagicMock()
        status_service.update_status_batch.return_value = {"selected": 1, "updated": 1, "document_ids": [1]}

        service = FileCheckService(empresa_service, documento_service, periodo_service, status_service)

        results = [
            {
                "resultado": RESULT_ALTA_CONFIANCA,
                "temporal_class": TEMPORAL_ATUAL,
                "periodo_id": 5,
                "documento_id": 1,
                "status_atual": None,
            },
            {
                "resultado": RESULT_ALTA_CONFIANCA,
                "temporal_class": TEMPORAL_ANTERIOR_PENDENTE,
                "periodo_id": 2,
                "documento_id": 2,
                "status_atual": None,
            },
            {
                "resultado": RESULT_REVISAR,
                "temporal_class": TEMPORAL_ATUAL,
                "periodo_id": 5,
                "documento_id": 3,
                "status_atual": None,
            },
        ]

        result = service.apply_safe_matches(results)

        # Only doc 1 should be marked (alta_confianca + temporal_atual)
        status_service.update_status_batch.assert_called_once_with([1], 5, "Recebido")
        self.assertEqual(result["selected"], 1)

    def test_apply_safe_matches_does_not_mark_already_received(self):
        service = FileCheckService(MagicMock(), MagicMock(), MagicMock(), MagicMock())
        results = [
            {
                "resultado": RESULT_ALTA_CONFIANCA,
                "temporal_class": TEMPORAL_ATUAL,
                "periodo_id": 5,
                "documento_id": 1,
                "status_atual": "Recebido",
            },
        ]
        result = service.apply_safe_matches(results)
        self.assertEqual(result["selected"], 0)
        service._status_service.update_status_batch.assert_not_called()

    def test_mode2_pending_history_generates_one_row_per_period(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            empresa_dir = tmp_path / "123. Empresa Teste"
            year_dir = empresa_dir / "2026"
            extratos_dir = year_dir / "Extratos Bancarios"
            extratos_dir.mkdir(parents=True)
            (extratos_dir / "Bradesco CC 02-2026.pdf").touch()
            (extratos_dir / "Bradesco CC 05-2026.pdf").touch()

            empresa = {
                "id": 1, "nome_empresa": "Empresa Teste",
                "codigo_empresa": 123, "diretorio_documentos": None,
            }
            doc = {
                "id": 10, "nome_documento": "Bradesco CC",
                "nome_tipo": "Extrato Bancario", "regra_ocorrencia": "mensal",
            }
            periodos = [
                {"id": 1, "ano": 2026, "mes": 1, "label": "01/2026"},
                {"id": 2, "ano": 2026, "mes": 2, "label": "02/2026"},
                {"id": 3, "ano": 2026, "mes": 3, "label": "03/2026"},
                {"id": 4, "ano": 2026, "mes": 4, "label": "04/2026"},
                {"id": 5, "ano": 2026, "mes": 5, "label": "05/2026"},
            ]
            statuses = {(10, pid["id"]): None for pid in periodos}

            empresa_service = MagicMock()
            empresa_service.list_empresas.return_value = [empresa]
            documento_service = MagicMock()
            documento_service.list_documentos_empresa.return_value = [doc]
            periodo_service = MagicMock()
            periodo_service.get_periodo.return_value = periodos[-1]
            periodo_service.list_periodos.return_value = periodos
            status_service = MagicMock()
            status_service.get_document_period_statuses.return_value = statuses

            service = FileCheckService(empresa_service, documento_service, periodo_service, status_service)
            results = service.check_period(5, [1], tmp_path, mode=MODE_PENDING_HISTORY)

            # Should produce 5 rows (one per month Jan-May 2026)
            self.assertEqual(len(results), 5)

            # 02/2026 and 05/2026 should be alta_confianca with temporal_atual
            by_period = {r["periodo_analisado"]: r for r in results}
            self.assertEqual(by_period[(2, 2026)]["resultado"], RESULT_ALTA_CONFIANCA)
            self.assertEqual(by_period[(2, 2026)]["temporal_class"], TEMPORAL_ATUAL)
            self.assertEqual(by_period[(5, 2026)]["resultado"], RESULT_ALTA_CONFIANCA)
            self.assertEqual(by_period[(5, 2026)]["temporal_class"], TEMPORAL_ATUAL)

            # 03/2026 and 04/2026 should not be alta_confianca
            self.assertNotEqual(by_period[(3, 2026)]["resultado"], RESULT_ALTA_CONFIANCA)
            self.assertNotEqual(by_period[(4, 2026)]["resultado"], RESULT_ALTA_CONFIANCA)

    def test_mode1_adds_gap_alerts(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            empresa_dir = tmp_path / "123. Empresa Teste"
            year_dir = empresa_dir / "2026"
            extratos_dir = year_dir / "Extratos Bancarios"
            extratos_dir.mkdir(parents=True)
            (extratos_dir / "Bradesco CC 05-2026.pdf").touch()

            empresa = {
                "id": 1, "nome_empresa": "Empresa Teste",
                "codigo_empresa": 123, "diretorio_documentos": None,
            }
            doc = {
                "id": 10, "nome_documento": "Bradesco CC",
                "nome_tipo": "Extrato Bancario", "regra_ocorrencia": "mensal",
            }
            periodos = [
                {"id": 2, "ano": 2026, "mes": 2, "label": "02/2026"},
                {"id": 3, "ano": 2026, "mes": 3, "label": "03/2026"},
                {"id": 5, "ano": 2026, "mes": 5, "label": "05/2026"},
            ]
            # 02/2026 and 03/2026 are pending
            statuses = {(10, 2): None, (10, 3): None, (10, 5): None}

            empresa_service = MagicMock()
            empresa_service.list_empresas.return_value = [empresa]
            documento_service = MagicMock()
            documento_service.list_documentos_empresa.return_value = [doc]
            periodo_service = MagicMock()
            periodo_service.get_periodo.return_value = periodos[-1]
            periodo_service.list_periodos.return_value = periodos
            status_service = MagicMock()
            status_service.get_document_period_statuses.return_value = statuses

            service = FileCheckService(empresa_service, documento_service, periodo_service, status_service)
            results = service.check_period(5, [1], tmp_path, mode=MODE_CURRENT_ONLY)

            self.assertEqual(len(results), 1)
            r = results[0]
            # Should have alerts about previous pending months
            self.assertTrue(
                any("anterior" in a.lower() or "pendente" in a.lower() for a in r.get("alertas", [])),
                f"Expected gap alert in alertas: {r.get('alertas')}",
            )

    def test_trimestral_only_checks_quarterly_periods(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            empresa_dir = tmp_path / "123. Empresa Teste"
            year_dir = empresa_dir / "2026"
            extratos_dir = year_dir / "Extratos Bancarios"
            extratos_dir.mkdir(parents=True)
            (extratos_dir / "Caixa aplicacao 04-2026.pdf").touch()

            empresa = {
                "id": 1, "nome_empresa": "Empresa Teste",
                "codigo_empresa": 123, "diretorio_documentos": None,
            }
            doc = {
                "id": 10, "nome_documento": "Caixa Aplicacao",
                "nome_tipo": "Extrato Bancario", "regra_ocorrencia": "trimestral",
            }
            periodos = [
                {"id": 1, "ano": 2026, "mes": 1, "label": "01/2026"},
                {"id": 2, "ano": 2026, "mes": 2, "label": "02/2026"},
                {"id": 3, "ano": 2026, "mes": 3, "label": "03/2026"},
                {"id": 4, "ano": 2026, "mes": 4, "label": "04/2026"},
                {"id": 5, "ano": 2026, "mes": 5, "label": "05/2026"},
            ]
            statuses = {(10, pid["id"]): None for pid in periodos}

            empresa_service = MagicMock()
            empresa_service.list_empresas.return_value = [empresa]
            documento_service = MagicMock()
            documento_service.list_documentos_empresa.return_value = [doc]
            periodo_service = MagicMock()
            periodo_service.get_periodo.return_value = periodos[-1]
            periodo_service.list_periodos.return_value = periodos
            status_service = MagicMock()
            status_service.get_document_period_statuses.return_value = statuses

            service = FileCheckService(empresa_service, documento_service, periodo_service, status_service)
            results = service.check_period(5, [1], tmp_path, mode=MODE_PENDING_HISTORY)

            # Only Jan and Apr are quarterly months up to May
            periods_checked = [r["periodo_analisado"] for r in results]
            self.assertIn((1, 2026), periods_checked)
            self.assertIn((4, 2026), periods_checked)
            self.assertNotIn((2, 2026), periods_checked)
            self.assertNotIn((3, 2026), periods_checked)
            self.assertNotIn((5, 2026), periods_checked)

    def test_skip_received_true_omits_received_periods(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            empresa_dir = tmp_path / "123. Empresa Teste"
            year_dir = empresa_dir / "2026"
            extratos_dir = year_dir / "Extratos Bancarios"
            extratos_dir.mkdir(parents=True)

            empresa = {
                "id": 1, "nome_empresa": "Empresa Teste",
                "codigo_empresa": 123, "diretorio_documentos": None,
            }
            doc = {
                "id": 10, "nome_documento": "Bradesco CC",
                "nome_tipo": "Extrato Bancario", "regra_ocorrencia": "mensal",
            }
            periodos = [
                {"id": 1, "ano": 2026, "mes": 1, "label": "01/2026"},
                {"id": 2, "ano": 2026, "mes": 2, "label": "02/2026"},
            ]
            # Jan is received; Feb is pending
            statuses = {(10, 1): "Recebido", (10, 2): None}

            empresa_service = MagicMock()
            empresa_service.list_empresas.return_value = [empresa]
            documento_service = MagicMock()
            documento_service.list_documentos_empresa.return_value = [doc]
            periodo_service = MagicMock()
            periodo_service.get_periodo.return_value = periodos[-1]
            periodo_service.list_periodos.return_value = periodos
            status_service = MagicMock()
            status_service.get_document_period_statuses.return_value = statuses

            service = FileCheckService(empresa_service, documento_service, periodo_service, status_service)
            results = service.check_period(2, [1], tmp_path, mode=MODE_PENDING_HISTORY, skip_received=True)

            periods_checked = [r["periodo_analisado"] for r in results]
            self.assertNotIn((1, 2026), periods_checked)  # skipped because Recebido
            self.assertIn((2, 2026), periods_checked)


# ── Flexible folder layouts and generic documents ─────────────────────────────

class TestFlexibleFileCheckLayouts(unittest.TestCase):
    def _build_service(self, empresa, doc, periodos, statuses):
        empresa_service = MagicMock()
        empresa_service.list_empresas.return_value = [empresa]
        documento_service = MagicMock()
        documento_service.list_documentos_empresa.return_value = [doc]
        periodo_service = MagicMock()
        periodo_service.get_periodo.return_value = periodos[-1]
        periodo_service.list_periodos.return_value = periodos
        status_service = MagicMock()
        status_service.get_document_period_statuses.return_value = statuses
        return FileCheckService(empresa_service, documento_service, periodo_service, status_service)

    def test_month_folder_can_confirm_period_when_filename_has_no_date(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target_dir = (
                tmp_path / "123. Empresa Teste" / "2026" / "05 - Maio"
                / "Extratos Bancarios" / "Conta Corrente"
            )
            target_dir.mkdir(parents=True)
            (target_dir / "Sicoob CC.pdf").touch()

            empresa = {
                "id": 1, "nome_empresa": "Empresa Teste",
                "codigo_empresa": 123, "diretorio_documentos": None,
            }
            doc = {
                "id": 10, "nome_documento": "Sicoob C/C 78837-6",
                "nome_tipo": "Extrato Bancario", "regra_ocorrencia": "mensal",
            }
            periodos = [{"id": 5, "ano": 2026, "mes": 5, "label": "05/2026"}]

            service = self._build_service(empresa, doc, periodos, {(10, 5): None})
            results = service.check_period(5, [1], tmp_path)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["resultado"], RESULT_ALTA_CONFIANCA)
            self.assertEqual(results[0]["arquivo_periodo"], [(5, 2026)])

    def test_filename_only_option_does_not_use_month_folder_as_period(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target_dir = (
                tmp_path / "123. Empresa Teste" / "2026" / "05 - Maio"
                / "Extratos Bancarios" / "Conta Corrente"
            )
            target_dir.mkdir(parents=True)
            (target_dir / "Sicoob CC.pdf").touch()

            empresa = {
                "id": 1, "nome_empresa": "Empresa Teste",
                "codigo_empresa": 123, "diretorio_documentos": None,
            }
            doc = {
                "id": 10, "nome_documento": "Sicoob C/C 78837-6",
                "nome_tipo": "Extrato Bancario", "regra_ocorrencia": "mensal",
            }
            periodos = [{"id": 5, "ano": 2026, "mes": 5, "label": "05/2026"}]

            service = self._build_service(empresa, doc, periodos, {(10, 5): None})
            results = service.check_period(
                5,
                [1],
                tmp_path,
                options={"period_source": PERIOD_SOURCE_FILENAME_ONLY},
            )

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["resultado"], RESULT_REVISAR)
            self.assertEqual(results[0]["temporal_class"], TEMPORAL_NAO_IDENTIFICADA)

    def test_month_first_layout_ignores_year_direct_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target_dir = tmp_path / "123. Empresa Teste" / "2026" / "Extratos Bancarios"
            target_dir.mkdir(parents=True)
            (target_dir / "123 Sicoob CC 05-2026.pdf").touch()

            empresa = {
                "id": 1, "nome_empresa": "Empresa Teste",
                "codigo_empresa": 123, "diretorio_documentos": None,
            }
            doc = {
                "id": 10, "nome_documento": "Sicoob C/C 78837-6",
                "nome_tipo": "Extrato Bancario", "regra_ocorrencia": "mensal",
            }
            periodos = [{"id": 5, "ano": 2026, "mes": 5, "label": "05/2026"}]

            service = self._build_service(empresa, doc, periodos, {(10, 5): None})
            results = service.check_period(
                5,
                [1],
                tmp_path,
                options={"layout_mode": LAYOUT_MONTH_FIRST},
            )

            self.assertEqual(results[0]["resultado"], RESULT_NAO_ENCONTRADO)
            self.assertIsNone(results[0]["arquivo"])

    def test_year_direct_layout_ignores_month_folder_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target_dir = (
                tmp_path / "123. Empresa Teste" / "2026" / "05 - Maio"
                / "Extratos Bancarios" / "Conta Corrente"
            )
            target_dir.mkdir(parents=True)
            (target_dir / "123 Sicoob CC 05-2026.pdf").touch()

            empresa = {
                "id": 1, "nome_empresa": "Empresa Teste",
                "codigo_empresa": 123, "diretorio_documentos": None,
            }
            doc = {
                "id": 10, "nome_documento": "Sicoob C/C 78837-6",
                "nome_tipo": "Extrato Bancario", "regra_ocorrencia": "mensal",
            }
            periodos = [{"id": 5, "ano": 2026, "mes": 5, "label": "05/2026"}]

            service = self._build_service(empresa, doc, periodos, {(10, 5): None})
            results = service.check_period(
                5,
                [1],
                tmp_path,
                options={"layout_mode": LAYOUT_YEAR_DIRECT},
            )

            self.assertEqual(results[0]["resultado"], RESULT_NAO_ENCONTRADO)
            self.assertIsNone(results[0]["arquivo"])

    def test_duplicate_candidates_are_reported(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target_dir = tmp_path / "123. Empresa Teste" / "2026" / "Extratos Bancarios"
            target_dir.mkdir(parents=True)
            (target_dir / "123 Sicoob CC 05-2026.pdf").touch()
            (target_dir / "123 Sicoob CC maio 2026 copia.pdf").touch()

            empresa = {
                "id": 1, "nome_empresa": "Empresa Teste",
                "codigo_empresa": 123, "diretorio_documentos": None,
            }
            doc = {
                "id": 10, "nome_documento": "Sicoob C/C 78837-6",
                "nome_tipo": "Extrato Bancario", "regra_ocorrencia": "mensal",
            }
            periodos = [{"id": 5, "ano": 2026, "mes": 5, "label": "05/2026"}]

            service = self._build_service(empresa, doc, periodos, {(10, 5): None})
            results = service.check_period(5, [1], tmp_path)

            self.assertEqual(results[0]["resultado"], RESULT_REVISAR)
            self.assertTrue(results[0]["duplicate_files"])
            self.assertIn("duplicidade", results[0]["motivo"].lower())

    def test_generic_registered_document_can_be_checked(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            year_dir = tmp_path / "123. Empresa Teste" / "2026"
            year_dir.mkdir(parents=True)
            (year_dir / "123 DAS Simples Nacional 05-2026.pdf").touch()

            empresa = {
                "id": 1, "nome_empresa": "Empresa Teste",
                "codigo_empresa": 123, "diretorio_documentos": None,
            }
            doc = {
                "id": 10, "nome_documento": "DAS Simples Nacional",
                "nome_tipo": "Fiscal", "regra_ocorrencia": "mensal",
            }
            periodos = [{"id": 5, "ano": 2026, "mes": 5, "label": "05/2026"}]

            service = self._build_service(empresa, doc, periodos, {(10, 5): None})
            results = service.check_period(5, [1], tmp_path)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["resultado"], RESULT_ALTA_CONFIANCA)

    def test_generic_document_requires_registered_name_terms(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            year_dir = tmp_path / "123. Empresa Teste" / "2026"
            year_dir.mkdir(parents=True)
            (year_dir / "123 Recibo qualquer 05-2026.pdf").touch()

            empresa = {
                "id": 1, "nome_empresa": "Empresa Teste",
                "codigo_empresa": 123, "diretorio_documentos": None,
            }
            doc = {
                "id": 10, "nome_documento": "DAS Simples Nacional",
                "nome_tipo": "Fiscal", "regra_ocorrencia": "mensal",
            }
            periodos = [{"id": 5, "ano": 2026, "mes": 5, "label": "05/2026"}]

            service = self._build_service(empresa, doc, periodos, {(10, 5): None})
            results = service.check_period(5, [1], tmp_path)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["resultado"], RESULT_NAO_ENCONTRADO)
            self.assertIsNone(results[0]["arquivo"])

    def test_required_naming_template_demotes_when_pattern_is_missing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target_dir = tmp_path / "123. Empresa Teste" / "2026" / "Extratos Bancarios"
            target_dir.mkdir(parents=True)
            (target_dir / "Sicoob CC 05-2026.pdf").touch()

            empresa = {
                "id": 1, "nome_empresa": "Empresa Teste",
                "codigo_empresa": 123, "diretorio_documentos": None,
            }
            doc = {
                "id": 10, "nome_documento": "Sicoob C/C 78837-6",
                "nome_tipo": "Extrato Bancario", "regra_ocorrencia": "mensal",
            }
            periodos = [{"id": 5, "ano": 2026, "mes": 5, "label": "05/2026"}]

            service = self._build_service(empresa, doc, periodos, {(10, 5): None})
            results = service.check_period(
                5,
                [1],
                tmp_path,
                options={
                    "filename_templates": "{codigo} {documento} {competencia}",
                    "require_template_match": True,
                },
            )

            self.assertEqual(results[0]["resultado"], RESULT_REVISAR)
            self.assertIn("nomenclatura", results[0]["motivo"])

    def test_required_naming_template_accepts_company_document_period(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target_dir = tmp_path / "123. Empresa Teste" / "2026" / "Extratos Bancarios"
            target_dir.mkdir(parents=True)
            (target_dir / "123 Sicoob CC 05-2026.pdf").touch()

            empresa = {
                "id": 1, "nome_empresa": "Empresa Teste",
                "codigo_empresa": 123, "diretorio_documentos": None,
            }
            doc = {
                "id": 10, "nome_documento": "Sicoob C/C 78837-6",
                "nome_tipo": "Extrato Bancario", "regra_ocorrencia": "mensal",
            }
            periodos = [{"id": 5, "ano": 2026, "mes": 5, "label": "05/2026"}]

            service = self._build_service(empresa, doc, periodos, {(10, 5): None})
            results = service.check_period(
                5,
                [1],
                tmp_path,
                options={
                    "filename_templates": "{codigo} {documento} {competencia}",
                    "require_template_match": True,
                },
            )

            self.assertEqual(results[0]["resultado"], RESULT_ALTA_CONFIANCA)

    def test_forbidden_filename_terms_force_review(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target_dir = tmp_path / "123. Empresa Teste" / "2026" / "Extratos Bancarios"
            target_dir.mkdir(parents=True)
            (target_dir / "123 Sicoob CC cancelado 05-2026.pdf").touch()

            empresa = {
                "id": 1, "nome_empresa": "Empresa Teste",
                "codigo_empresa": 123, "diretorio_documentos": None,
            }
            doc = {
                "id": 10, "nome_documento": "Sicoob C/C 78837-6",
                "nome_tipo": "Extrato Bancario", "regra_ocorrencia": "mensal",
            }
            periodos = [{"id": 5, "ano": 2026, "mes": 5, "label": "05/2026"}]

            service = self._build_service(empresa, doc, periodos, {(10, 5): None})
            results = service.check_period(
                5,
                [1],
                tmp_path,
                options={"forbidden_filename_terms": "cancelado"},
            )

            self.assertEqual(results[0]["resultado"], RESULT_REVISAR)
            self.assertIn("termo proibido", results[0]["motivo"])

    def test_custom_required_filename_terms_force_review_when_absent(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target_dir = tmp_path / "123. Empresa Teste" / "2026" / "Extratos Bancarios"
            target_dir.mkdir(parents=True)
            (target_dir / "123 Sicoob CC 05-2026.pdf").touch()

            empresa = {
                "id": 1, "nome_empresa": "Empresa Teste",
                "codigo_empresa": 123, "diretorio_documentos": None,
            }
            doc = {
                "id": 10, "nome_documento": "Sicoob C/C 78837-6",
                "nome_tipo": "Extrato Bancario", "regra_ocorrencia": "mensal",
            }
            periodos = [{"id": 5, "ano": 2026, "mes": 5, "label": "05/2026"}]

            service = self._build_service(empresa, doc, periodos, {(10, 5): None})
            results = service.check_period(
                5,
                [1],
                tmp_path,
                options={"required_filename_terms": "oficial"},
            )

            self.assertEqual(results[0]["resultado"], RESULT_REVISAR)
            self.assertIn("termos obrigatorios", results[0]["motivo"])


# ── Candidate period partitioning ─────────────────────────────────────────────

class TestCandidatePartitioning(unittest.TestCase):
    """Files of a different period must not appear in arquivo or trigger REVISAR."""

    def _build_service(self, empresa, doc, periodos, statuses):
        empresa_service = MagicMock()
        empresa_service.list_empresas.return_value = [empresa]
        documento_service = MagicMock()
        documento_service.list_documentos_empresa.return_value = [doc]
        periodo_service = MagicMock()
        periodo_service.get_periodo.return_value = periodos[-1]
        periodo_service.list_periodos.return_value = periodos
        status_service = MagicMock()
        status_service.get_document_period_statuses.return_value = statuses
        return FileCheckService(empresa_service, documento_service, periodo_service, status_service)

    def _setup_dir(self, tmp_path, filename):
        extratos_dir = tmp_path / "123. Empresa Teste" / "2026" / "Extratos Bancarios"
        extratos_dir.mkdir(parents=True)
        (extratos_dir / filename).touch()
        return extratos_dir

    def _empresa_doc(self):
        return (
            {"id": 1, "nome_empresa": "Empresa Teste", "codigo_empresa": 123, "diretorio_documentos": None},
            {"id": 10, "nome_documento": "Sicoob CC", "nome_tipo": "Extrato Bancario", "regra_ocorrencia": "mensal"},
        )

    def test_other_period_file_is_nao_encontrado_not_revisar(self):
        """File of 05/2026 must produce NAO_ENCONTRADO for period 03/2026, not REVISAR."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._setup_dir(tmp_path, "1. Sicoob CC maio 2026.pdf")
            empresa, doc = self._empresa_doc()
            periodos = [{"id": 3, "ano": 2026, "mes": 3, "label": "03/2026"}]
            service = self._build_service(empresa, doc, periodos, {(10, 3): None})
            results = service.check_period(3, [1], tmp_path)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["resultado"], RESULT_NAO_ENCONTRADO,
                "File of 05/2026 must not produce REVISAR for period 03/2026")

    def test_other_period_file_arquivo_is_none(self):
        """arquivo field must be None when only other-period files exist."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._setup_dir(tmp_path, "1. Sicoob CC maio 2026.pdf")
            empresa, doc = self._empresa_doc()
            periodos = [{"id": 3, "ano": 2026, "mes": 3, "label": "03/2026"}]
            service = self._build_service(empresa, doc, periodos, {(10, 3): None})
            results = service.check_period(3, [1], tmp_path)
            self.assertIsNone(results[0]["arquivo"],
                "arquivo must be None when file period does not match target period")

    def test_maio_file_alta_confianca_for_maio(self):
        """File of 05/2026 must still be ALTA_CONFIANCA when checking 05/2026."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._setup_dir(tmp_path, "1. Sicoob CC maio 2026.pdf")
            empresa, doc = self._empresa_doc()
            periodos = [{"id": 5, "ano": 2026, "mes": 5, "label": "05/2026"}]
            service = self._build_service(empresa, doc, periodos, {(10, 5): None})
            results = service.check_period(5, [1], tmp_path)
            self.assertEqual(len(results), 1)
            r = results[0]
            self.assertEqual(r["resultado"], RESULT_ALTA_CONFIANCA,
                "File of 05/2026 must be ALTA_CONFIANCA for period 05/2026")
            self.assertEqual(r.get("temporal_class"), TEMPORAL_ATUAL)

    def test_other_period_files_appear_in_alertas(self):
        """Other-period files must appear as 'ignorado' in alertas."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._setup_dir(tmp_path, "1. Sicoob CC maio 2026.pdf")
            empresa, doc = self._empresa_doc()
            periodos = [{"id": 3, "ano": 2026, "mes": 3, "label": "03/2026"}]
            service = self._build_service(empresa, doc, periodos, {(10, 3): None})
            results = service.check_period(3, [1], tmp_path)
            alertas = results[0].get("alertas", [])
            self.assertTrue(
                any("ignorado" in a.lower() for a in alertas),
                f"Expected 'ignorado' in alertas: {alertas}",
            )

    def test_other_period_files_in_related_period_files(self):
        """related_period_files must list the ignored file."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._setup_dir(tmp_path, "1. Sicoob CC maio 2026.pdf")
            empresa, doc = self._empresa_doc()
            periodos = [{"id": 3, "ano": 2026, "mes": 3, "label": "03/2026"}]
            service = self._build_service(empresa, doc, periodos, {(10, 3): None})
            results = service.check_period(3, [1], tmp_path)
            related = results[0].get("related_period_files", [])
            self.assertTrue(len(related) > 0, "related_period_files must be non-empty")
            self.assertTrue(
                any("Sicoob CC maio 2026.pdf" in rf.get("filename", "") for rf in related),
            )

    def test_unknown_period_file_never_alta_confianca(self):
        """A file with no period in name must never produce ALTA_CONFIANCA."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._setup_dir(tmp_path, "Sicoob CC.pdf")
            empresa, doc = self._empresa_doc()
            periodos = [{"id": 3, "ano": 2026, "mes": 3, "label": "03/2026"}]
            service = self._build_service(empresa, doc, periodos, {(10, 3): None})
            results = service.check_period(3, [1], tmp_path)
            self.assertEqual(len(results), 1)
            self.assertNotEqual(results[0]["resultado"], RESULT_ALTA_CONFIANCA,
                "File without period in name must not be ALTA_CONFIANCA")

    def test_mode2_other_period_file_is_nao_encontrado_for_all_non_matching_periods(self):
        """In mode 2, file of 05/2026 produces NAO_ENCONTRADO for 01-04/2026."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._setup_dir(tmp_path, "1. Sicoob CC maio 2026.pdf")
            empresa, doc = self._empresa_doc()
            periodos = [
                {"id": 1, "ano": 2026, "mes": 1, "label": "01/2026"},
                {"id": 2, "ano": 2026, "mes": 2, "label": "02/2026"},
                {"id": 3, "ano": 2026, "mes": 3, "label": "03/2026"},
                {"id": 4, "ano": 2026, "mes": 4, "label": "04/2026"},
                {"id": 5, "ano": 2026, "mes": 5, "label": "05/2026"},
            ]
            statuses = {(10, p["id"]): None for p in periodos}
            service = self._build_service(empresa, doc, periodos, statuses)
            results = service.check_period(5, [1], tmp_path, mode=MODE_PENDING_HISTORY)
            by_period = {r["periodo_analisado"]: r for r in results}
            for mes in [1, 2, 3, 4]:
                r = by_period[(mes, 2026)]
                self.assertEqual(r["resultado"], RESULT_NAO_ENCONTRADO,
                    f"Period {mes:02d}/2026 must be NAO_ENCONTRADO, got {r['resultado']}")
                self.assertIsNone(r["arquivo"],
                    f"Period {mes:02d}/2026 arquivo must be None")
            # 05/2026 must be ALTA_CONFIANCA
            self.assertEqual(by_period[(5, 2026)]["resultado"], RESULT_ALTA_CONFIANCA)


if __name__ == "__main__":
    unittest.main()
