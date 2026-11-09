"""Servidor MCP do DocFlow.

Expoe os dados e as operacoes do DocFlow (empresas, documentos, tipos, meios de
recebimento, periodos, status mensais, Panorama, cobranca, relatorios, usuarios, logs e
backup) como tools MCP, reaproveitando os mesmos services da aplicacao desktop - as
regras de negocio, validacoes, permissoes de admin e o log de auditoria sao exatamente
os mesmos da interface.

Configuracao (variaveis de ambiente):
- Usuario: o servidor age como o usuario "claude" do DocFlow (criado na primeira vez, sem
  precisar de senha); tudo que for alterado fica nos logs com esse nome. Opcional:
  DOCFLOW_MCP_USUARIO / DOCFLOW_MCP_SENHA para agir como outro usuario.
- DOCFLOW_DATABASE_URL: conexao com o PostgreSQL. Sem ela, usa a conexao salva pelo app
  desktop no perfil do usuario do sistema operacional.
"""

from __future__ import annotations

import base64
from datetime import date
import json
import functools
import os
from pathlib import Path
import secrets
import threading
from typing import Any, Callable, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from documentos_empresa_app.app_context import ApplicationServices, build_application_services
from documentos_empresa_app.database.connection import DatabaseError
from documentos_empresa_app.qt_ui.viewmodels import UI_SITUATION_LABELS, PanoramaViewModel
from documentos_empresa_app.utils.common import (
    STATUS_OPTIONS,
    ValidationError,
    format_competencia,
    format_period_label,
    format_utc_timestamp,
    parse_period_label,
)
from documentos_empresa_app.services.email_sender_service import (
    SIGNATURE_CID,
    load_email_signature,
    signature_html,
)
from documentos_empresa_app.utils.database_settings import resolve_database_conninfo
from documentos_empresa_app.utils.email_format import cid_imagem, imagens_usadas, para_html, texto_com_assinatura
from documentos_empresa_app.utils.security import hash_password

USER_ENV_VAR = "DOCFLOW_MCP_USUARIO"
PASSWORD_ENV_VAR = "DOCFLOW_MCP_SENHA"
MCP_USERNAME = "claude"

StatusValue = Literal["Recebido", "Pendente", "Encerrado", "Nao cobrar", ""]
OccurrenceRule = Literal["mensal", "trimestral", "anual_janeiro"]

mcp = MCPServer(
    name="docflow",
    title="DocFlow",
    instructions=(
        "Controle mensal de documentos que empresas-cliente de um escritorio contabil precisam "
        "entregar. Empresas sao identificadas pelo codigo (codigo_empresa); competencias sao "
        "informadas como MM/AAAA. Cada documento de uma empresa recebe um status por mes: "
        "Recebido, Pendente, Encerrado (para de cobrar dali em diante) ou Nao cobrar. Use "
        "'panorama' para a visao geral de um mes e 'controle_empresa' para a grade de uma "
        "empresa. Tools de exclusao exigem confirmar=true.\n\n"
        "Rotina de cobranca (o DocFlow e a memoria da cobranca: anote tudo nele):\n"
        "1. 'iniciar_rodada' no comeco de cada passada. Tudo que voce registrar depois fica ligado "
        "a essa rodada.\n"
        "2. 'o_que_fazer_agora' diz, documento por documento, a acao certa pelas regras do sistema "
        "(verificar, cobrar, recobrar, aguardar ou com_pessoa) e o porque. Siga essa lista; nao "
        "decida prazos nem limites por conta propria. Cada empresa traz os canais por onde envia, "
        "os emails de origem e as instrucoes de onde procurar.\n"
        "3. Para 'verificar': procure nos canais com as suas ferramentas (email, Onvio) e registre "
        "com 'registrar_verificacao', um resultado por documento:\n"
        "   - recebido: achou o documento certo, da competencia certa (o sistema da baixa sozinho; "
        "descreva em 'onde' remetente, data, assunto ou pasta);\n"
        "   - documento_com_problema: veio algo, mas errado (motivo: documento_errado, "
        "competencia_errada, ilegivel_ou_incompleto, empresa_errada ou outro);\n"
        "   - nao_encontrado: procurou direito e nao esta la;\n"
        "   - verificacao_falhou: nao conseguiu olhar (sem acesso, erro, fora do ar) - diga o motivo. "
        "Isso NAO gera cobranca.\n"
        "   Na duvida, NUNCA use recebido: use documento_com_problema ou 'encaminhar_para_pessoa'.\n"
        "   Se baixar o documento (ex: anexo do email), salve na pasta da empresa (campo pasta_documentos em "
        "'obter_empresa') e informe o caminho completo em 'arquivo': as pessoas abrem o arquivo "
        "ou a pasta direto no DocFlow para conferir.\n"
        "4. Depois de verificar, chame 'o_que_fazer_agora' de novo. Para 'cobrar'/'recobrar', gere o "
        "texto com 'mensagem_cobranca', envie pelo canal da empresa e registre com "
        "'registrar_cobranca' (o sistema numera cobranca e recobrancas). Se o cliente prometer "
        "enviar ate uma data, use 'registrar_promessa_envio'. Se o cliente responder algo que "
        "precisa de decisao humana, use 'encaminhar_para_pessoa'.\n"
        "5. Qualquer coisa que der errado e nao for de um documento (email fora do ar, empresa sem "
        "contato, erro de ferramenta), registre com 'registrar_ocorrencia' (tipo falha ou aviso).\n"
        "6. 'finalizar_rodada' com um resumo curto no fim.\n"
        "'ficha_empresa' e 'registro_documento' mostram o historico completo, inclusive o caminho "
        "de cada documento pelas situacoes.\n\n"
        "Envios automaticos - cobrancas e mala direta, por email ou WhatsApp (o DocFlow guarda as "
        "regras; voce envia):\n"
        "- Tudo e por competencia: a regra lista as competencias cobradas (ex: informe trimestral = "
        "3, 6, 9, 12) e, por padrao, o envio sai no mes seguinte (competencia 12/2025 e cobrada em "
        "janeiro/2026), porque o documento so fica pronto no fim do mes.\n"
        "- 'envios_a_fazer' lista, empresa por empresa, as mensagens que ja deveriam ter saido, com "
        "canal (email ou whatsapp), destinatarios/numero, assunto e corpo prontos e eventuais "
        "'instrucoes'. So vai por WhatsApp a empresa que liberou o WhatsApp para envios no cadastro "
        "('definir_whatsapp_empresa' com usar_nos_envios). Item de email: envie com a sua "
        "ferramenta de email ou, se o usuario preferir que saia pelo email do escritorio "
        "cadastrado no DocFlow, com 'enviar_emails_pelo_docflow' (ja registra). Item de WhatsApp: "
        "o texto e 'mensagem_whatsapp' (nao 'corpo'); use 'enviar_whatsapp' (com a API configurada "
        "envia direto; senao devolve o link wa.me). Registre cada um com 'registrar_envio' "
        "(enviado, ou falhou com o motivo).\n"
        "- WhatsApp sem a API: se voce tiver acesso ao navegador do usuario (WhatsApp Web aberto), "
        "abra o whatsapp_link de cada item, confira a mensagem, clique em enviar e registre - um "
        "por vez. Item com whatsapp_e_grupo=true e um grupo: o link abre o grupo, sem texto pronto - "
        "cole a mensagem_whatsapp no grupo e envie. Sem navegador, entregue ao usuario a lista de "
        "links (ele tambem pode usar 'WhatsApp em sequencia' na tela Envios automaticos).\n"
        "- Antes de enviar para muita gente, mostre ao usuario o resultado de 'conferir_envio' "
        "(quem recebe, quem fica de fora e por que).\n"
        "- Mala direta em copia oculta (modo 'cco'): o item e UM email so - envie para 'para' (o "
        "email do escritorio) com todos os enderecos de 'cco' em copia oculta (BCC), nunca em Para/Cc, "
        "e registre com 'registrar_envio' sem codigo_empresa. Quem liberou o WhatsApp sai da copia "
        "oculta e vem como item de WhatsApp separado. A lista de empresas e mantida com "
        "'lista_mala_direta', 'incluir_na_mala_direta' e 'remover_da_mala_direta' (num envio por "
        "tipo de documento, remover tira a empresa so daquele envio e incluir devolve).\n"
        "- Textos prontos: 'listar_modelos_mensagem' e 'salvar_modelo_mensagem'.\n"
        "- Nao invente destinatarios: item com sem_contato=true e registrado como falhou.\n"
        "- As regras (ex: Informe de Rendimentos trimestral, mala direta de aviso geral) sao criadas "
        "e alteradas com 'cadastrar_envio_programado' / 'atualizar_envio_programado' quando o "
        "usuario pedir. O WhatsApp de cada empresa e cadastrado com 'definir_whatsapp_empresa'.\n\n"
        "Acesso total: alem das tools especificas (preferidas, porque aplicam as regras e registram "
        "no historico), 'consultar_banco' roda qualquer SELECT e 'executar_sql' qualquer comando de "
        "escrita ou exclusao (confirmar=true). Use-os quando o usuario pedir algo que nenhuma tool cobre."
    ),
)

_services: ApplicationServices | None = None
_services_lock = threading.Lock()
# Rodada aberta nesta conexao: verificacoes, cobrancas e ocorrencias registradas enquanto
# ela estiver aberta ficam ligadas a ela.
_rodada_atual: int | None = None
_rodada_lock = threading.Lock()


# Infraestrutura ---------------------------------------------------------------------


def _usuario_do_claude(services: ApplicationServices) -> dict:
    """Usuario em nome de quem o Claude age quando o arquivo do Claude nao traz usuario e
    senha: o "claude" do DocFlow, criado na primeira vez (admin, com uma senha aleatoria que
    ninguem precisa saber - o MCP nao usa senha). O que ele faz aparece nos logs como claude."""
    repositorio = services.user_service.usuario_repository
    with repositorio.db_manager.connect():
        user = repositorio.get_by_username(MCP_USERNAME)
        if user is None:
            user_id = repositorio.create(MCP_USERNAME, hash_password(secrets.token_urlsafe(32)), "admin", 1)
            user = repositorio.get_by_id(user_id)
    if not user.get("ativa"):
        raise ToolError(
            f'O usuario "{MCP_USERNAME}" esta inativo no DocFlow. Reative-o em Usuarios para o Claude voltar a funcionar.'
        )
    return user


