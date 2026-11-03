from __future__ import annotations

import smtplib
import socket
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path
import shutil

from documentos_empresa_app.utils.common import CONFIG_DIR, ValidationError
from documentos_empresa_app.utils.email_format import cid_imagem, imagens_usadas, para_html, texto_com_assinatura
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
# Assinatura: fica a parte do login (da para cadastrar antes de ter o email de envio) e serve
# tambem ao Claude, que envia pela ferramenta de email dele. A imagem e copiada para a pasta
# de configuracao do DocFlow.
SIGNATURE_CONFIG_KEY = "assinatura_email"
SIGNATURE_IMAGE_NAME = "assinatura_email"
SIGNATURE_CID = "assinatura_docflow"
SIGNATURE_IMAGE_TYPES = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".gif": "gif"}
SIGNATURE_MAX_BYTES = 1_000_000
# Largura maxima da imagem no email (px): imagem maior e mostrada reduzida.
SIGNATURE_MAX_WIDTH = 600
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


def load_email_signature() -> dict:
    """{"texto": texto marcado, "imagem": caminho do arquivo ou "", "largura": px ou None}."""
    config = load_config()
    stored = config.get(SIGNATURE_CONFIG_KEY)
    if not isinstance(stored, dict):
        # A 2.0.7 guardava so o texto junto do login.
        antigo = config.get(EMAIL_CONFIG_KEY)
        stored = {"texto": antigo.get("assinatura") if isinstance(antigo, dict) else ""}
    imagem = ""
    nome = str(stored.get("imagem") or "")
    if nome and Path(nome).name == nome and (CONFIG_DIR / nome).is_file():
        imagem = str(CONFIG_DIR / nome)
    try:
        largura = int(stored.get("largura") or 0) or None
    except (TypeError, ValueError):
        largura = None
    return {"texto": str(stored.get("texto") or ""), "imagem": imagem, "largura": largura if imagem else None}


def save_email_signature(texto: str | None, imagem: str | None = None, largura: int | None = None) -> dict:
    """Guarda a assinatura. imagem: caminho de uma imagem nova (e copiada), "" tira a imagem,
    None mantem a atual. largura: como a imagem aparece no email (px; limitada a 600)."""
    atual = load_email_signature()
    nome_imagem = Path(atual["imagem"]).name if atual["imagem"] else ""
    if imagem == "":
        nome_imagem = ""
    elif imagem and Path(imagem) != Path(atual["imagem"] or "."):
        origem = Path(imagem)
        extensao = origem.suffix.lower()
        if extensao not in SIGNATURE_IMAGE_TYPES:
            raise ValidationError("A imagem da assinatura precisa ser PNG, JPG ou GIF.")
        if not origem.is_file():
            raise ValidationError(f"Arquivo nao encontrado: {origem}")
        if origem.stat().st_size > SIGNATURE_MAX_BYTES:
            raise ValidationError("A imagem da assinatura passa de 1 MB - use uma versao menor (ela vai em todo email).")
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        for antiga in CONFIG_DIR.glob(f"{SIGNATURE_IMAGE_NAME}.*"):
            antiga.unlink(missing_ok=True)
        nome_imagem = f"{SIGNATURE_IMAGE_NAME}{extensao}"
        shutil.copyfile(origem, CONFIG_DIR / nome_imagem)
    if not nome_imagem:
        for antiga in CONFIG_DIR.glob(f"{SIGNATURE_IMAGE_NAME}.*"):
            antiga.unlink(missing_ok=True)
    largura = min(int(largura), SIGNATURE_MAX_WIDTH) if largura and nome_imagem else None
    config = load_config()
    config[SIGNATURE_CONFIG_KEY] = {"texto": str(texto or "").strip(), "imagem": nome_imagem, "largura": largura}
    save_config(config)
    return load_email_signature()


