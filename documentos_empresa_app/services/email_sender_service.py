from __future__ import annotations

import smtplib
import socket
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from documentos_empresa_app.utils.common import ValidationError
from documentos_empresa_app.utils.helpers import load_config, save_config
from documentos_empresa_app.utils.secret_protection import protect_secret, unprotect_secret

EMAIL_CONFIG_KEY = "email_envio"
SEGURANCA_STARTTLS = "starttls"
SEGURANCA_SSL = "ssl"
SEGURANCA_NENHUMA = "nenhuma"
SEGURANCA_LABELS = {
    SEGURANCA_STARTTLS: "STARTTLS (porta 587)",
    SEGURANCA_SSL: "SSL/TLS (porta 465)",
    SEGURANCA_NENHUMA: "Sem criptografia (nao recomendado)",
}
DEFAULT_EMAIL_SETTINGS = {
    "host": "",
    "porta": 587,
    "seguranca": SEGURANCA_STARTTLS,
    "usuario": "",
    "senha": "",
    "remetente_nome": "",
    "remetente_email": "",
}
# Servidores mais comuns, para a pessoa so escolher e digitar email e senha.
PROVEDORES_SMTP = {
    "Gmail / Google Workspace": ("smtp.gmail.com", 587, SEGURANCA_STARTTLS),
    "Outlook / Microsoft 365": ("smtp.office365.com", 587, SEGURANCA_STARTTLS),
    "Hostinger": ("smtp.hostinger.com", 465, SEGURANCA_SSL),
}
# Provedores costumam recusar mensagens com destinatarios demais: a copia oculta e dividida.
MAX_DESTINATARIOS_POR_EMAIL = 90


def load_email_settings() -> dict:
    stored = load_config().get(EMAIL_CONFIG_KEY)
    settings = dict(DEFAULT_EMAIL_SETTINGS)
    if isinstance(stored, dict):
        settings.update({k: stored.get(k) or settings[k] for k in DEFAULT_EMAIL_SETTINGS})
        settings["senha"] = unprotect_secret(stored.get("senha")) or ""
    try:
        settings["porta"] = int(settings["porta"])
    except (TypeError, ValueError):
        settings["porta"] = DEFAULT_EMAIL_SETTINGS["porta"]
    if settings["seguranca"] not in SEGURANCA_LABELS:
        settings["seguranca"] = SEGURANCA_STARTTLS
    return settings


def save_email_settings(settings: dict) -> dict:
    """Guarda o login de envio neste computador. Senha vazia mantem a que ja estava salva."""
    atual = load_email_settings()
    normalizado = dict(DEFAULT_EMAIL_SETTINGS)
    for chave in DEFAULT_EMAIL_SETTINGS:
        normalizado[chave] = str(settings.get(chave) or "").strip()
    normalizado["senha"] = str(settings.get("senha") or "") or atual["senha"]
    if not normalizado["host"]:
        raise ValidationError("Informe o servidor de envio (SMTP).")
    try:
        normalizado["porta"] = int(normalizado["porta"] or DEFAULT_EMAIL_SETTINGS["porta"])
    except ValueError as exc:
        raise ValidationError("Porta invalida.") from exc
    if not 1 <= normalizado["porta"] <= 65535:
        raise ValidationError("Porta invalida.")
    if normalizado["seguranca"] not in SEGURANCA_LABELS:
        raise ValidationError("Seguranca invalida. Use starttls, ssl ou nenhuma.")
    if "@" not in normalizado["remetente_email"]:
        raise ValidationError("Informe o email que vai aparecer como remetente.")
    normalizado["usuario"] = normalizado["usuario"] or normalizado["remetente_email"]
    stored = dict(normalizado)
    # A senha fica protegida como a do banco (DPAPI no Windows).
    stored["senha"] = protect_secret(normalizado["senha"]) if normalizado["senha"] else None
    config = load_config()
    config[EMAIL_CONFIG_KEY] = stored
    save_config(config)
    return normalizado


def _conectar(settings: dict, timeout: float = 30):
    contexto = ssl.create_default_context()
    if settings["seguranca"] == SEGURANCA_SSL:
        smtp = smtplib.SMTP_SSL(settings["host"], settings["porta"], timeout=timeout, context=contexto)
    else:
        smtp = smtplib.SMTP(settings["host"], settings["porta"], timeout=timeout)
        if settings["seguranca"] == SEGURANCA_STARTTLS:
            smtp.starttls(context=contexto)
    if settings["usuario"]:
        smtp.login(settings["usuario"], settings["senha"])
    return smtp


