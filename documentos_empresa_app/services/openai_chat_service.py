from __future__ import annotations

from documentos_empresa_app.services.llm_types import (
    LLMChatError,
    REQUEST_TIMEOUT_SECONDS,
    build_chat_system_prompt,
    limit_chat_history,
)

DEFAULT_MODEL = "gpt-4o-mini"
MAX_RESPONSE_TOKENS = 1000


class OpenAIChatService:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, custom_instructions: str | None = None) -> None:
        import openai

        self._client = openai.OpenAI(api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS)
        self._model = model
        self._custom_instructions = custom_instructions
        self._openai = openai

    def send_message(self, document_text: str, history: list[dict], user_message: str) -> str:
        system_prompt = build_chat_system_prompt(document_text, self._custom_instructions)
        messages = [
            {"role": "system", "content": system_prompt},
            *limit_chat_history(history),
            {"role": "user", "content": user_message},
        ]

        try:
            response = self._client.chat.completions.create(
                model=self._model, messages=messages, max_tokens=MAX_RESPONSE_TOKENS
            )
        except self._openai.APIError as exc:
            raise LLMChatError("Falha ao consultar o agente.") from exc

        if not response.choices:
            raise LLMChatError("O agente nao retornou nenhuma resposta.")

        content = response.choices[0].message.content
        if not content:
            raise LLMChatError("O agente nao retornou uma resposta em texto.")
        return content