def get_services() -> ApplicationServices:
    """Conecta e autentica na primeira chamada (e nao na subida do servidor), para que um
    banco fora do ar ou um usuario errado apareca como erro da tool, com a mensagem, em
    vez de impedir o cliente MCP de listar as tools."""
    global _services
    with _services_lock:
        if _services is not None:
            return _services

        username = os.environ.get(USER_ENV_VAR, "").strip()
        password = os.environ.get(PASSWORD_ENV_VAR, "")
        conninfo = resolve_database_conninfo()
        if not conninfo:
            raise ToolError(
                "Banco de dados nao configurado. Defina DOCFLOW_DATABASE_URL ou configure a conexao "
                "abrindo o DocFlow desktop uma vez."
            )

        services = build_application_services(conninfo)
        services.periodo_service.ensure_operational_years()
        if username and password:
            # Configuracao antiga, com usuario e senha no arquivo do Claude: continua valendo.
            user = services.auth_service.authenticate(username, password)
            if user.get("deve_trocar_senha"):
                raise ToolError(
                    f'O usuario "{username}" precisa trocar a senha antes de usar o DocFlow. Entre uma vez '
                    "pelo aplicativo desktop para definir a senha nova."
                )
        else:
            user = _usuario_do_claude(services)
        services.session_service.login(user)
        _services = services
        return _services


def docflow_tool(*, read_only: bool, destructive: bool = False, idempotent: bool = False) -> Callable:
    """Registra a funcao como tool MCP e converte os erros de negocio do DocFlow em
    ToolError - assim a mensagem (ex: 'Ja existe uma empresa com esse codigo') chega ao
    cliente, em vez do generico 'Error executing tool'."""

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except ToolError:
                raise
            except ValidationError as exc:
                raise ToolError(str(exc)) from exc
            except DatabaseError as exc:
                detail = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
                raise ToolError(f"Erro no banco de dados: {detail}") from exc

        annotations = ToolAnnotations(
            read_only_hint=read_only,
            destructive_hint=destructive if not read_only else None,
            idempotent_hint=idempotent if not read_only else None,
            open_world_hint=False,
        )
        mcp.tool(annotations=annotations, structured_output=True)(wrapper)
        return fn

    return decorator


def _require_confirmation(confirmar: bool, what: str) -> None:
    if not confirmar:
        raise ToolError(f"{what} nao pode ser desfeito. Chame de novo com confirmar=true para prosseguir.")


def _period(services: ApplicationServices, competencia: str) -> dict[str, Any]:
    parsed = parse_period_label(competencia)
    if parsed is None:
        raise ToolError(f'Competencia invalida: "{competencia}". Use MM/AAAA, por exemplo 05/2026.')
    ano, mes = parsed
    for periodo in services.periodo_service.list_periodos():
        if periodo["ano"] == ano and periodo["mes"] == mes:
            return periodo
    raise ToolError(
        f"A competencia {mes:02d}/{ano} ainda nao existe. Gere os periodos do ano com 'gerar_periodos_ano'."
    )


def _company(services: ApplicationServices, codigo_empresa: int) -> dict[str, Any]:
    empresa = services.empresa_service.get_empresa_by_code(codigo_empresa)
    if not empresa:
        raise ToolError(f"Nenhuma empresa com o codigo {codigo_empresa}.")
    return empresa


def _company_ids(services: ApplicationServices, codigos: list[int] | None) -> list[int] | None:
    if not codigos:
        return None
    return [_company(services, codigo)["id"] for codigo in codigos]


def _tipo_by_name(services: ApplicationServices, nome_tipo: str) -> dict[str, Any]:
    wanted = nome_tipo.strip().casefold()
    for tipo in services.tipo_service.list_tipos():
        if tipo["nome_tipo"].casefold() == wanted:
            return tipo
    nomes = ", ".join(tipo["nome_tipo"] for tipo in services.tipo_service.list_tipos())
    raise ToolError(f'Tipo de documento "{nome_tipo}" nao existe. Tipos cadastrados: {nomes}.')


def _short_period(label: str) -> str:
    return label.split(" - ", 1)[0]


def _local(raw: str | None) -> str | None:
    """Horario gravado em UTC -> horario local legivel (dd/mm/aaaa hh:mm)."""
    return format_utc_timestamp(raw) if raw else None


def _public_company(empresa: dict) -> dict[str, Any]:
    return {
        "codigo_empresa": empresa["codigo_empresa"],
        "nome_empresa": empresa["nome_empresa"],
        "ativa": bool(empresa["ativa"]),
        "cnpj": empresa.get("cnpj"),
        "email_contato": empresa.get("email_contato"),
        "nome_contato": empresa.get("nome_contato"),
        "observacao": empresa.get("observacao"),
        "pasta_documentos": empresa.get("diretorio_documentos"),
        "nao_contatar_mala_direta": bool(empresa.get("nao_contatar_mala_direta")),
        "whatsapp": empresa.get("whatsapp"),
        "whatsapp_usar_nos_envios": bool(empresa.get("whatsapp_envios")),
        "whatsapp_grupo": empresa.get("whatsapp_grupo"),
        "cobranca_inicio_dia": empresa.get("cobranca_inicio_dia"),
        "cobranca_fim_dia": empresa.get("cobranca_fim_dia"),
        "cobranca_alerta_dias": empresa.get("cobranca_alerta_dias"),
        "canais_recebimento": empresa.get("canais_recebimento"),
        "emails_origem_documentos": empresa.get("emails_origem_documentos"),
        "instrucoes_busca": empresa.get("instrucoes_busca"),
    }


def _public_document(documento: dict) -> dict[str, Any]:
    return {
        "documento_id": documento["id"],
        "tipo": documento.get("nome_tipo"),
        "nome_documento": documento["nome_documento"],
        "meios_recebimento": documento.get("meios_recebimento"),
        "observacao": documento.get("observacao"),
    }


# Consultas ---------------------------------------------------------------------------


@docflow_tool(read_only=True)
def listar_empresas(somente_ativas: bool = True) -> list[dict[str, Any]]:
    """Lista as empresas-cliente cadastradas (codigo, nome, CNPJ, contato, regras de cobranca)."""
    services = get_services()
    return [_public_company(e) for e in services.empresa_service.list_empresas(active_only=somente_ativas)]


@docflow_tool(read_only=True)
def obter_empresa(codigo_empresa: int) -> dict[str, Any]:
    """Dados completos de uma empresa, incluindo os documentos que ela precisa entregar."""
    services = get_services()
    empresa = _company(services, codigo_empresa)
    result = _public_company(empresa)
    result["documentos"] = [
        _public_document(d) for d in services.documento_service.list_documentos_empresa(empresa["id"])
    ]
    return result


@docflow_tool(read_only=True)
def listar_documentos_empresa(codigo_empresa: int) -> list[dict[str, Any]]:
    """Documentos cadastrados para uma empresa (id, tipo, nome e meios de recebimento)."""
    services = get_services()
    empresa = _company(services, codigo_empresa)
    return [_public_document(d) for d in services.documento_service.list_documentos_empresa(empresa["id"])]


@docflow_tool(read_only=True)
def listar_tipos_documento() -> list[dict[str, Any]]:
    """Tipos de documento e sua regra de ocorrencia (mensal, trimestral ou anual_janeiro)."""
    services = get_services()
    return [
        {"tipo_id": t["id"], "nome_tipo": t["nome_tipo"], "regra_ocorrencia": t["regra_ocorrencia"]}
        for t in services.tipo_service.list_tipos()
    ]


@docflow_tool(read_only=True)
def listar_meios_recebimento() -> list[dict[str, Any]]:
    """Meios de recebimento disponiveis para os documentos (ex: Email, Onvio)."""
    services = get_services()
    return [{"meio_id": m["id"], "nome_meio": m["nome_meio"]} for m in services.delivery_method_service.list_methods()]


@docflow_tool(read_only=True)
def listar_competencias(ano: int | None = None) -> list[str]:
    """Competencias (MM/AAAA) ja geradas no sistema, opcionalmente filtradas por ano."""
    services = get_services()
    return [
        f'{p["mes"]:02d}/{p["ano"]}'
        for p in services.periodo_service.list_periodos()
        if ano is None or p["ano"] == ano
    ]


@docflow_tool(read_only=True)
def panorama(competencia: str, somente_ativas: bool = True) -> dict[str, Any]:
    """Visao geral de todas as empresas numa competencia (MM/AAAA): situacao do mes,
    progresso (documentos marcados / cobraveis) e meses anteriores ainda em aberto.
    As empresas vem ordenadas da mais urgente para a menos urgente."""
    services = get_services()
    periodo = _period(services, competencia)
    viewmodel = PanoramaViewModel(services)
    viewmodel.load(periodo["id"], somente_ativas)
    linhas = []
    for row in viewmodel.rows:
        anteriores = row.get("previous_period_items") or []
        linhas.append(
            {
                "codigo_empresa": row["codigo_empresa"],
                "nome_empresa": row["nome_empresa"],
                "situacao_do_mes": UI_SITUATION_LABELS.get(row["month_status_key"], row.get("situacao")),
                "marcados": row["marcados"],
                "total_cobravel": row["total_cobravel"],
                "recebidos": row["recebidos"],
                "pendentes": row["pendentes"],
                "faltando": row["faltando"],
                "meses_anteriores_em_aberto": [
                    {"competencia": _short_period(item["periodo_label"]), "documentos": item["document_count"]}
                    for item in anteriores
                ],
            }
        )
    return {"competencia": _short_period(format_period_label(periodo["ano"], periodo["mes"])), "empresas": linhas}


@docflow_tool(read_only=True)
def controle_empresa(codigo_empresa: int, competencia_inicial: str, competencia_final: str | None = None) -> dict[str, Any]:
    """Grade de status de uma empresa: cada documento com o status de cada competencia no
    intervalo (no maximo 12 meses). 'Nao cobrar' aparece nos meses fora da ocorrencia do tipo."""
    services = get_services()
    empresa = _company(services, codigo_empresa)
    inicio = _period(services, competencia_inicial)
    fim = _period(services, competencia_final) if competencia_final else inicio
    view = services.status_service.build_control_view(empresa["id"], inicio["id"], fim["id"])
    competencias = [f'{p["mes"]:02d}/{p["ano"]}' for p in view["periodos"]]
    documentos = []
    for group in view["groups"]:
        for documento in group["documentos"]:
            documentos.append(
                {
                    "documento_id": documento["id"],
                    "tipo": group["tipo_nome"],
                    "nome_documento": documento["nome_documento"],
                    "status": {
                        competencia: (cell or {}).get("status") or None
                        for competencia, cell in zip(competencias, documento["cells"])
                    },
                }
            )
    return {"codigo_empresa": codigo_empresa, "nome_empresa": empresa["nome_empresa"], "competencias": competencias,
            "documentos": documentos}


@docflow_tool(read_only=True)
def relatorio_pendencias(
    competencia_inicial: str,
    competencia_final: str | None = None,
    codigos_empresa: list[int] | None = None,
) -> dict[str, Any]:
    """Documentos pendentes (sem marcacao ou marcados como Pendente) no intervalo de
    competencias, para todas as empresas ou so as informadas."""
    services = get_services()
    inicio = _period(services, competencia_inicial)
    fim = _period(services, competencia_final) if competencia_final else inicio
    return services.pending_report_service.list_pending_rows(
        _company_ids(services, codigos_empresa), inicio["id"], fim["id"]
    )


