"""Desenho (HTML) do relatorio da rodada de cobranca: o que foi conferido, cobrado e baixado no dia.
Usa a mesma identidade visual dos outros relatorios (report_html)."""

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

RESULTADO_STYLE = {
    "recebido": ("#DDF3E8", "#17694A", "Encontrado"),
    "nao_encontrado": ("#FBE3E0", "#A93226", "Não encontrado"),
    "documento_com_problema": ("#FDEBD3", "#8A4E0B", "Com problema"),
    "verificacao_falhou": ("#E8ECF4", "#4D5A73", "Não conseguiu ver"),
}
RODADA_STYLE = {
    "concluida": ("#DDF3E8", "#17694A"),
    "concluida_com_falhas": ("#FDEBD3", "#8A4E0B"),
    "interrompida": ("#FBE3E0", "#A93226"),
    "em_andamento": ("#E2F3F6", "#203461"),
}
ONVIO_STYLE = {
    "baixada": ("#DDF3E8", "#17694A", "Baixada"),
    "erro": ("#FBE3E0", "#A93226", "Erro"),
}
CANAIS = {"email": "Email", "whatsapp": "WhatsApp", "onvio": "Onvio", "telefone": "Telefone"}
LIMITE_RECEBIDOS = 300
GREEN = "#1F8A5B"
RED = "#C0392B"
BROWN = "#B86E12"


def _pill(fundo: str, cor: str, texto: str, width: str = "") -> str:
    largura = f" width='{width}'" if width else ""
    return (
        f"<td bgcolor='{fundo}' style='background-color:{fundo};' align='center'{largura}>"
        f"<span style='color:{cor}; font-weight:600; font-size:8.5pt;'>{_esc(texto)}</span></td>"
    )


def _table(headers: list[tuple[str, str]], rows_html: list[str], accent: str = NAVY_DARK) -> str:
    """headers: [(titulo, largura)]. rows_html: linhas <tr> prontas."""
    head = ""
    for titulo, largura in headers:
        atributo = f" width='{largura}'" if largura else ""
        head += (
            f"<td bgcolor='{accent}' style='background-color:{accent};'{atributo}>"
            f"<span style='color:#FFFFFF; font-weight:600; font-size:8.5pt;'>{_esc(titulo)}</span></td>"
        )
    return (
        f"<table width='100%' cellspacing='0' cellpadding='5' "
        f"style='margin-top:8px; border-collapse:collapse; border:1px solid {LINE};'><tr>{head}</tr>"
        + "".join(rows_html)
        + "</table>"
    )


def _row(index: int, cells: list[str]) -> str:
    fundo = "#FFFFFF" if index % 2 == 0 else "#F7F9FC"
    return f"<tr bgcolor='{fundo}' style='background-color:{fundo};'>{''.join(cells)}</tr>"


def _cell(texto, color: str = TEXT, small: bool = False) -> str:
    estilo = f"color:{color};" + (" font-size:8.5pt;" if small else "")
    return f"<td><span style='{estilo}'>{_esc(texto)}</span></td>"


def _empresa_cell(codigo, nome) -> str:
    return (
        f"<td><span style='color:{NAVY}; font-weight:600;'>{_esc(codigo)}</span> "
        f"<span style='color:{TEXT};'>{_esc(nome)}</span></td>"
    )


def _vazio(texto: str) -> str:
    return (
        f"<table width='100%' cellspacing='0' cellpadding='9' style='margin-top:8px;'><tr>"
        f"<td bgcolor='#FFFFFF' style='background-color:#FFFFFF; border:1px solid {LINE};' align='center'>"
        f"<span style='color:{MUTED};'>{_esc(texto)}</span></td></tr></table>"
    )


