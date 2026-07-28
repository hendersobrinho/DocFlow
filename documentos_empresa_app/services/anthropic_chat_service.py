from __future__ import annotations

from documentos_empresa_app.services.llm_types import (
    ChatReply,
    COPY_FILE_TOOL_DESCRIPTION,
    COPY_FILE_TOOL_NAME,
    COPY_FILE_TOOL_PARAMETERS,
    LLMChatError,
    ORGANIZE_TOOL_DESCRIPTION,
    ORGANIZE_TOOL_NAME,
    ORGANIZE_TOOL_PARAMETERS,
    ProposedFileCopy,
    ProposedOrganize,
    REQUEST_TIMEOUT_SECONDS,
    build_chat_system_prompt,
    limit_chat_history,
)

DEFAULT_MODEL = "claude-haiku-4-5"

_COPY_FILE_TOOL = {
    "name": COPY_FILE_TOOL_NAME,
    "description": COPY_FILE_TOOL_DESCRIPTION,
    "input_schema": COPY_FILE_TOOL_PARAMETERS,
}
_ORGANIZE_TOOL = {
    "name": ORGANIZE_TOOL_NAME,
    "description": ORGANIZE_TOOL_DESCRIPTION,
    "input_schema": ORGANIZE_TOOL_PARAMETERS,
}


class AnthropicChatService:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, custom_instructions: str | None = None) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS)
        self._model = model
        self._custom_instructions = custom_instructions
        self._anthropic = anthropic

    def send_message(self, document_text: str, history: list[dict], user_message: str) -> ChatReply:
        system_prompt = build_chat_system_prompt(document_text, self._custom_instructions)
        user_entry = {"role": "user", "content": user_message}
        reply, assistant_entry = self._call(system_prompt, [*limit_chat_history(history), user_entry])
        history.append(user_entry)
        history.append(assistant_entry)
        return reply

    def resolve_proposed_copy(
        self,
        document_text: str,
        history: list[dict],
        proposed_copy: ProposedFileCopy,
        result_message: str,
    ) -> ChatReply:
        system_prompt = build_chat_system_prompt(document_text, self._custom_instructions)
        tool_result_entry = {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": proposed_copy.call_id,
                    "content": result_message,
                }
            ],
        }
        reply, assistant_entry = self._call(system_prompt, [*limit_chat_history(history), tool_result_entry])
        history.append(tool_result_entry)
        history.append(assistant_entry)
        return reply

    def resolve_proposed_organize(
        self,
        document_text: str,
        history: list[dict],
        proposed_organize: ProposedOrganize,
        result_message: str,
    ) -> ChatReply:
        system_prompt = build_chat_system_prompt(document_text, self._custom_instructions)
        tool_result_entry = {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": proposed_organize.call_id,
                    "content": result_message,
                }
            ],
        }
        reply, assistant_entry = self._call(system_prompt, [*limit_chat_history(history), tool_result_entry])
        history.append(tool_result_entry)
        history.append(assistant_entry)
        return reply

    def _call(self, system_prompt: str, messages: list[dict]) -> tuple[ChatReply, dict]:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=1000,
                system=system_prompt,
                messages=messages,
                tools=[_COPY_FILE_TOOL, _ORGANIZE_TOOL],
            )
        except self._anthropic.APIError as exc:
            raise LLMChatError("Falha ao consultar o agente.") from exc

        content_blocks: list[dict] = []
        text_parts: list[str] = []
        proposed_copy: ProposedFileCopy | None = None
        proposed_organize: ProposedOrganize | None = None

        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                content_blocks.append({"type": "text", "text": block.text})
                text_parts.append(block.text)
            elif block_type == "tool_use":
                content_blocks.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})
                if block.name == COPY_FILE_TOOL_NAME:
                    proposed_copy = self._parse_proposed_copy(block.id, block.input or {})
                elif block.name == ORGANIZE_TOOL_NAME:
                    proposed_organize = self._parse_proposed_organize(block.id, block.input or {})

        text = "\n".join(text_parts).strip() or None
        if text is None and proposed_copy is None and proposed_organize is None:
            raise LLMChatError("O agente nao retornou uma resposta em texto.")

        assistant_entry = {"role": "assistant", "content": content_blocks}
        return (
            ChatReply(text=text, proposed_copy=proposed_copy, proposed_organize=proposed_organize),
            assistant_entry,
        )

    def _parse_proposed_copy(self, call_id: str, tool_input: dict) -> ProposedFileCopy | None:
        destination_folder = str(tool_input.get("destination_folder") or "").strip()
        if not destination_folder:
            return None
        new_filename = tool_input.get("new_filename")
        return ProposedFileCopy(
            call_id=call_id,
            destination_folder=destination_folder,
            new_filename=str(new_filename).strip() if new_filename else None,
        )

    def _parse_proposed_organize(self, call_id: str, tool_input: dict) -> ProposedOrganize | None:
        try:
            mes = int(tool_input.get("mes"))
            ano = int(tool_input.get("ano"))
        except (TypeError, ValueError):
            return None
        if not 1 <= mes <= 12:
            return None
        banco = tool_input.get("banco")
        tipo_conta = tool_input.get("tipo_conta")
        return ProposedOrganize(
            call_id=call_id,
            mes=mes,
            ano=ano,
            banco=str(banco).strip() if banco else None,
            tipo_conta=str(tipo_conta).strip() if tipo_conta else None,
        )