@docflow_tool(read_only=True)
def fila_cobranca(somente_ativas: bool = True) -> list[dict[str, Any]]:
    """O que esta em aberto hoje, empresa por empresa: fase (Em cobranca / Em atraso), por
    onde a empresa envia os documentos (canais, emails de origem, instrucoes de busca) e,
    para cada documento e competencia, quantas vezes ja foi cobrado e quando."""
    fila = get_services().cobranca_service.fila(somente_ativas=somente_ativas)
    for item in fila:
        item.pop("empresa_id", None)
        item["ultima_cobranca_em"] = _local(item["ultima_cobranca_em"])
        for documento in item["documentos"]:
            documento.pop("periodo_id", None)
            documento["ultima_cobranca_em"] = _local(documento["ultima_cobranca_em"])
    return fila


@docflow_tool(read_only=True)
def mensagem_cobranca(codigo_empresa: int, canal: Literal["email", "whatsapp"] = "email") -> dict[str, Any]:
    """Texto pronto de cobranca dos documentos em aberto de uma empresa (email com assunto
    e corpo, ou mensagem de WhatsApp). So gera o texto - nada e enviado. No email vem tambem
    'assinatura' (a do escritorio, para ir no fim; veja 'assinatura_email')."""
    services = get_services()
    queue = services.collection_service.build_collection_queue(active_only=False)
    item = next((i for i in queue["items"] if i["codigo_empresa"] == codigo_empresa), None)
    if item is None:
        raise ToolError(f"A empresa {codigo_empresa} nao tem documentos em aberto para cobrar.")
    if canal == "whatsapp":
        return {"mensagem": services.collection_service.build_whatsapp_message(item)}
    return {**services.collection_service.build_email_draft(item), "assinatura": _assinatura_para_claude()}


@docflow_tool(read_only=True)
def configuracao_cobranca() -> dict[str, Any]:
    """Regras de cobranca: dia de inicio, dia de encerramento e dias de tolerancia antes do
    alerta de atraso; e as regras de acompanhamento (dias entre uma cobranca e a proxima,
    maximo de recobrancas antes de passar para uma pessoa, e se documento com problema vai
    direto para uma pessoa)."""
    services = get_services().collection_service
    return {**services.get_global_settings(), **services.get_followup_rules()}


@docflow_tool(read_only=True)
def listar_logs(limite: int = 100, codigo_empresa: int | None = None, competencia: str | None = None) -> list[dict[str, Any]]:
    """Historico de alteracoes (auditoria). Somente administradores."""
    services = get_services()
    empresa_id = _company(services, codigo_empresa)["id"] if codigo_empresa is not None else None
    ano = mes = None
    if competencia:
        parsed = parse_period_label(competencia)
        if parsed is None:
            raise ToolError(f'Competencia invalida: "{competencia}". Use MM/AAAA.')
        ano, mes = parsed
    logs = services.log_service.list_logs(limit=limite, empresa_id=empresa_id, periodo_ano=ano, periodo_mes=mes)
    return [
        {k: log.get(k) for k in ("data_hora", "username", "acao", "empresa_nome", "descricao")}
        for log in logs
    ]


@docflow_tool(read_only=True)
def listar_usuarios() -> list[dict[str, Any]]:
    """Usuarios do DocFlow (sem senha)."""
    return [
        {
            "usuario_id": u["id"],
            "username": u["username"],
            "tipo_usuario": u["tipo_usuario"],
            "ativo": bool(u["ativa"]),
        }
        for u in get_services().user_service.list_users()
    ]


# Ficha, cobrancas e verificacoes ------------------------------------------------------


class ItemCobranca(BaseModel):
    documento_id: int = Field(description="id do documento (ver listar_documentos_empresa)")
    competencia: str = Field(description="competencia cobrada, MM/AAAA")


ResultadoVerificacao = Literal["recebido", "documento_com_problema", "nao_encontrado", "verificacao_falhou"]
MotivoPessoa = Literal["cliente_respondeu", "documento_com_problema", "sem_canal", "baixa_falhou", "outro"]


class ItemVerificacao(BaseModel):
    documento_id: int = Field(description="id do documento verificado")
    competencia: str = Field(description="competencia do documento, MM/AAAA")
    resultado: ResultadoVerificacao = Field(
        description=(
            "recebido = achou o documento certo (o sistema da baixa); documento_com_problema = veio "
            "algo errado; nao_encontrado = procurou e nao esta la; verificacao_falhou = nao "
            "conseguiu olhar (nao gera cobranca). Na duvida, nunca use recebido."
        )
    )
    motivo: str | None = Field(
        default=None,
        description=(
            "documento_com_problema: documento_errado, competencia_errada, ilegivel_ou_incompleto, "
            "empresa_errada ou outro. verificacao_falhou: o motivo (obrigatorio), ex: 'sem acesso ao Onvio'."
        ),
    )
    onde: str | None = Field(
        default=None, description="onde foi encontrado: remetente, data, assunto do email, pasta do Onvio..."
    )
    observacao: str | None = Field(default=None, description="qualquer detalhe relevante")
    arquivo: str | None = Field(
        default=None,
        description=(
            "caminho completo do arquivo, se voce baixou o documento (ex: anexo do email salvo na "
            "pasta da empresa). Com isso as pessoas abrem o documento ou a pasta direto no DocFlow."
        ),
    )


def _format_historico(evento: dict) -> dict[str, Any]:
    base = {
        "data": _local(evento["realizada_em"]),
        "por": evento.get("username"),
    }
    if evento.get("tipo_evento") == "verificacao" or "fontes" in evento:
        return {
            **base,
            "evento": "Verificacao",
            "fontes": evento["fontes"],
            "resumo": evento.get("resumo"),
            "itens": evento["itens"],
        }
    return {
        **base,
        "evento": "Recobranca" if evento.get("recobranca") else "Cobranca",
        "canal": evento["canal"],
        "destinatario": evento.get("destinatario"),
        "assunto": evento.get("assunto"),
        "observacao": evento.get("observacao"),
        "itens": evento["itens"],
    }


@docflow_tool(read_only=True)
def ficha_empresa(codigo_empresa: int, limite_historico: int = 30) -> dict[str, Any]:
    """Ficha completa da empresa: dados, como envia os documentos ('recebimento' junta os
    canais marcados na empresa com o meio de cada documento), cada documento com o
    status do mes atual e quantas vezes foi cobrado/recobrado, o que esta em aberto e o
    historico de cobrancas e verificacoes (mais recente primeiro)."""
    services = get_services()
    empresa = _company(services, codigo_empresa)
    ficha = services.cobranca_service.ficha_empresa(empresa["id"], limite_historico=limite_historico)
    for documento in ficha["documentos"]:
        documento["ultima_cobranca_em"] = _local(documento["ultima_cobranca_em"])
    totais = ficha["totais"]
    totais["ultima_cobranca_em"] = _local(totais["ultima_cobranca_em"])
    totais["ultima_verificacao_em"] = _local(totais["ultima_verificacao_em"])
    return {
        "empresa": _public_company(ficha["empresa"]),
        "competencia_atual": ficha["competencia_atual"],
        "totais": totais,
        "documentos": ficha["documentos"],
        "recebimento": ficha["recebimento"],
        "em_aberto": ficha["em_aberto"],
        "proximas_acoes": [
            {k: v for k, v in doc.items() if k != "periodo_id"}
            for doc in (ficha["proximas_acoes"] or {}).get("documentos", [])
        ],
        "historico": [_format_historico(evento) for evento in ficha["historico"]],
    }


@docflow_tool(read_only=True)
def registro_documento(documento_id: int) -> dict[str, Any]:
    """Registro proprio de um documento, competencia por competencia: status, quantas vezes
    foi cobrado e recobrado (com data, canal e quem cobrou) e o resultado das verificacoes."""
    registro = get_services().cobranca_service.registro_documento(documento_id)
    for competencia in registro["competencias"]:
        competencia["status_atualizado_em"] = _local(competencia["status_atualizado_em"])
        for contato in competencia["contatos"]:
            contato["realizada_em"] = _local(contato["realizada_em"])
        for verificacao in competencia["verificacoes"]:
            verificacao["realizada_em"] = _local(verificacao["realizada_em"])
        for passo in competencia["caminho"]:
            passo["em"] = _local(passo["em"])
    return registro


@docflow_tool(read_only=True)
def historico_cobrancas(codigo_empresa: int | None = None, limite: int = 50) -> list[dict[str, Any]]:
    """Cobrancas registradas (mais recentes primeiro), de todas as empresas ou de uma."""
    services = get_services()
    empresa_id = _company(services, codigo_empresa)["id"] if codigo_empresa is not None else None
    cobrancas = services.cobranca_service.listar_cobrancas(limite, empresa_id=empresa_id)
    return [
        {"empresa": f'{c["codigo_empresa"]} - {c["nome_empresa"]}', **_format_historico(c)} for c in cobrancas
    ]


@docflow_tool(read_only=True)
def historico_verificacoes(codigo_empresa: int | None = None, limite: int = 50) -> list[dict[str, Any]]:
    """Relatorios de verificacao registrados (mais recentes primeiro): onde se procurou e o
    que foi ou nao encontrado."""
    services = get_services()
    empresa_id = _company(services, codigo_empresa)["id"] if codigo_empresa is not None else None
    verificacoes = services.cobranca_service.listar_verificacoes(limite, empresa_id=empresa_id)
    return [
        {"empresa": f'{v["codigo_empresa"]} - {v["nome_empresa"]}', **_format_historico(v)} for v in verificacoes
    ]


@docflow_tool(read_only=False, idempotent=True)
def definir_recebimento_empresa(
    codigo_empresa: int,
    canais_recebimento: list[str] | None = None,
    emails_origem_documentos: list[str] | None = None,
    instrucoes_busca: str | None = None,
) -> dict[str, Any]:
    """Define como a empresa envia os documentos: canais (ex: ["Email", "Onvio"]), emails de
    onde os documentos chegam e instrucoes livres de onde/como procura-los (ex: 'assunto
    Extrato; Onvio > pasta Bancos'). Campos omitidos ficam como estao; lista vazia ou texto
    vazio limpam o campo."""
    services = get_services()
    empresa = _company(services, codigo_empresa)
    services.empresa_service.set_recebimento(
        empresa["id"],
        canais_recebimento if canais_recebimento is not None else empresa.get("canais_recebimento"),
        emails_origem_documentos if emails_origem_documentos is not None else empresa.get("emails_origem_documentos"),
        instrucoes_busca if instrucoes_busca is not None else empresa.get("instrucoes_busca"),
    )
    return _public_company(services.empresa_service.get_empresa(empresa["id"]))


