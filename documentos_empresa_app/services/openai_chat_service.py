from __future__ import annotations

import json

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

DEFAULT_MODEL = "gpt-4o-mini"
MAX_RESPONSE_TOKENS = 1000

_COPY_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": COPY_FILE_TOOL_NAME,
        "description": COPY_FILE_TOOL_DESCRIPTION,
        "parameters": COPY_FILE_TOOL_PARAMETERS,
    },
}
_ORGANIZE_TOOL = {
    "type": "function",
    "function": {
        "name": ORGANIZE_TOOL_NAME,
        "description": ORGANIZE_TOOL_DESCRIPTION,
        "parameters": ORGANIZE_TOOL_PARAMETERS,
    },
}


class OpenAIChatService:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, custom_instructions: str | None = None) -> None:
        import openai

        self._client = openai.OpenAI(api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS)
        self._model = model
        self._custom_instructions = custom_instructions
        self._openai = openai

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
            "role": "tool",
            "tool_call_id": proposed_copy.call_id,
            "content": result_message,
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
            "role": "tool",
            "tool_call_id": proposed_organize.call_id,
            "content": result_message,
        }
        reply, assistant_entry = self._call(system_prompt, [*limit_chat_history(history), tool_result_entry])
        history.append(tool_result_entry)
        history.append(assistant_entry)
        return reply

    def _call(self, system_prompt: str, history_messages: list[dict]) -> tuple[ChatReply, dict]:
        messages = [{"role": "system", "content": system_prompt}, *history_messages]
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=MAX_RESPONSE_TOKENS,
                tools=[_COPY_FILE_TOOL, _ORGANIZE_TOOL],
            )
        except self._openai.APIError as exc:
            raise LLMChatError("Falha ao consultar o agente.") from exc

        if not response.choices:
            raise LLMChatError("O agente nao retornou nenhuma resposta.")

        message = response.choices[0].message
        tool_calls = message.tool_calls or []
        copy_call = next((call for call in tool_calls if call.function.name == COPY_FILE_TOOL_NAME), None)
        organize_call = next((call for call in tool_calls if call.function.name == ORGANIZE_TOOL_NAME), None)

        proposed_copy = self._parse_proposed_copy(copy_call) if copy_call is not None else None
        proposed_organize = self._parse_proposed_organize(organize_call) if organize_call is not None else None

        text = (message.content or "").strip() or None
        if text is None and proposed_copy is None and proposed_organize is None:
            raise LLMChatError("O agente nao retornou uma resposta em texto.")

        assistant_entry: dict = {"role": "assistant", "content": message.content}
        if tool_calls:
            assistant_entry["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.function.name, "arguments": call.function.arguments},
                }
                for call in tool_calls
            ]

        return (
            ChatReply(text=text, proposed_copy=proposed_copy, proposed_organize=proposed_organize),
            assistant_entry,
        )

    def _parse_proposed_copy(self, tool_call) -> ProposedFileCopy | None:
        try:
            tool_input = json.loads(tool_call.function.arguments or "{}")
        except json.JSONDecodeError:
            return None

        destination_folder = str(tool_input.get("destination_folder") or "").strip()
        if not destination_folder:
            return None
        new_filename = tool_input.get("new_filename")
        return ProposedFileCopy(
            call_id=tool_call.id,
            destination_folder=destination_folder,
            new_filename=str(new_filename).strip() if new_filename else None,
        )

    def _parse_proposed_organize(self, tool_call) -> ProposedOrganize | None:
        try:
            tool_input = json.loads(tool_call.function.arguments or "{}")
        except json.JSONDecodeError:
            return None

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
            call_id=tool_call.id,
            mes=mes,
            ano=ano,
            banco=str(banco).strip() if banco else None,
            tipo_conta=str(tipo_conta).strip() if tipo_conta else None,
        )
