from __future__ import annotations

from dataclasses import dataclass

from documentos_empresa_app.services.anthropic_document_classifier import DEFAULT_MODEL as ANTHROPIC_DEFAULT_MODEL
from documentos_empresa_app.services.openai_document_classifier import DEFAULT_MODEL as OPENAI_DEFAULT_MODEL
from documentos_empresa_app.services.session_service import SessionService
from documentos_empresa_app.utils.common import ValidationError
from documentos_empresa_app.utils.helpers import (
    load_agent_confidence_threshold,
    load_agent_custom_instructions,
    load_agent_model,
    load_agent_provider,
    resolve_agent_api_key,
    save_agent_api_key,
    save_agent_confidence_threshold,
    save_agent_custom_instructions,
    save_agent_model,
    save_agent_provider,
)

DEFAULT_CONFIDENCE_THRESHOLD = 0.75

PROVIDER_LABELS = {
    "anthropic": "Anthropic (Claude)",
    "openai": "OpenAI (ChatGPT)",
}

DEFAULT_MODELS = {
    "anthropic": ANTHROPIC_DEFAULT_MODEL,
    "openai": OPENAI_DEFAULT_MODEL,
}

AVAILABLE_MODELS = {
    "anthropic": (
        "claude-haiku-4-5",
        "claude-sonnet-5",
        "claude-opus-4-8",
    ),
    "openai": (
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-4.1-mini",
        "gpt-4.1",
    ),
}


@dataclass(slots=True)
class AgentSettings:
    provider: str
    api_key: str | None
    model: str
    confidence_threshold: float
    custom_instructions: str | None


class AgentConfigService:
    def __init__(self, session_service: SessionService) -> None:
        self.session_service = session_service

    def get_settings(self, provider: str | None = None) -> AgentSettings:
        self._ensure_admin()
        normalized_provider = self._normalize_provider(provider or load_agent_provider())
        return AgentSettings(
            provider=normalized_provider,
            api_key=resolve_agent_api_key(normalized_provider),
            model=load_agent_model(normalized_provider) or DEFAULT_MODELS[normalized_provider],
            confidence_threshold=load_agent_confidence_threshold() or DEFAULT_CONFIDENCE_THRESHOLD,
            custom_instructions=load_agent_custom_instructions(),
        )

    def save_settings(
        self,
        provider: str,
        api_key: str | None,
        model: str,
        confidence_threshold: float,
        custom_instructions: str | None,
    ) -> AgentSettings:
        self._ensure_admin()
        normalized_provider = self._normalize_provider(provider)
        normalized_model = str(model or "").strip() or DEFAULT_MODELS[normalized_provider]
        try:
            normalized_threshold = float(confidence_threshold)
        except (TypeError, ValueError) as exc:
            raise ValidationError("O limiar de confianca deve ser um numero entre 0 e 1.") from exc
        if not 0.0 <= normalized_threshold <= 1.0:
            raise ValidationError("O limiar de confianca deve estar entre 0 e 1.")

        save_agent_provider(normalized_provider)
        save_agent_api_key(normalized_provider, api_key)
        save_agent_model(normalized_provider, normalized_model)
        save_agent_confidence_threshold(normalized_threshold)
        save_agent_custom_instructions(custom_instructions)
        return self.get_settings(normalized_provider)

    def test_connection(self, provider: str, api_key: str, model: str) -> None:
        self._ensure_admin()
        normalized_provider = self._normalize_provider(provider)
        normalized_key = str(api_key or "").strip()
        if not normalized_key:
            raise ValidationError("Informe uma API key para testar.")
        normalized_model = str(model or "").strip() or DEFAULT_MODELS[normalized_provider]

        if normalized_provider == "openai":
            self._test_openai_connection(normalized_key, normalized_model)
        else:
            self._test_anthropic_connection(normalized_key, normalized_model)

    def _test_anthropic_connection(self, api_key: str, model: str) -> None:
        import anthropic

        from documentos_empresa_app.services.llm_types import REQUEST_TIMEOUT_SECONDS

        client = anthropic.Anthropic(api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS)
        try:
            client.messages.create(model=model, max_tokens=1, messages=[{"role": "user", "content": "ping"}])
        except anthropic.APIError as exc:
            raise ValidationError("Falha ao conectar com a Anthropic. Verifique a chave e o modelo.") from exc

    def _test_openai_connection(self, api_key: str, model: str) -> None:
        import openai

        from documentos_empresa_app.services.llm_types import REQUEST_TIMEOUT_SECONDS

        client = openai.OpenAI(api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS)
        try:
            client.chat.completions.create(
                model=model, max_tokens=1, messages=[{"role": "user", "content": "ping"}]
            )
        except openai.APIError as exc:
            raise ValidationError("Falha ao conectar com a OpenAI. Verifique a chave e o modelo.") from exc

    def _normalize_provider(self, provider: str) -> str:
        normalized = str(provider or "").strip().lower()
        if normalized not in AVAILABLE_MODELS:
            raise ValidationError("Selecione um provedor de IA valido.")
        return normalized

    def _ensure_admin(self) -> None:
        if not self.session_service.is_admin():
            raise ValidationError("Apenas usuarios admin podem alterar as configuracoes do agente.")
