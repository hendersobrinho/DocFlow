"""Formatacao simples dos textos de email: negrito, italico e sublinhado.

O texto guardado (corpo do envio, modelos, assinatura) continua sendo texto comum, com
quebras de linha normais, e so tres marcas: <b>negrito</b>, <i>italico</i> e <u>sublinhado</u>.
Os caracteres < > & digitados pela pessoa ficam como &lt; &gt; &amp;. Assim os campos entre
chaves ({empresa}, {documentos}...) continuam funcionando, e o texto antigo, sem marca
nenhuma, segue igual.

Daqui saem as tres versoes de cada mensagem: HTML (o email formatado), texto puro (a parte
de texto do email, o rascunho e a lista do Claude) e WhatsApp (*negrito* e _italico_).
"""

from __future__ import annotations

import html
import re

NEGRITO = "b"
ITALICO = "i"
SUBLINHADO = "u"
ESTILOS = (NEGRITO, ITALICO, SUBLINHADO)
_TOKEN = re.compile(r"(</?[biuBIU]>|&lt;|&gt;|&amp;)")
_ENTIDADES = {"&lt;": "<", "&gt;": ">", "&amp;": "&"}
# Fonte e tamanho do corpo do email (o programa de email de quem recebe usa os dele se nao tiver).
ESTILO_CORPO = "font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.5;color:#222222"

Trecho = tuple[str, frozenset]


def escapar(texto: str) -> str:
    """Texto digitado -> formato guardado (sem nenhuma marca)."""
    return str(texto).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def trechos(texto: str | None) -> list[Trecho]:
    """Quebra o texto marcado em trechos (texto, estilos). Marca sem par e ignorada; '<' e '&'
    soltos (texto antigo) ficam como estao."""
    ativos: set[str] = set()
    saida: list[Trecho] = []
    for parte in _TOKEN.split(str(texto or "")):
        if not parte:
            continue
        if parte in _ENTIDADES:
            parte_texto = _ENTIDADES[parte]
        elif _TOKEN.fullmatch(parte):
            estilo = parte.strip("</>").lower()
            if parte.startswith("</"):
                ativos.discard(estilo)
            else:
                ativos.add(estilo)
            continue
        else:
            parte_texto = parte
        estilos = frozenset(ativos)
        if saida and saida[-1][1] == estilos:
            saida[-1] = (saida[-1][0] + parte_texto, estilos)
        else:
            saida.append((parte_texto, estilos))
    return saida


def de_trechos(lista: list[Trecho]) -> str:
    """Trechos -> formato guardado (o inverso de trechos())."""
    saida: list[str] = []
    for texto, estilos in lista:
        if not texto:
            continue
        abre = "".join(f"<{e}>" for e in ESTILOS if e in estilos)
        fecha = "".join(f"</{e}>" for e in reversed(ESTILOS) if e in estilos)
        saida.append(f"{abre}{escapar(texto)}{fecha}")
    # Junta marcas que fecham e abrem de novo logo em seguida: <b>a</b><b>b</b> -> <b>ab</b>.
    return re.sub(r"</([biu])><\1>", "", "".join(saida))


def tem_formatacao(texto: str | None) -> bool:
    return any(estilos for _texto, estilos in trechos(texto))


def para_texto(texto: str | None) -> str:
    """Sem marcas: o texto como a pessoa le."""
    return "".join(parte for parte, _estilos in trechos(texto))


def _html_do_trecho(texto: str, estilos: frozenset) -> str:
    conteudo = html.escape(texto, quote=False)
    # Espacos seguidos (alinhamentos) somem no HTML: o segundo vira espaco fixo.
    conteudo = conteudo.replace("  ", " &nbsp;").replace("\n", "<br>\n")
    for estilo in ESTILOS:
        if estilo in estilos:
            conteudo = f"<{estilo}>{conteudo}</{estilo}>"
    return conteudo


def para_html(texto: str | None, assinatura: str | None = None) -> str:
    """O email formatado, com a assinatura no fim (se houver)."""
    corpo = "".join(_html_do_trecho(t, e) for t, e in trechos(texto))
    if assinatura and para_texto(assinatura).strip():
        corpo = corpo.rstrip() + "<br>\n<br>\n" + "".join(_html_do_trecho(t, e) for t, e in trechos(assinatura.strip()))
    return f'<div style="{ESTILO_CORPO}">{corpo}</div>'


def texto_com_assinatura(texto: str | None, assinatura: str | None = None) -> str:
    """A parte de texto puro do email: corpo + assinatura, sem marcas."""
    corpo = para_texto(texto)
    fim = para_texto(assinatura).strip() if assinatura else ""
    return f"{corpo.rstrip()}\n\n{fim}" if fim else corpo


def para_whatsapp(texto: str | None) -> str:
    """Negrito vira *assim*, italico vira _assim_; sublinhado nao existe no WhatsApp. As marcas
    ficam coladas no texto (o WhatsApp nao formata '* assim *') e nao atravessam linhas."""
    saida: list[str] = []
    for texto_trecho, estilos in trechos(texto):
        abre = ("*" if NEGRITO in estilos else "") + ("_" if ITALICO in estilos else "")
        if not abre:
            saida.append(texto_trecho)
            continue
        fecha = abre[::-1]
        linhas = []
        for linha in texto_trecho.split("\n"):
            miolo = linha.strip()
            if not miolo:
                linhas.append(linha)
                continue
            inicio = linha[: len(linha) - len(linha.lstrip())]
            fim = linha[len(linha.rstrip()) :]
            linhas.append(f"{inicio}{abre}{miolo}{fecha}{fim}")
        saida.append("\n".join(linhas))
    return "".join(saida)


class _CamposSeguros(dict):
    """Campo desconhecido fica como esta ({assim}), em vez de quebrar o texto."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def preencher(texto: str | None, campos: dict) -> str:
    """Troca {empresa}, {documentos}... no texto marcado. Os dados entram escapados: um nome
    de empresa com '<' ou '&' nao vira marca."""
    seguros = _CamposSeguros({chave: escapar(valor) for chave, valor in campos.items()})
    return str(texto or "").format_map(seguros)
