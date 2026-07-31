from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from documentos_empresa_app.services.document_extraction_service import DocumentExtractionError
from documentos_empresa_app.services.document_organizer_service import (
    DocumentOrganizerService,
    OrganizeNeedsInput,
    OrganizeProposal,
)
from documentos_empresa_app.services.llm_types import CompetenceSuggestion, LLMCompetenceSuggestionError
from documentos_empresa_app.utils.common import ValidationError


@dataclass(slots=True)
class BatchOrganizeRow:
    pendente_id: int
    nome_arquivo: str
    empresa_id: int
    empresa_nome: str
    suggestion: CompetenceSuggestion | None
    proposal: OrganizeProposal | None
    needs_input_message: str | None
    error: str | None


class BatchOrganizeService:
    def __init__(
        self,
        document_agent_service,
        document_organizer_service: DocumentOrganizerService,
        documento_service,
        competence_suggestion_client=None,
    ) -> None:
        self.document_agent_service = document_agent_service
        self.document_organizer_service = document_organizer_service
        self.documento_service = documento_service
        self.competence_suggestion_client = competence_suggestion_client

    def eligible_pendentes(self, pendentes: list[dict]) -> list[dict]:
        """So entram na tela de lote pendentes com empresa ja conhecida (sugerida pela
        classificacao ou ja selecionada manualmente) - nunca tenta adivinhar empresa aqui."""
        return [pendente for pendente in pendentes if pendente.get("empresa_sugerida_id")]

    def build_rows(self, pendentes: list[dict], *, empresas_root_dir: str | None) -> list[BatchOrganizeRow]:
        return [
            self._build_row(pendente, empresas_root_dir)
            for pendente in self.eligible_pendentes(pendentes)
        ]

    def execute_row(self, row: BatchOrganizeRow) -> Path:
        if row.proposal is None:
            raise ValidationError("Este item ainda nao tem uma proposta valida para confirmar.")
        return self.document_organizer_service.execute(row.pendente_id, row.empresa_id, row.proposal)

    def _build_row(self, pendente: dict, empresas_root_dir: str | None) -> BatchOrganizeRow:
        empresa_id = pendente["empresa_sugerida_id"]
        empresa_nome = pendente.get("empresa_sugerida_nome") or "-"

        if self.competence_suggestion_client is None:
            return self._row(
                pendente, empresa_id, empresa_nome, error="Sugestao de competencia por IA nao configurada."
            )

        try:
            text = self.document_agent_service.extraction_service.extract_text(
                Path(pendente["caminho_arquivo_original"])
            )
        except DocumentExtractionError as exc:
            return self._row(pendente, empresa_id, empresa_nome, error=f"Falha ao ler o documento: {exc}")

        registered_documents = self.documento_service.list_documentos_empresa(empresa_id)

        try:
            suggestion = self.competence_suggestion_client.suggest(text, registered_documents)
        except LLMCompetenceSuggestionError as exc:
            return self._row(pendente, empresa_id, empresa_nome, error=f"Falha na sugestao de competencia: {exc}")

        documento_empresa = next(
            (doc for doc in registered_documents if doc["id"] == suggestion.documento_empresa_id), None
        )
        if documento_empresa is None:
            return self._row(
                pendente,
                empresa_id,
                empresa_nome,
                suggestion=suggestion,
                needs_input_message=(
                    "A IA nao reconheceu nenhum documento cadastrado desta empresa para este arquivo. "
                    "Revise manualmente ou cadastre o documento antes de organizar."
                ),
            )

        try:
            proposal = self.document_organizer_service.propose(
                pendente["id"],
                empresa_id,
                suggestion.mes,
                suggestion.ano,
                banco=suggestion.banco,
                tipo_conta=suggestion.tipo_conta,
                empresas_root_dir=empresas_root_dir,
                documento_empresa=documento_empresa,
            )
        except ValidationError as exc:
            return self._row(pendente, empresa_id, empresa_nome, suggestion=suggestion, error=str(exc))

        if isinstance(proposal, OrganizeNeedsInput):
            return self._row(
                pendente, empresa_id, empresa_nome, suggestion=suggestion, needs_input_message=proposal.message
            )
        return self._row(pendente, empresa_id, empresa_nome, suggestion=suggestion, proposal=proposal)

    def _row(
        self,
        pendente: dict,
        empresa_id: int,
        empresa_nome: str,
        *,
        suggestion: CompetenceSuggestion | None = None,
        proposal: OrganizeProposal | None = None,
        needs_input_message: str | None = None,
        error: str | None = None,
    ) -> BatchOrganizeRow:
        return BatchOrganizeRow(
            pendente_id=pendente["id"],
            nome_arquivo=pendente["nome_arquivo"],
            empresa_id=empresa_id,
            empresa_nome=empresa_nome,
            suggestion=suggestion,
            proposal=proposal,
            needs_input_message=needs_input_message,
            error=error,
        )
