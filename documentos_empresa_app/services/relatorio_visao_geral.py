"""Visao geral da cobranca: o retrato de uma competencia (o que ja chegou e o que ainda falta, e por
onde cada coisa chegou) junto com o movimento de um dia (o que chegou, o que o robo do Onvio baixou,
o que o Claude salvou e o que foi cobrado).

Tudo sai do que o proprio sistema registra; o Claude so aparece quando registrou conferencias."""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path

from documentos_empresa_app.services.relatorio_rodada import LIMITE, coletar_dia

ESPERADOS = ("Recebido", "Pendente")
FORA_DA_CONTA = ("Encerrado", "Nao cobrar")


def _local(raw) -> datetime | None:
    try:
        return datetime.strptime(str(raw)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone()
    except (TypeError, ValueError):
        return None


def _data_curta(raw) -> str:
    momento = _local(raw)
    return momento.strftime("%d/%m") if momento else ""


def _ler_json(caminho: Path) -> dict:
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def _arquivos_na_pasta(pasta: Path) -> list[Path]:
    if not pasta.is_dir():
        return []
    try:
        return sorted(
            (p for p in pasta.rglob("*") if p.is_file() and not p.name.startswith("_")),
            key=lambda p: str(p).casefold(),
        )
    except OSError:
        return []


def _robo_da_competencia(pasta_base: Path | None, ano: int, mes: int, dia: date) -> dict:
    """O que o robo do Onvio deixou para a competencia: resumo da ultima passada por empresa e o que
    ainda esta na pasta dele (o que o Claude ja organizou sai de la)."""
    if not pasta_base:
        return {"passou": False, "empresas": {}, "pasta": "", "gerado_em": ""}
    pasta_comp = Path(pasta_base) / f"{mes:02d}-{ano}"
    resumo = _ler_json(pasta_comp / "_resumo.json")
    if not resumo:
        return {"passou": False, "empresas": {}, "pasta": str(pasta_comp), "gerado_em": ""}
    empresas: dict[str, dict] = {}
    for item in resumo.get("empresas") or []:
        if not isinstance(item, dict):
            continue
        codigo = str(item.get("codigo"))
        pasta = Path(item["pasta"]) if item.get("pasta") else None
        arquivos = _arquivos_na_pasta(pasta) if pasta else []
        hoje = 0
        for arquivo in arquivos:
            try:
                if datetime.fromtimestamp(arquivo.stat().st_mtime).date() == dia:
                    hoje += 1
            except OSError:
                continue
        empresas[codigo] = {
            "nome": item.get("nome") or "",
            "situacao": item.get("situacao") or "",
            "situacao_texto": item.get("situacao_texto") or "",
            "baixados": int(item.get("arquivos") or 0),
            "detalhe": item.get("detalhe") or "",
            "pasta": str(pasta) if pasta else "",
            "na_pasta": len(arquivos),
            "baixados_no_dia": hoje,
            "nomes": [a.name for a in arquivos],
        }
    gerado = str(resumo.get("gerado_em") or "")
    try:
        gerado = datetime.fromisoformat(gerado).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        pass
    return {
        "passou": True,
        "empresas": empresas,
        "pasta": str(pasta_comp),
        "gerado_em": gerado,
        "interrompido": resumo.get("interrompido"),
    }


def _ordem_empresa(codigo) -> tuple:
    texto = str(codigo)
    return (0, int(texto), "") if texto.isdigit() else (1, 0, texto.casefold())


def coletar_visao_geral(
    pending_report_service,
    cobranca_service,
    rodada_service,
    ano: int,
    mes: int,
    dia: date,
    pasta_onvio: Path | None = None,
) -> dict:
    competencia = f"{mes:02d}/{ano}"
    periodo = pending_report_service.periodo_repository.get_by_year_month(ano, mes)
    rows = []
    if periodo:
        rows = pending_report_service.list_pending_rows(
            None, periodo["id"], periodo["id"], all_statuses=True, include_unmarked=True
        )["rows"]

    # Conferencias do Claude para a competencia: o ultimo resultado de cada documento.
    conferencias: dict[int, dict] = {}
    for verificacao in sorted(cobranca_service.listar_verificacoes(LIMITE), key=lambda v: str(v["realizada_em"])):
        for item in verificacao["itens"]:
            if item["competencia"] != competencia:
                continue
            conferencias[item["documento_id"]] = {
                **item,
                "codigo_empresa": verificacao["codigo_empresa"],
                "nome_empresa": verificacao["nome_empresa"],
                "data": _data_curta(verificacao["realizada_em"]),
            }

    # Cobrancas da competencia por documento: quantas vezes e a ultima.
    cobrado: dict[int, dict] = {}
    for cobranca in sorted(cobranca_service.listar_cobrancas(LIMITE), key=lambda c: str(c["realizada_em"])):
        for item in cobranca["itens"]:
            if item["competencia"] != competencia:
                continue
            atual = cobrado.setdefault(item["documento_id"], {"vezes": 0, "ultima": "", "canal": ""})
            atual["vezes"] = max(atual["vezes"] + 1, int(item["sequencia"] or 0))
            atual["ultima"] = _data_curta(cobranca["realizada_em"])
            atual["canal"] = str(cobranca.get("canal") or "")

    robo = _robo_da_competencia(pasta_onvio, ano, mes, dia)

    empresas: dict[int, dict] = {}
    for row in rows:
        empresa = empresas.setdefault(
            row["empresa_id"],
            {
                "empresa_id": row["empresa_id"],
                "codigo": row["codigo_empresa"],
                "nome": row["nome_empresa"],
                "chegaram": [],
                "faltam": [],
                "fora": [],
                "robo": robo["empresas"].get(str(row["codigo_empresa"])),
                "claude": [],
            },
        )
        conferido = conferencias.get(row["documento_id"])
        meios = row.get("meios_recebimento") or ""
        doc = {
            "nome": row["nome_documento"],
            "tipo": row["tipo_documento"],
            "status": row["status"],
            "meios": meios,
            "marcado_em": _data_curta(row.get("updated_at")),
            "marcado_por": row.get("marcado_por") or "",
            "cobranca": cobrado.get(row["documento_id"]),
            "conferencia": conferido,
        }
        if row["status"] == "Recebido":
            if conferido and conferido["resultado"] == "recebido":
                doc["origem"] = "claude"
            elif empresa["robo"] and empresa["robo"]["situacao"] == "baixada" and "onvio" in meios.casefold():
                doc["origem"] = "robo"
            else:
                doc["origem"] = "manual"
            empresa["chegaram"].append(doc)
        elif row["status"] in ("Pendente", ""):
            empresa["faltam"].append(doc)
        else:
            empresa["fora"].append(doc)
        if conferido and conferido.get("arquivo"):
            empresa["claude"].append(conferido)

    lista = sorted(empresas.values(), key=lambda e: _ordem_empresa(e["codigo"]))
    for empresa in lista:
        empresa["esperados"] = len(empresa["chegaram"]) + len(empresa["faltam"])
    contadas = [e for e in lista if e["esperados"]]

    salvos_claude = sorted(
        (c for c in conferencias.values() if c.get("arquivo")),
        key=lambda c: (_ordem_empresa(c["codigo_empresa"]), str(c["nome_documento"]).casefold()),
    )
    chegaram = sum(len(e["chegaram"]) for e in lista)
    faltam = sum(len(e["faltam"]) for e in lista)

    do_dia = coletar_dia(
        cobranca_service,
        rodada_service,
        dia,
        pasta_onvio,
        recebidos_no_dia=getattr(pending_report_service, "recebidos_no_dia", None),
    )
    salvos_no_dia = [
        {**item, "codigo_empresa": v["codigo_empresa"], "nome_empresa": v["nome_empresa"], "hora": v["hora"]}
        for v in do_dia["verificacoes"]
        for item in v["itens"]
        if item.get("arquivo")
    ]

    return {
        "competencia": competencia,
        "ano": ano,
        "mes": mes,
        "dia": dia,
        "tem_periodo": periodo is not None,
        "empresas": lista,
        "robo": robo,
        "salvos_claude": salvos_claude,
        "dia_dados": do_dia,
        "salvos_no_dia": salvos_no_dia,
        "totais": {
            "esperados": chegaram + faltam,
            "chegaram": chegaram,
            "faltam": faltam,
            "fora": sum(len(e["fora"]) for e in lista),
            "empresas": len(contadas),
            "completas": sum(1 for e in contadas if not e["faltam"]),
            "com_falta": sum(1 for e in contadas if e["faltam"]),
            "pelo_robo": sum(1 for e in lista for d in e["chegaram"] if d["origem"] == "robo"),
            "pelo_claude": sum(1 for e in lista for d in e["chegaram"] if d["origem"] == "claude"),
            "manual": sum(1 for e in lista for d in e["chegaram"] if d["origem"] == "manual"),
            "robo_arquivos": sum(r["baixados"] for r in robo["empresas"].values() if r["situacao"] == "baixada"),
            "robo_empresas": sum(1 for r in robo["empresas"].values() if r["situacao"] == "baixada"),
            "robo_na_pasta": sum(r["na_pasta"] for r in robo["empresas"].values()),
            "robo_no_dia": sum(r["baixados_no_dia"] for r in robo["empresas"].values()),
            "cobrados": sum(1 for e in lista for d in e["faltam"] if d["cobranca"]),
        },
    }


def rodadas_recentes(rodada_service, dias: int = 31, limite: int = 20) -> list[dict]:
    """As rodadas do Claude dos ultimos dias, da mais nova para a mais antiga."""
    from datetime import timedelta

    corte = (datetime.now(timezone.utc) - timedelta(days=dias)).strftime("%Y-%m-%d %H:%M:%S")
    rodadas = [r for r in rodada_service.listar(200) if str(r.get("iniciada_em") or "") >= corte]
    rodadas.sort(key=lambda r: str(r["iniciada_em"]), reverse=True)
    return rodadas[:limite]


def procurados_nao_encontrados(cobranca_service) -> dict[tuple[int, int], str]:
    """{(documento_id, periodo_id): detalhe} dos documentos cuja ultima conferencia do Claude foi
    'nao encontrado' ou 'veio com problema'. Quem esta marcado como recebido nao entra (o
    relatorio so usa isto para os pendentes)."""
    from documentos_empresa_app.services.cobranca_service import MOTIVOS_PROBLEMA

    ultimo: dict[tuple[int, int], dict] = {}
    for verificacao in sorted(cobranca_service.listar_verificacoes(LIMITE), key=lambda v: str(v["realizada_em"])):
        for item in verificacao["itens"]:
            ultimo[(item["documento_id"], item["periodo_id"])] = {
                **item,
                "data": _data_curta(verificacao["realizada_em"]),
                "fontes": verificacao.get("fontes") or "",
            }
    resultado: dict[tuple[int, int], str] = {}
    for chave, item in ultimo.items():
        if item["resultado"] == "nao_encontrado":
            onde = f" em {item['fontes']}" if item.get("fontes") else ""
            detalhe = f"procurado{onde} em {item['data']}, não estava"
        elif item["resultado"] == "documento_com_problema":
            motivo = MOTIVOS_PROBLEMA.get(item.get("motivo") or "", "com problema")
            detalhe = f"veio errado ({motivo.lower()}) em {item['data']}"
        else:
            continue
        if item.get("observacao"):
            detalhe += f": {item['observacao']}"
        resultado[chave] = detalhe
    return resultado
