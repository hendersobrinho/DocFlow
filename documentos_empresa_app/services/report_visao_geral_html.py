"""Desenho (HTML) da visao geral da cobranca, na identidade visual do DocFlow.

Palavras simples e sempre com numero: "Chegou", "Falta", "Completa: chegaram os 8".
Nada de "tudo em dia" sem dizer do que."""

from __future__ import annotations

from documentos_empresa_app.services.report_html import (
    CYAN,
    LINE,
    MUTED,
    NAVY,
    NAVY_DARK,
    ORANGE,
    TEXT,
    _cards,
    _esc,
    _header,
    _section,
)
from documentos_empresa_app.services.report_rodada_html import (
    BROWN,
    CANAIS,
    GREEN,
    _cell,
    _empresa_cell,
    _pill,
    _row,
    _table,
    _vazio,
)

VERDE = ("#DDF3E8", "#17694A")
LARANJA = ("#FDEBD3", "#8A4E0B")
AZUL = ("#E2F3F6", "#203461")
CINZA = ("#E8ECF4", "#4D5A73")
VERMELHO = ("#FBE3E0", "#A93226")
ORIGEM = {"robo": "robô do Onvio", "claude": "Claude", "manual": "marcado à mão"}
LIMITE_LINHAS_DIA = 150
LIMITE_NOMES = 8


def _pct(parte: int, total: int) -> int:
    return round(100 * parte / total) if total else 0


def _barra(chegaram: int, faltam: int) -> str:
    total = chegaram + faltam
    if not total:
        return ""
    verde = max(min(_pct(chegaram, total), 100), 0)
    celulas = ""
    if verde:
        celulas += f"<td width='{verde}%' bgcolor='{GREEN}' style='background-color:{GREEN};' height='12'></td>"
    if verde < 100:
        celulas += f"<td width='{100 - verde}%' bgcolor='{ORANGE}' style='background-color:{ORANGE};' height='12'></td>"
    return (
        f"<table width='100%' cellspacing='0' cellpadding='0' style='margin-top:4px;'><tr>{celulas}</tr></table>"
    )


def _destaque(totais: dict, competencia: str) -> str:
    total = totais["esperados"]
    pct = _pct(totais["chegaram"], total)
    origem = []
    if totais["pelo_robo"]:
        origem.append(f"{totais['pelo_robo']} pelo robô do Onvio")
    if totais["pelo_claude"]:
        origem.append(f"{totais['pelo_claude']} conferido(s) pelo Claude")
    if totais["manual"]:
        origem.append(f"{totais['manual']} marcado(s) à mão")
    origem_txt = f" &nbsp;·&nbsp; {', '.join(origem)}" if origem else ""
    return (
        f"<table width='100%' cellspacing='0' cellpadding='10' style='margin-top:10px; border:1px solid {LINE};'><tr>"
        f"<td bgcolor='#FFFFFF' style='background-color:#FFFFFF;'>"
        f"<span style='color:{NAVY}; font-size:15pt; font-weight:600;'>Competência {_esc(competencia)}: "
        f"chegaram {totais['chegaram']} de {total} documento(s) ({pct}%)</span><br>"
        f"<span style='color:{MUTED}; font-size:9pt;'>Faltam {totais['faltam']}{origem_txt}</span>"
        f"{_barra(totais['chegaram'], totais['faltam'])}"
        f"<span style='color:{MUTED}; font-size:8pt;'>Verde: chegou &nbsp;·&nbsp; laranja: ainda falta. "
        f"Documentos marcados como “não cobrar” ou encerrados ({totais['fora']}) ficam fora da conta.</span>"
        f"</td></tr></table>"
    )


def _nomes(docs: list[dict], limite: int = LIMITE_NOMES) -> str:
    """Nomes dos documentos; quando dois tem o mesmo nome, o tipo entre parenteses separa um do outro."""
    repetidos = {n for n in (d["nome"] for d in docs) if sum(1 for d in docs if d["nome"] == n) > 1}
    nomes = [f"{d['nome']} ({d['tipo']})" if d["nome"] in repetidos and d.get("tipo") else d["nome"] for d in docs]
    texto = ", ".join(nomes[:limite])
    if len(nomes) > limite:
        texto += f" e mais {len(nomes) - limite}"
    return texto


