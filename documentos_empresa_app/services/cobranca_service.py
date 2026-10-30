from __future__ import annotations

from datetime import date, timedelta

from documentos_empresa_app.database.repositories import (
    CobrancaRepository,
    DocumentoRepository,
    EmpresaRepository,
    PeriodoRepository,
    SituacaoCobrancaRepository,
    StatusRepository,
    VerificacaoRepository,
)
from documentos_empresa_app.services.audit_service import AuditService
from documentos_empresa_app.services.collection_service import CollectionService
from documentos_empresa_app.services.session_service import SessionService
from documentos_empresa_app.services.status_service import StatusService
from documentos_empresa_app.utils.cache import ResultCache
from documentos_empresa_app.utils.common import (
    ValidationError,
    format_competencia,
    normalize_delivery_methods,
    parse_delivery_methods,
)

TIPO_COBRANCA = "Cobranca"
TIPO_RECOBRANCA = "Recobranca"
TIPO_VERIFICACAO = "Verificacao"


def tipo_da_sequencia(sequencia: int) -> str:
    return TIPO_COBRANCA if sequencia <= 1 else TIPO_RECOBRANCA


# Resultado de cada documento numa verificacao. "verificacao_falhou" e diferente de
# "nao_encontrado": nao deu para olhar (sem acesso, erro), entao nao gera cobranca.
RESULTADO_RECEBIDO = "recebido"
RESULTADO_PROBLEMA = "documento_com_problema"
RESULTADO_NAO_ENCONTRADO = "nao_encontrado"
RESULTADO_FALHOU = "verificacao_falhou"
RESULTADOS_VERIFICACAO = (RESULTADO_RECEBIDO, RESULTADO_PROBLEMA, RESULTADO_NAO_ENCONTRADO, RESULTADO_FALHOU)
RESULTADO_LABELS = {
    RESULTADO_RECEBIDO: "Recebido",
    RESULTADO_PROBLEMA: "Documento com problema",
    RESULTADO_NAO_ENCONTRADO: "Não encontrado",
    RESULTADO_FALHOU: "Verificação falhou",
}

# Situacao de cobranca de cada documento numa competencia: onde ele esta no fluxo.
SITUACAO_A_VERIFICAR = "a_verificar"
SITUACAO_RECEBIDO = "recebido"
SITUACAO_PROBLEMA = "documento_com_problema"
SITUACAO_NAO_ENCONTRADO = "nao_encontrado"
SITUACAO_FALHOU = "verificacao_falhou"
SITUACAO_COBRADO = "cobrado_aguardando"
SITUACAO_PROMESSA = "promessa_envio"
SITUACAO_PESSOA = "precisa_pessoa"
SITUACAO_LABELS = {
    SITUACAO_A_VERIFICAR: "A verificar",
    SITUACAO_RECEBIDO: "Recebido",
    SITUACAO_PROBLEMA: "Documento com problema",
    SITUACAO_NAO_ENCONTRADO: "Não encontrado",
    SITUACAO_FALHOU: "Verificação falhou",
    SITUACAO_COBRADO: "Cobrado, aguardando",
    SITUACAO_PROMESSA: "Cliente prometeu enviar",
    SITUACAO_PESSOA: "Precisa de uma pessoa",
}

MOTIVOS_PROBLEMA = {
    "documento_errado": "Documento errado",
    "competencia_errada": "Competência errada",
    "ilegivel_ou_incompleto": "Ilegível ou incompleto",
    "empresa_errada": "De outra empresa",
    "outro": "Outro problema",
}
MOTIVOS_PESSOA = {
    "baixa_falhou": "A baixa não pôde ser feita",
    "baixa_pendente": "Encontrado, falta dar baixa",
    "documento_com_problema": "Documento com problema",
    "limite_de_tentativas": "Limite de recobranças atingido",
    "cliente_respondeu": "Cliente respondeu e precisa de retorno",
    "sem_canal": "Sem canal para cobrar",
    "outro": "Outro motivo",
}

# Acoes sugeridas pelo planejador ("o que fazer agora").
ACAO_VERIFICAR = "verificar"
ACAO_COBRAR = "cobrar"
ACAO_RECOBRAR = "recobrar"
ACAO_AGUARDAR = "aguardar"
ACAO_PESSOA = "com_pessoa"
ACOES = (ACAO_VERIFICAR, ACAO_COBRAR, ACAO_RECOBRAR, ACAO_AGUARDAR, ACAO_PESSOA)
ACAO_LABELS = {
    ACAO_VERIFICAR: "Verificar",
    ACAO_COBRAR: "Cobrar",
    ACAO_RECOBRAR: "Recobrar",
    ACAO_AGUARDAR: "Aguardar",
    ACAO_PESSOA: "Com uma pessoa",
}


def motivo_label(motivo: str | None) -> str:
    if not motivo:
        return ""
    return MOTIVOS_PESSOA.get(motivo) or MOTIVOS_PROBLEMA.get(motivo) or motivo


def _date_of(raw) -> date | None:
    if not raw:
        return None
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


