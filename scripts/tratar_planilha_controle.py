"""Trata a "Planilha de Controle Unificada" (aba do ano) e gera uma planilha pronta para o
Importar > Cadastro completo do DocFlow, com o antes x depois e o relatorio do que ficou
de fora.

Uso:
    python scripts/tratar_planilha_controle.py "001 - Planilha de Controle Unificada 2026 (1).xlsx"
    (opcoes: --aba 2026 --ano 2026 --saida "arquivo.xlsx")

Regras principais (as mesmas do relatorio, aba "Regras"):
- Tipo diz o que e o documento; o nome fica curto (extrato de conta corrente = so o banco).
- Uma conta so naquele banco: o numero sai do nome e vai para a observacao do documento.
  Duas ou mais no mesmo banco: o numero fica no nome para diferenciar.
- "Aberta em" / "Encerrada em" no nome vira observacao e ajusta os meses (X antes de abrir,
  Encerrado a partir do fechamento).
- Linha "Documentacao (Cliente so envia...)" vira observacao da empresa; quando diz que o
  cliente envia o movimento contabil, vira o documento "Movimento Contabil".
- Emails da coluna OBSERVACAO vao para a empresa; anotacoes de contato digitadas no lugar do
  documento nao viram documento (vao para a observacao da empresa e para o relatorio).
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

MESES = ("Janeiro", "Fevereiro", "Marco", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro",
         "Outubro", "Novembro", "Dezembro")
MESES_PT = {"janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7,
            "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}

# Tipos do sistema (os que ja existem no DocFlow mantem o nome exato, para reaproveitar).
T_CC = "Extratos CC"
T_APLIC = "Extratos aplicacao"
T_EMPREST = "Empréstimos e Financiamentos"
T_CARTAO = "Cartões"
T_COMPROV = "Comprovantes"
T_PLAN = "Planilhas e Relatórios"
T_INFORME = "Informe de Rendimentos"
T_ANUIDADE = "Anuidades"
T_MOV = "Movimento contábil"
T_OUTROS = "Outros"

# Informe de Rendimentos fica mensal: o "trimestral" do sistema e jan/abr/jul/out e o
# escritorio cobra os informes em mar/jun/set/dez - os outros meses ja vem com X.
REGRA_DO_TIPO = {T_ANUIDADE: "anual"}  # os outros: mensal

# Bancos e instituicoes: (padrao procurado no texto sem acento e minusculo, nome padronizado).
# A ordem importa: os mais especificos primeiro.
BANCOS = (
    (r"banco do\s+brasil|b\.\s*brasil|banco brasil|banco brsil|\bbb\b|brasil rende|rende facil bb", "Banco do Brasil"),
    (r"banestes", "Banestes"),
    (r"bradesco|badesco", "Bradesco"),
    (r"caixa econ|\bcef\b|c\.e\.f|\bcaixa\b(?!inha)|girocaixa", "Caixa Economica"),
    (r"sicoob", "Sicoob"),
    (r"sicredi", "Sicredi"),
    (r"unicred", "Unicred"),
    (r"santander|santarder|getnet", "Santander"),
    (r"itau|\brede\b", "Itaú"),
    (r"\binter\b", "Inter"),
    (r"nubank|nu bank", "Nubank"),
    (r"c6\s*bank|\bc6\b", "C6 Bank"),
    (r"btg", "BTG Pactual"),
    (r"\bxp\b", "XP Investimentos"),
    (r"pagbank|pagseguro|paguebank", "PagBank"),
    (r"stone|\bton\b", "Stone"),
    (r"mercado pago", "Mercado Pago"),
    (r"cielo", "Cielo"),
    (r"infinity", "InfinitePay"),
    (r"sumup", "SumUp"),
    (r"picpay", "PicPay"),
)

# Como os bancos aparecem escritos, para tirar do texto do produto sem sobrar pedaco
# ("Banco do Brasil Rende Facil" -> "Rende Facil").
NOMES_ESCRITOS_DE_BANCO = re.compile(
    r"(?i)banco\s+do\s+brasil|banco\s+brasil|b\.\s*brasil|\bbrasil\b|\bbb\b|banestes|bradesco|badesco|"
    r"caixa\s+econ[oô]mica(\s+federal)?|\bc\.?e\.?f\b|\bcaixa\b|sicoob|sicredi|unicred|santander|santarder|"
    r"ita[uú]|\binter\b|nubank|nu bank|\bxp\b|btg(\s+pactual)?|pagbank|pagseguro|\bbanco\b"
)

# Meios de recebimento padronizados.
MEIO_EMAIL, MEIO_WPP, MEIO_ONVIO, MEIO_FISICO, MEIO_ACESSO = "Email", "WhatsApp", "Onvio", "Físico", "Acesso ao banco"

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def sem_acento(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in texto if not unicodedata.combining(c)).lower()


def limpa(texto) -> str:
    return re.sub(r"\s+", " ", str(texto or "")).strip(" -–")


@dataclass
class Documento:
    linha: int
    original: str
    envio_original: str
    obs_original: str
    tipo: str = ""
    nome: str = ""
    produto: str = ""          # detalhe que pode virar parte do nome se houver repeticao
    banco: str | None = None
    conta: str | None = None   # numero de conta/contrato encontrado
    conta_contexto: str | None = None  # conta corrente logo acima (aplicacao daquela conta)
    meios: list[str] = field(default_factory=list)
    obs: list[str] = field(default_factory=list)
    meses: list[str] = field(default_factory=lambda: [""] * 12)
    acoes: list[str] = field(default_factory=list)  # o que foi feito (para o antes x depois)


@dataclass
class Empresa:
    linha: int
    codigo_original: str
    codigo: int | None
    nome_original: str
    nome: str = ""
    emails: list[str] = field(default_factory=list)
    contato: str = ""
    obs: list[str] = field(default_factory=list)
    docs: list[Documento] = field(default_factory=list)
    juntados: list[tuple[Documento, Documento]] = field(default_factory=list)  # (removido, mantido)


@dataclass
class ForaDaImportacao:
    linha: int
    empresa: str
    conteudo: str
    motivo: str
    sugestao: str


# Datas -----------------------------------------------------------------------------


def acha_mes_ano(texto: str, ano_ref: int) -> tuple[int, int] | None:
    """Primeira data do texto como (ano, mes): 24/11/2025, 05/2026, 03.2026, marco/2026,
    agosto/25, 03/09 (dia/mes, ano de referencia)."""
    t = sem_acento(texto)
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", t)
    if m:
        ano = int(m.group(3)) + (2000 if len(m.group(3)) == 2 else 0)
        return ano, int(m.group(2))
    m = re.search(r"\b(\d{1,2})[./-](\d{4})\b", t)
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(2)), int(m.group(1))
    m = re.search(r"(" + "|".join(MESES_PT) + r")\s*/?\s*(\d{2,4})", t)
    if m:
        ano = int(m.group(2)) + (2000 if len(m.group(2)) == 2 else 0)
        return ano, MESES_PT[m.group(1)]
    m = re.search(r"\b(\d{1,2})/(\d{1,2})\b", t)
    if m and 1 <= int(m.group(2)) <= 12:
        return ano_ref, int(m.group(2))
    return None


def tira_datas(texto: str) -> str:
    t = re.sub(r"\d{1,2}/\d{1,2}/\d{2,4}", " ", texto)
    t = re.sub(r"\b\d{1,2}[./-]\d{4}\b", " ", t)
    t = re.sub(r"(?i)(janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s*/?\s*\d{2,4}", " ", t)
    return t


# Documento: classificacao ----------------------------------------------------------


def acha_banco(texto: str) -> str | None:
    t = sem_acento(texto)
    for padrao, nome in BANCOS:
        if re.search(padrao, t):
            return nome
    return None


def acha_numero(texto: str) -> str | None:
    """Numero de conta/contrato (ignora datas e anos)."""
    t = re.sub(r"(?i)\bag\.?:?\s*[\d-]+", " ", tira_datas(texto))  # agencia nao e a conta
    curto = re.search(r"(?i)c/?c\.?\s*(\d{3})\b(?![\d.-])", t)
    candidatos = re.findall(r"(?:n[ºo°]\s*)?\d[\d.\- ]*\d(?:-[\dxXpP])?|\d{3,}-[\dxXpP]", t)
    numeros = [limpa(c.replace("nº", "").replace("Nº", "")) for c in candidatos]
    numeros = [n for n in numeros if len(re.sub(r"\D", "", n)) >= 4]
    if not numeros:
        return curto.group(1) if curto else None
    # "2042 / 003 / 2993-8" (agencia / operacao / conta): a conta e a que tem digito.
    com_digito = [n for n in numeros if re.search(r"-[\dxXpP]$", n)]
    return (com_digito or numeros)[0]


QUALIFICADORES = (("consolidad", "Extrato consolidado"), ("unificad", "Extrato unificado"), ("identificad", "Extrato identificado"),
                  (r"\bpf\b", "Conta PF"), (r"pj\b", "Conta PJ"))


def detalhes_abertura_fechamento(doc: Documento, texto: str, ano: int) -> None:
    t = sem_acento(texto)
    if re.search(r"encerr|fechou|finalizou|cancelad", t):
        data = acha_mes_ano(texto, ano)
        if data:
            doc.obs.append(f"Encerrada em {data[1]:02d}/{data[0]}")
            if data[0] == ano:
                marca_encerrado(doc, data[1])
        else:
            doc.obs.append("Encerrada")
            usados = [i for i, v in enumerate(doc.meses) if v in ("OK", "P")]
            if usados and usados[-1] < 11 and all(v in ("", "X") for v in doc.meses[usados[-1] + 1:]):
                marca_encerrado(doc, usados[-1] + 2)
                doc.acoes.append("sem data: Encerrado no mês seguinte ao último recebido")
    if re.search(r"abert|abriu|abertura|a ?partir|inicio", t):
        data = acha_mes_ano(texto, ano)
        if data:
            doc.obs.append(f"Aberta em {data[1]:02d}/{data[0]}")
            if data[0] == ano:
                for i in range(data[1] - 1):
                    if not doc.meses[i]:
                        doc.meses[i] = "X"
                        if "meses antes da abertura = X" not in doc.acoes:
                            doc.acoes.append("meses antes da abertura = X")


def marca_encerrado(doc: Documento, mes: int) -> None:
    """Encerrado no mes do fechamento (ou no seguinte, se o mes ainda foi recebido) e nada
    depois - o sistema bloqueia os meses depois de Encerrado."""
    i = mes - 1
    while i < 12 and doc.meses[i] in ("OK", "P"):
        i += 1
    if i >= 12:
        return
    doc.meses[i] = "Encerrado"
    for j in range(i + 1, 12):
        doc.meses[j] = ""
    doc.acoes.append(f"{MESES[i][:3]} = Encerrado")


def classifica(doc: Documento, ano: int) -> str | None:
    motivo = _classifica(doc, ano)
    if doc.tipo and doc.tipo != T_CC:
        doc.obs = [o for o in doc.obs if o not in ("Conta PF", "Conta PJ")]
    return motivo


def _classifica(doc: Documento, ano: int) -> str | None:
    """Preenche tipo/nome/produto/obs. Devolve um motivo quando a linha nao e documento."""
    texto = limpa(doc.original)
    t = sem_acento(texto)
    banco = acha_banco(texto)
    doc.banco = banco

    if re.match(r"(ainda sem|sem conta|abertura dia|so envia|falar com)", t):
        return "anotacao"
    if "senha" in t:
        doc.acoes.append("senha retirada do nome (não copiada)")
        texto = re.split(r"(?i)\s*-?\s*senha", texto)[0]
        t = sem_acento(texto)

    detalhes_abertura_fechamento(doc, texto, ano)
    for chave, rotulo in QUALIFICADORES:
        if re.search(chave, t):
            doc.obs.append(rotulo)

    def com_banco(base: str) -> str:
        return f"{base} {banco}" if banco else base

    # Anuidades de conselho (CRM, CRO, CREA, CRF): cobradas em janeiro.
    m = re.match(r"(crm|cro|crea|crf)\b", t)
    if m:
        doc.tipo, doc.nome = T_ANUIDADE, m.group(1).upper()
        return None
    if re.search(r"inf[o]?r?me|rendiemnto", t) and "rendi" in t:
        doc.tipo = T_INFORME
        doc.nome = banco or "Informe de Rendimentos"
        if "anual" in t:
            doc.obs.append("Anual")
        return None
    if re.search(r"emprest|emrpest|financiamento|saldo devedor|pronampe|giro facil", t):
        doc.tipo = T_EMPREST
        doc.nome = banco or "Empréstimo"  # o tipo ja diz que e emprestimo
        numero = acha_numero(texto)
        if numero:
            doc.conta = numero
            doc.obs.append(f"Contrato {numero}")
        valor = re.search(r"R\$\s*[\d.,]+", texto)
        if valor:
            doc.obs.append(f"Valor {valor.group(0)}")
        return None
    if re.search(r"dem[o]?n?s?t?r", t) and ("evolu" in t or re.fullmatch(r"dem[o]?n?s?t?rativo\s+\w+", t)):
        # "Demostrativo Banestes" (sem "evolucao") tambem e o demonstrativo da aplicacao.
        doc.tipo, doc.nome = T_APLIC, com_banco("Demonstrativo de Evolução")
        if "aplica" in t:
            doc.obs.append("Da aplicação")
        return None
    if "conta capital" in t:
        doc.tipo, doc.nome = T_APLIC, com_banco("Conta Capital")
        if "trimestral" in t:
            doc.obs.append("Trimestral")
        return None
    if "poupanca" in t:
        doc.tipo, doc.nome = T_APLIC, com_banco("Poupança")
        numero = acha_numero(texto)
        if numero:
            doc.conta = numero
            doc.obs.append(f"Conta {numero}")
        return None
    adquirente = re.search(r"pagbank|pagseguro|stone|\bton\b|cielo|getnet|\brede\b|infinity|sumup|mercado pago", t)
    if re.search(r"cart[ao]|fatura|recebimento cart|getnet|\brede\b|cielo", t) or (
        adquirente and re.search(r"relatorio|venda|receb", t)
    ):
        if re.search(r"fatura|a pagar|cartao de credito(?! sicoob)|cartao de credito$", t) and not re.search(r"receb|venda", t):
            doc.tipo, doc.nome = T_CARTAO, com_banco("Fatura Cartão")
            bandeira = re.search(r"(?i)(visa|mastercard)", texto)
            final = re.findall(r"\d{4}(?!.*\d{4})", texto)
            if bandeira:
                doc.produto = bandeira.group(1).title()
                doc.obs.append(doc.produto + (f" final {final[0]}" if final else ""))
        else:
            tipo_rel = "Vendas" if "venda" in t else "Recebimentos"
            doc.tipo, doc.nome = T_CARTAO, com_banco(f"{tipo_rel} Cartão")
            if "excel" in t:
                doc.obs.append("Em Excel")
        return None
    if banco and re.match(r"(cc|c/c|conta corrente|extratos? (c/c|cc|da conta corrente))\b", t):
        pass  # conta corrente, mesmo que o nome do banco tenha "invest" (ex: CC XP Investimento)
    elif re.search(r"aplica|aplic\.|cdb|rdc|invest|rende facil|fundo|renda fixa|contamax|modificacao de posicao|\bdi\b", t):
        doc.tipo, doc.nome = T_APLIC, banco or "Aplicação"  # o tipo ja diz que e aplicacao
        produto = NOMES_ESCRITOS_DE_BANCO.sub(" ", texto)
        produto = re.sub(r"(?i)aplica[cç](õ|o)es|aplica[cç][aã]o|aplic\.|extratos? de|extratos?|consolidad[ao]|"
                         r"investimentos?$", " ", produto)
        produto = re.sub(r"\(.*?\)", " ", tira_datas(produto))
        produto = limpa(re.sub(r"(?i)encerr\w*|finaliz\w*|fechou|\bem\b|a partir de|abriu\w*|\s-\s|^-|-$", " ", produto))
        numero = acha_numero(texto)
        if numero:
            doc.conta = numero
            produto = limpa(produto.replace(numero, ""))
        if produto and len(produto) > 1:
            doc.produto = produto
            doc.obs.append(produto)
        return None
    if re.search(r"^iss\b|fgts|aluguel|moeda estrangeira|cambio", t):
        doc.tipo = T_OUTROS
        doc.nome = {"iss": "ISS", "fgts": "FGTS"}.get(t.split()[0], limpa(re.sub(r"\(.*?\)", "", texto)))
        if "aluguel" in t:
            doc.nome = "Aluguel"
        if "moeda" in t or "cambio" in t:
            doc.nome = "Câmbio (moeda estrangeira)"
        return None
    if re.search(r"comprovante|pagamento|pix|agendamento|transfer|consultar", t):
        if "iss" in t.split():
            doc.tipo, doc.nome = T_OUTROS, "ISS"
            return None
        if "pix" in t:
            base = "Pagamentos PIX"
        elif "convenio" in t:
            base = "Pagamentos de Convênios"
        elif "titulo" in t:
            base = "Pagamentos de Títulos"
        elif "transfer" in t:
            base = "Transferências"
        elif "agendamento" in t:
            base = "Agendamentos"
        elif "relatorio" in t or "contas pagas" in t:
            base = "Relatório de Pagamentos"
        else:
            base = "Comprovantes de Pagamento"
        doc.tipo, doc.nome = T_COMPROV, com_banco(base)
        if "pdf" in t:
            doc.obs.append("Em PDF")
        return None
    if re.search(r"^pl[\. ]|planilha|relatorio|controle|caixinha|^repasse|distribuicao de lucros", t):
        doc.tipo = T_PLAN
        if "distribuicao de lucros" in t and "-" in texto:
            doc.nome = "Distribuição de Lucros - " + limpa(texto.split("-", 1)[1].split("(")[0])
        elif re.search(r"rateio|repasse", t) and "nf" not in t:
            doc.nome = "Planilha de Repasse"
        elif re.search(r"lucro|rendimentos \(|socio", t):
            doc.nome = "Planilha de Distribuição de Lucros"
            if "reinf" in t:
                doc.obs.append("REINF")
        elif "repasse" in t and "nf" not in t:
            doc.nome = "Planilha de Repasse"
        elif re.search(r"caixa|caixinha", t):
            doc.nome = "Controle de Caixa"
        elif "financeir" in t:
            doc.nome = "Planilha Financeira"
        elif "cheque" in t:
            doc.nome = "Planilha de Cheques"
        elif "despesa" in t:
            doc.nome = "Planilha de Despesas"
        elif re.search(r"emitid|emissao", t):
            doc.nome = "Relatório de Notas Fiscais"
        elif re.search(r"receb|entrada", t):
            doc.nome = "Planilha de Recebimentos"
            if "fat" in t:
                doc.obs.append("Com faturamento")
        elif "nf" in t:
            doc.nome = "Planilha de Notas Fiscais" + (" e Repasse" if "repasse" in t else "")
        elif "pagamento" in t:
            doc.nome = "Relatório de Pagamentos"
        else:
            doc.nome = limpa(texto)
        return None
    if "movimento contabil" in t:
        doc.tipo, doc.nome = T_MOV, "Movimento Contábil"
        return None

    # Extrato de conta corrente (PF/PJ so faz sentido para conta corrente).
    if banco:
        doc.tipo, doc.nome = T_CC, banco
        numero = acha_numero(texto)
        if numero:
            doc.conta = numero
            agencia = re.search(r"(?i)ag\.?:?\s*([\d-]+)", texto)
            doc.obs.append(f"C/C {numero}" + (f" (ag. {agencia.group(1)})" if agencia else ""))
        if "sem moviment" in t:
            doc.obs.append("Sem movimentação")
        if "sem acesso" in t:
            doc.obs.append("Sem acesso")
        if "onvio" in t:
            doc.obs.append(limpa(re.sub(r"(?i).*?(posta no onvio.*)", r"\1", texto)).capitalize())
        return None
    if re.match(r"(banco|extrato bancario|extrato identificado|extrato aplicacao|cc |c/c|conta corrente)", t) or t in ("banco", "documentacao"):
        return "sem_banco"
    return "desconhecido"


# Meios de recebimento ----------------------------------------------------------------


def normaliza_meios(envio: str) -> tuple[list[str], str]:
    """(meios padronizados, anotacao que sobrou)."""
    texto = limpa(envio)
    t = sem_acento(texto)
    if not t or t in ("ok", "?", "none", "extratos", "extrato"):
        return [], ""
    meios = []
    if "onvio" in t or "oonvio" in t:
        meios.append(MEIO_ONVIO)
    if re.search(r"e-? ?mail|email", t):
        meios.append(MEIO_EMAIL)
    if re.search(r"whats|wpp|zap|whatsaapp", t):
        meios.append(MEIO_WPP)
    if re.search(r"fisico|correio|livreto", t):
        meios.append(MEIO_FISICO)
    if re.search(r"metodos tem acesso|\bacesso\b", t) and "somente o cliente" not in t and "drive" not in t:
        meios.append(MEIO_ACESSO)
    simples = {"onvio", "oonvio", "e-mail", "email", "e- mail", "whatsapp", "fisico", "fisico/e-mail", "fisico/ e-mail",
               "e-mail/ fisico", "e-mail - fisico", "fisico/onvio", "fisico/ onvio", "onvio/fisico/e-mail",
               "whatsapp / e-mail", "e-mail/ zap", "individual/whatsapp", "fisico/ acesso", "acesso",
               "metodos tem acesso ao banco", "whatsaapp", "extrato/ e-mail", "fisico/ digital", "digital"}
    nota = ""
    if t not in simples:
        nota = texto
    if "grupo zap" in t:
        nota = "Grupo de WhatsApp"
    if "wpp final" in t:
        nota = "WhatsApp " + re.sub(r"(?i)wpp\s*", "", texto).lower()
    if "ellen" in t:
        nota = "Ellen envia"
    return list(dict.fromkeys(meios)), nota


# Observacoes -------------------------------------------------------------------------

PALAVRAS_DE_NOTA = ("tem ", "documento", "envia", "prioridade", "falar", "solicitar", "importa", "sem ", "nao ",
                    "empresa", "grupo", "socio", "respons", "a partir", "so ", "mesmos", "manda", "apos", "esta")


def parece_nome_de_pessoa(texto: str) -> bool:
    t = sem_acento(texto)
    if not texto or any(c.isdigit() for c in texto) or len(texto.split()) > 5:
        return False
    if any(p in f"{t} " for p in PALAVRAS_DE_NOTA):
        return False
    return True


def separa_obs(obs: str) -> tuple[list[str], str]:
    emails = EMAIL_RE.findall(obs or "")
    resto = limpa(re.sub(r"[/;,]\s*$", "", EMAIL_RE.sub(" ", obs or "")).strip(" /;,:"))
    resto = limpa(re.sub(r"\s*/\s*$", "", resto))
    return emails, resto


# Leitura e montagem --------------------------------------------------------------------


def le_planilha(caminho: Path, aba: str, ano: int):
    wb = load_workbook(caminho, data_only=True)
    ws = wb[aba]
    # Celulas mescladas: o codigo e o nome da empresa costumam estar mesclados no bloco todo
    # (as vezes o codigo comeca uma linha depois do nome). Mapa linha -> (inicio do bloco, valor).
    mescladas: dict[tuple[int, int], tuple[int, object]] = {}
    for faixa in ws.merged_cells.ranges:
        if faixa.min_col <= 2:
            valor = ws.cell(faixa.min_row, faixa.min_col).value
            for linha in range(faixa.min_row, faixa.max_row + 1):
                for coluna in range(faixa.min_col, min(faixa.max_col, 2) + 1):
                    mescladas[(linha, coluna)] = (faixa.min_row, valor)
    empresas: list[Empresa] = []
    fora: list[ForaDaImportacao] = []
    atual: Empresa | None = None

    for r in range(1, ws.max_row + 1):
        valores = [ws.cell(r, c).value for c in range(1, 18)]
        if str(valores[0] or "").strip().lower().startswith("cód") or r < 6:
            continue
        cod, nome_emp, doc_txt, envio = (valores[0], valores[1], valores[2], valores[3])
        meses = [limpa(v) for v in valores[4:16]]
        obs = limpa(valores[16])
        if all(not limpa(v) for v in valores):
            continue

        codigo_txt = limpa(cod)
        nome_mesclado = mescladas.get((r, 2))
        dentro_do_bloco = bool(nome_mesclado and nome_mesclado[0] < r and atual and atual.linha >= nome_mesclado[0])
        if codigo_txt and not limpa(nome_emp) and dentro_do_bloco and not atual.codigo_original:
            # Codigo mesclado comecando abaixo do nome: e da mesma empresa.
            atual.codigo_original = codigo_txt
            atual.codigo = int(codigo_txt) if re.fullmatch(r"\d+", codigo_txt) else None
        elif codigo_txt or limpa(nome_emp):
            atual = Empresa(linha=r, codigo_original=codigo_txt,
                            codigo=int(codigo_txt) if re.fullmatch(r"\d+", codigo_txt) else None,
                            nome_original=limpa(nome_emp))
            trata_nome_empresa(atual)
            empresas.append(atual)
        if atual is None:
            continue

        doc = Documento(linha=r, original=limpa(doc_txt), envio_original=limpa(envio), obs_original=obs)
        for i, v in enumerate(meses):
            vv = v.upper()
            if vv in ("OK", "P", "X"):
                doc.meses[i] = vv
            elif v:
                doc.meses[i] = ""
                nota = v.strip()
                if "baixad" in sem_acento(nota):
                    atual.obs.append(nota.capitalize())
                else:
                    doc.obs.append(f"Conta {nota.lower()}")
                # So vira Encerrado se nao ha nada marcado depois (nunca apaga mes preenchido).
                if not any(limpa(x) for x in meses[i + 1:]):
                    marca_encerrado(doc, i + 1)
                    doc.acoes.append(f'"{nota}" na coluna {MESES[i][:3]} virou Encerrado')
                else:
                    doc.acoes.append(f'"{nota}" na coluna {MESES[i][:3]} foi para a observação')

        emails, resto = separa_obs(obs)
        for e in emails:
            if e.lower() not in [x.lower() for x in atual.emails]:
                atual.emails.append(e)

        primeira_linha = r == atual.linha
        if not doc.original:
            # Linha sem documento: contato/email da empresa.
            if resto:
                if not atual.contato and parece_nome_de_pessoa(resto):
                    atual.contato = resto
                else:
                    atual.obs.append(resto)
            if any(doc.meses):
                fora.append(ForaDaImportacao(r, atual.nome, f"(sem nome de documento) meses: {' '.join(m or '.' for m in doc.meses)}",
                                             "Linha com meses marcados mas sem o nome do documento.",
                                             "Informe qual é o documento ou apague a linha."))
            continue

        t_doc = sem_acento(doc.original)
        if re.match(r"documenta[cç]|documentos \(", t_doc):
            texto = re.sub(r"(?i)^documenta\w*|^documentos", "", doc.original).strip(" -")
            texto = limpa(texto.strip("() "))
            if sem_acento(texto) in ("extratos", "extrato"):
                texto = "Cliente envia os extratos"
            if texto:
                atual.obs.append(texto[0].upper() + texto[1:])
            if resto:
                if not atual.contato and parece_nome_de_pessoa(resto):
                    atual.contato = resto
                else:
                    atual.obs.append(resto)
            if re.search(r"mov", t_doc):
                doc.tipo, doc.nome = T_MOV, "Movimento Contábil"
                doc.meios = [MEIO_FISICO]
                doc.acoes.append('linha "Documentação" virou o documento Movimento Contábil (físico)')
                atual.docs.append(doc)
            continue

        motivo = classifica(doc, ano)
        if motivo == "anotacao":
            atual.obs.append(doc.original)
            fora.append(ForaDaImportacao(r, atual.nome, doc.original, "É uma anotação de contato, não um documento.",
                                         "Foi para a observação da empresa."))
            continue
        if motivo in ("sem_banco", "desconhecido"):
            fora.append(ForaDaImportacao(
                r, atual.nome, doc.original,
                "Não diz de qual banco é." if motivo == "sem_banco" else "Não deu para saber que documento é.",
                "Escreva o nome do banco/documento na planilha original e rode de novo."))
            continue

        if doc.tipo == T_ANUIDADE:
            # Anuidade so existe em janeiro; o sistema ja deixa os outros meses como "Nao cobrar".
            marcados_fora = [MESES[i][:3] for i in range(1, 12) if doc.meses[i] in ("OK", "P")]
            doc.meses[1:] = [""] * 11
            if marcados_fora:
                doc.acoes.append(f"anuidade: marcação em {', '.join(marcados_fora)} ignorada (só vale janeiro)")
        meios, nota_envio = normaliza_meios(doc.envio_original)
        if doc.tipo == T_ANUIDADE:
            meios = meios if sem_acento(doc.envio_original) not in ("ok",) else []
        elif not meios and atual.docs and sem_acento(doc.envio_original) in ("", "ok", "?", "none"):
            meios = list(atual.docs[-1].meios)
            if meios:
                doc.acoes.append("forma de envio em branco: usada a da linha de cima")
        doc.meios = meios
        if nota_envio:
            if re.search(r"cancelad|nao houve abertura", sem_acento(nota_envio)):
                fora.append(ForaDaImportacao(r, atual.nome, f"{doc.original} (envio: {nota_envio})",
                                             "A forma de envio diz que a conta foi cancelada/não foi aberta.",
                                             "Confirme se o documento ainda existe."))
                continue
            doc.obs.append(nota_envio)
        resto = resto.strip(" :;-")
        if resto and not primeira_linha and doc.tipo != T_ANUIDADE:
            doc.obs.append(resto)
        elif resto:
            if not atual.contato and parece_nome_de_pessoa(resto):
                atual.contato = resto
            else:
                atual.obs.append(resto)
        atual.docs.append(doc)

    for empresa in empresas:
        if empresa.codigo is None:
            if empresa.codigo_original:
                motivo = f'Código "{empresa.codigo_original}" não é um número inteiro.'
            else:
                motivo = "Empresa sem código na planilha."
            fora.append(ForaDaImportacao(empresa.linha, f"{empresa.codigo_original} {empresa.nome}".strip(),
                                         f"(empresa inteira, {len(empresa.docs)} documento(s))", motivo,
                                         "Coloque o código da empresa (filial com código próprio) e rode de novo."))
        completa_pelo_contexto(empresa)
        resolve_nomes_repetidos(empresa, fora)
    return empresas, fora


def trata_nome_empresa(emp: Empresa) -> None:
    nome = emp.nome_original
    for parenteses in re.findall(r"\(([^)]*)\)?", nome):
        p = limpa(parenteses)
        ps = sem_acento(p)
        data = re.search(r"\d{1,2}/\d{1,2}/?\d{2,4}", p)
        quando = data.group(0) if data else ""
        if ps.startswith(("const", "cnst")):
            emp.obs.append(f"Constituída em {quando}" if quando else p)
        elif ps.startswith("outro cont"):
            emp.obs.append(f"Veio de outro contador em {quando}" if quando else p)
        elif ps.startswith("transf"):
            emp.obs.append(f"Transferida em {quando}" if quando else p)
        elif re.fullmatch(r"[\d/]+", p):
            emp.obs.append(f"Desde {p}")
        elif p:
            emp.obs.append(p[0].upper() + p[1:])
    emp.nome = limpa(re.sub(r"\(.*?(\)|$)", "", nome))


NOMES_GENERICOS = {"Aplicação", "Demonstrativo de Evolução", "Informe de Rendimentos", "Empréstimo", "Fatura Cartão",
                   "Poupança", "Conta Capital"}


def completa_pelo_contexto(emp: Empresa) -> None:
    """Aplicacao/demonstrativo logo abaixo de uma conta corrente sao daquela conta (a planilha
    agrupa assim); e documento sem banco numa empresa que so tem conta em um banco e daquele
    banco."""
    ultima_conta: dict[str, str] = {}
    ultimo_banco_cc: str | None = None
    for doc in emp.docs:
        if doc.tipo == T_CC and doc.banco:
            ultimo_banco_cc = doc.banco
            if doc.conta:
                ultima_conta[doc.banco] = doc.conta
        elif doc.tipo == T_APLIC and not doc.banco and ultimo_banco_cc and doc.nome in ("Demonstrativo de Evolução", "Aplicação"):
            # Aplicacao/demonstrativo sem banco logo abaixo de uma conta: e daquele banco.
            doc.banco = ultimo_banco_cc
            doc.nome = ultimo_banco_cc if doc.nome == "Aplicação" else f"{doc.nome} {ultimo_banco_cc}"
            doc.acoes.append(f"banco da conta de cima ({ultimo_banco_cc}) - confira")
        if doc.tipo == T_APLIC and doc.banco and not doc.conta and doc.banco in ultima_conta:
            doc.conta_contexto = ultima_conta[doc.banco]
    bancos_cc = {d.banco for d in emp.docs if d.tipo == T_CC and d.banco}
    if len(bancos_cc) == 1:
        banco = next(iter(bancos_cc))
        for doc in emp.docs:
            if not doc.banco and doc.nome in NOMES_GENERICOS:
                doc.banco = banco
                so_banco = doc.tipo in (T_INFORME, T_EMPREST) or doc.nome == "Aplicação"
                doc.nome = banco if so_banco else f"{doc.nome} {banco}"
                doc.acoes.append(f"banco deduzido ({banco} é o único banco da empresa) - confira")
    junta_demonstrativos(emp)


def junta_demonstrativos(emp: Empresa) -> None:
    """O Demonstrativo de Evolucao e o extrato da aplicacao: quando a empresa tem a aplicacao
    e o demonstrativo do mesmo banco/conta, fica um documento so (a aplicacao). Demonstrativo
    sem aplicacao vira a aplicacao daquele banco."""
    def e_demonstrativo(d: Documento) -> bool:
        return d.tipo == T_APLIC and d.nome.startswith("Demonstrativo de Evolução")

    def e_aplicacao(d: Documento) -> bool:
        return d.tipo == T_APLIC and not d.nome.startswith(("Demonstrativo", "Poupança", "Conta Capital"))

    aplicacoes = [d for d in emp.docs if e_aplicacao(d)]
    for demo in [d for d in emp.docs if e_demonstrativo(d)]:
        conta = demo.conta or demo.conta_contexto
        mesmo_banco = [a for a in aplicacoes if a.banco == demo.banco]
        par = next((a for a in mesmo_banco if (a.conta or a.conta_contexto) == conta), None)
        if par is None and len(mesmo_banco) == 1:
            par = mesmo_banco[0]
        if par is None:
            # So o demonstrativo: ele e a aplicacao daquele banco.
            demo.nome = demo.banco or "Aplicação"
            demo.obs.insert(0, "Demonstrativo de evolução")
            demo.acoes.append("demonstrativo de evolução = extrato da aplicação: virou a aplicação do banco")
            aplicacoes.append(demo)
            continue
        for i, valor in enumerate(demo.meses):
            if not par.meses[i] and valor:
                par.meses[i] = valor
        for o in demo.obs:
            if o not in par.obs and not o.startswith("Da conta"):
                par.obs.append(o)
        if "Inclui o demonstrativo de evolução" not in par.obs:
            par.obs.append("Inclui o demonstrativo de evolução")
        par.acoes.append(f"juntado com o Demonstrativo de Evolução da linha {demo.linha}")
        emp.docs.remove(demo)
        emp.juntados.append((demo, par))


def resolve_nomes_repetidos(emp: Empresa, fora: list[ForaDaImportacao]) -> None:
    """Uma conta so naquele banco: nome curto. Repetiu (mesmo tipo e nome): diferencia pelo
    numero da conta/contrato ou pelo produto."""
    grupos: dict[tuple[str, str], list[Documento]] = defaultdict(list)
    for doc in emp.docs:
        grupos[(doc.tipo, sem_acento(doc.nome))].append(doc)
    for (_tipo, _nome), docs in grupos.items():
        if len(docs) < 2:
            continue
        def qualificador(d: Documento) -> str:
            q = next((o for o in d.obs if o.startswith(("Extrato ", "Conta P"))), "")
            return f"({q.replace('Extrato ', '').replace('Conta ', '')})" if q else ""

        def unicos(valores: list[str]) -> bool:
            return len(set(valores)) == len(valores) and sum(1 for v in valores if not v) <= 1

        opcoes = (
            [d.conta or "" for d in docs],                          # contas diferentes no mesmo banco
            [d.conta or d.conta_contexto or "" for d in docs],      # aplicacao da conta de cima
            [qualificador(d) for d in docs],                        # mesma conta: consolidado x normal, PF x PJ
            [d.conta or qualificador(d) for d in docs],
            [d.produto or "" for d in docs],                        # produtos diferentes (CDB, Rende Facil...)
        )
        sufixos = next((o for o in opcoes if unicos(o)), [d.conta or d.produto or "" for d in docs])
        vistos: Counter = Counter()
        for doc, sufixo in zip(docs, sufixos):
            if sufixo:
                separador = " - " if doc.tipo == T_APLIC and sufixo == doc.produto else " "
                if sufixo == doc.conta_contexto and sufixo != doc.conta:
                    doc.obs.append(f"Da conta {sufixo}")
                doc.nome = f"{doc.nome}{separador}{sufixo}"
                doc.acoes.append("mais de um igual na empresa: número/produto mantido no nome")
            vistos[sem_acento(doc.nome)] += 1
            if vistos[sem_acento(doc.nome)] > 1:
                doc.nome = f"{doc.nome} ({vistos[sem_acento(doc.nome)]})"
    # Duplicado exato depois de tudo: nao importa o segundo.
    finais: set[tuple[str, str]] = set()
    mantidos = []
    for doc in emp.docs:
        chave = (doc.tipo, sem_acento(doc.nome))
        if chave in finais:
            fora.append(ForaDaImportacao(doc.linha, emp.nome, doc.original, f'Repete o documento "{doc.nome}" ({doc.tipo}).',
                                         "Confira se são mesmo dois documentos; se forem, diferencie o nome."))
            continue
        finais.add(chave)
        mantidos.append(doc)
    emp.docs = mantidos


# Escrita -------------------------------------------------------------------------------

AZUL = PatternFill("solid", fgColor="1F4E78")
CINZA = PatternFill("solid", fgColor="F2F2F2")
STATUS_FILL = {"OK": PatternFill("solid", fgColor="D9EAD3"), "P": PatternFill("solid", fgColor="F4CCCC"),
               "X": PatternFill("solid", fgColor="FFF2CC"), "Encerrado": PatternFill("solid", fgColor="D9D9D9")}


def cabecalho(ws, titulos: list[str], larguras: list[int]) -> None:
    ws.append(titulos)
    for i, largura in enumerate(larguras, start=1):
        cell = ws.cell(1, i)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = AZUL
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = largura
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 30


def escreve(empresas: list[Empresa], fora: list[ForaDaImportacao], saida: Path, ano: int, so_primeiras: int | None) -> dict:
    wb = Workbook()
    imp = wb.active
    imp.title = "Importar"
    meses_cab = [f"{m} {ano}" for m in MESES]
    cabecalho(imp, ["Codigo", "Nome da empresa", "Email", "Contato", "Nome do documento", "Meio de recebimento",
                    "Tipo do documento", "Observacao", *meses_cab, "Observação do documento", "Regra do tipo"],
              [8, 28, 28, 20, 34, 22, 26, 40, *([11] * 12), 50, 14])
    comp = wb.create_sheet("Antes x depois")
    cabecalho(comp, ["Linha", "Empresa", "Documento ANTES", "Envio ANTES", "Obs ANTES", "→", "Nome DEPOIS", "Tipo DEPOIS",
                     "Meio DEPOIS", "Obs do documento DEPOIS", "O que mudou"],
              [7, 24, 44, 18, 30, 3, 32, 24, 20, 40, 44])

    selecionadas = [e for e in empresas if e.codigo is not None]
    if so_primeiras:
        selecionadas = selecionadas[:so_primeiras]
    total_docs = 0
    for emp in selecionadas:
        email = emp.emails[0] if emp.emails else ""
        obs_emp = list(dict.fromkeys(emp.obs))
        if len(emp.emails) > 1:
            obs_emp.append("Outros emails: " + ", ".join(emp.emails[1:]))
        dados_empresa = [emp.codigo, emp.nome, email, emp.contato]
        linhas = emp.docs or [None]
        for i, doc in enumerate(linhas):
            empresa_cols = dados_empresa if i == 0 else ["", "", "", ""]
            obs_col = "; ".join(obs_emp) if i == 0 else ""
            if doc is None:
                imp.append([*empresa_cols, "", "", "", obs_col, *([""] * 12), "", ""])
                continue
            total_docs += 1
            obs_doc = "; ".join(dict.fromkeys(o for o in doc.obs if o))
            imp.append([*empresa_cols, doc.nome, ", ".join(doc.meios), doc.tipo, obs_col, *doc.meses, obs_doc,
                        REGRA_DO_TIPO.get(doc.tipo, "mensal")])
            row = imp.max_row
            for j, valor in enumerate(doc.meses):
                if valor in STATUS_FILL:
                    imp.cell(row, 9 + j).fill = STATUS_FILL[valor]
                imp.cell(row, 9 + j).alignment = Alignment(horizontal="center")
            comp.append([doc.linha, emp.nome, doc.original, doc.envio_original, doc.obs_original, "→", doc.nome, doc.tipo,
                         ", ".join(doc.meios), obs_doc, "; ".join(doc.acoes)])
        for removido, mantido in emp.juntados:
            comp.append([removido.linha, emp.nome, removido.original, removido.envio_original, removido.obs_original, "→",
                         f"(juntado em: {mantido.nome})", mantido.tipo, "", "",
                         "é o extrato da mesma aplicação - ficou um documento só"])
        if emp is not selecionadas[-1]:
            for ws in (imp,):
                ws.append([])
    for ws in (imp, comp):
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                if cell.column in (8, 21) or (ws is comp and cell.column in (3, 5, 10, 11)):
                    cell.alignment = Alignment(wrap_text=True, vertical="top")

    nao = wb.create_sheet("Não importado")
    cabecalho(nao, ["Linha", "Empresa", "O que estava na planilha", "Por que ficou de fora", "O que fazer"], [7, 26, 52, 44, 52])
    for item in sorted(fora, key=lambda f: f.linha):
        if so_primeiras and not any(item.linha >= e.linha for e in selecionadas[:1]):
            continue
        nao.append([item.linha, item.empresa, item.conteudo, item.motivo, item.sugestao])
    for row in nao.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    regras = wb.create_sheet("Regras")
    regras.column_dimensions["A"].width = 120
    for linha in REGRAS_TEXTO.strip().splitlines():
        regras.append([linha])
    regras.cell(1, 1).font = Font(bold=True, size=13)

    # Linhas vazias entre empresas atrapalhariam a importacao: o sistema pula linhas em
    # branco, entao ficam so para leitura.
    wb.save(saida)
    tipos = Counter(d.tipo for e in selecionadas for d in e.docs)
    return {"empresas": len(selecionadas), "documentos": total_docs, "fora": len(fora), "tipos": tipos}


REGRAS_TEXTO = """
Como a planilha foi tratada
- Aba "Importar": no formato do DocFlow (Importar > Cadastro completo). Uma linha por documento; os dados da empresa só na primeira linha dela.
- Tipo = o que é o documento (Extratos CC, Extratos aplicacao, Empréstimos e Financiamentos, Cartões, Comprovantes, Planilhas e Relatórios, Informe de Rendimentos, Anuidades, Movimento contábil, Outros).
- Nome = curto e sem repetir o tipo (tipo e nome são campos separados no sistema). Extrato de conta corrente, aplicação, empréstimo e informe de rendimentos: só o banco (Banco do Brasil, Sicoob...). Quando o mesmo tipo tem coisas diferentes do mesmo banco, o nome diz qual: Poupança Banestes, Conta Capital Sicoob, Demonstrativo de Evolução Banestes; Fatura Cartão Sicoob x Vendas Cartão Cielo.
- Conta só uma naquele banco: o número sai do nome e vai para a Observação do documento (ex: "C/C 18649-0"). Duas ou mais contas/aplicações/contratos no mesmo banco: o número ou produto fica no nome para diferenciar.
- "Consolidado", "Unificado", "Identificado", produto da aplicação (CDB, RDC, Rende Fácil...), número de contrato, bandeira/final do cartão: vão para a Observação do documento.
- Demonstrativo de Evolução é o extrato da aplicação: se a empresa tem a aplicação e o demonstrativo do mesmo banco/conta, fica um documento só (a aplicação, com os meses dos dois). Demonstrativo sem aplicação vira a aplicação daquele banco.
- "Aberta em mm/aaaa": vira observação e os meses antes da abertura (no ano) ficam X (não cobrar).
- "Encerrada em mm/aaaa", "Fechou", "Finalizou": vira observação e o mês do fechamento fica "Encerrado" (os meses depois ficam em branco, porque o sistema bloqueia depois de Encerrado).
- Forma de envio padronizada: Email, WhatsApp, Onvio, Físico, Acesso ao banco (quando a Métodos baixa direto). O que sobrava de texto (ex: "Ellen envia", "Grupo de WhatsApp") foi para a Observação do documento. Em branco: usa a da linha de cima (como a planilha fazia).
- Linha "Documentação (Cliente só envia...)": vira observação da empresa. Quando diz que o cliente envia o movimento contábil físico, vira o documento "Movimento Contábil" (Físico), com os meses da linha.
- Coluna OBSERVAÇÃO: emails vão para o Email da empresa (o primeiro) e os outros para a observação dela; nome de pessoa na primeira linha vira o Contato; o resto vai para a observação do documento (ou da empresa, se estava na primeira linha).
- Nome da empresa: o que estava entre parênteses (Const. 18/02/2025, Outro Cont., Transf.) saiu do nome e foi para a observação da empresa.
- Anuidades (CRM, CRO, CREA, CRF): tipo Anuidades; a forma de envio "OK" que estava nessas linhas foi ignorada.
- Senha que estava no nome de um documento NÃO foi copiada para lugar nenhum.
- Aba "Não importado": o que ficou de fora e por quê.

