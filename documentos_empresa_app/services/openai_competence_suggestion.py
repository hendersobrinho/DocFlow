from __future__ import annotations

import json

from documentos_empresa_app.services.llm_types import (
    CompetenceSuggestion,
    LLMCompetenceSuggestionError,
    ORGANIZE_TOOL_DESCRIPTION,
    ORGANIZE_TOOL_NAME,
    REQUEST_TIMEOUT_SECONDS,
    build_competence_suggestion_system_prompt,
    build_organize_tool_parameters,
    clamp_suggestion_text,
    prepare_document_text_for_llm,
    wrap_untrusted_document_text,
)

DEFAULT_MODEL = "gpt-4o-mini"


class OpenAICompetenceSuggestionClient:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, custom_instructions: str | None = None) -> None:
        import openai

        self._client = openai.OpenAI(api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS)
        self._model = model
        self._custom_instructions = custom_instructions
        self._openai = openai

    def suggest(self, document_text: str, registered_documents: list[dict]) -> CompetenceSuggestion:
        truncated_text = prepare_document_text_for_llm(document_text)
        message_content = wrap_untrusted_document_text(truncated_text)
        system_prompt = build_competence_suggestion_system_prompt(self._custom_instructions, registered_documents)
        tool = {
            "type": "function",
            "function": {
                "name": ORGANIZE_TOOL_NAME,
                "description": ORGANIZE_TOOL_DESCRIPTION,
                "parameters": build_organize_tool_parameters(registered_documents),
            },
        }

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message_content},
                ],
                tools=[tool],
                tool_choice={"type": "function", "function": {"name": ORGANIZE_TOOL_NAME}},
            )
        except self._openai.APIError as exc:
            raise LLMCompetenceSuggestionError("Falha ao consultar o modelo de sugestao de competencia.") from exc

        if not response.choices:
            raise LLMCompetenceSuggestionError("O modelo nao retornou nenhuma resposta.")

        tool_calls = response.choices[0].message.tool_calls
        if not tool_calls:
            raise LLMCompetenceSuggestionError("O modelo nao retornou uma sugestao estruturada.")

        try:
            payload = json.loads(tool_calls[0].function.arguments)
        except (TypeError, ValueError) as exc:
            raise LLMCompetenceSuggestionError("O modelo retornou uma sugestao em formato invalido.") from exc

        if not isinstance(payload, dict):
            raise LLMCompetenceSuggestionError("O modelo retornou uma sugestao em formato invalido.")

        try:
            mes = int(payload.get("mes"))
            ano = int(payload.get("ano"))
        except (TypeError, ValueError) as exc:
            raise LLMCompetenceSuggestionError("O modelo retornou mes/ano em formato invalido.") from exc

        raw_documento_id = payload.get("documento_registrado_id")
        try:
            documento_empresa_id = int(raw_documento_id) if raw_documento_id is not None else None
        except (TypeError, ValueError):
            documento_empresa_id = None

        return CompetenceSuggestion(
            mes=mes,
            ano=ano,
            documento_empresa_id=documento_empresa_id,
            banco=clamp_suggestion_text(payload.get("banco")),
            tipo_conta=clamp_suggestion_text(payload.get("tipo_conta")),
        )