def _situacao_empresa(empresa: dict) -> str:
    faltam, esperados = len(empresa["faltam"]), empresa["esperados"]
    if not esperados:
        return _pill(*CINZA, "Nada a cobrar", "15%")
    if not faltam:
        return _pill(*VERDE, f"Completa: {esperados} de {esperados}", "15%")
    return _pill(*LARANJA, f"Falta(m) {faltam} de {esperados}", "15%")


def _como_chegou(docs: list[dict]) -> str:
    contagem: dict[str, int] = {}
    for doc in docs:
        contagem[doc["origem"]] = contagem.get(doc["origem"], 0) + 1
    return " · ".join(f"{n} {ORIGEM[o]}" for o, n in sorted(contagem.items(), key=lambda x: -x[1]))


def _canal(texto: str) -> str:
    return CANAIS.get(str(texto).lower(), str(texto).capitalize())


def _meios(docs: list[dict]) -> str:
    vistos: list[str] = []
    for doc in docs:
        for meio in str(doc.get("meios") or "").replace(";", ",").split(","):
            meio = meio.strip()
            if meio and meio.casefold() not in (v.casefold() for v in vistos):
                vistos.append(meio)
    return ", ".join(vistos) or "-"


def _secao_dia(dados: dict) -> list[str]:
    dia_dados = dados["dia_dados"]
    dia = dados["dia"].strftime("%d/%m/%Y")
    totais = dados["totais"]
    recebidos = dia_dados.get("recebidos") or []
    cobrancas = dia_dados["cobrancas"]
    salvos = dados["salvos_no_dia"]
    robo_hoje = sum(
        int(e.get("arquivos") or 0)
        for p in dia_dados.get("onvio") or []
        for e in p["empresas"]
        if e.get("situacao") == "baixada"
    )
    parts = [_section(f"O que aconteceu em {dia}", CYAN)]
    parts.append(
        _cards(
            [
                ("documento(s) chegaram", len(recebidos), *VERDE),
                ("arquivo(s) o robô baixou", robo_hoje, *AZUL),
                ("arquivo(s) o Claude salvou", len(salvos), "#FFFFFF", NAVY),
                ("cobrança(s) enviada(s)", len(cobrancas), *LARANJA),
            ]
        )
    )

    por_empresa: dict[str, dict] = {}

    def linha(codigo, nome):
        return por_empresa.setdefault(
            str(codigo), {"codigo": codigo, "nome": nome, "chegou": [], "robo": 0, "claude": [], "cobranca": []}
        )

    for item in recebidos:
        linha(item["codigo_empresa"], item["nome_empresa"])["chegou"].append(
            {"nome": f"{item['nome_documento']} ({item['competencia']})"}
        )
    for passada in dia_dados.get("onvio") or []:
        for empresa in passada["empresas"]:
            if empresa.get("situacao") == "baixada" and int(empresa.get("arquivos") or 0):
                linha(empresa.get("codigo"), empresa.get("nome"))["robo"] += int(empresa.get("arquivos") or 0)
    for item in salvos:
        linha(item["codigo_empresa"], item["nome_empresa"])["claude"].append({"nome": item["nome_documento"]})
    for cobranca in cobrancas:
        tipo = "recobrança" if cobranca.get("recobranca") else "cobrança"
        linha(cobranca["codigo_empresa"], cobranca["nome_empresa"])["cobranca"].append(
            f"{tipo} por {_canal(cobranca['canal'])} às {cobranca['hora']}"
        )

    if not por_empresa:
        return parts + [_vazio("Nada foi registrado neste dia: nada chegou, o robô não baixou e ninguém foi cobrado.")]

    ordenadas = sorted(por_empresa.values(), key=lambda e: (0, int(e["codigo"])) if str(e["codigo"]).isdigit() else (1, 0))
    linhas = []
    for i, e in enumerate(ordenadas[:LIMITE_LINHAS_DIA]):
        linhas.append(
            _row(
                i,
                [
                    _empresa_cell(e["codigo"], e["nome"]),
                    _cell(_nomes(e["chegou"], 5) or "-", GREEN if e["chegou"] else MUTED, True),
                    _cell(f"{e['robo']} arquivo(s)" if e["robo"] else "-", NAVY if e["robo"] else MUTED, True),
                    _cell(_nomes(e["claude"], 4) or "-", TEXT if e["claude"] else MUTED, True),
                    _cell("; ".join(e["cobranca"]) or "-", BROWN if e["cobranca"] else MUTED, True),
                ],
            )
        )
    cabecalho = [("Empresa", "24%"), ("Chegou", ""), ("Robô baixou", "14%"), ("Claude salvou", "17%"), ("Cobrado", "17%")]
    parts.append(_table(cabecalho, linhas, NAVY))
    if len(ordenadas) > LIMITE_LINHAS_DIA:
        parts.append(
            f"<p style='margin-top:6px; color:{MUTED};'>... e mais {len(ordenadas) - LIMITE_LINHAS_DIA} empresa(s) "
            f"com movimento no dia (marcação em massa).</p>"
        )
    if totais["robo_no_dia"] and not robo_hoje:
        parts.append(
            f"<p style='margin-top:6px; color:{MUTED};'>Há {totais['robo_no_dia']} arquivo(s) na pasta do robô "
            f"gravados neste dia.</p>"
        )
    return parts