class CobrancaService:
    """Registro do acompanhamento de cada empresa: as cobrancas feitas (com a contagem de
    cobranca/recobranca por documento e competencia) e as verificacoes nos canais de
    recebimento (o que foi encontrado, onde, e o que continua faltando).

    Uma cobranca e um contato (email, WhatsApp, Onvio, telefone...) cobrando um ou mais
    documentos de uma ou mais competencias. Para cada documento e competencia, a primeira
    cobranca tem sequencia 1; as seguintes sao recobrancas (2, 3...)."""

    def __init__(
        self,
        cobranca_repository: CobrancaRepository,
        verificacao_repository: VerificacaoRepository,
        empresa_repository: EmpresaRepository,
        documento_repository: DocumentoRepository,
        periodo_repository: PeriodoRepository,
        status_repository: StatusRepository,
        status_service: StatusService,
        collection_service: CollectionService,
        audit_service: AuditService | None = None,
        session_service: SessionService | None = None,
        situacao_repository: SituacaoCobrancaRepository | None = None,
    ) -> None:
        self.situacao_repository = situacao_repository or SituacaoCobrancaRepository(cobranca_repository.db_manager)
        self._plano_cache = ResultCache(cobranca_repository.db_manager)
        self.cobranca_repository = cobranca_repository
        self.verificacao_repository = verificacao_repository
        self.empresa_repository = empresa_repository
        self.documento_repository = documento_repository
        self.periodo_repository = periodo_repository
        self.status_repository = status_repository
        self.status_service = status_service
        self.collection_service = collection_service
        self.audit_service = audit_service
        self.session_service = session_service

    # Registro -----------------------------------------------------------------------

    def registrar_cobranca(
        self,
        empresa_id: int,
        canal: str,
        itens: list[tuple[int, int]] | None = None,
        *,
        destinatario: str | None = None,
        assunto: str | None = None,
        mensagem: str | None = None,
        observacao: str | None = None,
        rodada_id: int | None = None,
    ) -> dict:
        """Registra uma cobranca feita. 'itens' sao pares (documento_id, periodo_id); sem
        itens, registra todos os documentos em aberto da empresa ate hoje."""
        canal_normalizado = self._normalize_text(canal)
        if not canal_normalizado:
            raise ValidationError("Informe o canal usado na cobranca (ex: Email, WhatsApp, Onvio).")

        with self.empresa_repository.db_manager.connect():
            empresa = self._get_empresa(empresa_id)
            pares = self._dedupe(itens) if itens else self._itens_em_aberto(empresa_id)
            if not pares:
                raise ValidationError(f'A empresa "{empresa["nome_empresa"]}" nao tem documentos em aberto para cobrar.')
            documentos, periodos = self._validate_items(empresa, pares)

            cobranca_id = self.cobranca_repository.create(
                empresa_id,
                canal_normalizado,
                self._normalize_text(destinatario),
                self._normalize_text(assunto),
                self._normalize_text(mensagem),
                self._normalize_text(observacao),
                self._user_id(),
                rodada_id,
            )
            registrados = []
            for documento_id, periodo_id in pares:
                sequencia = self.cobranca_repository.next_sequence(documento_id, periodo_id)
                self.cobranca_repository.add_item(cobranca_id, documento_id, periodo_id, sequencia)
                self._set_situacao(
                    documento_id,
                    periodo_id,
                    SITUACAO_COBRADO,
                    detalhe=f"{tipo_da_sequencia(sequencia)} {sequencia} por {canal_normalizado}",
                    rodada_id=rodada_id,
                )
                periodo = periodos[periodo_id]
                registrados.append(
                    {
                        "documento_id": documento_id,
                        "nome_documento": documentos[documento_id]["nome_documento"],
                        "competencia": format_competencia(periodo["ano"], periodo["mes"]),
                        "sequencia": sequencia,
                        "tipo": tipo_da_sequencia(sequencia),
                    }
                )

            recobrancas = sum(1 for item in registrados if item["tipo"] == TIPO_RECOBRANCA)
            self._log(
                "COBRANCA_REGISTRADA",
                "cobranca",
                cobranca_id,
                (
                    f'Usuario {self._actor_name()} registrou cobranca por {canal_normalizado} para a empresa '
                    f'"{empresa["nome_empresa"]}": {len(registrados)} documento(s), '
                    f"{recobrancas} recobranca(s)."
                ),
                empresa,
            )
        return {
            "cobranca_id": cobranca_id,
            "empresa": empresa["nome_empresa"],
            "canal": canal_normalizado,
            "itens": registrados,
        }

    def registrar_verificacao(
        self,
        empresa_id: int,
        fontes: str | list[str],
        itens: list[dict],
        *,
        resumo: str | None = None,
        marcar_recebidos: bool = True,
        rodada_id: int | None = None,
    ) -> dict:
        """Registra o resultado de uma verificacao nos canais da empresa. Cada item:
        {documento_id, periodo_id, resultado, motivo, onde, observacao}. 'resultado' e um de
        RESULTADOS_VERIFICACAO; itens antigos com {encontrado: bool} continuam aceitos.

        - recebido: da baixa (status Recebido) se marcar_recebidos. Se a baixa falhar, o
          item vai para uma pessoa com o erro anotado.
        - documento_com_problema: veio algo, mas errado; 'motivo' diz o que (MOTIVOS_PROBLEMA).
          Nunca da baixa.
        - nao_encontrado: procurou e nao achou; entra na fila de cobranca.
        - verificacao_falhou: nao deu para olhar; volta a ser verificado, sem cobrar."""
        fontes_normalizadas = normalize_delivery_methods(fontes)
        if not fontes_normalizadas:
            raise ValidationError("Informe onde a verificacao foi feita (ex: Email, Onvio).")
        if not itens:
            raise ValidationError("Informe pelo menos um documento verificado.")
        itens_normalizados = [self._normalize_item_verificacao(item) for item in itens]

        with self.empresa_repository.db_manager.connect():
            empresa = self._get_empresa(empresa_id)
            pares = self._dedupe([(item["documento_id"], item["periodo_id"]) for item in itens_normalizados])
            documentos, periodos = self._validate_items(empresa, pares)
            verificacao_id = self.verificacao_repository.create(
                empresa_id, fontes_normalizadas, self._normalize_text(resumo), self._user_id(), rodada_id
            )

            registrados = []
            vistos: set[tuple[int, int]] = set()
            for item in itens_normalizados:
                chave = (item["documento_id"], item["periodo_id"])
                if chave in vistos:
                    continue
                vistos.add(chave)
                resultado = item["resultado"]
                motivo = item["motivo"]
                observacao = item["observacao"]
                baixa_feita = False
                baixa_erro = None

                if resultado == RESULTADO_RECEBIDO:
                    if marcar_recebidos:
                        try:
                            self.status_service.update_status(chave[0], chave[1], "Recebido")
                            baixa_feita = True
                        except ValidationError as exc:
                            baixa_erro = str(exc)
                    if baixa_feita:
                        self._set_situacao(chave[0], chave[1], SITUACAO_RECEBIDO, detalhe=item["onde"], rodada_id=rodada_id)
                    else:
                        self._set_situacao(
                            chave[0],
                            chave[1],
                            SITUACAO_PESSOA,
                            motivo="baixa_falhou" if baixa_erro else "baixa_pendente",
                            detalhe=baixa_erro or "Encontrado na verificação; a baixa ficou para uma pessoa.",
                            rodada_id=rodada_id,
                        )
                elif resultado == RESULTADO_PROBLEMA:
                    self._set_situacao(chave[0], chave[1], SITUACAO_PROBLEMA, motivo=motivo, detalhe=observacao, rodada_id=rodada_id)
                elif resultado == RESULTADO_NAO_ENCONTRADO:
                    self._set_situacao(chave[0], chave[1], SITUACAO_NAO_ENCONTRADO, detalhe=observacao, rodada_id=rodada_id)
                else:
                    self._set_situacao(
                        chave[0], chave[1], SITUACAO_FALHOU, motivo=motivo, detalhe=observacao, rodada_id=rodada_id
                    )

                self.verificacao_repository.add_item(
                    verificacao_id,
                    chave[0],
                    chave[1],
                    resultado,
                    item["onde"],
                    observacao,
                    motivo=motivo,
                    baixa_feita=baixa_feita,
                    baixa_erro=baixa_erro,
                    arquivo=item["arquivo"],
                )
                periodo = periodos[chave[1]]
                registrados.append(
                    {
                        "documento_id": chave[0],
                        "nome_documento": documentos[chave[0]]["nome_documento"],
                        "competencia": format_competencia(periodo["ano"], periodo["mes"]),
                        "resultado": resultado,
                        "encontrado": resultado in (RESULTADO_RECEBIDO, RESULTADO_PROBLEMA),
                        "motivo": motivo,
                        "baixa_feita": baixa_feita,
                        "baixa_erro": baixa_erro,
                        "status_aplicado": "Recebido" if baixa_feita else None,
                        "observacao": observacao,
                        "arquivo": item["arquivo"],
                    }
                )

            contagem = {r: sum(1 for item in registrados if item["resultado"] == r) for r in RESULTADOS_VERIFICACAO}
            partes = [f"{contagem[r]} {RESULTADO_LABELS[r].lower()}" for r in RESULTADOS_VERIFICACAO if contagem[r]]
            self._log(
                "VERIFICACAO_REGISTRADA",
                "verificacao",
                verificacao_id,
                (
                    f'Usuario {self._actor_name()} verificou {fontes_normalizadas} da empresa '
                    f'"{empresa["nome_empresa"]}": {", ".join(partes)}.'
                ),
                empresa,
            )
        return {
            "verificacao_id": verificacao_id,
            "empresa": empresa["nome_empresa"],
            "fontes": fontes_normalizadas,
            "resumo": contagem,
            "itens": registrados,
        }

    # Acoes sobre a situacao ----------------------------------------------------------

    FONTE_MANUAL = "Conferencia manual"

    def registrar_conferencia_manual(
        self,
        documento_id: int,
        periodo_id: int,
        chegou: bool,
        *,
        arquivo: str | None = None,
        observacao: str | None = None,
    ) -> dict:
        """Uma pessoa conferiu o documento na tela: chegou (da baixa) ou nao chegou (entra
        na fila de cobranca). Fica registrado como uma verificacao."""
        resultado = RESULTADO_RECEBIDO if chegou else RESULTADO_NAO_ENCONTRADO
        return self.resolver_manual(
            [(documento_id, periodo_id)], resultado, arquivo=arquivo, observacao=observacao
        )[0]

    def resolver_manual(
        self,
        itens: list[tuple[int, int]],
        resultado: str,
        *,
        motivo: str | None = None,
        arquivo: str | None = None,
        observacao: str | None = None,
    ) -> list[dict]:
        """Conferencia feita por uma pessoa na tela, para um ou varios documentos (de uma ou
        varias empresas). Vira uma verificacao por empresa, com fonte "Conferencia manual"."""
        pares = self._dedupe(itens or [])
        if not pares:
            raise ValidationError("Selecione pelo menos um documento.")
        documentos = {d["id"]: d for d in self.documento_repository.list_by_ids([p[0] for p in pares])}
        por_empresa: dict[int, list[dict]] = {}
        for documento_id, periodo_id in pares:
            documento = documentos.get(documento_id)
            if documento is None:
                raise ValidationError(f"Documento {documento_id} nao encontrado.")
            por_empresa.setdefault(documento["empresa_id"], []).append(
                {
                    "documento_id": documento_id,
                    "periodo_id": periodo_id,
                    "resultado": resultado,
                    "motivo": motivo,
                    "arquivo": arquivo,
                    "observacao": observacao,
                }
            )
        with self.empresa_repository.db_manager.connect():
            return [
                self.registrar_verificacao(empresa_id, [self.FONTE_MANUAL], itens_empresa)
                for empresa_id, itens_empresa in por_empresa.items()
            ]

    def mapa_empresa(self, empresa_id: int, meses: int = 12, ate_periodo_id: int | None = None) -> dict:
        """Visao panoramica da empresa: cada documento (agrupado por tipo) nos ultimos 'meses'
        meses ate 'ate_periodo_id' (ou o mes atual), com status, quem marcou e quando, e a
        situacao de cobranca de cada competencia."""
        limite = (date.today().year, date.today().month)
        if ate_periodo_id is not None:
            ate = self.periodo_repository.get_by_id(ate_periodo_id)
            if ate:
                limite = (ate["ano"], ate["mes"])
        periodos = [p for p in self.periodo_repository.list_all() if (p["ano"], p["mes"]) <= limite]
        periodos.sort(key=lambda p: (p["ano"], p["mes"]))
        periodos = periodos[-meses:]
        if not periodos:
            return {"periodos": [], "documentos": []}
        visao = self.status_service.build_control_view(empresa_id, periodos[0]["id"], periodos[-1]["id"])
        periodos_visao = visao["periodos"]
        documentos = [doc for grupo in visao["groups"] for doc in grupo["documentos"]]
        situacoes = {
            (row["documento_empresa_id"], row["periodo_id"]): row
            for row in self.situacao_repository.list_for_documents([d["id"] for d in documentos])
        }
        linhas = []
        for grupo in visao["groups"]:
            for doc in grupo["documentos"]:
                celulas = []
                for celula in doc["cells"]:
                    situacao = situacoes.get((doc["id"], celula["periodo_id"])) or {}
                    celulas.append(
                        {
                            "periodo_id": celula["periodo_id"],
                            "disponivel": bool(celula["available"]),
                            "status": celula["status"] or "",
                            "situacao": situacao.get("situacao"),
                            "situacao_motivo": situacao.get("motivo"),
                            "marcado_por": celula.get("updated_by_username") or None,
                            "marcado_em": celula.get("updated_at"),
                            "aviso": celula.get("read_only_hint"),
                        }
                    )
                linhas.append(
                    {
                        "documento_id": doc["id"],
                        "nome_documento": doc["nome_documento"],
                        "tipo": grupo["tipo_nome"],
                        "celulas": celulas,
                    }
                )
        return {
            "periodos": [
                {"periodo_id": p["id"], "competencia": format_competencia(p["ano"], p["mes"]), "ano": p["ano"], "mes": p["mes"]}
                for p in periodos_visao
            ],
            "documentos": linhas,
        }

    def registrar_promessa(
        self,
        itens: list[tuple[int, int]],
        aguardar_ate,
        detalhe: str | None = None,
        rodada_id: int | None = None,
    ) -> dict:
        """O cliente disse que vai mandar: nao cobra de novo ate 'aguardar_ate'."""
        prazo = _date_of(aguardar_ate)
        if prazo is None:
            raise ValidationError("Informe a data ate quando aguardar (AAAA-MM-DD).")
        if prazo < date.today():
            raise ValidationError("A data da promessa ja passou.")
        return self._aplicar_em_lote(
            itens,
            SITUACAO_PROMESSA,
            "PROMESSA_REGISTRADA",
            f"promessa de envio ate {prazo.strftime('%d/%m/%Y')}",
            detalhe=detalhe,
            aguardar_ate=prazo.isoformat(),
            rodada_id=rodada_id,
        )

    def encaminhar_para_pessoa(
        self, itens: list[tuple[int, int]], motivo: str, detalhe: str | None = None, rodada_id: int | None = None
    ) -> dict:
        motivo_normalizado = self._normalize_text(motivo) or "outro"
        return self._aplicar_em_lote(
            itens,
            SITUACAO_PESSOA,
            "ENCAMINHADO_PESSOA",
            f"encaminhado para uma pessoa ({motivo_label(motivo_normalizado)})",
            motivo=motivo_normalizado,
            detalhe=detalhe,
            rodada_id=rodada_id,
        )

    def devolver_para_fluxo(self, itens: list[tuple[int, int]], detalhe: str | None = None) -> dict:
        """Uma pessoa resolveu o que travava: o documento volta a ser verificado/cobrado."""
        return self._aplicar_em_lote(
            itens, SITUACAO_A_VERIFICAR, "DEVOLVIDO_FLUXO", "devolvido para o acompanhamento", detalhe=detalhe
        )

    def dar_baixa_manual(self, itens: list[tuple[int, int]], detalhe: str | None = None) -> dict:
        """Uma pessoa confirma que o documento chegou: marca Recebido e encerra a situacao."""
        pares = self._dedupe(itens)
        with self.empresa_repository.db_manager.connect():
            for documento_id, periodo_id in pares:
                self.status_service.update_status(documento_id, periodo_id, "Recebido")
            return self._aplicar_em_lote(
                pares, SITUACAO_RECEBIDO, "BAIXA_MANUAL", "baixa manual", detalhe=detalhe or "Baixa dada por uma pessoa."
            )

    def _aplicar_em_lote(
        self,
        itens: list[tuple[int, int]],
        situacao: str,
        acao_log: str,
        descricao: str,
        *,
        motivo: str | None = None,
        detalhe: str | None = None,
        aguardar_ate: str | None = None,
        rodada_id: int | None = None,
    ) -> dict:
        pares = self._dedupe(itens or [])
        if not pares:
            raise ValidationError("Selecione pelo menos um documento.")
        detalhe_normalizado = self._normalize_text(detalhe)
        with self.empresa_repository.db_manager.connect():
            documentos = {d["id"]: d for d in self.documento_repository.list_by_ids([p[0] for p in pares])}
            por_empresa: dict[int, list[tuple[int, int]]] = {}
            for documento_id, periodo_id in pares:
                documento = documentos.get(documento_id)
                if documento is None:
                    raise ValidationError(f"Documento {documento_id} nao encontrado.")
                if not self.periodo_repository.get_by_id(periodo_id):
                    raise ValidationError("Competencia nao encontrada.")
                por_empresa.setdefault(documento["empresa_id"], []).append((documento_id, periodo_id))
            for empresa_id, pares_empresa in por_empresa.items():
                empresa = self._get_empresa(empresa_id)
                for documento_id, periodo_id in pares_empresa:
                    self._set_situacao(
                        documento_id,
                        periodo_id,
                        situacao,
                        motivo=motivo,
                        detalhe=detalhe_normalizado,
                        aguardar_ate=aguardar_ate,
                        rodada_id=rodada_id,
                    )
                nomes = ", ".join(documentos[d]["nome_documento"] for d, _ in pares_empresa)
                texto = f'Usuario {self._actor_name()} registrou {descricao} na empresa "{empresa["nome_empresa"]}": {nomes}.'
                if detalhe_normalizado:
                    texto += f" {detalhe_normalizado}"
                self._log(acao_log, "situacao_cobranca", pares_empresa[0][0], texto, empresa)
        return {"situacao": situacao, "documentos": len(pares)}

    def _set_situacao(
        self,
        documento_id: int,
        periodo_id: int,
        situacao: str,
        *,
        motivo: str | None = None,
        detalhe: str | None = None,
        aguardar_ate: str | None = None,
        rodada_id: int | None = None,
    ) -> None:
        atual = self.situacao_repository.get(documento_id, periodo_id)
        detalhe = self._normalize_text(detalhe)
        motivo = self._normalize_text(motivo)
        self.situacao_repository.upsert(
            documento_id, periodo_id, situacao, motivo, detalhe, aguardar_ate, self._user_id(), rodada_id
        )
        mudou = (
            atual is None
            or atual["situacao"] != situacao
            or atual.get("motivo") != motivo
            or atual.get("detalhe") != detalhe
            or atual.get("aguardar_ate") != aguardar_ate
        )
        if mudou:
            self.situacao_repository.add_event(
                documento_id,
                periodo_id,
                atual["situacao"] if atual else None,
                situacao,
                motivo,
                detalhe,
                self._user_id(),
                rodada_id,
            )

    def _normalize_item_verificacao(self, item: dict) -> dict:
        resultado = self._normalize_text(item.get("resultado"))
        if resultado is None:
            resultado = RESULTADO_RECEBIDO if item.get("encontrado") else RESULTADO_NAO_ENCONTRADO
        if resultado not in RESULTADOS_VERIFICACAO:
            raise ValidationError(
                f'Resultado "{resultado}" invalido. Use um de: {", ".join(RESULTADOS_VERIFICACAO)}.'
            )
        motivo = self._normalize_text(item.get("motivo"))
        if resultado == RESULTADO_PROBLEMA and motivo is None:
            motivo = "outro"
        if resultado == RESULTADO_FALHOU and motivo is None and not self._normalize_text(item.get("observacao")):
            raise ValidationError("Quando a verificacao falha, diga o motivo (ex: sem acesso ao Onvio).")
        return {
            "documento_id": int(item["documento_id"]),
            "periodo_id": int(item["periodo_id"]),
            "resultado": resultado,
            "motivo": motivo,
            "onde": self._normalize_text(item.get("onde")),
            "observacao": self._normalize_text(item.get("observacao")),
            "arquivo": self._normalize_text(item.get("arquivo")),
        }

    # Planejamento ------------------------------------------------------------------

    def proximas_acoes(
        self,
        empresa_id: int | None = None,
        somente_ativas: bool = True,
        hoje: date | None = None,
    ) -> dict:
        """O que fazer agora com cada documento em aberto, pelas regras do sistema:
        verificar, cobrar, recobrar, aguardar ou deixar com uma pessoa - e por que.
        Fica em cache ate a proxima escrita (Painel, menu e Cobrancas pedem no mesmo clique)."""
        return self._plano_filtrado(empresa_id, somente_ativas, hoje, copy=True)

    def _plano_filtrado(self, empresa_id: int | None, somente_ativas: bool, hoje: date | None, *, copy: bool) -> dict:
        # O plano e calculado uma vez para todas as empresas (em cache ate a proxima escrita)
        # e filtrado aqui: Painel, menu, Cobrancas e Ficha usam o mesmo calculo.
        hoje = hoje or date.today()
        plano = self._plano_cache.get(hoje, lambda: self._proximas_acoes(hoje), copy=copy)
        if empresa_id is None and not somente_ativas:
            return plano
        empresas = [
            e
            for e in plano["empresas"]
            if (empresa_id is None or e["empresa_id"] == empresa_id) and (not somente_ativas or e["empresa_ativa"])
        ]
        resumo = {acao: 0 for acao in ACOES}
        for empresa in empresas:
            for doc in empresa["documentos"]:
                resumo[doc["acao"]] += 1
        return {**plano, "resumo": resumo, "empresas": empresas}

    def _proximas_acoes(self, hoje: date) -> dict:
        regras = self.collection_service.get_followup_rules()
        queue = self.collection_service.queue_snapshot(reference_date=hoje, active_only=False)
        items = queue["items"]
        document_ids = [doc["documento_id"] for item in items for doc in item["documents"]]
        counts = {
            (row["documento_empresa_id"], row["periodo_id"]): row
            for row in self.cobranca_repository.counts_by_document_period(document_ids)
        }
        situacoes = {
            (row["documento_empresa_id"], row["periodo_id"]): row
            for row in self.situacao_repository.list_for_documents(document_ids)
        }
        empresas = {e["id"]: e for e in self.empresa_repository.list_by_ids([i["empresa_id"] for i in items])}

        resumo = {acao: 0 for acao in ACOES}
        resultado_empresas = []
        for item in items:
            empresa = empresas.get(item["empresa_id"], {})
            documentos = []
            for doc in item["documents"]:
                chave = (doc["documento_id"], doc["periodo_id"])
                count = counts.get(chave, {})
                situacao = situacoes.get(chave)
                vezes = int(count.get("vezes") or 0)
                ultima = count.get("ultima_cobranca_em")
                acao, porque, quando = self._decidir(situacao, vezes, ultima, regras, hoje)
                resumo[acao] += 1
                documentos.append(
                    {
                        "documento_id": doc["documento_id"],
                        "periodo_id": doc["periodo_id"],
                        "nome_documento": doc["nome_documento"],
                        "observacao_documento": doc.get("observacao"),
                        "competencia": doc["periodo_label"].split(" - ", 1)[0],
                        "status": doc["status"],
                        "acao": acao,
                        "porque": porque,
                        "proxima_acao_em": quando.isoformat() if quando else None,
                        "situacao": situacao["situacao"] if situacao else None,
                        "situacao_motivo": situacao.get("motivo") if situacao else None,
                        "situacao_detalhe": situacao.get("detalhe") if situacao else None,
                        "situacao_atualizada_em": situacao.get("atualizado_em") if situacao else None,
                        "vezes_cobrado": vezes,
                        "ultima_cobranca_em": ultima,
                    }
                )
            acoes_empresa = {d["acao"] for d in documentos}
            acao_principal = next(a for a in ACOES if a in acoes_empresa)
            resultado_empresas.append(
                {
                    "empresa_id": item["empresa_id"],
                    "codigo_empresa": item["codigo_empresa"],
                    "nome_empresa": item["nome_empresa"],
                    "fase": item["phase_label"],
                    "em_atraso": item["phase_key"] == CollectionService.PHASE_EM_ATRASO,
                    "empresa_ativa": bool(item["empresa_ativa"]),
                    "acao_principal": acao_principal,
                    "canais_recebimento": parse_delivery_methods(empresa.get("canais_recebimento")),
                    "emails_origem_documentos": empresa.get("emails_origem_documentos"),
                    "instrucoes_busca": empresa.get("instrucoes_busca"),
                    "email_contato": empresa.get("email_contato"),
                    "nome_contato": empresa.get("nome_contato"),
                    "documentos": documentos,
                }
            )
        resultado_empresas.sort(key=lambda e: (ACOES.index(e["acao_principal"]), not e["em_atraso"], e["codigo_empresa"]))
        return {"data": hoje.isoformat(), "regras": regras, "resumo": resumo, "empresas": resultado_empresas}

    @staticmethod
    def _decidir(situacao: dict | None, vezes: int, ultima_cobranca, regras: dict, hoje: date):
        """Regra de cada documento. Devolve (acao, porque, data da proxima acao)."""
        nome = situacao["situacao"] if situacao else None
        ultima = _date_of(ultima_cobranca)
        liberado_em = ultima + timedelta(days=regras["dias_entre_cobrancas"]) if ultima else None

        if nome == SITUACAO_PESSOA:
            return ACAO_PESSOA, motivo_label(situacao.get("motivo")) or "Encaminhado para uma pessoa", None
        if nome == SITUACAO_PROMESSA:
            prazo = _date_of(situacao.get("aguardar_ate"))
            if prazo and hoje <= prazo:
                return ACAO_AGUARDAR, f"Cliente prometeu enviar até {prazo.strftime('%d/%m/%Y')}", prazo + timedelta(days=1)
            return ACAO_VERIFICAR, "Prazo prometido pelo cliente venceu", None
        if nome == SITUACAO_COBRADO or (nome is None and vezes > 0):
            if liberado_em and hoje < liberado_em:
                return ACAO_AGUARDAR, "Cobrado há pouco; dando tempo para o cliente enviar", liberado_em
            return ACAO_VERIFICAR, "Já passou o prazo depois da cobrança; ver se chegou", None
        if nome == SITUACAO_PROBLEMA and regras["problema_vai_para_pessoa"]:
            return ACAO_PESSOA, f"Documento com problema: {motivo_label(situacao.get('motivo')) or 'ver detalhe'}", None
        if nome in (SITUACAO_NAO_ENCONTRADO, SITUACAO_PROBLEMA):
            prefixo = "Veio com problema" if nome == SITUACAO_PROBLEMA else "Não encontrado na verificação"
            if vezes == 0:
                return ACAO_COBRAR, f"{prefixo}; ainda não foi cobrado", None
            if liberado_em and hoje < liberado_em:
                return ACAO_AGUARDAR, f"{prefixo}; esperando o intervalo entre cobranças", liberado_em
            if vezes - 1 >= regras["max_recobrancas"]:
                return ACAO_PESSOA, f"Limite de recobranças atingido ({vezes} cobranças)", None
            return ACAO_RECOBRAR, f"{prefixo}; já cobrado {vezes} vez(es)", None
        if nome == SITUACAO_FALHOU:
            return ACAO_VERIFICAR, f"Última verificação falhou: {situacao.get('motivo') or situacao.get('detalhe') or 'sem detalhe'}", None
        if nome == SITUACAO_RECEBIDO:
            return ACAO_VERIFICAR, "Marcado como recebido, mas o status voltou a ficar em aberto", None
        if nome == SITUACAO_A_VERIFICAR:
            return ACAO_VERIFICAR, "Devolvido para o acompanhamento", None
        return ACAO_VERIFICAR, "Ainda não verificado", None

    def precisa_de_atencao(self) -> list[dict]:
        """Documentos que estao com uma pessoa (pelas regras ou porque alguem encaminhou),
        com empresa, motivo e o que ja foi feito."""
        plano = self._plano_filtrado(None, False, None, copy=False)  # so leitura
        casos = []
        for empresa in plano["empresas"]:
            for doc in empresa["documentos"]:
                if doc["acao"] != ACAO_PESSOA:
                    continue
                casos.append(
                    {
                        "empresa_id": empresa["empresa_id"],
                        "codigo_empresa": empresa["codigo_empresa"],
                        "nome_empresa": empresa["nome_empresa"],
                        "email_contato": empresa["email_contato"],
                        **doc,
                    }
                )
        casos.sort(key=lambda c: (c["situacao_atualizada_em"] or ""), reverse=True)
        return casos

    # Consultas ----------------------------------------------------------------------

    def ficha_empresa(self, empresa_id: int, limite_historico: int = 50) -> dict:
        """Tudo sobre a empresa num lugar so: dados, como recebe os documentos, cada
        documento com sua contagem de cobrancas/recobrancas, o que esta em aberto e o
        historico de cobrancas e verificacoes."""
        empresa = self._get_empresa(empresa_id)
        documentos = self.documento_repository.list_by_company(empresa_id)
        stats = {row["documento_empresa_id"]: row for row in self.cobranca_repository.document_stats(empresa_id)}

        periodo_atual = self._periodo_atual()
        status_atual: dict[int, str | None] = {}
        if periodo_atual and documentos:
            for row in self.status_repository.list_for_documents_and_periods(
                [d["id"] for d in documentos], [periodo_atual["id"]]
            ):
                status_atual[row["documento_empresa_id"]] = row["status"]

        documentos_ficha = []
        for documento in documentos:
            stat = stats.get(documento["id"], {})
            documentos_ficha.append(
                {
                    "documento_id": documento["id"],
                    "tipo": documento["nome_tipo"],
                    "nome_documento": documento["nome_documento"],
                    "meios_recebimento": documento.get("meios_recebimento"),
                    "observacao": documento.get("observacao"),
                    "status_mes_atual": status_atual.get(documento["id"]),
                    "cobrancas": int(stat.get("cobrancas") or 0),
                    "recobrancas": int(stat.get("recobrancas") or 0),
                    "ultima_cobranca_em": stat.get("ultima_cobranca_em"),
                }
            )

        cobrancas = self.listar_cobrancas(limite_historico, empresa_id=empresa_id)
        contatos = self.cobranca_repository.count_contacts(empresa_id)
        verificacoes = self.listar_verificacoes(limite_historico, empresa_id=empresa_id)
        historico = sorted(
            [{"tipo_evento": "cobranca", **c} for c in cobrancas]
            + [{"tipo_evento": "verificacao", **v} for v in verificacoes],
            key=lambda evento: (evento["realizada_em"] or "", evento["id"]),
            reverse=True,
        )[:limite_historico]

        return {
            "empresa": empresa,
            "competencia_atual": (
                format_competencia(periodo_atual["ano"], periodo_atual["mes"]) if periodo_atual else None
            ),
            "documentos": documentos_ficha,
            "em_aberto": self._em_aberto_da_empresa(empresa_id),
            "proximas_acoes": next(iter(self.proximas_acoes(empresa_id, somente_ativas=False)["empresas"]), None),
            "totais": {
                # Contatos (cada envio feito), separados entre cobranca e recobranca. A
                # contagem por documento fica em "documentos".
                "contatos": int(contatos["total"]),
                "cobrancas": int(contatos["total"]) - int(contatos["recobrancas"]),
                "recobrancas": int(contatos["recobrancas"]),
                "verificacoes": len(verificacoes),
                "ultima_cobranca_em": cobrancas[0]["realizada_em"] if cobrancas else None,
                "ultima_verificacao_em": verificacoes[0]["realizada_em"] if verificacoes else None,
            },
            "historico": historico,
        }

    def registro_documento(self, documento_id: int) -> dict:
        """Registro proprio de um documento, competencia por competencia: status, quantas
        vezes foi cobrado (e quando) e o que as verificacoes encontraram."""
        documento = self.documento_repository.get_by_id(documento_id)
        if not documento:
            raise ValidationError("Documento nao encontrado.")
        empresa = self._get_empresa(documento["empresa_id"])
        cobrancas = self.cobranca_repository.list_items_by_document(documento_id)
        verificacoes = self.verificacao_repository.list_items_by_document(documento_id)
        periodos = {p["id"]: p for p in self.periodo_repository.list_all()}
        status_rows = self.status_repository.list_for_documents_and_periods([documento_id], list(periodos))
        status_by_period = {row["periodo_id"]: row for row in status_rows}
        situacoes = {row["periodo_id"]: row for row in self.situacao_repository.list_for_documents([documento_id])}
        eventos = self.situacao_repository.list_events_by_document(documento_id)

        period_ids = (
            {row["periodo_id"] for row in status_rows if row.get("status")}
            | {row["periodo_id"] for row in cobrancas}
            | {row["periodo_id"] for row in verificacoes}
            | set(situacoes)
        )
        competencias = []
        for periodo_id in sorted(period_ids, key=lambda pid: (periodos[pid]["ano"], periodos[pid]["mes"]), reverse=True):
            periodo = periodos[periodo_id]
            cobrancas_mes = [c for c in cobrancas if c["periodo_id"] == periodo_id]
            status_row = status_by_period.get(periodo_id) or {}
            competencias.append(
                {
                    "periodo_id": periodo_id,
                    "competencia": format_competencia(periodo["ano"], periodo["mes"]),
                    "status": status_row.get("status"),
                    "status_atualizado_em": status_row.get("updated_at"),
                    "situacao": (situacoes.get(periodo_id) or {}).get("situacao"),
                    "situacao_motivo": (situacoes.get(periodo_id) or {}).get("motivo"),
                    "situacao_detalhe": (situacoes.get(periodo_id) or {}).get("detalhe"),
                    "aguardar_ate": (situacoes.get(periodo_id) or {}).get("aguardar_ate"),
                    "caminho": [
                        {
                            "em": ev["criado_em"],
                            "de": ev["situacao_anterior"],
                            "para": ev["situacao_nova"],
                            "motivo": ev["motivo"],
                            "detalhe": ev["detalhe"],
                            "por": ev["username"],
                            "rodada_id": ev["rodada_id"],
                        }
                        for ev in eventos
                        if ev["periodo_id"] == periodo_id
                    ],
                    "cobrancas": sum(1 for c in cobrancas_mes if c["sequencia"] == 1),
                    "recobrancas": sum(1 for c in cobrancas_mes if c["sequencia"] > 1),
                    "contatos": [
                        {
                            "realizada_em": c["realizada_em"],
                            "tipo": tipo_da_sequencia(c["sequencia"]),
                            "sequencia": c["sequencia"],
                            "canal": c["canal"],
                            "destinatario": c["destinatario"],
                            "por": c["username"],
                        }
                        for c in cobrancas_mes
                    ],
                    "verificacoes": [
                        {
                            "realizada_em": v["realizada_em"],
                            "fontes": v["fontes"],
                            "encontrado": bool(v["encontrado"]),
                            "resultado": v.get("resultado"),
                            "motivo": v.get("motivo"),
                            "baixa_feita": bool(v.get("baixa_feita")),
                            "baixa_erro": v.get("baixa_erro"),
                            "arquivo": v.get("arquivo"),
                            "onde": v["onde"],
                            "observacao": v["observacao"],
                            "por": v["username"],
                        }
                        for v in verificacoes
                        if v["periodo_id"] == periodo_id
                    ],
                }
            )
        return {
            "documento_id": documento_id,
            "empresa": {"codigo_empresa": empresa["codigo_empresa"], "nome_empresa": empresa["nome_empresa"]},
            "tipo": documento["nome_tipo"],
            "nome_documento": documento["nome_documento"],
            "meios_recebimento": documento.get("meios_recebimento"),
            "observacao": documento.get("observacao"),
            "total_cobrancas": sum(1 for c in cobrancas if c["sequencia"] == 1),
            "total_recobrancas": sum(1 for c in cobrancas if c["sequencia"] > 1),
            "competencias": competencias,
        }

    def listar_cobrancas(self, limite: int = 100, empresa_id: int | None = None) -> list[dict]:
        cobrancas = self.cobranca_repository.list_recent(limite, empresa_id=empresa_id)
        itens_por_cobranca: dict[int, list[dict]] = {}
        for item in self.cobranca_repository.list_items([c["id"] for c in cobrancas]):
            itens_por_cobranca.setdefault(item["cobranca_id"], []).append(
                {
                    "documento_id": item["documento_empresa_id"],
                    "nome_documento": item["nome_documento"],
                    "competencia": format_competencia(item["ano"], item["mes"]),
                    "sequencia": item["sequencia"],
                    "tipo": tipo_da_sequencia(item["sequencia"]),
                }
            )
        for cobranca in cobrancas:
            cobranca["itens"] = itens_por_cobranca.get(cobranca["id"], [])
            cobranca["recobranca"] = any(item["sequencia"] > 1 for item in cobranca["itens"])
        return cobrancas

    def listar_verificacoes(self, limite: int = 100, empresa_id: int | None = None) -> list[dict]:
        verificacoes = self.verificacao_repository.list_recent(limite, empresa_id=empresa_id)
        itens_por_verificacao: dict[int, list[dict]] = {}
        for item in self.verificacao_repository.list_items([v["id"] for v in verificacoes]):
            itens_por_verificacao.setdefault(item["verificacao_id"], []).append(
                {
                    "documento_id": item["documento_empresa_id"],
                    "periodo_id": item["periodo_id"],
                    "nome_documento": item["nome_documento"],
                    "competencia": format_competencia(item["ano"], item["mes"]),
                    "encontrado": bool(item["encontrado"]),
                    "resultado": item.get("resultado")
                    or (RESULTADO_RECEBIDO if item["encontrado"] else RESULTADO_NAO_ENCONTRADO),
                    "motivo": item.get("motivo"),
                    "baixa_feita": bool(item.get("baixa_feita")),
                    "baixa_erro": item.get("baixa_erro"),
                    "arquivo": item.get("arquivo"),
                    "onde": item["onde"],
                    "observacao": item["observacao"],
                }
            )
        for verificacao in verificacoes:
            verificacao["itens"] = itens_por_verificacao.get(verificacao["id"], [])
        return verificacoes

    def fila(self, somente_ativas: bool = True) -> list[dict]:
        """Empresas com documentos em aberto hoje, com o que cada documento ja recebeu de
        cobranca e como/onde a empresa envia os documentos - tudo que e preciso para
        decidir entre verificar, cobrar ou recobrar."""
        queue = self.collection_service.queue_snapshot(active_only=somente_ativas)
        document_ids = [doc["documento_id"] for item in queue["items"] for doc in item["documents"]]
        counts = {
            (row["documento_empresa_id"], row["periodo_id"]): row
            for row in self.cobranca_repository.counts_by_document_period(document_ids)
        }
        empresas = {e["id"]: e for e in self.empresa_repository.list_by_ids([i["empresa_id"] for i in queue["items"]])}

        fila = []
        for item in queue["items"]:
            empresa = empresas.get(item["empresa_id"], {})
            documentos = []
            for doc in item["documents"]:
                count = counts.get((doc["documento_id"], doc["periodo_id"]), {})
                documentos.append(
                    {
                        "documento_id": doc["documento_id"],
                        "periodo_id": doc["periodo_id"],
                        "nome_documento": doc["nome_documento"],
                        "competencia": doc["periodo_label"].split(" - ", 1)[0],
                        "vezes_cobrado": int(count.get("vezes") or 0),
                        "ultima_cobranca_em": count.get("ultima_cobranca_em"),
                    }
                )
            ultimas = [d["ultima_cobranca_em"] for d in documentos if d["ultima_cobranca_em"]]
            fila.append(
                {
                    "empresa_id": item["empresa_id"],
                    "codigo_empresa": item["codigo_empresa"],
                    "nome_empresa": item["nome_empresa"],
                    "fase": item["phase_label"],
                    "em_atraso": item["phase_key"] == CollectionService.PHASE_EM_ATRASO,
                    "canais_recebimento": parse_delivery_methods(empresa.get("canais_recebimento")),
                    "emails_origem_documentos": empresa.get("emails_origem_documentos"),
                    "instrucoes_busca": empresa.get("instrucoes_busca"),
                    "email_contato": empresa.get("email_contato"),
                    "nome_contato": empresa.get("nome_contato"),
                    "documentos": documentos,
                    "nunca_cobrados": sum(1 for d in documentos if d["vezes_cobrado"] == 0),
                    "ultima_cobranca_em": max(ultimas) if ultimas else None,
                }
            )
        return fila

    # Auxiliares ---------------------------------------------------------------------

    def _itens_em_aberto(self, empresa_id: int) -> list[tuple[int, int]]:
        return [
            (doc["documento_id"], doc["periodo_id"])
            for periodo in self._em_aberto_da_empresa(empresa_id, raw=True)
            for doc in periodo["documents"]
        ]

    def _em_aberto_da_empresa(self, empresa_id: int, raw: bool = False) -> list[dict]:
        queue = self.collection_service.queue_snapshot(active_only=False)
        item = next((i for i in queue["items"] if i["empresa_id"] == empresa_id), None)
        if item is None:
            return []
        if raw:
            return item["period_items"]
        return [
            {
                "competencia": period_item["periodo_label"].split(" - ", 1)[0],
                "fase": period_item["phase_label"],
                "documentos": [
                    {"documento_id": doc["documento_id"], "nome_documento": doc["nome_documento"]}
                    for doc in period_item["documents"]
                ],
            }
            for period_item in item["period_items"]
        ]

    def _validate_items(
        self, empresa: dict, pares: list[tuple[int, int]]
    ) -> tuple[dict[int, dict], dict[int, dict]]:
        documentos = {d["id"]: d for d in self.documento_repository.list_by_ids([p[0] for p in pares])}
        periodos: dict[int, dict] = {}
        for documento_id, periodo_id in pares:
            documento = documentos.get(documento_id)
            if documento is None or documento["empresa_id"] != empresa["id"]:
                raise ValidationError(
                    f'O documento {documento_id} nao pertence a empresa "{empresa["nome_empresa"]}".'
                )
            if periodo_id not in periodos:
                periodo = self.periodo_repository.get_by_id(periodo_id)
                if not periodo:
                    raise ValidationError("Competencia nao encontrada.")
                periodos[periodo_id] = periodo
        return documentos, periodos

    def _periodo_atual(self) -> dict | None:
        hoje = date.today()
        return self.periodo_repository.get_by_year_month(hoje.year, hoje.month)

    def _get_empresa(self, empresa_id: int) -> dict:
        empresa = self.empresa_repository.get_by_id(empresa_id)
        if not empresa:
            raise ValidationError("Empresa nao encontrada.")
        return empresa

    @staticmethod
    def _dedupe(pares: list[tuple[int, int]]) -> list[tuple[int, int]]:
        return list(dict.fromkeys((int(d), int(p)) for d, p in pares))

    @staticmethod
    def _normalize_text(value) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    def _user_id(self) -> int | None:
        return self.session_service.get_user_id() if self.session_service else None

    def _actor_name(self) -> str:
        return self.session_service.get_username() if self.session_service else "Sistema"

    def _log(self, acao: str, entidade: str, entidade_id: int, descricao: str, empresa: dict) -> None:
        if self.audit_service:
            self.audit_service.log(
                acao, entidade, entidade_id, descricao, empresa_id=empresa["id"], empresa_nome=empresa["nome_empresa"]
            )
