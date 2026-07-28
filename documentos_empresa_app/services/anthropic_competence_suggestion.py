from __future__ import annotations

from documentos_empresa_app.services.llm_types import (
    CompetenceSuggestion,
    LLMCompetenceSuggestionError,
    ORGANIZE_TOOL_DESCRIPTION,
    ORGANIZE_TOOL_NAME,
    ORGANIZE_TOOL_PARAMETERS,
    REQUEST_TIMEOUT_SECONDS,
    build_competence_suggestion_system_prompt,
    clamp_suggestion_text,
    prepare_document_text_for_llm,
    wrap_untrusted_document_text,
)

DEFAULT_MODEL = "claude-haiku-4-5"

COMPETENCE_SUGGESTION_TOOL = {
    "name": ORGANIZE_TOOL_NAME,
    "description": ORGANIZE_TOOL_DESCRIPTION,
    "input_schema": ORGANIZE_TOOL_PARAMETERS,
}


class AnthropicCompetenceSuggestionClient:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, custom_instructions: str | None = None) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS)
        self._model = model
        self._custom_instructions = custom_instructions
        self._anthropic = anthropic

    def suggest(self, document_text: str) -> CompetenceSuggestion:
        truncated_text = prepare_document_text_for_llm(document_text)
        message_content = wrap_untrusted_document_text(truncated_text)
        system_prompt = build_competence_suggestion_system_prompt(self._custom_instructions)

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=300,
                system=system_prompt,
                messages=[{"role": "user", "content": message_content}],
                tools=[COMPETENCE_SUGGESTION_TOOL],
                tool_choice={"type": "tool", "name": ORGANIZE_TOOL_NAME},
            )
        except self._anthropic.APIError as exc:
            raise LLMCompetenceSuggestionError("Falha ao consultar o modelo de sugestao de competencia.") from exc

        tool_use_block = next(
            (block for block in response.content if getattr(block, "type", None) == "tool_use"),
            None,
        )
        if tool_use_block is None:
            raise LLMCompetenceSuggestionError("O modelo nao retornou uma sugestao estruturada.")

        payload = tool_use_block.input
        if not isinstance(payload, dict):
            raise LLMCompetenceSuggestionError("O modelo retornou uma sugestao em formato invalido.")

        return self._parse_payload(payload)

    def _parse_payload(self, payload: dict) -> CompetenceSuggestion:
        try:
            mes = int(payload.get("mes"))
            ano = int(payload.get("ano"))
        except (TypeError, ValueError) as exc:
            raise LLMCompetenceSuggestionError("O modelo retornou mes/ano em formato invalido.") from exc

        return CompetenceSuggestion(
            mes=mes,
            ano=ano,
            banco=clamp_suggestion_text(payload.get("banco")),
            tipo_conta=clamp_suggestion_text(payload.get("tipo_conta")),
        )
