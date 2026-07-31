from __future__ import annotations

import json

from documentos_empresa_app.services.llm_types import (
    CADASTRAR_DOCUMENTO_TOOL_DESCRIPTION,
    CADASTRAR_DOCUMENTO_TOOL_NAME,
    CADASTRAR_DOCUMENTO_TOOL_PARAMETERS,
    ChatReply,
    COPY_FILE_TOOL_DESCRIPTION,
    COPY_FILE_TOOL_NAME,
    COPY_FILE_TOOL_PARAMETERS,
    DAR_BAIXA_TOOL_DESCRIPTION,
    DAR_BAIXA_TOOL_NAME,
    LLMChatError,
    ORGANIZE_TOOL_DESCRIPTION,
    ORGANIZE_TOOL_NAME,
    ProposedCadastrarDocumento,
    ProposedDarBaixa,
    ProposedFileCopy,
    ProposedOrganize,
    REQUEST_TIMEOUT_SECONDS,
    build_chat_system_prompt,
    build_dar_baixa_tool_parameters,
    build_organize_tool_parameters,
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
_CADASTRAR_DOCUMENTO_TOOL = {
    "type": "function",
    "function": {
        "name": CADASTRAR_DOCUMENTO_TOOL_NAME,
        "description": CADASTRAR_DOCUMENTO_TOOL_DESCRIPTION,
        "parameters": CADASTRAR_DOCUMENTO_TOOL_PARAMETERS,
    },
}


class OpenAIChatService:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, custom_instructions: str | None = None) -> None:
        import openai

        self._client = openai.OpenAI(api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS)
        self._model = model
        self._custom_instructions = custom_instructions
        self._openai = openai

    def send_message(
        self,
        document_text: str,
        history: list[dict],
        user_message: str,
        registered_documents: list[dict],
        tipos_catalog: list[dict],
    ) -> ChatReply:
        system_prompt = build_chat_system_prompt(
            document_text, self._custom_instructions, registered_documents, tipos_catalog
        )
        user_entry = {"role": "user", "content": user_message}
        reply, assistant_entry = self._call(
            system_prompt, [*limit_chat_history(history), user_entry], registered_documents
        )
        history.append(user_entry)
        history.append(assistant_entry)
        return reply

    def resolve_proposed_copy(
        self,
        document_text: str,
        history: list[dict],
        proposed_copy: ProposedFileCopy,
        result_message: str,
        registered_documents: list[dict],
        tipos_catalog: list[dict],
    ) -> ChatReply:
        return self._resolve_tool_result(
            document_text, history, proposed_copy.call_id, result_message, registered_documents, tipos_catalog
        )

    def resolve_proposed_organize(
        self,
        document_text: str,
        history: list[dict],
        proposed_organize: ProposedOrganize,
        result_message: str,
        registered_documents: list[dict],
        tipos_catalog: list[dict],
    ) -> ChatReply:
        return self._resolve_tool_result(
            document_text, history, proposed_organize.call_id, result_message, registered_documents, tipos_catalog
        )

    def resolve_proposed_cadastrar_documento(
        self,
        document_text: str,
        history: list[dict],
        proposed_cadastrar_documento: ProposedCadastrarDocumento,
        result_message: str,
        registered_documents: list[dict],
        tipos_catalog: list[dict],
    ) -> ChatReply:
        return self._resolve_tool_result(
            document_text,
            history,
            proposed_cadastrar_documento.call_id,
            result_message,
            registered_documents,
            tipos_catalog,
        )

    def resolve_proposed_dar_baixa(
        self,
        document_text: str,
        history: list[dict],
        proposed_dar_baixa: ProposedDarBaixa,
        result_message: str,
        registered_documents: list[dict],
        tipos_catalog: list[dict],
    ) -> ChatReply:
        return self._resolve_tool_result(
            document_text, history, proposed_dar_baixa.call_id, result_message, registered_documents, tipos_catalog
        )

    def _resolve_tool_result(
        self,
        document_text: str,
        history: list[dict],
        call_id: str,
        result_message: str,
        registered_documents: list[dict],
        tipos_catalog: list[dict],
    ) -> ChatReply:
        system_prompt = build_chat_system_prompt(
            document_text, self._custom_instructions, registered_documents, tipos_catalog
        )
        tool_result_entry = {
            "role": "tool",
            "tool_call_id": call_id,
            "content": result_message,
        }
        reply, assistant_entry = self._call(
            system_prompt, [*limit_chat_history(history), tool_result_entry], registered_documents
        )
        history.append(tool_result_entry)
        history.append(assistant_entry)
        return reply

    def _call(
        self, system_prompt: str, history_messages: list[dict], registered_documents: list[dict]
    ) -> tuple[ChatReply, dict]:
        organize_tool = {
            "type": "function",
            "function": {
                "name": ORGANIZE_TOOL_NAME,
                "description": ORGANIZE_TOOL_DESCRIPTION,
                "parameters": build_organize_tool_parameters(registered_documents),
            },
        }
        dar_baixa_tool = {
            "type": "function",
            "function": {
                "name": DAR_BAIXA_TOOL_NAME,
                "description": DAR_BAIXA_TOOL_DESCRIPTION,
                "parameters": build_dar_baixa_tool_parameters(registered_documents),
            },
        }
        messages = [{"role": "system", "content": system_prompt}, *history_messages]
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=MAX_RESPONSE_TOKENS,
                tools=[_COPY_FILE_TOOL, organize_tool, _CADASTRAR_DOCUMENTO_TOOL, dar_baixa_tool],
            )
        except self._openai.APIError as exc:
            raise LLMChatError("Falha ao consultar o agente.") from exc

        if not response.choices:
            raise LLMChatError("O agente nao retornou nenhuma resposta.")

        message = response.choices[0].message
        tool_calls = message.tool_calls or []
        copy_call = next((call for call in tool_calls if call.function.name == COPY_FILE_TOOL_NAME), None)
        organize_call = next((call for call in tool_calls if call.function.name == ORGANIZE_TOOL_NAME), None)
        cadastrar_call = next(
            (call for call in tool_calls if call.function.name == CADASTRAR_DOCUMENTO_TOOL_NAME), None
        )
        dar_baixa_call = next((call for call in tool_calls if call.function.name == DAR_BAIXA_TOOL_NAME), None)

        proposed_copy = self._parse_proposed_copy(copy_call) if copy_call is not None else None
        proposed_organize = self._parse_proposed_organize(organize_call) if organize_call is not None else None
        proposed_cadastrar_documento = (
            self._parse_proposed_cadastrar_documento(cadastrar_call) if cadastrar_call is not None else None
        )
        proposed_dar_baixa = self._parse_proposed_dar_baixa(dar_baixa_call) if dar_baixa_call is not None else None

        text = (message.content or "").strip() or None
        if (
            text is None
            and proposed_copy is None
            and proposed_organize is None
            and proposed_cadastrar_documento is None
            and proposed_dar_baixa is None
        ):
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
            ChatReply(
                text=text,
                proposed_copy=proposed_copy,
                proposed_organize=proposed_organize,
                proposed_cadastrar_documento=proposed_cadastrar_documento,
                proposed_dar_baixa=proposed_dar_baixa,
            ),
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
        raw_documento_id = tool_input.get("documento_registrado_id")
        try:
            documento_empresa_id = int(raw_documento_id) if raw_documento_id is not None else None
        except (TypeError, ValueError):
            documento_empresa_id = None
        banco = tool_input.get("banco")
        tipo_conta = tool_input.get("tipo_conta")
        return ProposedOrganize(
            call_id=tool_call.id,
            mes=mes,
            ano=ano,
            documento_empresa_id=documento_empresa_id,
            banco=str(banco).strip() if banco else None,
            tipo_conta=str(tipo_conta).strip() if tipo_conta else None,
        )

    def _parse_proposed_cadastrar_documento(self, tool_call) -> ProposedCadastrarDocumento | None:
        try:
            tool_input = json.loads(tool_call.function.arguments or "{}")
        except json.JSONDecodeError:
            return None

        nome_tipo = str(tool_input.get("nome_tipo") or "").strip()
        nome_documento = str(tool_input.get("nome_documento") or "").strip()
        if not nome_tipo or not nome_documento:
            return None
        raw_meios = tool_input.get("meios_recebimento")
        meios_recebimento = (
            tuple(str(item).strip() for item in raw_meios if str(item).strip())
            if isinstance(raw_meios, list)
            else None
        )
        regra = tool_input.get("regra_ocorrencia_novo_tipo")
        return ProposedCadastrarDocumento(
            call_id=tool_call.id,
            nome_tipo=nome_tipo,
            nome_documento=nome_documento,
            meios_recebimento=meios_recebimento or None,
            regra_ocorrencia_novo_tipo=str(regra).strip() if regra else None,
        )

    def _parse_proposed_dar_baixa(self, tool_call) -> ProposedDarBaixa | None:
        try:
            tool_input = json.loads(tool_call.function.arguments or "{}")
        except json.JSONDecodeError:
            return None

        try:
            documento_empresa_id = int(tool_input.get("documento_empresa_id"))
            mes = int(tool_input.get("mes"))
            ano = int(tool_input.get("ano"))
        except (TypeError, ValueError):
            return None
        if not 1 <= mes <= 12:
            return None
        status = tool_input.get("status")
        return ProposedDarBaixa(
            call_id=tool_call.id,
            documento_empresa_id=documento_empresa_id,
            mes=mes,
            ano=ano,
            status=str(status).strip() if status else None,
        )
