r"""Linha de comando do robo do Onvio.

    python -m documentos_empresa_app.onvio 03/2026
    python -m documentos_empresa_app.onvio 03/2026 --codigos 170,180 --destino D:\Onvio --de-novo

Sem --codigos usa as empresas ativas do DocFlow.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

from documentos_empresa_app.onvio.api import OnvioError
from documentos_empresa_app.onvio.navegador import sessao_onvio
from documentos_empresa_app.onvio.robo import ROTULOS, baixar_competencia, pasta_padrao


def _empresas_do_docflow(codigos: list[str] | None) -> list[tuple[str, str]]:
    from documentos_empresa_app.app_context import build_application_services
    from documentos_empresa_app.utils.database_settings import resolve_database_conninfo

    services = build_application_services(resolve_database_conninfo())
    try:
        empresas = services.empresa_service.list_empresas(active_only=not codigos)
    finally:
        services.database_maintenance_service.db_manager.close()
    lista = [(str(e["codigo_empresa"]), e["nome_empresa"]) for e in empresas]
    if codigos:
        nomes = dict(lista)
        lista = [(c, nomes.get(c, "")) for c in codigos]
    return lista


def main(argv: list[str] | None = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description="Baixa do Onvio os documentos da competência.")
    parser.add_argument("competencia", help="MM/AAAA, ex: 03/2026")
    parser.add_argument("--codigos", help="Só estas empresas (códigos separados por vírgula)")
    parser.add_argument("--destino", help=f"Pasta (padrão: {pasta_padrao()})")
    parser.add_argument("--de-novo", action="store_true", help="Baixa de novo mesmo quem já foi baixado")
    args = parser.parse_args(argv)

    achado = re.fullmatch(r"\s*(\d{1,2})\s*[/-]\s*(\d{4})\s*", args.competencia)
    if not achado or not 1 <= int(achado.group(1)) <= 12:
        parser.error("Competência inválida. Use MM/AAAA.")
    mes, ano = int(achado.group(1)), int(achado.group(2))
    codigos = [c.strip() for c in args.codigos.split(",") if c.strip()] if args.codigos else None
    empresas = _empresas_do_docflow(codigos)

    def progresso(feitas: int, total: int, resultado, mensagem: str) -> None:
        print(f"[{feitas}/{total}] {mensagem}", flush=True)

    try:
        with sessao_onvio(avisar=lambda m: print(m, flush=True)) as api:
            resumo = baixar_competencia(
                api, ano, mes, empresas, Path(args.destino) if args.destino else None, args.de_novo, progresso
            )
    except OnvioError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    print()
    print(resumo.texto())
    print(f"Pasta: {resumo.pasta}")
    for empresa in resumo.empresas:
        if empresa.situacao not in ("baixada", "ja_baixada", "sem_pasta"):
            print(f"  {empresa.codigo} - {empresa.nome}: {ROTULOS[empresa.situacao]} {empresa.detalhe}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
