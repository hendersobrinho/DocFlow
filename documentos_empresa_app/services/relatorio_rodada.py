"""Relatorio da rodada de cobranca de um dia: o que foi conferido (encontrado ou nao), o que foi
cobrado, como terminou cada rodada e o que o robo do Onvio baixou.

Os horarios do banco estao em UTC; o "dia" e sempre o dia local de quem esta olhando."""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path

LIMITE = 3000  # quantos registros recentes olhar para achar os do dia

RESULTADOS_NAO_ENCONTRADOS = ("nao_encontrado", "documento_com_problema", "verificacao_falhou")


def _momento_local(raw) -> datetime | None:
    try:
        return datetime.strptime(str(raw)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone()
    except (TypeError, ValueError):
        return None


def _do_dia(raw, dia: date) -> bool:
    momento = _momento_local(raw)
    return momento is not None and momento.date() == dia


def _hora(raw) -> str:
    momento = _momento_local(raw)
    return momento.strftime("%H:%M") if momento else "-"


def _onvio_do_dia(dia: date, pasta_base: Path | None) -> list[dict]:
    """Passadas do robo do Onvio feitas no dia (le o _resumo.json de cada competencia)."""
    if not pasta_base or not Path(pasta_base).is_dir():
        return []
    passadas: list[dict] = []
    for caminho in sorted(Path(pasta_base).glob("*/_resumo.json")):
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
            gerado = datetime.fromisoformat(str(dados.get("gerado_em")))
        except (OSError, ValueError):
            continue
        if gerado.date() != dia:
            continue
        passadas.append(
            {
                "competencia": dados.get("competencia") or caminho.parent.name,
                "pasta": dados.get("pasta") or str(caminho.parent),
                "hora": gerado.strftime("%H:%M"),
                "interrompido": dados.get("interrompido"),
                "empresas": [e for e in dados.get("empresas") or [] if isinstance(e, dict)],
            }
        )
    return passadas


def coletar_dia(
    cobranca_service, rodada_service, dia: date, pasta_onvio: Path | None = None, recebidos_no_dia=None
) -> dict:
    """Reune tudo o que aconteceu na cobranca no dia informado (data local). O que o proprio sistema
    sabe (recebidos marcados, cobrancas registradas, passadas do robo do Onvio) sempre entra; as
    conferencias e rodadas so aparecem quando o Claude as registrou."""
    recebidos = list(recebidos_no_dia(dia)) if recebidos_no_dia else []
    verificacoes = []
    for verificacao in cobranca_service.listar_verificacoes(LIMITE):
        if not _do_dia(verificacao["realizada_em"], dia):
            continue
        verificacoes.append({**verificacao, "hora": _hora(verificacao["realizada_em"])})

    cobrancas = []
    for cobranca in cobranca_service.listar_cobrancas(LIMITE):
        if not _do_dia(cobranca["realizada_em"], dia):
            continue
        cobrancas.append({**cobranca, "hora": _hora(cobranca["realizada_em"])})

    rodadas = []
    for rodada in rodada_service.listar(200):
        if not _do_dia(rodada["iniciada_em"], dia):
            continue
        rodadas.append(
            {
                **rodada,
                "hora_inicio": _hora(rodada["iniciada_em"]),
                "hora_fim": _hora(rodada["finalizada_em"]) if rodada.get("finalizada_em") else "",
            }
        )
    rodadas.sort(key=lambda r: str(r["iniciada_em"]))

    encontrados, nao_encontrados = [], []
    for verificacao in verificacoes:
        for item in verificacao["itens"]:
            linha = {
                "codigo_empresa": verificacao["codigo_empresa"],
                "nome_empresa": verificacao["nome_empresa"],
                "hora": verificacao["hora"],
                "fontes": verificacao.get("fontes") or "",
                **item,
            }
            (encontrados if item["resultado"] == "recebido" else nao_encontrados).append(linha)
    ordenar = lambda l: (int(l["codigo_empresa"]), str(l["nome_documento"]).casefold(), l["competencia"])  # noqa: E731
    encontrados.sort(key=ordenar)
    nao_encontrados.sort(key=ordenar)
    cobrancas.sort(key=lambda c: (int(c["codigo_empresa"]), str(c["realizada_em"])))

    empresas = {v["empresa_id"] for v in verificacoes} | {c["empresa_id"] for c in cobrancas}
    return {
        "dia": dia,
        "rodadas": rodadas,
        "verificacoes": verificacoes,
        "encontrados": encontrados,
        "nao_encontrados": nao_encontrados,
        "cobrancas": cobrancas,
        "onvio": _onvio_do_dia(dia, pasta_onvio),
        "recebidos": recebidos,
        "totais": {
            "recebidos": len(recebidos),
            "empresas_recebidas": len({r["empresa_id"] for r in recebidos}),
            "empresas": len(empresas),
            "encontrados": len(encontrados),
            "nao_encontrados": sum(1 for i in nao_encontrados if i["resultado"] == "nao_encontrado"),
            "com_problema": sum(1 for i in nao_encontrados if i["resultado"] == "documento_com_problema"),
            "falhas": sum(1 for i in nao_encontrados if i["resultado"] == "verificacao_falhou"),
            "cobrancas": sum(1 for c in cobrancas if not c.get("recobranca")),
            "recobrancas": sum(1 for c in cobrancas if c.get("recobranca")),
        },
    }