def _secao_rodadas(rodadas: list[dict]) -> list[str]:
    parts = [_section("Como foi a rodada", CYAN)]
    for rodada in rodadas:
        fundo, cor = RODADA_STYLE.get(rodada.get("status_efetivo"), ("#E8ECF4", "#4D5A73"))
        fim = f" às {rodada['hora_fim']}" if rodada.get("hora_fim") else ""
        resumo = f"<br><span style='color:{TEXT};'>{_esc(rodada['resumo'])}</span>" if rodada.get("resumo") else ""
        parts.append(
            f"<table width='100%' cellspacing='0' cellpadding='7' style='margin-top:8px; border:1px solid {LINE};'><tr>"
            f"<td bgcolor='#FFFFFF' style='background-color:#FFFFFF;'>"
            f"<span style='color:{NAVY}; font-weight:600;'>Rodada {rodada['id']}</span>"
            f"<span style='color:{MUTED};'> &nbsp;·&nbsp; começou às {rodada['hora_inicio']}{_esc(fim)}"
            f" &nbsp;·&nbsp; {rodada.get('empresas', 0)} empresa(s), {rodada.get('verificacoes', 0)} conferência(s),"
            f" {rodada.get('cobrancas', 0)} cobrança(s)</span>{resumo}</td>"
            f"{_pill(fundo, cor, rodada.get('status_label', ''), '17%')}</tr></table>"
        )
        ocorrencias = [o for o in rodada.get("ocorrencias") or [] if o["tipo"] in ("falha", "aviso")]
        if ocorrencias:
            linhas = []
            for i, o in enumerate(ocorrencias):
                tipo = ("#FBE3E0", "#A93226", "Falha") if o["tipo"] == "falha" else ("#FDEBD3", "#8A4E0B", "Aviso")
                empresa = f"{o['codigo_empresa']} - {o['nome_empresa']}" if o.get("codigo_empresa") else "Geral"
                linhas.append(_row(i, [_pill(*tipo, width="10%"), _cell(empresa, MUTED, True), _cell(o["mensagem"])]))
            parts.append(_table([("Tipo", "10%"), ("Empresa", "28%"), ("O que aconteceu", "")], linhas, MUTED))
    return parts


def _secao_encontrados(itens: list[dict]) -> list[str]:
    parts = [_section(f"O que foi encontrado ({len(itens)})", GREEN)]
    if not itens:
        return parts + [_vazio("Nenhum documento foi encontrado nas conferências deste dia.")]
    linhas = []
    for i, item in enumerate(itens):
        baixa = ("#DDF3E8", "#17694A", "Baixa dada") if item.get("baixa_feita") else ("#FDEBD3", "#8A4E0B", "Sem baixa")
        onde = item.get("onde") or item.get("fontes") or ""
        linhas.append(
            _row(
                i,
                [
                    _empresa_cell(item["codigo_empresa"], item["nome_empresa"]),
                    _cell(item["nome_documento"]),
                    _cell(item["competencia"], MUTED, True),
                    _cell(onde, MUTED, True),
                    _pill(*baixa, width="12%"),
                ],
            )
        )
    cabecalho = [("Empresa", "27%"), ("Documento", "24%"), ("Competência", "13%"), ("Onde estava", ""), ("Baixa", "12%")]
    return parts + [_table(cabecalho, linhas, GREEN)]


def _secao_nao_encontrados(itens: list[dict]) -> list[str]:
    parts = [_section(f"O que não foi encontrado ({len(itens)})", RED)]
    if not itens:
        return parts + [_vazio("Nada ficou sem ser encontrado.")]
    linhas = []
    for i, item in enumerate(itens):
        estilo = RESULTADO_STYLE.get(item["resultado"], RESULTADO_STYLE["nao_encontrado"])
        detalhe = " · ".join(t for t in (item.get("motivo"), item.get("observacao"), item.get("onde")) if t)
        linhas.append(
            _row(
                i,
                [
                    _empresa_cell(item["codigo_empresa"], item["nome_empresa"]),
                    _cell(item["nome_documento"]),
                    _cell(item["competencia"], MUTED, True),
                    _pill(*estilo, width="16%"),
                    _cell(detalhe, MUTED, True),
                ],
            )
        )
    cabecalho = [("Empresa", "27%"), ("Documento", "22%"), ("Competência", "13%"), ("Resultado", "16%"), ("Detalhe", "")]
    return parts + [_table(cabecalho, linhas, RED)]


