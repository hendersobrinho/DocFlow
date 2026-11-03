from __future__ import annotations

import base64
import calendar
import re
from datetime import date
from pathlib import Path

from documentos_empresa_app.database.repositories import (
    EmpresaRepository,
    EnvioProgramadoRepository,
    ImagemEmailRepository,
    ModeloMensagemRepository,
    TipoRepository,
)
from documentos_empresa_app.services.audit_service import AuditService
from documentos_empresa_app.services.session_service import SessionService
from documentos_empresa_app.services.whatsapp_service import build_link, format_whatsapp
from documentos_empresa_app.utils.common import (
    CONFIG_DIR,
    MONTH_NAMES,
    ValidationError,
    format_competencia,
)
from documentos_empresa_app.utils.email_format import imagens_usadas, para_texto, para_whatsapp, preencher

# Na contabilidade se trabalha por competencia: o extrato/informe de marco so fica pronto no
# fim de marco, entao a cobranca da competencia 03 sai em abril. Por isso o padrao e o mes
# seguinte; "mesmo_mes" serve para avisos que saem dentro da propria competencia.
ENVIAR_MES_SEGUINTE = "mes_seguinte"
ENVIAR_MESMO_MES = "mesmo_mes"
ENVIAR_EM_LABELS = {
    ENVIAR_MES_SEGUINTE: "No mês seguinte à competência",
    ENVIAR_MESMO_MES: "No próprio mês da competência",
}
CANAL_EMAIL = "email"
CANAL_WHATSAPP = "whatsapp"
CANAL_AUTOMATICO = "automatico"
CANAL_LABELS = {
    CANAL_AUTOMATICO: "Automático (WhatsApp de quem autorizou, email dos demais)",
    CANAL_EMAIL: "Só email",
    CANAL_WHATSAPP: "Só WhatsApp",
}
# Mala direta: um email por empresa, ou um email so para o proprio escritorio (email_para)
# com todas as empresas da lista em copia oculta - como o escritorio ja faz.
MODO_INDIVIDUAL = "individual"
MODO_CCO = "cco"
MODO_LABELS = {
    MODO_INDIVIDUAL: "Uma mensagem por empresa",
    MODO_CCO: "Um email só, com as empresas em cópia oculta (WhatsApp segue um a um)",
}
# Situacao de cada empresa na lista da mala direta.
SITUACAO_RECEBE = "recebe"
SITUACAO_SEM_EMAIL = "sem_email"
SITUACAO_NAO_CONTATAR = "nao_contatar"
SITUACAO_INATIVA = "inativa"
SITUACAO_LISTA_LABELS = {
    SITUACAO_RECEBE: "Recebe",
    SITUACAO_SEM_EMAIL: "Sem email nem WhatsApp liberado",
    SITUACAO_NAO_CONTATAR: "Pediu para não receber",
    SITUACAO_INATIVA: "Empresa inativa",
}
# Conferencia: o que a regra faz com cada empresa candidata numa competencia.
CONF_VAI_RECEBER = "vai_receber"
CONF_JA_RECEBEU = "ja_recebeu"
CONF_JA_ENTREGOU = "ja_entregou"
CONF_SEM_CONTATO = "sem_contato"
CONF_FORA = "fora"
CONFERENCIA_LABELS = {
    CONF_VAI_RECEBER: "Vai receber",
    CONF_JA_RECEBEU: "Já recebeu nesta competência",
    CONF_JA_ENTREGOU: "Já entregou - não será cobrada",
    CONF_SEM_CONTATO: "Sem contato cadastrado",
    CONF_FORA: "Fora deste envio",
}
MOTIVO_TIRADA = "Tirada deste envio"
STATUS_ENVIO = ("enviado", "falhou")
MESES_TRIMESTRAIS = (3, 6, 9, 12)
# Campos que podem aparecer no assunto e no corpo, entre chaves: {empresa}, {documentos}...
CAMPOS_MODELO = {
    "empresa": "nome da empresa",
    "codigo": "codigo da empresa",
    "contato": "nome do contato (ou 'cliente', se nao houver)",
    "competencia": "competencia cobrada, MM/AAAA",
    "mes": "nome do mes da competencia",
    "ano": "ano da competencia",
    "documentos": "lista dos documentos que faltam, um por linha",
}
IMAGEM_TIPOS = ("png", "jpeg", "gif")
IMAGEM_MAX_BYTES = 3_000_000
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