@docflow_tool(read_only=False)
def registrar_cobranca(
    codigo_empresa: int,
    canal: str,
    itens: list[ItemCobranca] | None = None,
    destinatario: str | None = None,
    assunto: str | None = None,
    mensagem: str | None = None,
    observacao: str | None = None,
) -> dict[str, Any]:
    """Registra uma cobranca JA FEITA (o envio em si e feito por fora - email, WhatsApp,
    Onvio). Sem 'itens', registra todos os documentos em aberto da empresa. O sistema
    numera cada documento/competencia: 1a vez = cobranca, seguintes = recobranca."""
    services = get_services()
    empresa = _company(services, codigo_empresa)
    pares = None
    if itens:
        pares = [(item.documento_id, _period(services, item.competencia)["id"]) for item in itens]
    return services.cobranca_service.registrar_cobranca(
        empresa["id"],
        canal,
        pares,
        destinatario=destinatario,
        assunto=assunto,
        mensagem=mensagem,
        observacao=observacao,
        rodada_id=_rodada_atual,
    )


@docflow_tool(read_only=False)
def registrar_verificacao(
    codigo_empresa: int,
    fontes: list[str],
    itens: list[ItemVerificacao],
    resumo: str | None = None,
    marcar_recebidos: bool = True,
) -> dict[str, Any]:
    """Registra o relatorio de uma verificacao feita nos canais da empresa (fontes, ex:
    ["Email", "Onvio"]): para cada documento/competencia, o resultado e onde foi visto. Os
    recebidos ganham baixa (status Recebido), a menos que marcar_recebidos=false; se a
    baixa falhar, o documento vai para uma pessoa. A resposta diz, por item, se a baixa
    foi feita."""
    services = get_services()
    empresa = _company(services, codigo_empresa)
    itens_service = [
        {
            "documento_id": item.documento_id,
            "periodo_id": _period(services, item.competencia)["id"],
            "resultado": item.resultado,
            "motivo": item.motivo,
            "onde": item.onde,
            "observacao": item.observacao,
            "arquivo": item.arquivo,
        }
        for item in itens
    ]
    return services.cobranca_service.registrar_verificacao(
        empresa["id"],
        fontes,
        itens_service,
        resumo=resumo,
        marcar_recebidos=marcar_recebidos,
        rodada_id=_rodada_atual,
    )


# Rodadas e acompanhamento --------------------------------------------------------------


def _pares(services: ApplicationServices, empresa: dict, itens: list[ItemCobranca] | None) -> list[tuple[int, int]]:
    if itens:
        return [(item.documento_id, _period(services, item.competencia)["id"]) for item in itens]
    pares = services.cobranca_service._itens_em_aberto(empresa["id"])
    if not pares:
        raise ToolError(f'A empresa {empresa["codigo_empresa"]} nao tem documentos em aberto.')
    return pares


def _public_rodada(rodada: dict) -> dict[str, Any]:
    return {
        "rodada_id": rodada["id"],
        "status": rodada["status_label"],
        "iniciada_em": _local(rodada["iniciada_em"]),
        "finalizada_em": _local(rodada["finalizada_em"]),
        "resumo": rodada["resumo"],
        "empresas": rodada["empresas"],
        "verificacoes": rodada["verificacoes"],
        "cobrancas": rodada["cobrancas"],
        "falhas": rodada["falhas"],
        "avisos": rodada["avisos"],
        "ocorrencias": [
            {
                "tipo": o["tipo"],
                "mensagem": o["mensagem"],
                "empresa": f'{o["codigo_empresa"]} - {o["nome_empresa"]}' if o["codigo_empresa"] else None,
                "em": _local(o["criado_em"]),
            }
            for o in rodada.get("ocorrencias", [])
        ],
    }


def _ensure_rodada(services: ApplicationServices) -> int:
    global _rodada_atual
    with _rodada_lock:
        if _rodada_atual is not None:
            rodada = services.rodada_service.obter(_rodada_atual)
            if rodada["status"] == "em_andamento":
                return _rodada_atual
        _rodada_atual = services.rodada_service.iniciar("claude")["id"]
        return _rodada_atual


@docflow_tool(read_only=False)
def iniciar_rodada() -> dict[str, Any]:
    """Abre uma rodada de cobranca (uma passada pelas empresas). Verificacoes, cobrancas e
    ocorrencias registradas a seguir ficam ligadas a ela, e as pessoas veem no DocFlow o que
    cada rodada fez e o que deu errado. Se ja houver uma rodada aberta nesta conexao, ela
    continua."""
    services = get_services()
    return _public_rodada(services.rodada_service.obter(_ensure_rodada(services)))


@docflow_tool(read_only=False)
def registrar_ocorrencia(
    tipo: Literal["falha", "aviso", "info"], mensagem: str, codigo_empresa: int | None = None
) -> dict[str, Any]:
    """Anota na rodada algo que aconteceu e nao e resultado de um documento: falha (algo
    impediu o trabalho - email fora do ar, sem acesso ao Onvio, erro de ferramenta), aviso
    (algo estranho que uma pessoa deve olhar - empresa sem email de contato, cliente bravo)
    ou info. Abre uma rodada se nao houver."""
    services = get_services()
    empresa_id = _company(services, codigo_empresa)["id"] if codigo_empresa is not None else None
    return services.rodada_service.registrar_ocorrencia(_ensure_rodada(services), tipo, mensagem, empresa_id)


@docflow_tool(read_only=False)
def finalizar_rodada(resumo: str | None = None) -> dict[str, Any]:
    """Fecha a rodada aberta com um resumo curto do que foi feito. Fica 'Concluida com
    falhas' se alguma falha foi registrada."""
    global _rodada_atual
    services = get_services()
    with _rodada_lock:
        if _rodada_atual is None:
            raise ToolError("Nao ha rodada aberta nesta conexao.")
        rodada = services.rodada_service.finalizar(_rodada_atual, resumo)
        _rodada_atual = None
    return _public_rodada(rodada)


@docflow_tool(read_only=True)
def historico_rodadas(limite: int = 10) -> list[dict[str, Any]]:
    """Rodadas anteriores (mais recente primeiro) com o que cada uma fez e o que deu errado.
    Uma rodada que nunca foi finalizada aparece como Interrompida."""
    return [_public_rodada(r) for r in get_services().rodada_service.listar(limite)]


@docflow_tool(read_only=True)
def o_que_fazer_agora(codigo_empresa: int | None = None, incluir_aguardando: bool = False) -> dict[str, Any]:
    """Plano de acao calculado pelas regras do sistema. Para cada documento em aberto diz a
    acao (verificar, cobrar, recobrar, aguardar, com_pessoa), o porque, a situacao atual e
    quantas vezes ja foi cobrado. Empresas vem na ordem de prioridade, com os canais, emails
    de origem e instrucoes de busca. Por padrao omite documentos em 'aguardar' e
    'com_pessoa' (nao ha nada para voce fazer neles); o resumo conta todos."""
    services = get_services()
    empresa_id = _company(services, codigo_empresa)["id"] if codigo_empresa is not None else None
    plano = services.cobranca_service.proximas_acoes(empresa_id)
    empresas = []
    for empresa in plano["empresas"]:
        documentos = []
        for doc in empresa["documentos"]:
            if not incluir_aguardando and doc["acao"] in ("aguardar", "com_pessoa"):
                continue
            doc.pop("periodo_id", None)
            doc["ultima_cobranca_em"] = _local(doc["ultima_cobranca_em"])
            doc["situacao_atualizada_em"] = _local(doc["situacao_atualizada_em"])
            documentos.append(doc)
        if not documentos:
            continue
        empresa.pop("empresa_id", None)
        empresa["documentos"] = documentos
        empresas.append(empresa)
    return {
        "data": plano["data"],
        "regras": plano["regras"],
        "resumo": plano["resumo"],
        "rodada_aberta": _rodada_atual,
        "empresas": empresas,
    }


@docflow_tool(read_only=False)
def registrar_promessa_envio(
    codigo_empresa: int,
    aguardar_ate: str,
    itens: list[ItemCobranca] | None = None,
    detalhe: str | None = None,
) -> dict[str, Any]:
    """O cliente prometeu enviar: os documentos ficam em 'aguardar' ate a data (AAAA-MM-DD)
    e depois voltam a ser verificados. Sem 'itens', vale para tudo que esta em aberto na
    empresa. Anote em 'detalhe' o que o cliente disse e por onde."""
    services = get_services()
    empresa = _company(services, codigo_empresa)
    return services.cobranca_service.registrar_promessa(
        _pares(services, empresa, itens), aguardar_ate, detalhe, rodada_id=_rodada_atual
    )


@docflow_tool(read_only=False)
def encaminhar_para_pessoa(
    codigo_empresa: int,
    motivo: MotivoPessoa,
    detalhe: str,
    itens: list[ItemCobranca] | None = None,
) -> dict[str, Any]:
    """Tira os documentos do fluxo automatico e coloca na tela 'Precisa de atencao' do
    DocFlow, para uma pessoa decidir. Use quando estiver em duvida, quando o cliente
    responder algo que precisa de decisao, ou quando nao houver como cobrar. 'detalhe'
    explica o caso para a pessoa. Sem 'itens', vale para tudo em aberto na empresa."""
    services = get_services()
    empresa = _company(services, codigo_empresa)
    return services.cobranca_service.encaminhar_para_pessoa(
        _pares(services, empresa, itens), motivo, detalhe, rodada_id=_rodada_atual
    )


# Empresas ----------------------------------------------------------------------------


@docflow_tool(read_only=False)
def cadastrar_empresa(
    codigo_empresa: int,
    nome_empresa: str,
    email_contato: str | None = None,
    nome_contato: str | None = None,
    observacao: str | None = None,
    cnpj: str | None = None,
) -> dict[str, Any]:
    """Cadastra uma empresa-cliente. Observacao tem no maximo 255 caracteres.
    email_contato aceita mais de um email separado por virgula (a cobranca vai para todos)."""
    services = get_services()
    empresa_id = services.empresa_service.create_empresa(
        codigo_empresa, nome_empresa, email_contato, nome_contato, observacao, cnpj
    )
    return _public_company(services.empresa_service.get_empresa(empresa_id))


@docflow_tool(read_only=False, idempotent=True)
def atualizar_empresa(
    codigo_empresa: int,
    nome_empresa: str | None = None,
    email_contato: str | None = None,
    nome_contato: str | None = None,
    observacao: str | None = None,
    cnpj: str | None = None,
) -> dict[str, Any]:
    """Atualiza dados cadastrais. So os campos informados mudam; para apagar um campo
    opcional, informe texto vazio (""). email_contato aceita mais de um email separado por
    virgula (a cobranca vai para todos)."""
    services = get_services()
    empresa = _company(services, codigo_empresa)

    def pick(new: str | None, field: str):
        return empresa.get(field) if new is None else new

    services.empresa_service.update_empresa(
        empresa["id"],
        pick(nome_empresa, "nome_empresa"),
        pick(email_contato, "email_contato"),
        pick(nome_contato, "nome_contato"),
        pick(observacao, "observacao"),
        pick(cnpj, "cnpj"),
    )
    return _public_company(services.empresa_service.get_empresa(empresa["id"]))