def _secao_faltam(dados: dict) -> list[str]:
    com_falta = [e for e in dados["empresas"] if e["faltam"]]
    com_falta.sort(key=lambda e: (-len(e["faltam"]), str(e["nome"]).casefold()))
    total = sum(len(e["faltam"]) for e in com_falta)
    parts = [
        _section(f"O que ainda falta chegar: {total} documento(s) de {len(com_falta)} empresa(s)", ORANGE)
    ]
    if not com_falta:
        return parts + [_vazio(f"Não falta nenhum documento da competência {dados['competencia']}.")]
    linhas = []
    for i, e in enumerate(com_falta):
        cobrados = [d for d in e["faltam"] if d["cobranca"]]
        if cobrados:
            vezes = max(d["cobranca"]["vezes"] for d in cobrados)
            ultima = max((d["cobranca"]["ultima"] for d in cobrados), key=lambda t: (t[3:], t[:2]))
            cobranca = f"{len(cobrados)} de {len(e['faltam'])} cobrado(s), até {vezes}x, última em {ultima}"
            cor = BROWN
        else:
            cobranca, cor = "Ainda não cobrado", MUTED
        robo = e.get("robo") if any("onvio" in str(d.get("meios") or "").casefold() for d in e["faltam"]) else None
        if robo and robo["situacao"] == "baixada":
            robo_txt = f"Baixou {robo['baixados']} arquivo(s): conferir"
        elif robo:
            robo_txt = robo["situacao_texto"] or robo["situacao"]
        else:
            robo_txt = "-"
        linhas.append(
            _row(
                i,
                [
                    _empresa_cell(e["codigo"], e["nome"]),
                    _pill(*LARANJA, f"{len(e['faltam'])} de {e['esperados']}", "9%"),
                    _cell(_nomes(e["faltam"])),
                    _cell(_meios(e["faltam"]), MUTED, True),
                    _cell(cobranca, cor, True),
                    _cell(robo_txt, NAVY if robo and robo["situacao"] == "baixada" else MUTED, True),
                ],
            )
        )
    cabecalho = [
        ("Empresa", "22%"),
        ("Faltam", "9%"),
        ("Documentos que faltam", ""),
        ("Costuma chegar por", "12%"),
        ("Cobrança", "16%"),
        ("Onvio", "13%"),
    ]
    return parts + [_table(cabecalho, linhas, BROWN)]