def _secao_cobrancas(cobrancas: list[dict]) -> list[str]:
    parts = [_section(f"Cobranças enviadas ({len(cobrancas)})", ORANGE)]
    if not cobrancas:
        return parts + [_vazio("Nenhuma cobrança foi enviada neste dia.")]
    linhas = []
    for i, cobranca in enumerate(cobrancas):
        docs = "; ".join(
            f"{item['nome_documento']} ({item['competencia']}"
            + (f", {item['tipo']} {item['sequencia']}" if item["sequencia"] > 1 else "")
            + ")"
            for item in cobranca["itens"]
        )
        tipo = ("#FDEBD3", "#8A4E0B", "Recobrança") if cobranca.get("recobranca") else ("#E2F3F6", "#203461", "Cobrança")
        linhas.append(
            _row(
                i,
                [
                    _cell(cobranca["hora"], MUTED, True),
                    _empresa_cell(cobranca["codigo_empresa"], cobranca["nome_empresa"]),
                    _cell(CANAIS.get(str(cobranca["canal"]).lower(), str(cobranca["canal"]).capitalize()), TEXT, True),
                    _cell(cobranca.get("destinatario") or "-", MUTED, True),
                    _cell(docs),
                    _pill(*tipo, width="12%"),
                ],
            )
        )
    cabecalho = [("Hora", "7%"), ("Empresa", "22%"), ("Canal", "11%"), ("Para", "17%"), ("Documentos cobrados", ""), ("Tipo", "12%")]
    return parts + [_table(cabecalho, linhas, BROWN)]


def _secao_onvio(passadas: list[dict]) -> list[str]:
    parts = [_section("Baixado do Onvio", CYAN)]
    for passada in passadas:
        baixadas = [e for e in passada["empresas"] if e.get("situacao") == "baixada"]
        com_erro = [e for e in passada["empresas"] if e.get("situacao") == "erro"]
        outras = len(passada["empresas"]) - len(baixadas) - len(com_erro)
        arquivos = sum(int(e.get("arquivos") or 0) for e in baixadas)
        parts.append(
            f"<p style='margin-top:8px; margin-bottom:0px;'><span style='color:{NAVY}; font-weight:600;'>"
            f"Competência {_esc(passada['competencia'])}</span>"
            f"<span style='color:{MUTED};'> &nbsp;·&nbsp; passada às {passada['hora']} &nbsp;·&nbsp; "
            f"{len(baixadas)} empresa(s) com arquivos baixados ({arquivos} arquivo(s)), "
            f"{len(com_erro)} com erro, {outras} sem arquivos para baixar</span></p>"
        )
        sem_arquivos = [e for e in passada["empresas"] if e.get("situacao") not in ("baixada", "erro")]
        if sem_arquivos:
            nomes = ", ".join(f"{e.get('codigo')}" for e in sem_arquivos[:60]) + ("..." if len(sem_arquivos) > 60 else "")
            parts.append(
                f"<p style='margin-top:2px; margin-bottom:0px; color:{MUTED}; font-size:8.5pt;'>"
                f"Sem arquivos para baixar (sem pasta da competência, pasta vazia ou fora do Onvio): {_esc(nomes)}</p>"
            )
        if passada.get("interrompido"):
            parts.append(f"<p style='color:#A93226; margin-top:2px;'>Parou antes do fim: {_esc(passada['interrompido'])}</p>")
        linhas = []
        for i, empresa in enumerate(baixadas + com_erro):
            estilo = ONVIO_STYLE.get(empresa["situacao"], ONVIO_STYLE["baixada"])
            detalhe = (
                f"{int(empresa.get('arquivos') or 0)} arquivo(s) baixado(s)"
                if empresa["situacao"] == "baixada"
                else (empresa.get("detalhe") or "")
            )
            linhas.append(
                _row(i, [_empresa_cell(empresa.get("codigo"), empresa.get("nome")), _pill(*estilo, width="13%"), _cell(detalhe, MUTED, True)])
            )
        if linhas:
            parts.append(_table([("Empresa", "40%"), ("Situação", "13%"), ("Detalhe", "")], linhas, NAVY))
    return parts


