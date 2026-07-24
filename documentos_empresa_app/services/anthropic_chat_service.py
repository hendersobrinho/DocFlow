from __future__ import annotations

from documentos_empresa_app.services.llm_types import (
    LLMChatError,
    REQUEST_TIMEOUT_SECONDS,
    build_chat_system_prompt,
    limit_chat_history,
)

DEFAULT_MODEL = "claude-haiku-4-5"


class AnthropicChatService:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, custom_instructions: str | None = None) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS)
        self._model = model
        self._custom_instructions = custom_instructions
        self._anthropic = anthropic

    def send_message(self, document_text: str, history: list[dict], user_message: str) -> str:
        system_prompt = build_chat_system_prompt(document_text, self._custom_instructions)
        messages = [*limit_chat_history(history), {"role": "user", "content": user_message}]

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=1000,
                system=system_prompt,
                messages=messages,
            )
        except self._anthropic.APIError as exc:
            raise LLMChatError("Falha ao consultar o agente.") from exc

        text_block = next((block for block in response.content if getattr(block, "type", None) == "text"), None)
        if text_block is None:
            raise LLMChatError("O agente nao retornou uma resposta em texto.")
        return text_block.text