@docflow_tool(read_only=False, idempotent=True)
def definir_empresa_ativa(codigo_empresa: int, ativa: bool) -> dict[str, Any]:
    """Ativa ou inativa uma empresa (inativas saem do Panorama e da cobranca por padrao)."""
    services = get_services()
    empresa = _company(services, codigo_empresa)
    services.empresa_service.set_empresa_ativa(empresa["id"], ativa)
    return _public_company(services.empresa_service.get_empresa(empresa["id"]))


@docflow_tool(read_only=False, idempotent=True)
def definir_pasta_empresa(codigo_empresa: int, pasta: str | None) -> dict[str, Any]:
    """Define (ou limpa, com null) a pasta no disco onde ficam os documentos da empresa."""
    services = get_services()
    empresa = _company(services, codigo_empresa)
    services.empresa_service.set_empresa_directory(empresa["id"], pasta)
    return _public_company(services.empresa_service.get_empresa(empresa["id"]))


@docflow_tool(read_only=False, idempotent=True)
def definir_mala_direta_empresa(codigo_empresa: int, nao_contatar: bool) -> dict[str, Any]:
    """Marca se a empresa deve ficar fora da mala direta por email."""
    services = get_services()
    empresa = _company(services, codigo_empresa)
    services.empresa_service.set_nao_contatar_mala_direta(empresa["id"], nao_contatar)
    return _public_company(services.empresa_service.get_empresa(empresa["id"]))


@docflow_tool(read_only=False, idempotent=True)
def definir_whatsapp_empresa(
    codigo_empresa: int,
    whatsapp: str | None = None,
    usar_nos_envios: bool | None = None,
    link_grupo: str | None = None,
) -> dict[str, Any]:
    """WhatsApp de cobranca da empresa. whatsapp: numero (ex: "(27) 99999-8888"; sem DDI
    assume +55), "" apaga, omitido mantem. usar_nos_envios: so com true os envios automaticos
    vao por WhatsApp para ela. link_grupo: link de convite do grupo onde a empresa e atendida
    (https://chat.whatsapp.com/...) - tem preferencia sobre o numero; "" apaga, omitido mantem."""
    services = get_services()
    empresa = _company(services, codigo_empresa)
    if whatsapp is not None:
        services.empresa_service.set_whatsapp(empresa["id"], whatsapp)
    if usar_nos_envios is not None or link_grupo is not None:
        atual = services.empresa_service.get_empresa(empresa["id"])
        usar = bool(atual.get("whatsapp_envios")) if usar_nos_envios is None else usar_nos_envios
        grupo = atual.get("whatsapp_grupo") if link_grupo is None else link_grupo
        services.empresa_service.set_whatsapp_envios(empresa["id"], usar, grupo)
    return _public_company(services.empresa_service.get_empresa(empresa["id"]))


@docflow_tool(read_only=False, idempotent=True)
def definir_cobranca_empresa(
    codigo_empresa: int,
    inicio_dia: int | None = None,
    fim_dia: int | None = None,
    alerta_apos_dias: int | None = None,
) -> dict[str, Any]:
    """Regra de cobranca propria da empresa. Campos nulos usam a regra global."""
    services = get_services()
    empresa = _company(services, codigo_empresa)
    services.collection_service.update_company_settings(empresa["id"], inicio_dia, fim_dia, alerta_apos_dias)
    return _public_company(services.empresa_service.get_empresa(empresa["id"]))


@docflow_tool(read_only=False, idempotent=True)
def definir_cobranca_global(inicio_dia: int, fim_dia: int, alerta_apos_dias: int) -> dict[str, Any]:
    """Regra global de cobranca, usada pelas empresas sem regra propria."""
    return get_services().collection_service.update_global_settings(inicio_dia, fim_dia, alerta_apos_dias)


@docflow_tool(read_only=False, idempotent=True)
def definir_regras_acompanhamento(
    dias_entre_cobrancas: int, max_recobrancas: int, problema_vai_para_pessoa: bool
) -> dict[str, Any]:
    """Regras do acompanhamento usadas por 'o_que_fazer_agora': quantos dias esperar depois
    de cobrar antes de verificar/recobrar, quantas recobrancas antes de passar o caso para
    uma pessoa, e se documento com problema vai direto para uma pessoa."""
    return get_services().collection_service.update_followup_rules(
        dias_entre_cobrancas, max_recobrancas, problema_vai_para_pessoa
    )


@docflow_tool(read_only=False, destructive=True)
def excluir_empresa(codigo_empresa: int, confirmar: bool = False) -> str:
    """Exclui a empresa com todos os seus documentos e status. Exige confirmar=true."""
    services = get_services()
    empresa = _company(services, codigo_empresa)
    _require_confirmation(confirmar, f'Excluir a empresa "{empresa["nome_empresa"]}" e todos os seus documentos')
    services.empresa_service.delete_empresa(empresa["id"])
    return f'Empresa {codigo_empresa} - {empresa["nome_empresa"]} excluida.'


# Documentos --------------------------------------------------------------------------


@docflow_tool(read_only=False)
def cadastrar_documento(
    codigo_empresa: int,
    tipo: str,
    nome_documento: str,
    meios_recebimento: list[str] | None = None,
    observacao: str | None = None,
) -> dict[str, Any]:
    """Cadastra um documento que a empresa precisa entregar. 'tipo' e o nome de um tipo ja
    cadastrado (ver listar_tipos_documento). O nome e curto e nao repete o tipo (extrato de
    conta corrente: so o banco); numero da conta, produto, contrato vao em 'observacao'."""
    services = get_services()
    empresa = _company(services, codigo_empresa)
    tipo_row = _tipo_by_name(services, tipo)
    documento_id = services.documento_service.create_documento(
        empresa["id"], tipo_row["id"], nome_documento, meios_recebimento, observacao=observacao
    )
    return _public_document(services.documento_service.get_documento(documento_id))


@docflow_tool(read_only=False, idempotent=True)
def atualizar_documento(
    documento_id: int,
    tipo: str | None = None,
    nome_documento: str | None = None,
    meios_recebimento: list[str] | None = None,
    observacao: str | None = None,
) -> dict[str, Any]:
    """Altera tipo, nome, meios de recebimento e/ou observacao de um documento. So os campos
    informados mudam (observacao vazia "" limpa)."""
    services = get_services()
    documento = services.documento_service.get_documento(documento_id)
    tipo_id = _tipo_by_name(services, tipo)["id"] if tipo else documento["tipo_documento_id"]
    services.documento_service.update_documento(
        documento_id,
        tipo_id,
        nome_documento if nome_documento is not None else documento["nome_documento"],
        meios_recebimento if meios_recebimento is not None else documento.get("meios_recebimento"),
        **({"observacao": observacao} if observacao is not None else {}),
    )
    return _public_document(services.documento_service.get_documento(documento_id))


@docflow_tool(read_only=False, destructive=True)
def excluir_documento(documento_id: int, confirmar: bool = False) -> str:
    """Exclui um documento e todo o seu historico de status. Exige confirmar=true."""
    services = get_services()
    documento = services.documento_service.get_documento(documento_id)
    _require_confirmation(confirmar, f'Excluir o documento "{documento["nome_documento"]}" e seu historico')
    services.documento_service.delete_documento(documento_id)
    return f'Documento {documento_id} - {documento["nome_documento"]} excluido.'


# Status ------------------------------------------------------------------------------


@docflow_tool(read_only=False, idempotent=True)
def marcar_status(documento_ids: list[int], competencia: str, status: StatusValue) -> dict[str, Any]:
    """Marca o status de um ou mais documentos numa competencia (MM/AAAA). Use "" para
    limpar a marcacao. 'Encerrado' faz o documento parar de ser cobrado dali em diante."""
    services = get_services()
    periodo = _period(services, competencia)
    valor = status or None
    if valor not in STATUS_OPTIONS and valor is not None:
        raise ToolError(f"Status invalido: {status}.")
    if len(documento_ids) == 1:
        services.status_service.update_status(documento_ids[0], periodo["id"], valor)
        return {"atualizados": 1, "competencia": competencia, "status": valor}
    resultado = services.status_service.update_status_batch(documento_ids, periodo["id"], valor)
    return {"competencia": competencia, "status": valor, **resultado}


# Tipos, meios e periodos ---------------------------------------------------------------


@docflow_tool(read_only=False)
def cadastrar_tipo_documento(nome_tipo: str, regra_ocorrencia: OccurrenceRule = "mensal") -> dict[str, Any]:
    """Cadastra um tipo de documento. regra_ocorrencia: mensal, trimestral (mar/jun/set/dez)
    ou anual_janeiro."""
    services = get_services()
    tipo_id = services.tipo_service.create_tipo(nome_tipo, regra_ocorrencia)
    tipo = services.tipo_service.get_tipo(tipo_id)
    return {"tipo_id": tipo["id"], "nome_tipo": tipo["nome_tipo"], "regra_ocorrencia": tipo["regra_ocorrencia"]}


@docflow_tool(read_only=False, idempotent=True)
def atualizar_tipo_documento(tipo_id: int, nome_tipo: str, regra_ocorrencia: OccurrenceRule) -> dict[str, Any]:
    """Renomeia um tipo e/ou troca a regra de ocorrencia."""
    services = get_services()
    services.tipo_service.update_tipo(tipo_id, nome_tipo, regra_ocorrencia)
    tipo = services.tipo_service.get_tipo(tipo_id)
    return {"tipo_id": tipo["id"], "nome_tipo": tipo["nome_tipo"], "regra_ocorrencia": tipo["regra_ocorrencia"]}


@docflow_tool(read_only=False, destructive=True)
def excluir_tipo_documento(tipo_id: int, confirmar: bool = False) -> str:
    """Exclui um tipo que nao esteja em uso por nenhum documento. Exige confirmar=true."""
    services = get_services()
    tipo = services.tipo_service.get_tipo(tipo_id)
    _require_confirmation(confirmar, f'Excluir o tipo "{tipo["nome_tipo"]}"')
    services.tipo_service.delete_tipo(tipo_id)
    return f'Tipo "{tipo["nome_tipo"]}" excluido.'


@docflow_tool(read_only=False)
def cadastrar_meio_recebimento(nome_meio: str) -> dict[str, Any]:
    """Cadastra um meio de recebimento (ex: Email, Onvio, Portal)."""
    services = get_services()
    method_id = services.delivery_method_service.create_method(nome_meio)
    return {"meio_id": method_id, "nome_meio": services.delivery_method_service.get_method(method_id)["nome_meio"]}


@docflow_tool(read_only=False, idempotent=True)
def renomear_meio_recebimento(meio_id: int, nome_meio: str) -> str:
    """Renomeia um meio de recebimento (os documentos que usam o nome antigo sao atualizados)."""
    services = get_services()
    afetados = services.delivery_method_service.update_method(meio_id, nome_meio)
    return f'Meio renomeado para "{nome_meio}" ({afetados} documento(s) atualizado(s)).'


