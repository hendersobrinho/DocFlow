from __future__ import annotations

from documentos_empresa_app.services.llm_types import (
    LLMClassificationError,
    LLMSuggestion,
    REQUEST_TIMEOUT_SECONDS,
    SUGGESTION_TOOL_DESCRIPTION,
    SUGGESTION_TOOL_NAME,
    SUGGESTION_TOOL_PARAMETERS,
    build_classification_system_prompt,
    clamp_suggestion_text,
    prepare_document_text_for_llm,
    wrap_untrusted_document_text,
)

DEFAULT_MODEL = "claude-haiku-4-5"

SUGGESTION_TOOL = {
    "name": SUGGESTION_TOOL_NAME,
    "description": SUGGESTION_TOOL_DESCRIPTION,
    "input_schema": SUGGESTION_TOOL_PARAMETERS,
}


class AnthropicDocumentClassifierClient:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, custom_instructions: str | None = None) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS)
        self._model = model
        self._custom_instructions = custom_instructions
        self._anthropic = anthropic

    def suggest(self, document_text: str, known_company_names: list[str]) -> LLMSuggestion:
        truncated_text = prepare_document_text_for_llm(document_text)
        message_content = wrap_untrusted_document_text(truncated_text)
        system_prompt = build_classification_system_prompt(known_company_names, self._custom_instructions)

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=500,
                system=system_prompt,
                messages=[{"role": "user", "content": message_content}],
                tools=[SUGGESTION_TOOL],
                tool_choice={"type": "tool", "name": SUGGESTION_TOOL_NAME},
            )
        except self._anthropic.APIError as exc:
            raise LLMClassificationError("Falha ao consultar o modelo de classificacao.") from exc

        tool_use_block = next(
            (block for block in response.content if getattr(block, "type", None) == "tool_use"),
            None,
        )
        if tool_use_block is None:
            raise LLMClassificationError("O modelo nao retornou uma sugestao estruturada.")

        payload = tool_use_block.input
        if not isinstance(payload, dict):
            raise LLMClassificationError("O modelo retornou uma sugestao em formato invalido.")

        try:
            confidence = float(payload.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0

        return LLMSuggestion(
            suggested_company_name=clamp_suggestion_text(payload.get("suggested_company_name")),
            suggested_cnpj=clamp_suggestion_text(payload.get("suggested_cnpj")),
            suggested_document_type=clamp_suggestion_text(payload.get("suggested_document_type")),
            confidence=max(0.0, min(1.0, confidence)),
        )