def _secao_recebidos(itens: list[dict]) -> list[str]:
    parts = [_section(f"Chegou e foi marcado como recebido ({len(itens)})", GREEN)]
    if not itens:
        return parts + [_vazio("Nenhum documento foi marcado como recebido neste dia.")]
    linhas = []
    for i, item in enumerate(itens[:LIMITE_RECEBIDOS]):
        linhas.append(
            _row(
                i,
                [
                    _cell(item["hora"], MUTED, True),
                    _empresa_cell(item["codigo_empresa"], item["nome_empresa"]),
                    _cell(item["tipo_documento"], MUTED, True),
                    _cell(item["nome_documento"]),
                    _cell(item["competencia"], MUTED, True),
                    _cell(item.get("username") or "", MUTED, True),
                ],
            )
        )
    cabecalho = [("Hora", "7%"), ("Empresa", "26%"), ("Tipo", "17%"), ("Documento", ""), ("Competência", "13%"), ("Marcado por", "12%")]
    parts.append(_table(cabecalho, linhas, GREEN))
    if len(itens) > LIMITE_RECEBIDOS:
        restante = itens[LIMITE_RECEBIDOS:]
        empresas = len({r["empresa_id"] for r in restante})
        parts.append(
            f"<p style='margin-top:6px; color:{MUTED};'>... e mais {len(restante)} documento(s) de {empresas} empresa(s) "
            f"(lista cortada em {LIMITE_RECEBIDOS} para o relatório não ficar enorme; foi uma marcação em massa).</p>"
        )
    return parts


def _total_baixado(passadas: list[dict]) -> int:
    return sum(int(e.get("arquivos") or 0) for p in passadas for e in p["empresas"] if e.get("situacao") == "baixada")


def build_rodada_html(dados: dict, generated_at: str) -> str:
    """Relatorio da cobranca do dia, montado pelo proprio sistema com o que ele registra: documentos
    marcados como recebidos, cobrancas enviadas e o que o robo do Onvio baixou. As conferencias e
    rodadas do Claude entram so quando existem. 'dados' vem de services.relatorio_rodada.coletar_dia."""
    dia = dados["dia"]
    totais = dados["totais"]
    rodadas = dados["rodadas"]
    subtitle = f"Dia {dia.strftime('%d/%m/%Y')} &nbsp;|&nbsp; chegou, baixado e cobrado"
    verde, vermelho, laranja = RESULTADO_STYLE["recebido"], RESULTADO_STYLE["nao_encontrado"], RESULTADO_STYLE["documento_com_problema"]
    onvio = dados.get("onvio") or []
    tem_conferencias = bool(dados["verificacoes"])

    cartoes = [
        ("recebido(s) no dia", totais.get("recebidos", 0), verde[0], verde[1]),
        ("empresa(s) que enviaram", totais.get("empresas_recebidas", 0), "#FFFFFF", NAVY),
        ("arquivo(s) baixado(s) do Onvio", _total_baixado(onvio), "#E2F3F6", NAVY),
        ("cobrança(s) enviada(s)", totais["cobrancas"] + totais["recobrancas"], laranja[0], laranja[1]),
    ]
    if tem_conferencias:
        cartoes.append(("não encontrado(s)", totais["nao_encontrados"] + totais["com_problema"], vermelho[0], vermelho[1]))

    parts = [
        f"<html><body style=\"font-family: 'Segoe UI', Arial, sans-serif; color:{TEXT}; font-size:9.5pt;\">",
        _header("Relatório da cobrança do dia", subtitle, generated_at),
        _cards(cartoes),
    ]
    parts += _secao_recebidos(dados.get("recebidos") or [])
    if onvio:
        parts += _secao_onvio(onvio)
    parts += _secao_cobrancas(dados["cobrancas"])
    if tem_conferencias:
        parts += _secao_encontrados(dados["encontrados"])
        parts += _secao_nao_encontrados(dados["nao_encontrados"])
    if rodadas:
        parts += _secao_rodadas(rodadas)
    if not (dados.get("recebidos") or dados["cobrancas"] or onvio or tem_conferencias or rodadas):
        parts.append(_vazio("Nada foi registrado neste dia: nenhum documento recebido, cobrança ou download do Onvio."))
    parts.append("</body></html>")
    return "".join(parts)