def signature_html(assinatura: dict, imagem_src: str | None = None) -> str:
    """So a assinatura em HTML (para o Claude colar no fim do email que ele monta)."""
    src = imagem_src if imagem_src is not None else (f"cid:{SIGNATURE_CID}" if assinatura.get("imagem") else None)
    return para_html("", assinatura.get("texto"), src, assinatura.get("largura")).replace("<br>\n<br>\n", "", 1)


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

    def __init__(self, settings_loader=load_email_settings, connect=_conectar, signature_loader=load_email_signature) -> None:
        self._settings_loader = settings_loader
        self._connect = connect
        self._signature_loader = signature_loader

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
            "corpo": "Se este email chegou, o DocFlow já consegue enviar as mensagens por este endereço.\n\n"
            "Abaixo, a assinatura que vai no fim de cada email.",
        }
        resultado = self.enviar_lote([mensagem], settings=settings)[0]
        if not resultado["ok"]:
            raise ValidationError(resultado["erro"])
        return settings["remetente_email"]

    def enviar_lote(self, mensagens: list[dict], on_progress=None, settings: dict | None = None) -> list[dict]:
        """mensagens: [{"para": [...], "cco": [...], "assunto", "corpo", "corpo_formatado"?}]. A
        assinatura cadastrada vai no fim de cada uma. Usa uma conexao so e
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
        assinatura = self._signature_loader()
        resultados: list[dict] = []
        try:
            for numero, mensagem in enumerate(mensagens):
                if on_progress:
                    on_progress(numero, len(mensagens))
                try:
                    for parte in self._partes(mensagem, settings["remetente_email"]):
                        email = self._montar(parte, remetente, assinatura)
                        smtp.send_message(email, to_addrs=parte["para"] + parte["cco"])
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
    def _montar(mensagem: dict, remetente: str, assinatura: dict | None = None) -> EmailMessage:
        email = EmailMessage()
        email["From"] = remetente
        email["To"] = ", ".join(mensagem["para"])
        email["Subject"] = mensagem["assunto"]
        email["Message-ID"] = make_msgid(domain=remetente.rsplit("@", 1)[-1].strip(">") or None)
        # Cco nao vai no cabecalho: so na lista de entrega (to_addrs), para ninguem ver os outros.
        # Texto puro para quem nao le HTML e o formatado (negrito, sublinhado, assinatura).
        marcado = mensagem.get("corpo_formatado") or mensagem["corpo"]
        assinatura = assinatura or {}
        texto = assinatura.get("texto")
        imagem = Path(assinatura["imagem"]) if assinatura.get("imagem") else None
        if imagem and not imagem.is_file():
            imagem = None
        email.set_content(texto_com_assinatura(marcado, texto))
        src = f"cid:{SIGNATURE_CID}" if imagem else None
        email.add_alternative(
            f'<!DOCTYPE html><html><body>{para_html(marcado, texto, src, assinatura.get("largura"))}</body></html>',
            subtype="html",
        )
        # Imagens embutidas (nao vao como anexo): o HTML aponta para elas pelo Content-ID. As do
        # meio do texto vem em mensagem["imagens"] ({id: {"tipo", "dados"}}).
        embutidas = [
            (dados["dados"], dados["tipo"], cid_imagem(imagem_id), f"imagem_{imagem_id}.{dados['tipo']}")
            for imagem_id, dados in (mensagem.get("imagens") or {}).items()
            if imagem_id in imagens_usadas(marcado)
        ]
        if imagem:
            embutidas.append(
                (imagem.read_bytes(), SIGNATURE_IMAGE_TYPES.get(imagem.suffix.lower(), "png"), SIGNATURE_CID, imagem.name)
            )
        if embutidas:
            parte_html = email.get_payload()[1]
            for dados, subtipo, cid, nome in embutidas:
                parte_html.add_related(
                    dados, maintype="image", subtype=subtipo, cid=f"<{cid}>", disposition="inline", filename=nome
                )
        return email
