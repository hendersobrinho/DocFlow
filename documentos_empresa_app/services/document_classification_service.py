from __future__ import annotations

from dataclasses import dataclass
import re

from documentos_empresa_app.services.llm_types import LLMClassificationError

CNPJ_REGEX = re.compile(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}")


@dataclass(slots=True)
class ClassificationResult:
    matched_empresa: dict | None
    cnpj_extraido: str | None
    origem: str
    tipo_documento_sugerido: str | None
    confianca: float | None
    empresa_sugerida_nome: str | None
    motivo: str | None


class DocumentClassificationService:
    def __init__(self, llm_client=None, confidence_threshold: float = 0.75) -> None:
        self.llm_client = llm_client
        self.confidence_threshold = confidence_threshold

    def classify(
        self,
        text: str,
        empresa_cnpj_index: dict[str, dict],
        known_company_names: list[str],
    ) -> ClassificationResult:
        candidates = self.extract_cnpj_candidates(text)
        for candidate in candidates:
            empresa = empresa_cnpj_index.get(candidate)
            if empresa:
                return ClassificationResult(
                    matched_empresa=empresa,
                    cnpj_extraido=candidate,
                    origem="regex_cnpj",
                    tipo_documento_sugerido=None,
                    confianca=1.0,
                    empresa_sugerida_nome=empresa.get("nome_empresa"),
                    motivo=None,
                )

        cnpj_extraido = candidates[0] if candidates else None

        if not self.llm_client:
            return ClassificationResult(
                matched_empresa=None,
                cnpj_extraido=cnpj_extraido,
                origem="nenhuma",
                tipo_documento_sugerido=None,
                confianca=None,
                empresa_sugerida_nome=None,
                motivo="Classificacao por IA nao configurada.",
            )

        try:
            suggestion = self.llm_client.suggest(text, known_company_names)
        except LLMClassificationError as exc:
            return ClassificationResult(
                matched_empresa=None,
                cnpj_extraido=cnpj_extraido,
                origem="nenhuma",
                tipo_documento_sugerido=None,
                confianca=None,
                empresa_sugerida_nome=None,
                motivo=f"Falha na classificacao por IA: {exc}",
            )

        suggested_cnpj = self.normalize_cnpj(suggestion.suggested_cnpj) if suggestion.suggested_cnpj else None
        matched_empresa = empresa_cnpj_index.get(suggested_cnpj) if suggested_cnpj else None

        if matched_empresa and suggestion.confidence >= self.confidence_threshold:
            return ClassificationResult(
                matched_empresa=matched_empresa,
                cnpj_extraido=suggested_cnpj or cnpj_extraido,
                origem="llm",
                tipo_documento_sugerido=suggestion.suggested_document_type,
                confianca=suggestion.confidence,
                empresa_sugerida_nome=matched_empresa.get("nome_empresa"),
                motivo=None,
            )

        motivo = (
            "Sugestao da IA nao corresponde a uma empresa cadastrada."
            if suggestion.suggested_company_name and not matched_empresa
            else "Confianca da sugestao da IA abaixo do minimo exigido."
            if matched_empresa
            else "IA nao conseguiu identificar a empresa do documento."
        )
        return ClassificationResult(
            matched_empresa=None,
            cnpj_extraido=suggested_cnpj or cnpj_extraido,
            origem="llm",
            tipo_documento_sugerido=suggestion.suggested_document_type,
            confianca=suggestion.confidence,
            empresa_sugerida_nome=suggestion.suggested_company_name,
            motivo=motivo,
        )

    @staticmethod
    def extract_cnpj_candidates(text: str) -> list[str]:
        candidates: list[str] = []
        seen: set[str] = set()
        for match in CNPJ_REGEX.finditer(text or ""):
            normalized = DocumentClassificationService.normalize_cnpj(match.group(0))
            if normalized and normalized not in seen:
                seen.add(normalized)
                candidates.append(normalized)
        return candidates

    @staticmethod
    def normalize_cnpj(raw: str) -> str | None:
        digits = re.sub(r"\D", "", str(raw or ""))
        if len(digits) != 14:
            return None
        return digits