class EmailSenderService:
    """Envia emails pelo login cadastrado no DocFlow (SMTP) - para a equipe enviar apertando um
    botao, sem depender do Claude nem do programa de email."""

    def __init__(self, settings_loader=load_email_settings, connect=_conectar) -> None:
        self._settings_loader = settings_loader
        self._connect = connect

    def settings(self) -> dict:
        return self._settings_loader()

    def configurado(self) -> bool:
        settings = self.settings()
        return bool(settings["host"] and settings["remetente_email"])

    def remetente(self) -> str:
        settings = self.settings()
        return formataddr((settings["remetente_nome"], settings["remetente_email"])) if settings["remetente_email"] else ""

    def testar(self, settings: dict | None = None) -> str:
        """Manda um email de teste para o proprio remetente. Devolve para onde foi."""
        settings = settings or self.settings()
        mensagem = {
            "para": [settings["remetente_email"]],
            "cco": [],
            "assunto": "Teste de envio do DocFlow",
            "corpo": "Se este email chegou, o DocFlow ja consegue enviar as mensagens por este endereço.",
        }
        resultado = self.enviar_lote([mensagem], settings=settings)[0]
        if not resultado["ok"]:
            raise ValidationError(resultado["erro"])
        return settings["remetente_email"]

    def enviar_lote(self, mensagens: list[dict], on_progress=None, settings: dict | None = None) -> list[dict]:
        """mensagens: [{"para": [...], "cco": [...], "assunto", "corpo"}]. Usa uma conexao so e
        devolve, na mesma ordem, {"ok": True} ou {"ok": False, "erro": "..."}. Erro de login ou
        de conexao interrompe tudo (ValidationError); recusa de uma mensagem nao para as outras."""
        settings = settings or self.settings()
        if not (settings["host"] and settings["remetente_email"]):
            raise ValidationError("Configure o email de envio primeiro (Envios automáticos > Email de envio).")
        try:
            smtp = self._connect(settings)
        except smtplib.SMTPAuthenticationError as exc:
            raise ValidationError(
                "O servidor recusou o usuario ou a senha. No Gmail e no Microsoft 365 use uma "
                "senha de app (a senha normal costuma ser bloqueada)."
            ) from exc
        except (smtplib.SMTPException, OSError, socket.timeout) as exc:
            raise ValidationError(f"Nao foi possivel conectar ao servidor de email: {exc}") from exc
        remetente = formataddr((settings["remetente_nome"], settings["remetente_email"]))
        resultados: list[dict] = []
        try:
            for numero, mensagem in enumerate(mensagens):
                if on_progress:
                    on_progress(numero, len(mensagens))
                try:
                    for parte in self._partes(mensagem, settings["remetente_email"]):
                        smtp.send_message(self._montar(parte, remetente), to_addrs=parte["para"] + parte["cco"])
                    resultados.append({"ok": True})
                except (smtplib.SMTPException, OSError) as exc:
                    resultados.append({"ok": False, "erro": f"Recusado pelo servidor: {exc}"})
        finally:
            try:
                smtp.quit()
            except (smtplib.SMTPException, OSError):
                pass
        if on_progress:
            on_progress(len(mensagens), len(mensagens))
        return resultados

    @staticmethod
    def _partes(mensagem: dict, remetente_email: str) -> list[dict]:
        """Copia oculta grande vira varios emails iguais, cada um com parte da lista."""
        para = list(mensagem.get("para") or []) or [remetente_email]
        cco = list(mensagem.get("cco") or [])
        if not cco:
            return [{**mensagem, "para": para, "cco": []}]
        return [
            {**mensagem, "para": para, "cco": cco[i : i + MAX_DESTINATARIOS_POR_EMAIL]}
            for i in range(0, len(cco), MAX_DESTINATARIOS_POR_EMAIL)
        ]

    @staticmethod
    def _montar(mensagem: dict, remetente: str) -> EmailMessage:
        email = EmailMessage()
        email["From"] = remetente
        email["To"] = ", ".join(mensagem["para"])
        email["Subject"] = mensagem["assunto"]
        email["Message-ID"] = make_msgid(domain=remetente.rsplit("@", 1)[-1].strip(">") or None)
        # Cco nao vai no cabecalho: so na lista de entrega (to_addrs), para ninguem ver os outros.
        email.set_content(mensagem["corpo"])
        return email