def _secao_chegaram(dados: dict) -> list[str]:
    empresas = [e for e in dados["empresas"] if e["chegaram"]]
    total = sum(len(e["chegaram"]) for e in empresas)
    parts = [_section(f"O que já chegou: {total} documento(s) de {len(empresas)} empresa(s)", GREEN)]
    if not empresas:
        return parts + [_vazio(f"Nenhum documento da competência {dados['competencia']} chegou ainda.")]
    linhas = []
    for i, e in enumerate(empresas):
        linhas.append(
            _row(
                i,
                [
                    _empresa_cell(e["codigo"], e["nome"]),
                    _situacao_empresa(e),
                    _cell(_nomes(e["chegaram"], 10)),
                    _cell(_como_chegou(e["chegaram"]), MUTED, True),
                ],
            )
        )
    cabecalho = [("Empresa", "24%"), ("Situação", "15%"), ("Documentos que chegaram", ""), ("Como chegou", "17%")]
    parts.append(_table(cabecalho, linhas, GREEN))
    sem_nada = [e for e in dados["empresas"] if e["esperados"] and not e["chegaram"]]
    if sem_nada:
        parts.append(
            f"<p style='margin-top:6px; color:{MUTED};'>Ainda não chegou nada de {len(sem_nada)} empresa(s): "
            f"{_esc(', '.join(str(e['codigo']) for e in sem_nada[:80]))}{'...' if len(sem_nada) > 80 else ''} "
            f"(estão na lista do que falta).</p>"
        )
    return parts


def _secao_arquivos(dados: dict) -> list[str]:
    robo = dados["robo"]
    totais = dados["totais"]
    parts = [_section("Arquivos: o que o robô baixou e o que o Claude salvou", CYAN)]

    if not robo["passou"]:
        parts.append(_vazio(f"O robô do Onvio ainda não passou na competência {dados['competencia']}."))
    else:
        interrompido = (
            f"<br><span style='color:#A93226;'>Parou antes do fim: {_esc(robo['interrompido'])}</span>"
            if robo.get("interrompido")
            else ""
        )
        parts.append(
            f"<p style='margin-top:8px; margin-bottom:0px;'><span style='color:{NAVY}; font-weight:600;'>Robô do Onvio</span>"
            f"<span style='color:{MUTED};'> &nbsp;·&nbsp; última passada em {_esc(robo['gerado_em'])} &nbsp;·&nbsp; "
            f"{totais['robo_arquivos']} arquivo(s) de {totais['robo_empresas']} empresa(s) &nbsp;·&nbsp; "
            f"{totais['robo_na_pasta']} ainda na pasta do robô (o Claude ainda não organizou)</span>{interrompido}<br>"
            f"<span style='color:{MUTED}; font-size:8.5pt;'>{_esc(robo['pasta'])}</span></p>"
        )
        nomes_por_codigo = {str(e["codigo"]): e["nome"] for e in dados["empresas"]}
        baixadas = [(c, r) for c, r in robo["empresas"].items() if r["situacao"] in ("baixada", "erro")]
        baixadas.sort(key=lambda x: (0, int(x[0])) if x[0].isdigit() else (1, 0))
        linhas = []
        for i, (codigo, r) in enumerate(baixadas):
            if r["situacao"] == "erro":
                situacao = _pill(*VERMELHO, "Erro", "14%")
                detalhe = r["detalhe"] or "-"
            else:
                situacao = _pill(*VERDE, f"{r['baixados']} arquivo(s)", "14%")
                detalhe = (
                    f"{r['na_pasta']} na pasta: " + ", ".join(r["nomes"][:5]) + (" ..." if len(r["nomes"]) > 5 else "")
                    if r["na_pasta"]
                    else "Pasta já organizada (nada sobrando)"
                )
            linhas.append(
                _row(i, [_empresa_cell(codigo, nomes_por_codigo.get(codigo) or r.get("nome") or ""), situacao, _cell(detalhe, MUTED, True)])
            )
        if linhas:
            parts.append(_table([("Empresa", "26%"), ("Robô baixou", "14%"), ("O que está na pasta do robô", "")], linhas, NAVY))
        sem = [c for c, r in robo["empresas"].items() if r["situacao"] not in ("baixada", "erro")]
        if sem:
            parts.append(
                f"<p style='margin-top:6px; color:{MUTED}; font-size:8.5pt;'>Sem arquivo no Onvio para esta competência "
                f"({len(sem)}): {_esc(', '.join(sorted(sem, key=lambda c: int(c) if c.isdigit() else 0)[:90]))}"
                f"{'...' if len(sem) > 90 else ''}</p>"
            )

    salvos = dados["salvos_claude"]
    parts.append(
        f"<p style='margin-top:12px; margin-bottom:0px;'><span style='color:{NAVY}; font-weight:600;'>"
        f"Salvos pelo Claude ({len(salvos)})</span><span style='color:{MUTED};'> &nbsp;·&nbsp; "
        f"documentos que o Claude achou, guardou na pasta da empresa e registrou</span></p>"
    )
    if not salvos:
        parts.append(_vazio("O Claude ainda não salvou nenhum arquivo desta competência."))
        return parts
    linhas = []
    for i, item in enumerate(salvos):
        baixa = _pill(*VERDE, "Baixa dada", "10%") if item.get("baixa_feita") else _pill(*LARANJA, "Sem baixa", "10%")
        linhas.append(
            _row(
                i,
                [
                    _empresa_cell(item["codigo_empresa"], item["nome_empresa"]),
                    _cell(item["nome_documento"]),
                    _cell(item["arquivo"], MUTED, True),
                    _cell(item.get("onde") or "-", MUTED, True),
                    _cell(item["data"], MUTED, True),
                    baixa,
                ],
            )
        )
    cabecalho = [
        ("Empresa", "20%"),
        ("Documento", "16%"),
        ("Onde foi salvo", ""),
        ("Onde achou", "17%"),
        ("Dia", "6%"),
        ("Baixa", "10%"),
    ]
    parts.append(_table(cabecalho, linhas, NAVY_DARK))
    return parts