@docflow_tool(read_only=False, destructive=True)
def excluir_meio_recebimento(meio_id: int, confirmar: bool = False) -> str:
    """Exclui um meio de recebimento e o remove dos documentos que o usam. Exige confirmar=true."""
    services = get_services()
    meio = services.delivery_method_service.get_method(meio_id)
    _require_confirmation(confirmar, f'Excluir o meio de recebimento "{meio["nome_meio"]}"')
    afetados = services.delivery_method_service.delete_method(meio_id)
    return f'Meio "{meio["nome_meio"]}" excluido ({afetados} documento(s) atualizado(s)).'


@docflow_tool(read_only=False, idempotent=True)
def gerar_periodos_ano(ano: int) -> dict[str, Any]:
    """Gera as 12 competencias de um ano (so cria as que faltam)."""
    return get_services().periodo_service.generate_year(ano)


@docflow_tool(read_only=False, destructive=True)
def excluir_periodos_ano(ano: int, confirmar: bool = False) -> dict[str, Any]:
    """Exclui todas as competencias de um ano e os status marcados nelas. Exige confirmar=true."""
    _require_confirmation(confirmar, f"Excluir o ano {ano} e todos os status marcados nele")
    return get_services().periodo_service.delete_year(ano)


# Usuarios ----------------------------------------------------------------------------


@docflow_tool(read_only=False)
def cadastrar_usuario(
    username: str, senha: str, tipo_usuario: Literal["admin", "comum"] = "comum", ativo: bool = True
) -> dict[str, Any]:
    """Cadastra um usuario do DocFlow. Somente administradores."""
    services = get_services()
    user_id = services.user_service.create_user(username, senha, tipo_usuario, ativo)
    user = services.user_service.get_user(user_id)
    return {"usuario_id": user["id"], "username": user["username"], "tipo_usuario": user["tipo_usuario"]}


@docflow_tool(read_only=False, idempotent=True)
def atualizar_usuario(
    usuario_id: int,
    username: str | None = None,
    tipo_usuario: Literal["admin", "comum"] | None = None,
    ativo: bool | None = None,
    nova_senha: str | None = None,
) -> dict[str, Any]:
    """Altera nome, perfil, situacao ou senha de um usuario. Somente administradores."""
    services = get_services()
    user = services.user_service.get_user(usuario_id)
    services.user_service.update_user(
        usuario_id,
        username or user["username"],
        tipo_usuario or user["tipo_usuario"],
        bool(user["ativa"]) if ativo is None else ativo,
        password=nova_senha,
    )
    user = services.user_service.get_user(usuario_id)
    return {"usuario_id": user["id"], "username": user["username"], "tipo_usuario": user["tipo_usuario"],
            "ativo": bool(user["ativa"])}


# Arquivos: relatorios, planilhas, backup -----------------------------------------------


@docflow_tool(read_only=False)
def exportar_relatorio_pendencias(
    caminho_arquivo: str,
    competencia_inicial: str,
    competencia_final: str | None = None,
    formato: Literal["xlsx", "pdf"] = "xlsx",
    codigos_empresa: list[int] | None = None,
) -> dict[str, Any]:
    """Gera o relatorio de pendencias em Excel ou PDF no caminho informado (no computador
    onde o servidor MCP roda)."""
    services = get_services()
    inicio = _period(services, competencia_inicial)
    fim = _period(services, competencia_final) if competencia_final else inicio
    ids = _company_ids(services, codigos_empresa)
    if formato == "pdf":
        return services.pending_report_service.export_pending_report_pdf(caminho_arquivo, ids, inicio["id"], fim["id"])
    return services.pending_report_service.export_pending_report(caminho_arquivo, ids, inicio["id"], fim["id"])


@docflow_tool(read_only=False)
def importar_planilha(
    caminho_arquivo: str,
    conteudo: Literal["empresas", "documentos", "cadastro_completo"],
    codigo_empresa: int | None = None,
) -> dict[str, Any]:
    """Importa uma planilha .xlsx no layout do DocFlow: 'empresas', 'documentos' (de uma
    empresa - informe codigo_empresa) ou 'cadastro_completo' (empresas + documentos + status)."""
    services = get_services()
    if conteudo == "empresas":
        return services.import_service.import_empresas(caminho_arquivo)
    if conteudo == "documentos":
        if codigo_empresa is None:
            raise ToolError("Informe codigo_empresa para importar documentos.")
        return services.import_service.import_documentos(caminho_arquivo, _company(services, codigo_empresa)["id"])
    return services.import_service.import_cadastros_completos(caminho_arquivo)


@docflow_tool(read_only=False)
def criar_backup(caminho_arquivo: str, senha: str | None = None) -> dict[str, Any]:
    """Gera um backup completo do banco (.dfbak), opcionalmente criptografado com senha."""
    return get_services().database_maintenance_service.create_backup(caminho_arquivo, password=senha)


@docflow_tool(read_only=False, destructive=True)
def restaurar_backup(caminho_arquivo: str, senha: str | None = None, confirmar: bool = False) -> dict[str, Any]:
    """Substitui TODOS os dados atuais pelos do backup (.dfbak, ou .db do DocFlow antigo).
    Exige confirmar=true."""
    _require_confirmation(confirmar, "Restaurar o backup apaga todos os dados atuais e")
    return get_services().database_maintenance_service.restore_backup(caminho_arquivo, password=senha)


@docflow_tool(read_only=False, destructive=True)
def limpar_logs_antigos(dias_de_retencao: int, confirmar: bool = False) -> str:
    """Apaga os logs de auditoria mais antigos que o numero de dias informado. Somente
    administradores. Exige confirmar=true."""
    services = get_services()
    _require_confirmation(confirmar, f"Apagar os logs com mais de {dias_de_retencao} dias")
    removidos = services.log_service.purge_logs_older_than(dias_de_retencao)
    return f"{removidos} log(s) removido(s)."


# Envios automaticos (email e WhatsApp) ---------------------------------------------------


def _public_envio(envio: dict) -> dict[str, Any]:
    return {
        "envio_id": envio["id"],
        "nome": envio["nome"],
        "ativo": envio["ativo"],
        "tipo_documento": envio.get("nome_tipo"),
        "publico": envio["publico_label"],
        "empresa_ids": envio["empresa_ids_lista"],
        "empresa_ids_tiradas": envio["empresa_ids_excluidas_lista"],
        "modo": envio["modo"],
        "email_para": envio.get("email_para"),
        "competencias": envio["meses_lista"],
        "enviar_em": envio["enviar_em"],
        "dia_envio": envio["dia_envio"],
        "canal": envio["canal"],
        "somente_pendentes": envio["somente_pendentes"],
        "assunto": envio["assunto"],
        "corpo": envio["corpo"],
        "corpo_whatsapp": envio.get("corpo_whatsapp"),
        "instrucoes": envio.get("instrucoes"),
        "proximo_envio": envio.get("proximo_envio"),
        "proxima_competencia": envio.get("proxima_competencia"),
    }


def _envio_dados(
    services: ApplicationServices,
    nome: str | None,
    tipo_documento: str | None,
    codigos_empresas: list[int] | None,
    competencias: list[int] | str | None,
    enviar_em: str | None,
    dia_envio: int | None,
    canal: str | None,
    assunto: str | None,
    corpo: str | None,
    somente_pendentes: bool | None,
    instrucoes: str | None,
    ativo: bool | None,
    modo: str | None = None,
    email_para: str | None = None,
    corpo_whatsapp: str | None = None,
) -> dict[str, Any]:
    dados: dict[str, Any] = {
        "corpo_whatsapp": corpo_whatsapp,
        "modo": modo,
        "email_para": email_para,
        "nome": nome,
        "meses": competencias,
        "enviar_em": enviar_em,
        "dia_envio": dia_envio,
        "canal": canal,
        "assunto": assunto,
        "corpo": corpo,
        "somente_pendentes": somente_pendentes,
        "instrucoes": instrucoes,
        "ativo": ativo,
    }
    if tipo_documento is not None:
        # "" (ou "todas") tira o tipo: a regra vira mala direta.
        texto = tipo_documento.strip()
        dados["tipo_documento_id"] = None if texto.casefold() in ("", "todas") else _tipo_by_name(services, texto)["id"]
    if codigos_empresas is not None:
        # [] volta a mala direta para todas as empresas ativas.
        dados["empresa_ids"] = [_company(services, codigo)["id"] for codigo in codigos_empresas]
    return dados


@docflow_tool(read_only=True)
def listar_envios_programados() -> list[dict[str, Any]]:
    """Envios automaticos configurados no DocFlow (cobrancas como o Informe de Rendimentos
    trimestral e malas diretas): publico, competencias cobradas, quando sai (enviar_em +
    dia_envio), canal, texto e a data/competencia do proximo envio."""
    return [_public_envio(envio) for envio in get_services().envio_programado_service.listar()]


@docflow_tool(read_only=True)
def envios_a_fazer(data: str | None = None, envio_id: int | None = None) -> dict[str, Any]:
    """Mensagens que ja deveriam ter saido (por padrao, hoje): um item por empresa, com canal
    (email ou whatsapp), destinatarios/whatsapp, assunto e corpo prontos e a competencia
    cobrada. 'corpo' e o texto puro; 'corpo_formatado' tem as marcas <b>, <i> e <u> (negrito,
    italico, sublinhado); 'corpo_html' e o email pronto em HTML, ja com a assinatura do
    escritorio, e 'corpo_com_assinatura' o mesmo em texto puro. Se houver imagem na
    assinatura ('assinatura.imagem'), anexe o arquivo como imagem embutida com o Content-ID
    indicado (veja 'assinatura_email'). Imagens do meio do texto vem em 'imagens' (arquivo e
    Content-ID): anexe cada uma como imagem embutida com o seu Content-ID. Envie cada um (email pela sua ferramenta de email, WhatsApp com 'enviar_whatsapp')
    e registre com 'registrar_envio' - o item some da lista depois de registrado como enviado.
    Itens com sem_contato=true nao tem para onde ir: registre como falhou com o motivo.
    data: AAAA-MM-DD (opcional, para simular outro dia)."""
    services = get_services()
    hoje = _parse_date(data)
    itens = services.envio_programado_service.a_enviar(hoje, envio_id)
    assinatura = load_email_signature()
    return {
        "data": hoje.isoformat(),
        "total": len(itens),
        "assinatura": _assinatura_para_claude(),
        "itens": [_com_assinatura(services, item, assinatura) for item in itens],
    }


def _assinatura_para_claude(incluir_base64: bool = False) -> dict[str, Any] | None:
    """A assinatura cadastrada no DocFlow (Envios automaticos > Assinatura do email)."""
    assinatura = load_email_signature()
    texto = texto_com_assinatura("", assinatura["texto"]).strip()
    if not texto and not assinatura["imagem"]:
        return None
    dados: dict[str, Any] = {
        "texto": texto,
        "html": signature_html(assinatura),
        "imagem": None,
    }
    if assinatura["imagem"]:
        arquivo = Path(assinatura["imagem"])
        imagem: dict[str, Any] = {
            "caminho": str(arquivo),
            "tipo": "image/" + {".jpg": "jpeg", ".jpeg": "jpeg"}.get(arquivo.suffix.lower(), arquivo.suffix.lower().lstrip(".")),
            "content_id": SIGNATURE_CID,
            "largura": assinatura["largura"],
        }
        if incluir_base64:
            imagem["base64"] = base64.b64encode(arquivo.read_bytes()).decode("ascii")
        dados["imagem"] = imagem
    return dados