class _CamposDoModelo(dict):
    """Campo desconhecido fica como esta ({assim}), em vez de quebrar o texto."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def parse_meses(raw) -> list[int]:
    """'3,6,9,12', [3, 6, 9, 12] ou 'trimestral'/'mensal' -> lista ordenada de meses."""
    if isinstance(raw, str):
        texto = raw.strip().lower()
        if texto == "mensal":
            return list(range(1, 13))
        if texto == "trimestral":
            return list(MESES_TRIMESTRAIS)
        partes = [p for p in re.split(r"[\s,;/]+", texto) if p]
    else:
        partes = list(raw or [])
    try:
        meses = sorted({int(p) for p in partes})
    except (TypeError, ValueError) as exc:
        raise ValidationError("Meses invalidos. Use numeros de 1 a 12, por exemplo 3,6,9,12.") from exc
    if not meses or any(m < 1 or m > 12 for m in meses):
        raise ValidationError("Escolha pelo menos um mes, de 1 a 12.")
    return meses


def format_meses(meses: list[int]) -> str:
    if meses == list(range(1, 13)):
        return "Todo mês"
    return ", ".join(MONTH_NAMES[m][:3] for m in meses)


def parse_empresa_ids(raw) -> list[int]:
    """'1, 5,7' ou [1, 5, 7] -> [1, 5, 7] (sem repetir)."""
    partes = [p for p in re.split(r"[\s,;]+", raw.strip()) if p] if isinstance(raw, str) else list(raw or [])
    try:
        return sorted({int(p) for p in partes})
    except (TypeError, ValueError) as exc:
        raise ValidationError("Lista de empresas invalida: use os ids separados por virgula.") from exc


def _mes_somado(ano: int, mes: int, delta: int) -> tuple[int, int]:
    total = ano * 12 + mes - 1 + delta
    return total // 12, total % 12 + 1


def split_emails(raw: str | None) -> list[str]:
    vistos: set[str] = set()
    emails: list[str] = []
    for email in EMAIL_RE.findall(str(raw or "")):
        if email.casefold() not in vistos:
            vistos.add(email.casefold())
            emails.append(email)
    return emails


def whatsapp_liberado(empresa: dict) -> tuple[str | None, str | None]:
    """(numero, link do grupo) que podem ser usados nos envios - so de quem marcou no cadastro
    que o WhatsApp pode ser usado. Sem a marcacao, nada sai por WhatsApp."""
    if not empresa.get("whatsapp_envios"):
        return None, None
    return empresa.get("whatsapp") or None, empresa.get("whatsapp_grupo") or None


def data_de_envio(ano: int, mes: int, dia: int) -> date:
    """Dia 31 em mes de 30 dias (ou 29+ em fevereiro) vira o ultimo dia do mes."""
    return date(ano, mes, min(dia, calendar.monthrange(ano, mes)[1]))


class EnvioProgramadoService:
    """Envios automaticos (cobranca e mala direta, por email ou WhatsApp): o DocFlow e o centro
    de informacao (regras, textos, destinatarios e o registro do que ja foi enviado). O Claude,
    pelo MCP, consulta o que esta para enviar, envia e registra o resultado aqui; no WhatsApp a
    pessoa abre a conversa pronta pelo link (ou, com a API configurada, o envio e direto)."""

    def __init__(
        self,
        envio_repository: EnvioProgramadoRepository,
        empresa_repository: EmpresaRepository,
        tipo_repository: TipoRepository,
        audit_service: AuditService | None = None,
        session_service: SessionService | None = None,
        modelo_repository: ModeloMensagemRepository | None = None,
        imagem_repository: ImagemEmailRepository | None = None,
    ) -> None:
        self.envio_repository = envio_repository
        self.empresa_repository = empresa_repository
        self.tipo_repository = tipo_repository
        self.modelo_repository = modelo_repository
        self.imagem_repository = imagem_repository
        self._cache_imagens: dict[int, dict] = {}
        self.audit_service = audit_service
        self.session_service = session_service

    # Regras ----------------------------------------------------------------------------

    def listar(self, hoje: date | None = None) -> list[dict]:
        hoje = hoje or date.today()
        return [self._decorate(envio, hoje) for envio in self.envio_repository.list_all()]

    def obter(self, envio_id: int) -> dict:
        envio = self.envio_repository.get(int(envio_id))
        if not envio:
            raise ValidationError("Envio programado nao encontrado.")
        return self._decorate(envio, date.today())

    def criar(self, dados: dict) -> dict:
        self._ensure_admin()
        normalizado = self._normalize(dados)
        envio_id = self.envio_repository.create(normalizado)
        self._log("CADASTRO_ENVIO_PROGRAMADO", envio_id, f'Envio programado "{normalizado["nome"]}" cadastrado.')
        return self.obter(envio_id)

    def atualizar(self, envio_id: int, dados: dict) -> dict:
        self._ensure_admin()
        atual = self.obter(envio_id)
        base = {campo: atual[campo] for campo in EnvioProgramadoRepository._CAMPOS}
        base.update({k: v for k, v in dados.items() if v is not None})
        normalizado = self._normalize(base)
        self.envio_repository.update(atual["id"], normalizado)
        self._log("EDICAO_ENVIO_PROGRAMADO", atual["id"], f'Envio programado "{normalizado["nome"]}" editado.')
        return self.obter(atual["id"])

    def definir_ativo(self, envio_id: int, ativo: bool) -> dict:
        return self.atualizar(envio_id, {"ativo": 1 if ativo else 0})

    def excluir(self, envio_id: int) -> None:
        self._ensure_admin()
        envio = self.obter(envio_id)
        self.envio_repository.delete(envio["id"])
        self._log("EXCLUSAO_ENVIO_PROGRAMADO", envio["id"], f'Envio programado "{envio["nome"]}" excluido.')

    # O que enviar ----------------------------------------------------------------------

    def competencia_do_envio(self, envio: dict, ano: int, mes: int) -> tuple[int, int]:
        """Competencia cobrada por um envio feito em mes/ano."""
        if envio["enviar_em"] == ENVIAR_MES_SEGUINTE:
            return _mes_somado(ano, mes, -1)
        return ano, mes

    def mes_do_envio(self, envio: dict, ano: int, mes: int) -> tuple[int, int]:
        """Em que mes sai o envio da competencia mes/ano."""
        if envio["enviar_em"] == ENVIAR_MES_SEGUINTE:
            return _mes_somado(ano, mes, 1)
        return ano, mes

    def proximo_envio(self, envio: dict, hoje: date | None = None) -> tuple[date, tuple[int, int]] | None:
        """(data do proximo envio, competencia que ele cobra)."""
        hoje = hoje or date.today()
        competencias = parse_meses(envio["meses"])
        for deslocamento in range(-1, 13):
            ano, mes = _mes_somado(hoje.year, hoje.month, deslocamento)
            if mes not in competencias:
                continue
            quando = data_de_envio(*self.mes_do_envio(envio, ano, mes), int(envio["dia_envio"]))
            if quando >= hoje:
                return quando, (ano, mes)
        return None

    def a_enviar(self, hoje: date | None = None, envio_id: int | None = None, incluir_enviados: bool = False) -> list[dict]:
        """Mensagens que ja deveriam ter saido neste mes: regra ativa, a competencia que este mes
        cobra esta entre as da regra e o dia de envio ja chegou (quem perdeu o dia continua na
        lista ate o fim do mes). Cada item e uma empresa, com canal, destinatarios e texto prontos."""
        hoje = hoje or date.today()
        itens: list[dict] = []
        envios = [self.obter(envio_id)] if envio_id is not None else self.listar(hoje)
        for envio in envios:
            ano, mes = self.competencia_do_envio(envio, hoje.year, hoje.month)
            if not envio["ativo"] or mes not in parse_meses(envio["meses"]):
                continue
            if hoje < data_de_envio(hoje.year, hoje.month, int(envio["dia_envio"])):
                continue
            itens.extend(self._itens_da_regra(envio, ano, mes, incluir_enviados))
        return itens

    def previa(self, envio_id: int, ano: int, mes: int) -> list[dict]:
        """Quem receberia e com que texto o envio da competencia mes/ano."""
        return self._itens_da_regra(self.obter(envio_id), ano, mes, incluir_enviados=True)

    def _itens_da_regra(self, envio: dict, ano: int, mes: int, incluir_enviados: bool) -> list[dict]:
        """Uma mensagem por empresa; na copia oculta, quem recebe por email vai junto num
        email so (primeiro item) e quem recebe por WhatsApp continua um a um."""
        itens = self._itens_por_empresa(envio, ano, mes, incluir_enviados)
        if envio["modo"] != MODO_CCO:
            return itens
        por_email = [item for item in itens if item["canal"] == CANAL_EMAIL]
        outros = [item for item in itens if item["canal"] != CANAL_EMAIL]
        cco = self._item_cco(envio, ano, mes, por_email)
        return ([cco] if cco else []) + outros

    def _itens_por_empresa(self, envio: dict, ano: int, mes: int, incluir_enviados: bool) -> list[dict]:
        cco = envio["modo"] == MODO_CCO
        linhas = self.envio_repository.list_destinatarios(
            None if cco else envio["tipo_documento_id"],
            parse_empresa_ids(envio.get("empresa_ids")),
            ano,
            mes,
            False if cco else bool(envio["somente_pendentes"]),
        )
        excluidas = set(parse_empresa_ids(envio.get("empresa_ids_excluidas")))
        enviados = self.envio_repository.list_enviados(envio["id"], ano, mes)
        por_empresa: dict[int, dict] = {}
        for linha in linhas:
            if linha["empresa_id"] in excluidas:
                continue
            empresa = por_empresa.setdefault(linha["empresa_id"], {**linha, "documentos": []})
            if linha["nome_documento"]:
                empresa["documentos"].append(linha["nome_documento"])
        itens: list[dict] = []
        for empresa in por_empresa.values():
            ja_enviado = empresa["empresa_id"] in enviados
            if ja_enviado and not incluir_enviados:
                continue
            itens.append(self._item_empresa(envio, empresa, ano, mes, ja_enviado))
        return itens

    def _item_empresa(self, envio: dict, empresa: dict, ano: int, mes: int, ja_enviado: bool) -> dict:
        campos = _CamposDoModelo(
            empresa=empresa["nome_empresa"],
            codigo=empresa["codigo_empresa"],
            contato=str(empresa.get("nome_contato") or "").strip() or "cliente",
            competencia=format_competencia(ano, mes),
            mes=MONTH_NAMES[mes],
            ano=ano,
            documentos="\n".join(f"- {nome}" for nome in empresa["documentos"]),
        )
        emails = split_emails(empresa.get("email_contato"))
        numero, grupo = whatsapp_liberado(empresa)
        canal = self._canal_da_empresa(envio["canal"], bool(numero or grupo))
        corpo_formatado = preencher(envio["corpo"], campos)
        if envio.get("corpo_whatsapp"):
            mensagem_whatsapp = envio["corpo_whatsapp"].format_map(campos)
        else:
            # Sem texto proprio: o do email, com o negrito/italico no jeito do WhatsApp.
            mensagem_whatsapp = para_whatsapp(corpo_formatado)
        if grupo:
            # Grupo nao aceita texto pronto no link: a tela copia a mensagem e abre o grupo.
            link = grupo
        elif numero:
            link = build_link(numero, mensagem_whatsapp)
        else:
            link = None
        return {
            "envio_id": envio["id"],
            "envio_nome": envio["nome"],
            "competencia": format_competencia(ano, mes),
            "modo": MODO_INDIVIDUAL,
            "empresa_id": empresa["empresa_id"],
            "codigo_empresa": empresa["codigo_empresa"],
            "nome_empresa": empresa["nome_empresa"],
            "canal": canal,
            "destinatarios": emails,
            "whatsapp": numero,
            "whatsapp_formatado": format_whatsapp(numero),
            "whatsapp_grupo": grupo,
            "whatsapp_e_grupo": bool(grupo),
            "whatsapp_link": link,
            "whatsapp_destino": "Grupo do WhatsApp" if grupo else format_whatsapp(numero),
            "sem_contato": not (link if canal == CANAL_WHATSAPP else emails),
            "sem_email": not emails,
            "documentos": empresa["documentos"],
            "assunto": envio["assunto"].format_map(campos),
            "corpo": para_texto(corpo_formatado),
            "corpo_formatado": corpo_formatado,
            "mensagem_whatsapp": mensagem_whatsapp,
            "instrucoes": envio.get("instrucoes"),
            "ja_enviado": ja_enviado,
        }

    def _item_cco(self, envio: dict, ano: int, mes: int, por_email: list[dict]) -> dict | None:
        """Mala direta em copia oculta: um item so, para o email do escritorio, com as empresas
        (de email) que ainda nao receberam esta competencia. Quem entrar na lista depois do
        envio aparece num novo item so com ela."""
        empresas = [
            {
                "empresa_id": item["empresa_id"],
                "codigo_empresa": item["codigo_empresa"],
                "nome_empresa": item["nome_empresa"],
                "emails": item["destinatarios"],
                "ja_enviado": item["ja_enviado"],
            }
            for item in por_email
            if item["destinatarios"]
        ]
        if not empresas:
            return None
        sem_email = [f'{item["codigo_empresa"]} - {item["nome_empresa"]}' for item in por_email if not item["destinatarios"]]
        campos = _CamposDoModelo(competencia=format_competencia(ano, mes), mes=MONTH_NAMES[mes], ano=ano)
        cco: list[str] = []
        for empresa in empresas:
            cco.extend(e for e in empresa["emails"] if e.casefold() not in {c.casefold() for c in cco})
        para = envio.get("email_para") or None
        return {
            "envio_id": envio["id"],
            "envio_nome": envio["nome"],
            "competencia": format_competencia(ano, mes),
            "modo": MODO_CCO,
            "canal": CANAL_EMAIL,
            "para": para,
            "cco": cco,
            "empresas": empresas,
            "empresas_sem_email": sem_email,
            # Campos dos itens individuais, para quem le a lista sem olhar o modo.
            "empresa_id": None,
            "codigo_empresa": None,
            "nome_empresa": f"Cópia oculta: {len(empresas)} empresa(s)",
            "destinatarios": [para] if para else [],
            "whatsapp": None,
            "whatsapp_formatado": "",
            "whatsapp_grupo": None,
            "whatsapp_e_grupo": False,
            "whatsapp_link": None,
            "whatsapp_destino": "",
            "sem_contato": not para,
            "sem_email": not para,
            "documentos": [],
            "assunto": envio["assunto"].format_map(campos),
            "corpo": para_texto(preencher(envio["corpo"], campos)),
            "corpo_formatado": preencher(envio["corpo"], campos),
            "mensagem_whatsapp": "",
            "instrucoes": envio.get("instrucoes"),
            "ja_enviado": all(empresa["ja_enviado"] for empresa in empresas),
        }

    @staticmethod
    def _canal_da_empresa(canal_regra: str, whatsapp_liberado_: bool) -> str:
        """No automatico vai por WhatsApp quem liberou o WhatsApp para envios (numero ou grupo);
        os demais recebem email."""
        if canal_regra != CANAL_AUTOMATICO:
            return canal_regra
        return CANAL_WHATSAPP if whatsapp_liberado_ else CANAL_EMAIL

    # Registro --------------------------------------------------------------------------

    def registrar(
        self,
        envio_id: int,
        empresa_id: int,
        competencia: tuple[int, int],
        status: str,
        destinatarios: list[str] | str | None = None,
        detalhe: str | None = None,
        rodada_id: int | None = None,
        canal: str = CANAL_EMAIL,
    ) -> dict:
        status = str(status or "").strip().lower()
        if status not in STATUS_ENVIO:
            raise ValidationError(f"Status invalido. Use um de: {', '.join(STATUS_ENVIO)}.")
        canal = str(canal or CANAL_EMAIL).strip().lower()
        if canal not in (CANAL_EMAIL, CANAL_WHATSAPP):
            raise ValidationError("Canal invalido. Use email ou whatsapp.")
        envio = self.obter(envio_id)
        empresa = self.empresa_repository.get_by_id(int(empresa_id))
        if not empresa:
            raise ValidationError("Empresa nao encontrada.")
        detalhe = str(detalhe or "").strip() or None
        if status == "falhou" and not detalhe:
            raise ValidationError("Diga o motivo da falha em 'detalhe'.")
        if isinstance(destinatarios, (list, tuple)):
            destinatarios = ", ".join(str(d).strip() for d in destinatarios if str(d).strip())
        destinatarios = str(destinatarios or "").strip() or None
        ano, mes = competencia

        registro_id = self.envio_repository.registrar(
            envio["id"], empresa["id"], ano, mes, status, destinatarios, detalhe, self._user_id(), rodada_id, canal
        )
        if registro_id is None:
            return {"registrado": False, "motivo": "Ja havia um envio com sucesso desta regra para a empresa nesta competencia."}
        if self.audit_service:
            self.audit_service.log(
                f"ENVIO_{canal.upper()}_{'REGISTRADO' if status == 'enviado' else 'FALHOU'}",
                "envio_programado",
                envio["id"],
                f'"{envio["nome"]}" {format_competencia(ano, mes)} ({canal}): {status}'
                + (f" para {destinatarios}" if destinatarios else "")
                + (f" ({detalhe})" if detalhe else "")
                + ".",
                empresa_id=empresa["id"],
                empresa_nome=empresa["nome_empresa"],
                periodo_ano=ano,
                periodo_mes=mes,
            )
        return {"registrado": True, "registro_id": registro_id, "status": status}

    def competencias_para_conferir(self, envio: dict, hoje: date | None = None) -> list[tuple[int, int]]:
        """Competencias da regra em volta de hoje (6 meses para tras, 12 para frente), em ordem."""
        hoje = hoje or date.today()
        meses = parse_meses(envio["meses"])
        return [
            competencia
            for competencia in (_mes_somado(hoje.year, hoje.month, d) for d in range(-6, 13))
            if competencia[1] in meses
        ]

    def conferencia(self, envio_id: int, ano: int, mes: int) -> dict:
        """A regra aplicada numa competencia, empresa por empresa: quem vai receber (por qual
        canal, com que texto) e quem fica de fora e por que. Nao registra nada."""
        envio = self.obter(envio_id)
        quando = data_de_envio(*self.mes_do_envio(envio, ano, mes), int(envio["dia_envio"]))
        itens = self._itens_por_empresa(envio, ano, mes, incluir_enviados=True)
        cco = None
        if envio["modo"] == MODO_CCO:
            cco = self._item_cco(envio, ano, mes, [item for item in itens if item["canal"] == CANAL_EMAIL])
        linhas: list[dict] = []

        def linha(empresa: dict, situacao: str, **extra) -> dict:
            return {
                "empresa_id": empresa["empresa_id"],
                "codigo_empresa": empresa["codigo_empresa"],
                "nome_empresa": empresa["nome_empresa"],
                "situacao": situacao,
                "situacao_label": CONFERENCIA_LABELS[situacao],
                "canal": extra.get("canal"),
                "contato": extra.get("contato", ""),
                "documentos": extra.get("documentos", []),
                "motivo": extra.get("motivo", ""),
                "item": extra.get("item"),
                "item_empresa": extra.get("item_empresa"),
            }

        for item in itens:
            if item["ja_enviado"]:
                situacao = CONF_JA_RECEBEU
            elif item["sem_contato"]:
                situacao = CONF_SEM_CONTATO
            else:
                situacao = CONF_VAI_RECEBER
            whatsapp = item["canal"] == CANAL_WHATSAPP
            motivo = ""
            if situacao == CONF_SEM_CONTATO:
                motivo = "Sem WhatsApp liberado no cadastro" if whatsapp else "Sem email cadastrado"
            linhas.append(
                linha(
                    item,
                    situacao,
                    canal=item["canal"],
                    contato=item["whatsapp_destino"] if whatsapp else ", ".join(item["destinatarios"]),
                    documentos=item["documentos"],
                    motivo=motivo,
                    # Na copia oculta o email e o mesmo para todas: a previa mostra o email unico.
                    item=cco if cco and not whatsapp and item["destinatarios"] else item,
                    item_empresa=item,
                )
            )
        dentro = {item["empresa_id"] for item in itens}
        excluidas = set(parse_empresa_ids(envio.get("empresa_ids_excluidas")))
        if envio["tipo_documento_id"] is not None and envio["modo"] != MODO_CCO:
            # Quem tem o documento mas ja entregou (ou esta Encerrado / Nao cobrar), ou foi tirada.
            vistas: set[int] = set()
            for candidata in self.envio_repository.list_destinatarios(envio["tipo_documento_id"], None, ano, mes, False):
                if candidata["empresa_id"] in dentro or candidata["empresa_id"] in vistas:
                    continue
                vistas.add(candidata["empresa_id"])
                if candidata["empresa_id"] in excluidas:
                    linhas.append(linha(candidata, CONF_FORA, motivo=MOTIVO_TIRADA))
                else:
                    linhas.append(linha(candidata, CONF_JA_ENTREGOU, motivo=candidata.get("status") or ""))
        else:
            for empresa in self.situacao_lista(envio["id"]):
                if empresa["empresa_id"] not in dentro:
                    linhas.append(linha(empresa, CONF_FORA, motivo=empresa["situacao_label"]))

        ordem = list(CONFERENCIA_LABELS)
        linhas.sort(key=lambda l: (ordem.index(l["situacao"]), l["codigo_empresa"]))
        resumo = {situacao: sum(1 for l in linhas if l["situacao"] == situacao) for situacao in CONFERENCIA_LABELS}
        por_canal = {
            canal: sum(1 for l in linhas if l["situacao"] == CONF_VAI_RECEBER and l["canal"] == canal)
            for canal in (CANAL_EMAIL, CANAL_WHATSAPP)
        }
        return {
            "envio_id": envio["id"],
            "envio_nome": envio["nome"],
            "competencia": format_competencia(ano, mes),
            "data_envio": quando.isoformat(),
            "modo": envio["modo"],
            "resumo": resumo,
            "por_canal": por_canal,
            "item_cco": cco,
            "linhas": linhas,
        }

    def registrar_mala_direta(
        self,
        envio_id: int,
        competencia: tuple[int, int],
        status: str,
        detalhe: str | None = None,
        rodada_id: int | None = None,
        empresa_ids: list[int] | None = None,
    ) -> dict:
        """Registra o email em copia oculta para cada empresa que estava nele (ou so para as
        empresa_ids informadas)."""
        envio = self.obter(envio_id)
        if envio["modo"] != MODO_CCO:
            raise ValidationError("Este envio nao e uma mala direta em copia oculta.")
        ano, mes = competencia
        item = next((i for i in self._itens_da_regra(envio, ano, mes, False) if i["modo"] == MODO_CCO), None)
        if not item:
            return {"registrado": False, "motivo": "Nenhuma empresa pendente nesta competencia.", "empresas": 0}
        if status == "enviado" and not item["para"]:
            raise ValidationError("Informe o email do escritorio (campo 'Para') antes de enviar a mala direta.")
        escolhidas = {int(i) for i in empresa_ids} if empresa_ids else None
        registradas = 0
        for empresa in item["empresas"]:
            if escolhidas is not None and empresa["empresa_id"] not in escolhidas:
                continue
            resultado = self.registrar(
                envio["id"], empresa["empresa_id"], competencia, status, empresa["emails"], detalhe, rodada_id
            )
            registradas += 1 if resultado["registrado"] else 0
        return {"registrado": registradas > 0, "status": status, "empresas": registradas}

    def situacao_lista(self, envio_id: int) -> list[dict]:
        """Cada empresa da lista (envio sem tipo de documento) e se ela recebe, por qual canal -
        ou por que nao. Lista vazia significa todas as empresas ativas."""
        envio = self.obter(envio_id)
        ids = envio["empresa_ids_lista"]
        if ids:
            empresas = self.empresa_repository.list_by_ids(ids)
        else:
            empresas = self.empresa_repository.list_all(active_only=True)
        linhas = []
        for empresa in empresas:
            emails = split_emails(empresa.get("email_contato"))
            numero, grupo = whatsapp_liberado(empresa)
            canal = self._canal_da_empresa(envio["canal"], bool(numero or grupo))
            tem_contato = bool(numero or grupo) if canal == CANAL_WHATSAPP else bool(emails)
            if not empresa["ativa"]:
                situacao = SITUACAO_INATIVA
            elif empresa.get("nao_contatar_mala_direta"):
                situacao = SITUACAO_NAO_CONTATAR
            elif not tem_contato:
                situacao = SITUACAO_SEM_EMAIL
            else:
                situacao = SITUACAO_RECEBE
            linhas.append(
                {
                    "empresa_id": empresa["id"],
                    "codigo_empresa": empresa["codigo_empresa"],
                    "nome_empresa": empresa["nome_empresa"],
                    "emails": emails,
                    "canal": canal,
                    "whatsapp_destino": "Grupo do WhatsApp" if grupo else format_whatsapp(numero),
                    "situacao": situacao,
                    "situacao_label": SITUACAO_LISTA_LABELS[situacao],
                }
            )
        return linhas

    def incluir_empresas(self, envio_id: int, empresa_ids: list[int]) -> dict:
        """Poe empresas no envio. Envio de um tipo de documento: devolve as que tinham sido
        tiradas (o publico continua vindo do tipo). Mala direta: entra na lista."""
        envio = self.obter(envio_id)
        novas = {int(i) for i in empresa_ids}
        if envio["tipo_documento_id"] is not None:
            restantes = sorted(set(envio["empresa_ids_excluidas_lista"]) - novas)
            return self.atualizar(envio["id"], {"empresa_ids_excluidas": restantes})
        atuais = envio["empresa_ids_lista"] or [e["empresa_id"] for e in self.situacao_lista(envio_id)]
        return self.atualizar(envio["id"], {"empresa_ids": sorted(set(atuais) | novas)})

    def remover_empresas(self, envio_id: int, empresa_ids: list[int]) -> dict:
        """Tira empresas do envio (num envio por tipo de documento elas ficam como excecao)."""
        envio = self.obter(envio_id)
        tirar = {int(i) for i in empresa_ids}
        if envio["tipo_documento_id"] is not None:
            return self.atualizar(
                envio["id"], {"empresa_ids_excluidas": sorted(set(envio["empresa_ids_excluidas_lista"]) | tirar)}
            )
        atuais = envio["empresa_ids_lista"] or [e["empresa_id"] for e in self.situacao_lista(envio_id)]
        restantes = sorted(set(atuais) - tirar)
        if not restantes:
            # Lista vazia quer dizer "todas as ativas": nunca deixa a remocao virar o contrario.
            raise ValidationError("A lista nao pode ficar vazia. Para parar de enviar, desative o envio.")
        return self.atualizar(envio["id"], {"empresa_ids": restantes})

    # Envio pelo email do DocFlow ---------------------------------------------------------

    def enviar_emails(
        self,
        envio_id: int,
        ano: int,
        mes: int,
        sender,
        empresa_ids: list[int] | None = None,
        on_progress=None,
    ) -> dict:
        """Envia agora, pelo email configurado no DocFlow (sender: EmailSenderService), os
        emails ainda nao enviados da competencia - um por empresa, ou o da copia oculta - e
        registra cada empresa como enviada (ou a falha). empresa_ids limita a algumas."""
        envio = self.obter(envio_id)
        escolhidas = {int(i) for i in empresa_ids} if empresa_ids else None
        mensagens: list[dict] = []
        for item in self._itens_da_regra(envio, ano, mes, incluir_enviados=False):
            if item["canal"] != CANAL_EMAIL:
                continue
            if item["modo"] == MODO_CCO:
                empresas = [e for e in item["empresas"] if escolhidas is None or e["empresa_id"] in escolhidas]
                if not empresas:
                    continue
                cco: list[str] = []
                for empresa in empresas:
                    cco.extend(e for e in empresa["emails"] if e.casefold() not in {c.casefold() for c in cco})
                mensagens.append(
                    {
                        "para": [item["para"]] if item["para"] else [],
                        "cco": cco,
                        "assunto": item["assunto"],
                        "corpo": item["corpo"],
                        "corpo_formatado": item["corpo_formatado"],
                        "imagens": self.imagens_do_texto(item["corpo_formatado"]),
                        "empresas": empresas,
                        "nome": item["nome_empresa"],
                    }
                )
            elif item["destinatarios"] and (escolhidas is None or item["empresa_id"] in escolhidas):
                mensagens.append(
                    {
                        "para": item["destinatarios"],
                        "cco": [],
                        "assunto": item["assunto"],
                        "corpo": item["corpo"],
                        "corpo_formatado": item["corpo_formatado"],
                        "imagens": self.imagens_do_texto(item["corpo_formatado"]),
                        "empresas": [
                            {
                                "empresa_id": item["empresa_id"],
                                "emails": item["destinatarios"],
                            }
                        ],
                        "nome": f'{item["codigo_empresa"]} - {item["nome_empresa"]}',
                    }
                )
        if not mensagens:
            return {"mensagens": 0, "enviadas": 0, "falhas": [], "empresas": 0}
        resultados = sender.enviar_lote(mensagens, on_progress=on_progress)
        enviadas, falhas, empresas_ok = 0, [], 0
        for mensagem, resultado in zip(mensagens, resultados):
            ok = resultado.get("ok")
            enviadas += 1 if ok else 0
            if not ok:
                falhas.append(f'{mensagem["nome"]}: {resultado.get("erro")}')
            for empresa in mensagem["empresas"]:
                registro = self.registrar(
                    envio["id"],
                    empresa["empresa_id"],
                    (ano, mes),
                    "enviado" if ok else "falhou",
                    empresa["emails"],
                    "Enviado pelo email do DocFlow" if ok else str(resultado.get("erro") or "Falha no envio"),
                )
                empresas_ok += 1 if ok and registro["registrado"] else 0
        return {"mensagens": len(mensagens), "enviadas": enviadas, "falhas": falhas, "empresas": empresas_ok}

    # Modelos de mensagem ----------------------------------------------------------------

    def listar_modelos(self) -> list[dict]:
        return self.modelo_repository.list_all() if self.modelo_repository else []

    # Imagens do meio do texto -------------------------------------------------------------

    def salvar_imagem(self, dados: bytes, tipo: str, nome: str | None = None) -> int:
        """Guarda uma imagem para usar no texto do email (<img id="...">). Devolve o id."""
        if self.imagem_repository is None:
            raise ValidationError("Imagens no texto nao estao disponiveis.")
        tipo = str(tipo or "").lower().replace("image/", "").replace("jpg", "jpeg")
        if tipo not in IMAGEM_TIPOS:
            raise ValidationError("A imagem precisa ser PNG, JPG ou GIF.")
        if not dados:
            raise ValidationError("Imagem vazia.")
        if len(dados) > IMAGEM_MAX_BYTES:
            raise ValidationError("A imagem passa de 3 MB - use uma versao menor (ela vai dentro do email).")
        imagem_id = self.imagem_repository.insert(
            (str(nome).strip()[:200] or None) if nome else None, tipo, base64.b64encode(dados).decode("ascii")
        )
        self._cache_imagens[imagem_id] = {"id": imagem_id, "tipo": tipo, "dados": dados}
        return imagem_id

    def imagem(self, imagem_id: int) -> dict | None:
        """{"id", "tipo" (png/jpeg/gif), "dados": bytes} ou None se nao existe."""
        imagem_id = int(imagem_id)
        if imagem_id in self._cache_imagens:
            return self._cache_imagens[imagem_id]
        if self.imagem_repository is None:
            return None
        linha = self.imagem_repository.get(imagem_id)
        if not linha:
            return None
        imagem = {"id": imagem_id, "tipo": linha["tipo"], "dados": base64.b64decode(linha["dados"])}
        self._cache_imagens[imagem_id] = imagem
        return imagem

    def imagens_do_texto(self, texto: str | None) -> dict[int, dict]:
        """As imagens que o texto usa (as que sumiram do banco ficam de fora)."""
        encontradas = {}
        for imagem_id in imagens_usadas(texto):
            imagem = self.imagem(imagem_id)
            if imagem:
                encontradas[imagem_id] = imagem
        return encontradas

    def arquivo_imagem(self, imagem_id: int, pasta: Path | None = None) -> Path | None:
        """Grava a imagem num arquivo (para o Claude anexar no email que ele monta)."""
        imagem = self.imagem(imagem_id)
        if not imagem:
            return None
        pasta = Path(pasta or CONFIG_DIR / "imagens_email")
        pasta.mkdir(parents=True, exist_ok=True)
        arquivo = pasta / f"imagem_{imagem['id']}.{'jpg' if imagem['tipo'] == 'jpeg' else imagem['tipo']}"
        if not arquivo.is_file() or arquivo.stat().st_size != len(imagem["dados"]):
            arquivo.write_bytes(imagem["dados"])
        return arquivo

    def salvar_modelo(self, nome: str, assunto: str | None, corpo: str, corpo_whatsapp: str | None = None) -> dict:
        """Guarda um texto pronto para reaproveitar (mesmo nome substitui o texto)."""
        self._ensure_admin()
        if not self.modelo_repository:
            raise ValidationError("Modelos de mensagem indisponiveis.")
        nome = str(nome or "").strip()
        corpo = str(corpo or "").strip()
        if not nome:
            raise ValidationError("De um nome ao modelo.")
        if not corpo:
            raise ValidationError("O modelo precisa ter o texto da mensagem.")
        modelo_id = self.modelo_repository.save(
            nome,
            str(assunto or "").strip() or None,
            corpo,
            str(corpo_whatsapp or "").strip() or None,
        )
        if self.audit_service:
            self.audit_service.log("MODELO_MENSAGEM_SALVO", "modelo_mensagem", modelo_id, f'Modelo "{nome}" salvo.')
        return self.modelo_repository.get(modelo_id)

    def excluir_modelo(self, modelo_id: int) -> None:
        self._ensure_admin()
        if not self.modelo_repository:
            return
        modelo = self.modelo_repository.get(int(modelo_id))
        if not modelo:
            raise ValidationError("Modelo nao encontrado.")
        self.modelo_repository.delete(modelo["id"])
        if self.audit_service:
            self.audit_service.log(
                "MODELO_MENSAGEM_EXCLUIDO", "modelo_mensagem", modelo["id"], f'Modelo "{modelo["nome"]}" excluido.'
            )

    def historico(self, envio_id: int | None = None, empresa_id: int | None = None, limite: int = 200) -> list[dict]:
        return self.envio_repository.list_historico(envio_id, empresa_id, max(1, min(int(limite), 2000)))

    # Apoio -----------------------------------------------------------------------------

    def _normalize(self, dados: dict) -> dict:
        nome = str(dados.get("nome") or "").strip()
        if not nome:
            raise ValidationError("Informe o nome do envio.")
        assunto = str(dados.get("assunto") or "").strip()
        corpo = str(dados.get("corpo") or "").strip()
        if not assunto or not corpo:
            raise ValidationError("Informe o assunto e o texto da mensagem.")
        try:
            dia = int(dados.get("dia_envio"))
        except (TypeError, ValueError) as exc:
            raise ValidationError("Informe o dia do envio (1 a 31).") from exc
        if not 1 <= dia <= 31:
            raise ValidationError("O dia do envio deve ser de 1 a 31.")
        enviar_em = str(dados.get("enviar_em") or ENVIAR_MES_SEGUINTE)
        if enviar_em not in ENVIAR_EM_LABELS:
            raise ValidationError("'Enviar em' invalido. Use mes_seguinte ou mesmo_mes.")
        canal = str(dados.get("canal") or CANAL_AUTOMATICO)
        if canal not in CANAL_LABELS:
            raise ValidationError("Canal invalido. Use automatico, email ou whatsapp.")
        modo = str(dados.get("modo") or MODO_INDIVIDUAL)
        if modo not in MODO_LABELS:
            raise ValidationError("Modo invalido. Use individual ou cco.")
        email_para = str(dados.get("email_para") or "").strip() or None
        if email_para:
            emails_para = split_emails(email_para)
            if len(emails_para) != 1:
                raise ValidationError("Em 'Para' informe um email so (o do escritorio).")
            email_para = emails_para[0]
        tipo_id = dados.get("tipo_documento_id")
        if modo == MODO_CCO and tipo_id is not None:
            raise ValidationError("A copia oculta e so para mala direta (sem tipo de documento).")
        empresa_ids: list[int] = []
        excluidas: list[int] = []
        if tipo_id is not None:
            tipo_id = int(tipo_id)
            if not self.tipo_repository.get_by_id(tipo_id):
                raise ValidationError("Tipo de documento nao encontrado.")
            # O publico vem do tipo; aqui so as empresas tiradas deste envio.
            excluidas = parse_empresa_ids(dados.get("empresa_ids_excluidas"))
        else:
            # Sem tipo e mala direta: para as empresas escolhidas ou, sem escolha, para todas.
            empresa_ids = parse_empresa_ids(dados.get("empresa_ids"))
            encontradas = {e["id"] for e in self.empresa_repository.list_by_ids(empresa_ids)}
            if set(empresa_ids) - encontradas:
                raise ValidationError("Empresa nao encontrada na lista do envio.")
        return {
            "nome": nome,
            "ativo": 1 if dados.get("ativo", 1) else 0,
            "tipo_documento_id": tipo_id,
            "meses": ",".join(str(m) for m in parse_meses(dados.get("meses"))),
            "dia_envio": dia,
            "enviar_em": enviar_em,
            "canal": canal,
            "empresa_ids": ",".join(str(i) for i in empresa_ids) or None,
            "modo": modo,
            "email_para": email_para,
            "empresa_ids_excluidas": ",".join(str(i) for i in excluidas) or None,
            "corpo_whatsapp": str(dados.get("corpo_whatsapp") or "").strip() or None,
            "somente_pendentes": 1 if dados.get("somente_pendentes", 1) else 0,
            "assunto": assunto,
            "corpo": corpo,
            "instrucoes": str(dados.get("instrucoes") or "").strip() or None,
        }

    def _decorate(self, envio: dict, hoje: date) -> dict:
        meses = parse_meses(envio["meses"])
        envio["ativo"] = bool(envio["ativo"])
        envio["somente_pendentes"] = bool(envio["somente_pendentes"])
        envio["meses_lista"] = meses
        envio["meses_label"] = format_meses(meses)
        envio["empresa_ids_lista"] = parse_empresa_ids(envio.get("empresa_ids"))
        envio["empresa_ids_excluidas_lista"] = parse_empresa_ids(envio.get("empresa_ids_excluidas"))
        envio["enviar_em_label"] = ENVIAR_EM_LABELS[envio["enviar_em"]]
        envio["canal_label"] = CANAL_LABELS[envio["canal"]]
        envio["modo_label"] = MODO_LABELS[envio["modo"]]
        if envio["modo"] == MODO_CCO:
            quantas = len(envio["empresa_ids_lista"])
            envio["publico_label"] = "Mala direta em cópia oculta: " + (
                f"{quantas} empresa(s)" if quantas else "todas as empresas ativas"
            )
        elif envio.get("nome_tipo"):
            tiradas = len(envio["empresa_ids_excluidas_lista"])
            envio["publico_label"] = envio["nome_tipo"] + (f" (menos {tiradas} tirada(s))" if tiradas else "")
        elif envio["empresa_ids_lista"]:
            envio["publico_label"] = f"Mala direta: {len(envio['empresa_ids_lista'])} empresa(s) escolhida(s)"
        else:
            envio["publico_label"] = "Mala direta: todas as empresas ativas"
        proximo = self.proximo_envio(envio, hoje) if envio["ativo"] else None
        envio["proximo_envio"] = proximo[0].isoformat() if proximo else None
        envio["proxima_competencia"] = format_competencia(*proximo[1]) if proximo else None
        return envio

    def _ensure_admin(self) -> None:
        if self.session_service and not self.session_service.is_admin():
            raise ValidationError("Apenas usuarios admin podem configurar envios automaticos.")

    def _user_id(self) -> int | None:
        return self.session_service.get_user_id() if self.session_service else None

    def _log(self, acao: str, envio_id: int, descricao: str) -> None:
        if self.audit_service:
            self.audit_service.log(acao, "envio_programado", envio_id, descricao)