def _data_hora(raw) -> tuple[str, str]:
    from datetime import datetime, timezone

    try:
        momento = datetime.strptime(str(raw)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone()
    except (TypeError, ValueError):
        return "-", ""
    return momento.strftime("%d/%m/%Y"), momento.strftime("%H:%M")


RODADA_PILL = {
    "concluida": VERDE,
    "concluida_com_falhas": LARANJA,
    "interrompida": VERMELHO,
    "em_andamento": AZUL,
}


def _tabela_rodadas(rodadas: list[dict]) -> list[str]:
    parts = [
        f"<p style='margin-top:12px; margin-bottom:0px;'><span style='color:{NAVY}; font-weight:600;'>"
        f"Rodadas do Claude ({len(rodadas)})</span><span style='color:{MUTED};'> &nbsp;·&nbsp; "
        f"cada passada do Claude pela cobrança, com o que ele fez e o que deu errado</span></p>"
    ]
    if not rodadas:
        return parts + [_vazio("O Claude não fez nenhuma rodada de cobrança no período.")]
    linhas = []
    for i, rodada in enumerate(rodadas):
        dia, inicio = _data_hora(rodada.get("iniciada_em"))
        _d, fim = _data_hora(rodada.get("finalizada_em")) if rodada.get("finalizada_em") else ("", "")
        falhas = [o for o in rodada.get("ocorrencias") or [] if o.get("tipo") == "falha"]
        avisos = [o for o in rodada.get("ocorrencias") or [] if o.get("tipo") == "aviso"]
        detalhe = rodada.get("resumo") or ""
        if falhas or avisos:
            problemas = "; ".join(str(o.get("mensagem") or "") for o in (falhas + avisos)[:3])
            detalhe = (detalhe + " · " if detalhe else "") + f"{len(falhas)} falha(s), {len(avisos)} aviso(s): {problemas}"
        linhas.append(
            _row(
                i,
                [
                    _cell(dia, MUTED, True),
                    _cell(f"{inicio}" + (f" às {fim}" if fim else ""), MUTED, True),
                    _cell(
                        f"{rodada.get('empresas', 0)} empresa(s) · {rodada.get('verificacoes', 0)} conferência(s) · "
                        f"{rodada.get('cobrancas', 0)} cobrança(s)",
                        TEXT,
                        True,
                    ),
                    _pill(*RODADA_PILL.get(rodada.get("status_efetivo"), CINZA), rodada.get("status_label") or "", "13%"),
                    _cell(detalhe or "-", MUTED, True),
                ],
            )
        )
    cabecalho = [("Dia", "9%"), ("Horário", "9%"), ("O que fez", "27%"), ("Como terminou", "13%"), ("Resumo e falhas", "")]
    return parts + [_table(cabecalho, linhas, NAVY_DARK)]


def build_secao_robo_claude(dados: dict, rodadas: list[dict]) -> str:
    """O resumo do robo do Onvio e do Claude para a competencia (sem <html>), para entrar no fim de
    outro relatorio: o que o robo baixou, o que o Claude conferiu e salvou, e as rodadas dele."""
    totais = dados["totais"]
    conferidos = [
        d["conferencia"]
        for e in dados["empresas"]
        for d in e["chegaram"] + e["faltam"] + e["fora"]
        if d.get("conferencia")
    ]
    encontrados = sum(1 for c in conferidos if c["resultado"] == "recebido")
    nao_encontrados = len(conferidos) - encontrados
    parts = [
        _section(f"Robô do Onvio e Claude na competência {dados['competencia']}", CYAN),
        _cards(
            [
                ("arquivo(s) o robô baixou", totais["robo_arquivos"], *AZUL),
                ("empresa(s) com arquivo no Onvio", totais["robo_empresas"], "#FFFFFF", NAVY),
                ("ainda na pasta do robô", totais["robo_na_pasta"], "#FFFFFF", MUTED),
                ("conferido(s) pelo Claude: encontrado(s)", encontrados, *VERDE),
                ("conferido(s): não encontrado(s)", nao_encontrados, *LARANJA),
            ]
        ),
    ]
    arquivos = _secao_arquivos(dados)
    parts += arquivos[1:]  # o titulo da secao ja esta acima
    parts += _tabela_rodadas(rodadas)
    return "".join(parts)


def build_visao_geral_html(dados: dict, generated_at: str) -> str:
    """'dados' vem de services.relatorio_visao_geral.coletar_visao_geral."""
    totais = dados["totais"]
    competencia = dados["competencia"]
    subtitle = (
        f"Competência {_esc(competencia)} &nbsp;|&nbsp; movimento do dia {dados['dia'].strftime('%d/%m/%Y')}"
    )
    parts = [
        f"<html><body style=\"font-family: 'Segoe UI', Arial, sans-serif; color:{TEXT}; font-size:9.5pt;\">",
        _header("Visão geral da cobrança", subtitle, generated_at),
    ]
    if not dados["tem_periodo"]:
        parts.append(_vazio(f"A competência {competencia} ainda não foi criada no sistema."))
    else:
        parts.append(_destaque(totais, competencia))
        parts.append(
            _cards(
                [
                    ("documento(s) chegaram", totais["chegaram"], *VERDE),
                    ("documento(s) faltam", totais["faltam"], *LARANJA),
                    ("empresa(s) completas", totais["completas"], "#FFFFFF", GREEN),
                    ("empresa(s) com falta", totais["com_falta"], "#FFFFFF", BROWN),
                    ("falta(m) já cobrado(s)", totais["cobrados"], *AZUL),
                ]
            )
        )
    parts += _secao_dia(dados)
    if dados["tem_periodo"]:
        parts += _secao_faltam(dados)
        parts += _secao_chegaram(dados)
    parts += _secao_arquivos(dados)
    parts.append(
        f"<p style='margin-top:14px; color:{MUTED}; font-size:8pt;'>Como ler: “chegou” é documento marcado como "
        f"recebido; “falta” é documento pendente. “Como chegou” diz quem confirmou: o robô do Onvio (baixou os "
        f"arquivos da empresa e o documento chega pelo Onvio), o Claude (conferiu e registrou) ou alguém que marcou "
        f"à mão. “Completa” quer dizer que chegaram todos os documentos cobrados da empresa nesta competência.</p>"
    )
    parts.append("</body></html>")
    return "".join(parts)