def _com_assinatura(services: ApplicationServices, item: dict[str, Any], assinatura: dict[str, Any]) -> dict[str, Any]:
    """Item de email com o corpo pronto em HTML (formatado + assinatura) e em texto, e as
    imagens do meio do texto (arquivo + Content-ID). assinatura: load_email_signature()."""
    if item.get("canal") != "email":
        return item
    marcado = item.get("corpo_formatado") or item.get("corpo") or ""
    src = f"cid:{SIGNATURE_CID}" if assinatura["imagem"] else None
    servico = services.envio_programado_service
    imagens = []
    for imagem_id in imagens_usadas(marcado):
        arquivo = servico.arquivo_imagem(imagem_id)
        if arquivo:
            tipo = servico.imagem(imagem_id)["tipo"]
            imagens.append({"content_id": cid_imagem(imagem_id), "caminho": str(arquivo), "tipo": f"image/{tipo}"})
    return {
        **item,
        "corpo_html": para_html(marcado, assinatura["texto"], src, assinatura["largura"]),
        "corpo_com_assinatura": texto_com_assinatura(marcado, assinatura["texto"]),
        "imagens": imagens,
    }


@docflow_tool(read_only=True)
def assinatura_email(incluir_base64: bool = False) -> dict[str, Any]:
    """Assinatura que vai no fim de todo email do escritorio (cadastrada em Envios automaticos
    > Assinatura do email): texto, html e imagem. A imagem fica no arquivo 'imagem.caminho';
    no html ela aparece como <img src="cid:assinatura_docflow"> - anexe o arquivo como imagem
    embutida (inline) com esse Content-ID. Se a sua ferramenta de email nao aceitar imagem
    embutida, use incluir_base64=true para receber o conteudo ou anexe o arquivo. Sem
    assinatura cadastrada devolve cadastrada=false."""
    dados = _assinatura_para_claude(incluir_base64)
    return {"cadastrada": dados is not None, **(dados or {})}


@docflow_tool(read_only=True)
def documentos_baixados_onvio(competencia: str, codigo_empresa: str | None = None) -> dict[str, Any]:
    """O que o robo do Onvio baixou numa competencia (MM/AAAA): pasta no computador e, por
    empresa, a situacao (baixada, sem pasta, sem cliente no Onvio, erro...) e os arquivos
    baixados com o caminho completo, separados pela subpasta do Onvio (Extrato Bancario,
    Nota Fiscal...). Use para classificar e salvar cada arquivo na pasta da empresa
    (pasta_documentos em 'obter_empresa') e registrar com 'registrar_verificacao'.
    Trabalhe so com o que esta na pasta: MOVA (nao copie) cada arquivo tratado para a pasta da
    empresa, entao o que sobra no download e o que ainda falta tratar. O robo lembra o que ja
    baixou (pelo id no Onvio), nao baixa de novo o que foi movido ou renomeado e, nas proximas
    passadas, traz so os arquivos que chegaram depois: 'novos' (por empresa) lista os da ultima
    passada. Depois de dar baixa em tudo como Recebido, a empresa sai das proximas passadas.
    O robo roda no DocFlow em Panorama > Ferramentas > Baixar documentos do Onvio."""
    from documentos_empresa_app.onvio.robo import RESUMO
    from documentos_empresa_app.utils.helpers import load_ui_state

    parsed = parse_period_label(competencia)
    if parsed is None:
        raise ToolError(f'Competencia invalida: "{competencia}". Use MM/AAAA.')
    ano, mes = parsed
    from documentos_empresa_app.onvio.robo import pasta_padrao

    base = Path(load_ui_state("onvio:destino", "") or pasta_padrao())
    pasta = base / f"{mes:02d}-{ano}"
    caminho = pasta / RESUMO
    if not caminho.exists():
        return {
            "baixado": False,
            "pasta": str(pasta),
            "mensagem": "O robo ainda nao baixou essa competencia. Rode no DocFlow: Panorama > Ferramentas > Baixar documentos do Onvio.",
        }
    resumo = json.loads(caminho.read_text(encoding="utf-8"))
    empresas = resumo.get("empresas") or []
    if codigo_empresa is not None:
        empresas = [e for e in empresas if str(e.get("codigo")) == str(codigo_empresa).strip()]
    for empresa in empresas:
        alvo = Path(empresa.get("pasta") or "")
        arquivos = []
        if empresa.get("pasta") and alvo.is_dir():
            for arquivo in sorted(p for p in alvo.rglob("*") if p.is_file()):
                relativo = arquivo.relative_to(alvo)
                arquivos.append({
                    "subpasta": str(relativo.parent) if relativo.parent != Path(".") else "",
                    "nome": arquivo.name,
                    "caminho": str(arquivo),
                    "tamanho_kb": round(arquivo.stat().st_size / 1024, 1),
                })
        empresa["lista_arquivos"] = arquivos
    return {"baixado": True, **resumo, "empresas": empresas}


@docflow_tool(read_only=True)
def previa_envio(envio_id: int, competencia: str) -> list[dict[str, Any]]:
    """Quem receberia e com que texto o envio da competencia informada (MM/AAAA - a
    competencia cobrada, nao o mes em que sai). Mostra tambem quem ja recebeu
    (ja_enviado=true). Nao registra nada."""
    parsed = parse_period_label(competencia)
    if parsed is None:
        raise ToolError(f'Competencia invalida: "{competencia}". Use MM/AAAA.')
    ano, mes = parsed
    return get_services().envio_programado_service.previa(envio_id, ano, mes)


@docflow_tool(read_only=True)
def conferir_envio(envio_id: int, competencia: str | None = None) -> dict[str, Any]:
    """A regra aplicada numa competencia (MM/AAAA; padrao: a que este mes cobra), empresa por
    empresa: quem vai receber (canal e contato), quem ja recebeu, quem ja entregou o
    documento, quem esta sem contato e quem esta fora da lista. Use para conferir antes de
    enviar. Nao registra nada."""
    services = get_services()
    servico = services.envio_programado_service
    if competencia:
        parsed = parse_period_label(competencia)
        if parsed is None:
            raise ToolError(f'Competencia invalida: "{competencia}". Use MM/AAAA.')
    else:
        hoje = date.today()
        parsed = servico.competencia_do_envio(servico.obter(envio_id), hoje.year, hoje.month)
    dados = servico.conferencia(envio_id, *parsed)
    for linha in dados["linhas"]:
        linha.pop("item", None)
        linha.pop("item_empresa", None)
    return dados


@docflow_tool(read_only=False)
def registrar_envio(
    envio_id: int,
    competencia: str,
    status: Literal["enviado", "falhou"],
    codigo_empresa: int | None = None,
    canal: Literal["email", "whatsapp"] = "email",
    destinatarios: list[str] | None = None,
    detalhe: str | None = None,
) -> dict[str, Any]:
    """Registra o resultado de um item de 'envios_a_fazer' (competencia e canal como vieram
    no item). Na mala direta em copia oculta (modo 'cco') deixe codigo_empresa vazio: registra
    todas as empresas que estavam no Cco. 'falhou' exige o motivo em detalhe e o item continua
    na lista para nova tentativa. Um mesmo envio com sucesso nao e registrado duas vezes."""
    services = get_services()
    parsed = parse_period_label(competencia)
    if parsed is None:
        raise ToolError(f'Competencia invalida: "{competencia}". Use MM/AAAA.')
    if codigo_empresa is None:
        return services.envio_programado_service.registrar_mala_direta(
            envio_id, parsed, status, detalhe, rodada_id=_rodada_atual
        )
    empresa = _company(services, codigo_empresa)
    return services.envio_programado_service.registrar(
        envio_id, empresa["id"], parsed, status, destinatarios, detalhe, rodada_id=_rodada_atual, canal=canal
    )


@docflow_tool(read_only=False)
def enviar_whatsapp(whatsapp: str, mensagem: str, template: str | None = None, parametros: list[str] | None = None) -> dict[str, Any]:
    """Envia uma mensagem de WhatsApp. Com a WhatsApp Cloud API configurada no DocFlow, envia
    direto (fora da janela de 24h a Meta so aceita 'template' aprovado, com 'parametros' na
    ordem do modelo). Sem a API devolve enviado=false e o 'link' wa.me com a mensagem pronta:
    mostre o link ao usuario para ele clicar e enviar. Nao registra nada - use
    'registrar_envio' depois de enviado."""
    return get_services().whatsapp_service.enviar(whatsapp, mensagem, template, parametros)


@docflow_tool(read_only=True)
def historico_envios(envio_id: int | None = None, codigo_empresa: int | None = None, limite: int = 100) -> list[dict[str, Any]]:
    """Mensagens registradas (enviadas e falhas, email e WhatsApp), da mais recente para a
    mais antiga."""
    services = get_services()
    empresa_id = _company(services, codigo_empresa)["id"] if codigo_empresa is not None else None
    registros = services.envio_programado_service.historico(envio_id, empresa_id, limite)
    for registro in registros:
        registro["registrado_em"] = _local(registro["registrado_em"])
    return registros


@docflow_tool(read_only=False)
def cadastrar_envio_programado(
    nome: str,
    competencias: list[int] | str,
    dia_envio: int,
    assunto: str,
    corpo: str,
    tipo_documento: str | None = None,
    codigos_empresas: list[int] | None = None,
    enviar_em: Literal["mes_seguinte", "mesmo_mes"] = "mes_seguinte",
    canal: Literal["automatico", "email", "whatsapp"] = "automatico",
    somente_pendentes: bool = True,
    instrucoes: str | None = None,
    ativo: bool = True,
    modo: Literal["individual", "cco"] = "individual",
    email_para: str | None = None,
    corpo_whatsapp: str | None = None,
) -> dict[str, Any]:
    """Cria um envio automatico. competencias: as competencias cobradas, lista (ex: [3, 6, 9,
    12]) ou 'mensal'/'trimestral'. enviar_em: 'mes_seguinte' (padrao da contabilidade - a
    competencia 03 e cobrada em abril, no dia_envio) ou 'mesmo_mes'.
    Publico: com tipo_documento, as empresas que tem esse tipo (com somente_pendentes, so as
    que ainda nao entregaram a competencia); sem tipo e mala direta - para codigos_empresas
    ou, sem lista, todas as ativas (respeita quem pediu para ficar fora da mala direta).
    canal: 'automatico' manda WhatsApp para quem liberou o WhatsApp para envios (numero ou
    grupo) e email para os demais. Assunto e corpo aceitam {empresa}, {codigo}, {contato},
    {competencia}, {mes}, {ano} e {documentos}; o corpo aceita <b>negrito</b>, <i>italico</i> e
    <u>sublinhado</u> (escreva < > & como &lt; &gt; &amp;). corpo_whatsapp e o texto do WhatsApp
    (vazio = o mesmo corpo, com *negrito* e _italico_). A assinatura cadastrada no DocFlow vai
    no fim dos emails enviados por ele. instrucoes: orientacoes para quem envia.
    modo='cco' (so mala direta): um email so para email_para (o email do escritorio) com as
    empresas em copia oculta - no texto use so {competencia}, {mes} e {ano}; quem e de
    WhatsApp recebe a mensagem um a um.
    Somente administradores."""
    services = get_services()
    dados = _envio_dados(
        services, nome, tipo_documento, codigos_empresas, competencias, enviar_em, dia_envio,
        canal, assunto, corpo, somente_pendentes, instrucoes, ativo, modo, email_para, corpo_whatsapp,
    )
    return _public_envio(services.envio_programado_service.criar(dados))


