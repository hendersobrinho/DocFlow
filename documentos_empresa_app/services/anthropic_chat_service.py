from __future__ import annotations

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

DEFAULT_MODEL = "claude-haiku-4-5"

_COPY_FILE_TOOL = {
    "name": COPY_FILE_TOOL_NAME,
    "description": COPY_FILE_TOOL_DESCRIPTION,
    "input_schema": COPY_FILE_TOOL_PARAMETERS,
}
_CADASTRAR_DOCUMENTO_TOOL = {
    "name": CADASTRAR_DOCUMENTO_TOOL_NAME,
    "description": CADASTRAR_DOCUMENTO_TOOL_DESCRIPTION,
    "input_schema": CADASTRAR_DOCUMENTO_TOOL_PARAMETERS,
}


class AnthropicChatService:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, custom_instructions: str | None = None) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS)
        self._model = model
        self._custom_instructions = custom_instructions
        self._anthropic = anthropic

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
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": call_id,
                    "content": result_message,
                }
            ],
        }
        reply, assistant_entry = self._call(
            system_prompt, [*limit_chat_history(history), tool_result_entry], registered_documents
        )
        history.append(tool_result_entry)
        history.append(assistant_entry)
        return reply

    def _call(
        self, system_prompt: str, messages: list[dict], registered_documents: list[dict]
    ) -> tuple[ChatReply, dict]:
        organize_tool = {
            "name": ORGANIZE_TOOL_NAME,
            "description": ORGANIZE_TOOL_DESCRIPTION,
            "input_schema": build_organize_tool_parameters(registered_documents),
        }
        dar_baixa_tool = {
            "name": DAR_BAIXA_TOOL_NAME,
            "description": DAR_BAIXA_TOOL_DESCRIPTION,
            "input_schema": build_dar_baixa_tool_parameters(registered_documents),
        }
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=1000,
                system=system_prompt,
                messages=messages,
                tools=[_COPY_FILE_TOOL, organize_tool, _CADASTRAR_DOCUMENTO_TOOL, dar_baixa_tool],
            )
        except self._anthropic.APIError as exc:
            raise LLMChatError("Falha ao consultar o agente.") from exc

        content_blocks: list[dict] = []
        text_parts: list[str] = []
        proposed_copy: ProposedFileCopy | None = None
        proposed_organize: ProposedOrganize | None = None
        proposed_cadastrar_documento: ProposedCadastrarDocumento | None = None
        proposed_dar_baixa: ProposedDarBaixa | None = None

        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                content_blocks.append({"type": "text", "text": block.text})
                text_parts.append(block.text)
            elif block_type == "tool_use":
                content_blocks.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})
                tool_input = block.input or {}
                if block.name == COPY_FILE_TOOL_NAME:
                    proposed_copy = self._parse_proposed_copy(block.id, tool_input)
                elif block.name == ORGANIZE_TOOL_NAME:
                    proposed_organize = self._parse_proposed_organize(block.id, tool_input)
                elif block.name == CADASTRAR_DOCUMENTO_TOOL_NAME:
                    proposed_cadastrar_documento = self._parse_proposed_cadastrar_documento(block.id, tool_input)
                elif block.name == DAR_BAIXA_TOOL_NAME:
                    proposed_dar_baixa = self._parse_proposed_dar_baixa(block.id, tool_input)

        text = "\n".join(text_parts).strip() or None
        if (
            text is None
            and proposed_copy is None
            and proposed_organize is None
            and proposed_cadastrar_documento is None
            and proposed_dar_baixa is None
        ):
            raise LLMChatError("O agente nao retornou uma resposta em texto.")

        assistant_entry = {"role": "assistant", "content": content_blocks}
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
        raw_documento_id = tool_input.get("documento_registrado_id")
        try:
            documento_empresa_id = int(raw_documento_id) if raw_documento_id is not None else None
        except (TypeError, ValueError):
            documento_empresa_id = None
        banco = tool_input.get("banco")
        tipo_conta = tool_input.get("tipo_conta")
        return ProposedOrganize(
            call_id=call_id,
            mes=mes,
            ano=ano,
            documento_empresa_id=documento_empresa_id,
            banco=str(banco).strip() if banco else None,
            tipo_conta=str(tipo_conta).strip() if tipo_conta else None,
        )

    def _parse_proposed_cadastrar_documento(
        self, call_id: str, tool_input: dict
    ) -> ProposedCadastrarDocumento | None:
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
            call_id=call_id,
            nome_tipo=nome_tipo,
            nome_documento=nome_documento,
            meios_recebimento=meios_recebimento or None,
            regra_ocorrencia_novo_tipo=str(regra).strip() if regra else None,
        )

    def _parse_proposed_dar_baixa(self, call_id: str, tool_input: dict) -> ProposedDarBaixa | None:
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
            call_id=call_id,
            documento_empresa_id=documento_empresa_id,
            mes=mes,
            ano=ano,
            status=str(status).strip() if status else None,
        )
