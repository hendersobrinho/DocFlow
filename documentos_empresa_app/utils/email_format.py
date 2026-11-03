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

from dataclasses import dataclass
import html
import re
from typing import Callable

NEGRITO = "b"
ITALICO = "i"
SUBLINHADO = "u"
ESTILOS = (NEGRITO, ITALICO, SUBLINHADO)
# Imagem no meio do texto: <img id="12" width="400"> - o id e o da imagem guardada no banco
# (tabela imagens_email), para valer em todos os computadores.
_IMAGEM = re.compile(r'<img id="(\d+)"(?: width="(\d+)")?>')
_TOKEN = re.compile(r'(<img id="\d+"(?: width="\d+")?>|</?[biuBIU]>|&lt;|&gt;|&amp;)')
_ENTIDADES = {"&lt;": "<", "&gt;": ">", "&amp;": "&"}
# Fonte e tamanho do corpo do email (o programa de email de quem recebe usa os dele se nao tiver).
ESTILO_CORPO = "font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.5;color:#222222"

Trecho = tuple[str, frozenset]


@dataclass(frozen=True)
class Imagem:
    """Trecho que e uma imagem: ("", frozenset({Imagem(id, largura)}))."""

    id: int
    largura: int | None = None


def imagem_do_trecho(estilos: frozenset) -> Imagem | None:
    return next((e for e in estilos if isinstance(e, Imagem)), None)


def marca_imagem(imagem_id: int, largura: int | None = None) -> str:
    return f'<img id="{int(imagem_id)}"' + (f' width="{int(largura)}"' if largura else "") + ">"


def cid_imagem(imagem_id: int) -> str:
    """Content-ID da imagem no email enviado (src="cid:...")."""
    return f"docflow_img{int(imagem_id)}"


def imagens_usadas(texto: str | None) -> list[int]:
    """Ids das imagens do texto, sem repetir, na ordem."""
    vistos: list[int] = []
    for match in _IMAGEM.finditer(str(texto or "")):
        if int(match.group(1)) not in vistos:
            vistos.append(int(match.group(1)))
    return vistos


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
        imagem = _IMAGEM.fullmatch(parte)
        if imagem:
            largura = int(imagem.group(2)) if imagem.group(2) else None
            saida.append(("", frozenset({Imagem(int(imagem.group(1)), largura)})))
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
        if saida and saida[-1][1] == estilos and not imagem_do_trecho(estilos):
            saida[-1] = (saida[-1][0] + parte_texto, estilos)
        else:
            saida.append((parte_texto, estilos))
    return saida


def de_trechos(lista: list[Trecho]) -> str:
    """Trechos -> formato guardado (o inverso de trechos())."""
    saida: list[str] = []
    for texto, estilos in lista:
        imagem = imagem_do_trecho(estilos)
        if imagem:
            saida.append(marca_imagem(imagem.id, imagem.largura))
            continue
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


def _src_padrao(imagem_id: int) -> str:
    return f"cid:{cid_imagem(imagem_id)}"


def _html_do_trecho(texto: str, estilos: frozenset, src_imagens: Callable[[int], str] = _src_padrao) -> str:
    imagem = imagem_do_trecho(estilos)
    if imagem:
        tamanho = f' width="{imagem.largura}"' if imagem.largura else ""
        return f'<img src="{html.escape(src_imagens(imagem.id))}"{tamanho} alt="" style="border:0;max-width:100%">'
    conteudo = html.escape(texto, quote=False)
    # Espacos seguidos (alinhamentos) somem no HTML: o segundo vira espaco fixo.
    conteudo = conteudo.replace("  ", " &nbsp;").replace("\n", "<br>\n")
    for estilo in ESTILOS:
        if estilo in estilos:
            conteudo = f"<{estilo}>{conteudo}</{estilo}>"
    return conteudo


def para_html(
    texto: str | None,
    assinatura: str | None = None,
    imagem_src: str | None = None,
    largura: int | None = None,
    src_imagens: Callable[[int], str] = _src_padrao,
) -> str:
    """O email formatado, com a assinatura no fim (se houver): o texto dela e, embaixo, a
    imagem (imagem_src: 'cid:...' no email enviado, o arquivo na previa). src_imagens: de onde
    vem cada imagem do meio do texto (padrao: 'cid:docflow_img<id>', embutida no email)."""
    corpo = "".join(_html_do_trecho(t, e, src_imagens) for t, e in trechos(texto))
    fim = ""
    if assinatura and para_texto(assinatura).strip():
        fim = "".join(_html_do_trecho(t, e) for t, e in trechos(assinatura.strip()))
    if imagem_src:
        tamanho = f' width="{int(largura)}"' if largura else ""
        imagem = f'<img src="{html.escape(imagem_src)}"{tamanho} alt="Assinatura" style="border:0">'
        fim = f"{fim}<br>\n{imagem}" if fim else imagem
    if fim:
        corpo = corpo.rstrip() + "<br>\n<br>\n" + fim
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
