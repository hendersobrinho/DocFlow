"""Abre o DocFlow direto na janela principal, sem splash, sem tela de conexao e sem login.

Uso exclusivo de desenvolvimento - serve para ver a interface rapidamente enquanto se
mexe no layout. Conecta num banco local (DOCFLOW_DATABASE_URL ou, por padrao, o banco
'docflow_dev' no servidor local, criado se nao existir), entra como o primeiro admin e,
se o banco nao tiver nenhuma empresa, cadastra dados de exemplo.

    .venv/bin/python scripts/dev_preview.py                 # abre a janela
    .venv/bin/python scripts/dev_preview.py --screenshots DIR   # salva um PNG por tela e sai
    .venv/bin/python scripts/dev_preview.py --page Panorama     # abre ja numa tela (nome como aparece no menu)
"""

from __future__ import annotations

import argparse
from datetime import date
import os
import re
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402
from psycopg.conninfo import conninfo_to_dict, make_conninfo  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from documentos_empresa_app.app_context import ApplicationServices, build_application_services  # noqa: E402
from documentos_empresa_app.qt_ui.icons import app_icon  # noqa: E402
from documentos_empresa_app.qt_ui.main_window import MainWindow  # noqa: E402
from documentos_empresa_app.qt_ui.theme import ThemeManager  # noqa: E402
from documentos_empresa_app.utils.common import APP_NAME  # noqa: E402

DEFAULT_DEV_DATABASE_URL = "dbname=docflow_dev"

DEMO_EMPRESAS = (
    (1, "Metodos Contabilidade", "financeiro@metodos.com.br", "Carla"),
    (2, "Padaria Pao Quente", "contato@paoquente.com.br", "Jose"),
    (3, "Clinica Bem Estar", None, None),
    (4, "Construtora Alicerce", "adm@alicerce.com.br", "Marina"),
)
DEMO_DOCUMENTOS = (
    ("Extratos CC", "Banco do Brasil CC"),
    ("Extratos CC", "Sicoob CC"),
    ("Extratos aplicacao", "Sicoob Aplicacao"),
    ("Contratos", "Contrato Social"),
    ("Comprovantes", "Folha de Pagamento"),
)
DEMO_STATUSES = ("Recebido", "Recebido", "Pendente", None, "Recebido")


def ensure_database(conninfo: str) -> None:
    try:
        psycopg.connect(conninfo, connect_timeout=5).close()
        return
    except psycopg.OperationalError:
        pass
    dbname = conninfo_to_dict(conninfo).get("dbname")
    with psycopg.connect(make_conninfo(conninfo, dbname="postgres"), autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))


def login_as_admin(services: ApplicationServices) -> None:
    with services.database_maintenance_service.db_manager.connect() as connection:
        admin = connection.execute(
            """
            SELECT id, username, tipo_usuario, ativa
            FROM usuarios
            WHERE tipo_usuario = 'admin' AND ativa = 1
            ORDER BY id
            LIMIT 1
            """
        ).fetchone()
    services.session_service.login(dict(admin))


def seed_demo_data(services: ApplicationServices) -> None:
    if services.empresa_service.list_empresas(active_only=False):
        return

    hoje = date.today()
    services.periodo_service.generate_year(hoje.year)
    periodos = {(p["ano"], p["mes"]): p for p in services.periodo_service.list_periodos()}

    for codigo, nome, email, contato in DEMO_EMPRESAS:
        empresa_id = services.empresa_service.create_empresa(codigo, nome, email, contato)
        for index, (nome_tipo, nome_documento) in enumerate(DEMO_DOCUMENTOS[: 2 + codigo]):
            tipo_id = services.tipo_service.get_or_create_tipo(nome_tipo)["id"]
            documento_id = services.documento_service.create_documento(
                empresa_id, tipo_id, nome_documento, ["Email"]
            )
            for mes in range(1, hoje.month + 1):
                status = DEMO_STATUSES[(index + mes + codigo) % len(DEMO_STATUSES)]
                if mes < hoje.month and status is None:
                    status = "Recebido"
                periodo = periodos.get((hoje.year, mes))
                if periodo and status:
                    services.status_service.update_status(documento_id, periodo["id"], status)