@docflow_tool(read_only=False, idempotent=True)
def atualizar_envio_programado(
    envio_id: int,
    nome: str | None = None,
    competencias: list[int] | str | None = None,
    dia_envio: int | None = None,
    assunto: str | None = None,
    corpo: str | None = None,
    tipo_documento: str | None = None,
    codigos_empresas: list[int] | None = None,
    enviar_em: Literal["mes_seguinte", "mesmo_mes"] | None = None,
    canal: Literal["automatico", "email", "whatsapp"] | None = None,
    somente_pendentes: bool | None = None,
    instrucoes: str | None = None,
    ativo: bool | None = None,
    modo: Literal["individual", "cco"] | None = None,
    email_para: str | None = None,
    corpo_whatsapp: str | None = None,
) -> dict[str, Any]:
    """Altera so os campos informados de um envio automatico. tipo_documento="todas"
    transforma em mala direta; codigos_empresas=[] volta a mala direta para todas as
    empresas (para incluir ou tirar algumas, prefira 'incluir_na_mala_direta' /
    'remover_da_mala_direta'); corpo_whatsapp="" volta a usar o corpo no WhatsApp.
    Somente administradores."""
    services = get_services()
    dados = _envio_dados(
        services, nome, tipo_documento, codigos_empresas, competencias, enviar_em, dia_envio,
        canal, assunto, corpo, somente_pendentes, instrucoes, ativo, modo, email_para, corpo_whatsapp,
    )
    return _public_envio(services.envio_programado_service.atualizar(envio_id, dados))


@docflow_tool(read_only=True)
def lista_mala_direta(envio_id: int) -> list[dict[str, Any]]:
    """Empresas da lista de uma mala direta, por qual canal recebem (email ou whatsapp) e se
    recebem (recebe, sem_email = sem email nem WhatsApp liberado, nao_contatar ou inativa).
    Para envios por tipo de documento use 'conferir_envio'."""
    return get_services().envio_programado_service.situacao_lista(envio_id)


@docflow_tool(read_only=False, idempotent=True)
def incluir_na_mala_direta(envio_id: int, codigos_empresas: list[int]) -> dict[str, Any]:
    """Coloca empresas num envio: na mala direta entram na lista (ex: cliente novo); num envio
    por tipo de documento, volta a empresa que tinha sido tirada dele."""
    services = get_services()
    ids = [_company(services, codigo)["id"] for codigo in codigos_empresas]
    return _public_envio(services.envio_programado_service.incluir_empresas(envio_id, ids))


@docflow_tool(read_only=False, idempotent=True)
def remover_da_mala_direta(envio_id: int, codigos_empresas: list[int]) -> dict[str, Any]:
    """Tira empresas de um envio. Na mala direta saem da lista (ex: cliente que saiu; a lista
    nao pode ficar vazia - para parar, desative o envio). Num envio por tipo de documento a
    empresa continua com o documento, mas deixa de receber este envio."""
    services = get_services()
    ids = [_company(services, codigo)["id"] for codigo in codigos_empresas]
    return _public_envio(services.envio_programado_service.remover_empresas(envio_id, ids))


@docflow_tool(read_only=False)
def enviar_emails_pelo_docflow(
    envio_id: int,
    competencia: str | None = None,
    codigos_empresas: list[int] | None = None,
    confirmar: bool = False,
) -> dict[str, Any]:
    """Envia agora, pelo email do escritorio cadastrado no DocFlow (tela Envios automaticos >
    Email de envio), os emails ainda nao enviados de um envio na competencia (MM/AAAA; padrao:
    a que este mes cobra) e registra cada empresa. codigos_empresas limita a algumas. Itens de
    WhatsApp nao sao enviados aqui. Sem confirmar=true so mostra quantos emails sairiam."""
    services = get_services()
    servico = services.envio_programado_service
    if competencia:
        parsed = parse_period_label(competencia)
        if parsed is None:
            raise ToolError(f'Competencia invalida: "{competencia}". Use MM/AAAA.')
    else:
        hoje = date.today()
        parsed = servico.competencia_do_envio(servico.obter(envio_id), hoje.year, hoje.month)
    ids = [_company(services, codigo)["id"] for codigo in codigos_empresas] if codigos_empresas else None
    if not confirmar:
        itens = [
            i for i in servico.previa(envio_id, *parsed)
            if i["canal"] == "email" and not i["ja_enviado"] and not i["sem_contato"]
            and (ids is None or i["empresa_id"] in ids or i["modo"] == "cco")
        ]
        return {
            "competencia": format_competencia(*parsed),
            "emails_a_enviar": len(itens),
            "remetente": services.email_sender_service.remetente() or None,
            "configurado": services.email_sender_service.configurado(),
            "aviso": "Nada foi enviado. Chame de novo com confirmar=true para enviar.",
        }
    resultado = servico.enviar_emails(envio_id, *parsed, services.email_sender_service, empresa_ids=ids)
    return {"competencia": format_competencia(*parsed), **resultado}


@docflow_tool(read_only=True)
def listar_modelos_mensagem() -> list[dict[str, Any]]:
    """Textos prontos guardados no DocFlow (assunto, texto do email e do WhatsApp), para
    reaproveitar em envios."""
    return get_services().envio_programado_service.listar_modelos()


@docflow_tool(read_only=False, idempotent=True)
def salvar_modelo_mensagem(nome: str, corpo: str, assunto: str | None = None, corpo_whatsapp: str | None = None) -> dict[str, Any]:
    """Guarda um texto pronto (mesmo nome substitui). Aceita os mesmos campos dos envios:
    {empresa}, {codigo}, {contato}, {competencia}, {mes}, {ano}, {documentos}."""
    return get_services().envio_programado_service.salvar_modelo(nome, assunto, corpo, corpo_whatsapp)


@docflow_tool(read_only=False, destructive=True)
def excluir_modelo_mensagem(modelo_id: int, confirmar: bool = False) -> str:
    """Exclui um texto pronto. Exige confirmar=true."""
    _require_confirmation(confirmar, "Excluir o modelo de mensagem")
    get_services().envio_programado_service.excluir_modelo(modelo_id)
    return "Modelo excluido."


@docflow_tool(read_only=False, destructive=True)
def excluir_envio_programado(envio_id: int, confirmar: bool = False) -> str:
    """Exclui um envio automatico e o historico dele. Exige confirmar=true."""
    services = get_services()
    envio = services.envio_programado_service.obter(envio_id)
    _require_confirmation(confirmar, f'Excluir o envio "{envio["nome"]}" e o historico dele')
    services.envio_programado_service.excluir(envio_id)
    return f'Envio "{envio["nome"]}" excluido.'


def _parse_date(raw: str | None) -> date:
    if not raw:
        return date.today()
    try:
        return date.fromisoformat(raw.strip())
    except ValueError as exc:
        raise ToolError(f'Data invalida: "{raw}". Use AAAA-MM-DD.') from exc


# Acesso livre ao banco -------------------------------------------------------------------

SQL_ROW_LIMIT = 1000


def _require_admin(services: ApplicationServices) -> None:
    if not services.session_service.is_admin():
        raise ToolError("Apenas usuarios admin podem usar SQL direto no banco.")


def _json_value(value: Any) -> Any:
    return value if value is None or isinstance(value, (bool, int, float, str)) else str(value)


@docflow_tool(read_only=True)
def consultar_banco(sql: str, limite: int = 200) -> dict[str, Any]:
    """Roda uma consulta SQL (PostgreSQL) somente leitura no banco do DocFlow, para qualquer
    pergunta que as outras tools nao respondam. A transacao e READ ONLY: comandos de escrita
    falham aqui (use 'executar_sql'). Tabelas principais: empresas, documentos_empresa,
    tipos_documento, periodos, status_documento_mensal, cobrancas, cobranca_itens,
    verificacoes, verificacao_itens, situacoes_cobranca, situacao_eventos, rodadas,
    envios_programados, envios_registrados, usuarios, logs. Devolve ate 'limite' linhas
    (maximo 1000). Somente administradores."""
    services = get_services()
    _require_admin(services)
    limite = max(1, min(int(limite), SQL_ROW_LIMIT))
    db_manager = services.database_maintenance_service.db_manager
    with db_manager.connect() as connection:
        connection.raw.execute("SET TRANSACTION READ ONLY")
        cursor = connection.raw.execute(sql)
        if cursor.description is None:
            return {"colunas": [], "linhas": [], "total_retornado": 0, "truncado": False}
        colunas = [coluna.name for coluna in cursor.description]
        linhas = cursor.fetchmany(limite + 1)
    truncado = len(linhas) > limite
    return {
        "colunas": colunas,
        "linhas": [{k: _json_value(v) for k, v in linha.items()} for linha in linhas[:limite]],
        "total_retornado": min(len(linhas), limite),
        "truncado": truncado,
    }


@docflow_tool(read_only=False, destructive=True)
def executar_sql(sql: str, confirmar: bool = False) -> dict[str, Any]:
    """Executa SQL de escrita (INSERT, UPDATE, DELETE, ALTER...) direto no banco do DocFlow,
    numa transacao: se der erro, nada e aplicado. Use quando nenhuma tool especifica fizer o
    que foi pedido - aqui as regras e validacoes do sistema NAO sao aplicadas. Fica
    registrado no Historico de acoes. Exige confirmar=true. Somente administradores."""
    services = get_services()
    _require_admin(services)
    _require_confirmation(confirmar, "SQL direto no banco")
    db_manager = services.database_maintenance_service.db_manager
    with db_manager.connect() as connection:
        db_manager.mark_written()
        cursor = connection.raw.execute(sql)
        linhas_afetadas = cursor.rowcount
        retorno = None
        if cursor.description is not None:
            retorno = [{k: _json_value(v) for k, v in linha.items()} for linha in cursor.fetchmany(SQL_ROW_LIMIT)]
        services.audit_service.log("SQL_DIRETO", "banco", None, f"SQL executado pelo MCP: {sql.strip()[:900]}")
    return {"linhas_afetadas": linhas_afetadas, "retorno": retorno}


def main() -> None:
    mcp.run("stdio")