Atenção
- A coluna "Observação do documento" vai para a observação de cada documento (campo novo do sistema).
- A coluna "Regra do tipo" define a regra quando o tipo ainda não existe: "Anuidades" anual (janeiro), o resto mensal. "Informe de Rendimentos" fica mensal com X nos meses sem cobrança, porque o trimestral do sistema é jan/abr/jul/out e o escritório cobra em mar/jun/set/dez. Tipo que já existe mantém a regra cadastrada.
- Documento que já existe na empresa (mesmo tipo e nome) é reaproveitado: a importação só completa os meses e a observação, sem duplicar.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("planilha", type=Path)
    parser.add_argument("--aba", default="2026")
    parser.add_argument("--ano", type=int, default=2026)
    parser.add_argument("--saida", type=Path)
    parser.add_argument("--so-primeiras", type=int, help="gera só as N primeiras empresas (para conferir o formato)")
    args = parser.parse_args()
    saida = args.saida or args.planilha.with_name(f"{args.planilha.stem} - TRATADA para importar.xlsx")
    empresas, fora = le_planilha(args.planilha, args.aba, args.ano)
    resumo = escreve(empresas, fora, saida, args.ano, args.so_primeiras)
    print(f"Gerado: {saida}")
    print(f"Empresas: {resumo['empresas']} | documentos: {resumo['documentos']} | fora da importação: {resumo['fora']}")
    for tipo, n in resumo["tipos"].most_common():
        print(f"  {n:4d}  {tipo}")


if __name__ == "__main__":
    main()