def seed_demo_history(services: ApplicationServices) -> None:
    """Forma de envio, cobrancas (com recobranca) e uma verificacao de exemplo, para as
    telas de Cobrancas e Ficha da empresa nao abrirem vazias."""
    cobranca_service = services.cobranca_service
    if cobranca_service.listar_cobrancas(1) or cobranca_service.listar_verificacoes(1):
        return

    fila = cobranca_service.fila(somente_ativas=False)
    recebimento = {
        1: (["Email"], "financeiro@metodos.com.br", "Extratos chegam por email com assunto 'Extrato'."),
        2: (["Email", "Onvio"], "contato@paoquente.com.br", "Folha no Onvio > Departamento Pessoal."),
        4: (["Onvio"], None, "Tudo no Onvio, pasta Documentos do mes."),
    }
    for empresa in services.empresa_service.list_empresas(active_only=False):
        if empresa["codigo_empresa"] in recebimento:
            canais, email, instrucoes = recebimento[empresa["codigo_empresa"]]
            services.empresa_service.set_recebimento(empresa["id"], canais, email, instrucoes)

    for posicao, item in enumerate(fila):
        primeiro = item["documentos"][:2]
        pares = [(d["documento_id"], d["periodo_id"]) for d in primeiro]
        if not pares:
            continue
        cobranca_service.registrar_cobranca(
            item["empresa_id"], "Email", pares, destinatario=item.get("email_contato"),
            assunto=f'Documentos em aberto - {item["nome_empresa"]}',
        )
        if posicao % 2 == 0:
            cobranca_service.registrar_cobranca(item["empresa_id"], "WhatsApp", pares[:1])
        if posicao == 0 and len(pares) > 1:
            cobranca_service.registrar_verificacao(
                item["empresa_id"],
                ["Email", "Onvio"],
                [
                    {"documento_id": pares[0][0], "periodo_id": pares[0][1], "resultado": "recebido",
                     "onde": "Email do financeiro, assunto 'Extrato'"},
                    {"documento_id": pares[1][0], "periodo_id": pares[1][1], "resultado": "nao_encontrado"},
                ],
                resumo="Um extrato chegou por email; o outro ainda nao apareceu.",
            )


def seed_demo_round(services: ApplicationServices) -> None:
    """Uma rodada do Claude com todos os resultados possiveis, para as telas de Precisa de
    atencao, Verificacoes e Rodadas mostrarem como fica cada caso."""
    if services.rodada_service.listar(1):
        return
    cobranca_service = services.cobranca_service
    plano = cobranca_service.proximas_acoes(somente_ativas=False)
    empresas = [e for e in plano["empresas"] if len(e["documentos"]) >= 4]
    if not empresas:
        return
    rodada = services.rodada_service.iniciar("claude")
    empresa = empresas[0]
    docs = empresa["documentos"]
    cobranca_service.registrar_verificacao(
        empresa["empresa_id"],
        ["Email", "Onvio"],
        [
            {"documento_id": docs[0]["documento_id"], "periodo_id": docs[0]["periodo_id"], "resultado": "recebido",
             "onde": "Email de financeiro@metodos.com.br em 08/10, assunto 'Extrato setembro'"},
            {"documento_id": docs[1]["documento_id"], "periodo_id": docs[1]["periodo_id"],
             "resultado": "documento_com_problema", "motivo": "competencia_errada",
             "observacao": "Mandaram o extrato de agosto no lugar do de setembro"},
            {"documento_id": docs[2]["documento_id"], "periodo_id": docs[2]["periodo_id"],
             "resultado": "nao_encontrado"},
            {"documento_id": docs[3]["documento_id"], "periodo_id": docs[3]["periodo_id"],
             "resultado": "verificacao_falhou", "motivo": "Onvio pediu novo login"},
        ],
        resumo="Email conferido; o Onvio pediu login de novo e nao deu para olhar a pasta.",
        rodada_id=rodada["id"],
    )
    services.rodada_service.registrar_ocorrencia(
        rodada["id"], "falha", "Sem acesso ao Onvio: a sessao expirou.", empresa["empresa_id"]
    )
    if len(empresas) > 1:
        outra = empresas[1]
        services.rodada_service.registrar_ocorrencia(
            rodada["id"], "aviso", "Cliente respondeu pedindo para ligar.", outra["empresa_id"]
        )
        cobranca_service.encaminhar_para_pessoa(
            [(outra["documentos"][0]["documento_id"], outra["documentos"][0]["periodo_id"])],
            "cliente_respondeu",
            "Respondeu o email dizendo que a contadora nova vai mandar tudo; pediu para ligar.",
            rodada_id=rodada["id"],
        )
    services.rodada_service.finalizar(rodada["id"], "2 empresas olhadas; o Onvio pediu login de novo na primeira.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--screenshots", type=Path, help="salva um PNG de cada tela nesta pasta e sai")
    parser.add_argument("--page", help="nome da tela para abrir (ex: Panorama)")
    parser.add_argument("--sem-exemplos", action="store_true", help="nao cadastra dados de exemplo")
    args = parser.parse_args()

    conninfo = os.environ.get("DOCFLOW_DATABASE_URL") or DEFAULT_DEV_DATABASE_URL
    ensure_database(conninfo)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(app_icon())
    ThemeManager.instance().apply(app)

    services = build_application_services(conninfo)
    login_as_admin(services)
    if not args.sem_exemplos:
        seed_demo_data(services)
        seed_demo_history(services)
        seed_demo_round(services)

    window = MainWindow(services)
    window.show()

    # O texto do botao pode trazer um contador, ex: "Precisa de atencao (3)".
    page_titles = [re.sub(r" \(\d+\)$", "", button.text()) for _index, button in sorted(window.nav_buttons.items())]
    if args.page:
        window._select_page(page_titles.index(args.page))

    if args.screenshots:
        args.screenshots.mkdir(parents=True, exist_ok=True)
        window.resize(1440, 880)
        for index, title in enumerate(page_titles):
            window._select_page(index)
            app.processEvents()
            target = args.screenshots / f"{index + 1:02d}-{title.lower().replace(' ', '-')}.png"
            window.grab().save(str(target))
            print(target)
        window.close()
        return

    app.exec()


if __name__ == "__main__":
    main()
