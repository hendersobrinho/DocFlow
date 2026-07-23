from __future__ import annotations

from dataclasses import dataclass

DEFAULT_MODEL = "claude-haiku-4-5"
MAX_DOCUMENT_TEXT_CHARS = 6000

SUGGESTION_TOOL_NAME = "sugerir_classificacao_documento"
SUGGESTION_TOOL = {
    "name": SUGGESTION_TOOL_NAME,
    "description": "Registra a sugestao de classificacao de um documento recebido.",
    "input_schema": {
        "type": "object",
        "properties": {
            "suggested_company_name": {
                "type": ["string", "null"],
                "description": "Nome da empresa sugerida, ou null se nao for possivel identificar.",
            },
            "suggested_cnpj": {
                "type": ["string", "null"],
                "description": "CNPJ (somente digitos) da empresa sugerida, ou null se nao encontrado no texto.",
            },
            "suggested_document_type": {
                "type": ["string", "null"],
                "description": "Tipo do documento (ex: boleto, extrato, nota fiscal), ou null se nao identificado.",
            },
            "confidence": {
                "type": "number",
                "description": "Confianca da sugestao, de 0 a 1.",
            },
        },
        "required": ["suggested_company_name", "suggested_cnpj", "suggested_document_type", "confidence"],
    },
}


@dataclass(slots=True)
class LLMSuggestion:
    suggested_company_name: str | None
    suggested_cnpj: str | None
    suggested_document_type: str | None
    confidence: float


class LLMClassificationError(Exception):
    """Erro ao consultar o modelo de linguagem para classificacao de documento."""


class AnthropicDocumentClassifierClient:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._anthropic = anthropic

    def suggest(self, document_text: str, known_company_names: list[str]) -> LLMSuggestion:
        truncated_text = str(document_text or "")[:MAX_DOCUMENT_TEXT_CHARS]
        companies_hint = ", ".join(known_company_names[:200]) if known_company_names else "(nenhuma cadastrada)"

        system_prompt = (
            "Voce ajuda a organizar documentos recebidos (boletos, extratos, notas fiscais) para um "
            "escritorio que presta servico para varias empresas clientes. Dado o texto extraido de um "
            "documento, identifique a qual empresa ele provavelmente pertence e o tipo de documento. "
            "Use a ferramenta fornecida para responder. Se nao tiver certeza, retorne null nos campos "
            "correspondentes e uma confianca baixa.\n\n"
            f"Empresas ja cadastradas no sistema: {companies_hint}"
        )

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=500,
                system=system_prompt,
                messages=[{"role": "user", "content": truncated_text or "(documento sem texto extraivel)"}],
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
        try:
            confidence = float(payload.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0

        return LLMSuggestion(
            suggested_company_name=payload.get("suggested_company_name") or None,
            suggested_cnpj=payload.get("suggested_cnpj") or None,
            suggested_document_type=payload.get("suggested_document_type") or None,
            confidence=max(0.0, min(1.0, confidence)),
        )
