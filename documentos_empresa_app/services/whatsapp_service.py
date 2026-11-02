from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

from documentos_empresa_app.utils.common import ValidationError
from documentos_empresa_app.utils.helpers import load_config, save_config
from documentos_empresa_app.utils.secret_protection import protect_secret, unprotect_secret

WHATSAPP_CONFIG_KEY = "whatsapp"
PROVEDOR_LINK = "link"
PROVEDOR_CLOUD_API = "cloud_api"
PROVEDORES = (PROVEDOR_LINK, PROVEDOR_CLOUD_API)
DEFAULT_WHATSAPP_SETTINGS = {
    "provedor": PROVEDOR_LINK,
    "phone_number_id": "",
    "token": "",
    "api_version": "v21.0",
}
DDI_BRASIL = "55"


def normalize_whatsapp(raw: str | None) -> str | None:
    """'(27) 99999-8888', '+55 27 99999-8888' -> '5527999998888'. Numero brasileiro sem DDI
    (10 ou 11 digitos) ganha o 55; vazio vira None."""
    digitos = re.sub(r"\D", "", str(raw or ""))
    if not digitos:
        return None
    if digitos.startswith("00"):
        digitos = digitos[2:]
    if len(digitos) in (10, 11):
        digitos = DDI_BRASIL + digitos
    if not 12 <= len(digitos) <= 15:
        raise ValidationError("WhatsApp invalido. Use DDD + numero, por exemplo (27) 99999-8888.")
    return digitos


def format_whatsapp(numero: str | None) -> str:
    """'5527999998888' -> '+55 (27) 99999-8888'; outros paises ficam so com o +."""
    if not numero:
        return ""
    if numero.startswith(DDI_BRASIL) and len(numero) in (12, 13):
        ddd, resto = numero[2:4], numero[4:]
        return f"+55 ({ddd}) {resto[:-4]}-{resto[-4:]}"
    return "+" + numero


GRUPO_RE = re.compile(r"^(?:https?://)?chat\.whatsapp\.com/(?:invite/)?([A-Za-z0-9]{10,40})/?$")


def normalize_grupo_link(raw: str | None) -> str | None:
    """Link de convite do grupo -> 'https://chat.whatsapp.com/CODIGO'. Vazio vira None."""
    texto = str(raw or "").strip()
    if not texto:
        return None
    achado = GRUPO_RE.match(texto)
    if not achado:
        raise ValidationError(
            "Link do grupo invalido. No WhatsApp, abra o grupo > Convidar via link > Copiar link "
            "(fica assim: https://chat.whatsapp.com/...)."
        )
    return f"https://chat.whatsapp.com/{achado.group(1)}"


def build_link(numero: str, mensagem: str = "") -> str:
    """Link que abre a conversa no WhatsApp (app ou web) com a mensagem ja escrita."""
    link = f"https://wa.me/{numero}"
    if mensagem:
        link += "?text=" + urllib.parse.quote(mensagem)
    return link


def load_whatsapp_settings() -> dict:
    stored = load_config().get(WHATSAPP_CONFIG_KEY)
    settings = dict(DEFAULT_WHATSAPP_SETTINGS)
    if isinstance(stored, dict):
        settings.update({k: stored.get(k) or settings[k] for k in DEFAULT_WHATSAPP_SETTINGS})
        settings["token"] = unprotect_secret(stored.get("token")) or ""
    if settings["provedor"] not in PROVEDORES:
        settings["provedor"] = PROVEDOR_LINK
    return settings


def save_whatsapp_settings(settings: dict) -> dict:
    normalizado = dict(DEFAULT_WHATSAPP_SETTINGS)
    normalizado.update({k: str(settings.get(k) or "").strip() or normalizado[k] for k in DEFAULT_WHATSAPP_SETTINGS})
    if normalizado["provedor"] not in PROVEDORES:
        raise ValidationError(f"Provedor invalido. Use um de: {', '.join(PROVEDORES)}.")
    if normalizado["provedor"] == PROVEDOR_CLOUD_API and not (normalizado["phone_number_id"] and normalizado["token"]):
        raise ValidationError("Para a API do WhatsApp informe o phone_number_id e o token.")
    stored = dict(normalizado)
    # O token fica protegido como a senha do banco (DPAPI no Windows).
    stored["token"] = protect_secret(normalizado["token"]) if normalizado["token"] else None
    config = load_config()
    config[WHATSAPP_CONFIG_KEY] = stored
    save_config(config)
    return normalizado


class CloudApiSender:
    """Envio direto pela WhatsApp Cloud API (Meta). Fica desligado ate alguem configurar o
    provedor 'cloud_api'. Atencao: fora da janela de 24h desde a ultima mensagem do cliente a
    Meta so aceita mensagens de modelo (template) aprovadas - texto livre volta com erro."""

    def __init__(self, phone_number_id: str, token: str, api_version: str = "v21.0", timeout: float = 20) -> None:
        self.url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
        self.token = token
        self.timeout = timeout

    def send_text(self, numero: str, mensagem: str) -> dict:
        return self._post({"messaging_product": "whatsapp", "to": numero, "type": "text", "text": {"body": mensagem}})

    def send_template(self, numero: str, template: str, idioma: str = "pt_BR", parametros: list[str] | None = None) -> dict:
        corpo: dict = {"name": template, "language": {"code": idioma}}
        if parametros:
            corpo["components"] = [
                {"type": "body", "parameters": [{"type": "text", "text": str(p)} for p in parametros]}
            ]
        return self._post({"messaging_product": "whatsapp", "to": numero, "type": "template", "template": corpo})

    def _post(self, payload: dict) -> dict:
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            detalhe = exc.read().decode("utf-8", "replace")[:500]
            raise ValidationError(f"A API do WhatsApp recusou a mensagem ({exc.code}): {detalhe}") from exc
        except urllib.error.URLError as exc:
            raise ValidationError(f"Sem conexao com a API do WhatsApp: {exc.reason}") from exc


class WhatsAppService:
    """Hoje o DocFlow monta o link wa.me (a pessoa clica e envia pelo proprio WhatsApp).
    Com o provedor 'cloud_api' configurado, enviar() manda direto pela API da Meta."""

    def __init__(self, settings_loader=load_whatsapp_settings, sender_factory=CloudApiSender) -> None:
        self._settings_loader = settings_loader
        self._sender_factory = sender_factory

    def settings(self) -> dict:
        return self._settings_loader()

    def api_ativa(self) -> bool:
        settings = self.settings()
        return settings["provedor"] == PROVEDOR_CLOUD_API and bool(settings["phone_number_id"] and settings["token"])

    def enviar(self, numero: str, mensagem: str, template: str | None = None, parametros: list[str] | None = None) -> dict:
        numero = normalize_whatsapp(numero)
        if not numero:
            raise ValidationError("Informe o numero de WhatsApp.")
        link = build_link(numero, mensagem)
        if not self.api_ativa():
            return {"enviado": False, "modo": PROVEDOR_LINK, "numero": numero, "link": link}
        settings = self.settings()
        sender = self._sender_factory(settings["phone_number_id"], settings["token"], settings["api_version"])
        if template:
            resposta = sender.send_template(numero, template, parametros=parametros)
        else:
            resposta = sender.send_text(numero, mensagem)
        mensagem_id = ((resposta.get("messages") or [{}])[0]).get("id")
        return {"enviado": True, "modo": PROVEDOR_CLOUD_API, "numero": numero, "mensagem_id": mensagem_id, "link": link}
