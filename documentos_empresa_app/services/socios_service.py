"""Socios das empresas e a conferencia das retiradas acima de R$ 50 mil no mes.

Regra (Lei 15.270/2025, desde janeiro de 2026): quando a mesma empresa paga mais de R$ 50 mil
no mes ao mesmo socio pessoa fisica, retem 10% de IR sobre o total do mes (nao so sobre o que
passou). Os pagamentos do mes se somam; o limite e por par empresa-socio.

O Claude le os extratos que chegaram, acha o que saiu da conta da empresa para cada socio e
registra aqui (registrar_revisao). O sistema soma o mes inteiro, de todos os extratos da
empresa, e abre um alerta quando o total passa do limite. As pessoas resolvem na tela."""

from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import re

from documentos_empresa_app.database.repositories import EmpresaRepository, PeriodoRepository, SocioRepository
from documentos_empresa_app.services.audit_service import AuditService
from documentos_empresa_app.services.session_service import SessionService
from documentos_empresa_app.utils.common import ValidationError

LIMITE_CENTAVOS = 50_000_00  # R$ 50.000,00 por mes, da mesma empresa ao mesmo socio
ALIQUOTA_RETENCAO = Decimal("0.10")

RESULTADO_REVISADO = "revisado"
RESULTADO_NAO_DEU = "nao_deu"
RESULTADOS_REVISAO = (RESULTADO_REVISADO, RESULTADO_NAO_DEU)

STATUS_ABERTO = "aberto"
STATUS_RESOLVIDO = "resolvido"
STATUS_DESCARTADO = "descartado"
STATUS_ALERTA = (STATUS_ABERTO, STATUS_RESOLVIDO, STATUS_DESCARTADO)
STATUS_LABELS = {
    STATUS_ABERTO: "A resolver",
    STATUS_RESOLVIDO: "Resolvido",
    STATUS_DESCARTADO: "Descartado",
}


# CPF ----------------------------------------------------------------------------------


def normalizar_cpf(raw) -> str:
    """So os 11 digitos. Aceita com ou sem pontuacao; recusa CPF invalido."""
    digitos = re.sub(r"\D", "", str(raw or ""))
    if len(digitos) < 11 and digitos:
        digitos = digitos.zfill(11)  # planilha que perdeu os zeros do comeco
    if len(digitos) != 11 or digitos == digitos[0] * 11:
        raise ValidationError(f'CPF invalido: "{raw}". Informe os 11 digitos.')
    for tamanho in (9, 10):
        soma = sum(int(digitos[i]) * (tamanho + 1 - i) for i in range(tamanho))
        verificador = (soma * 10) % 11 % 10
        if verificador != int(digitos[tamanho]):
            raise ValidationError(f'CPF invalido: "{raw}" (digito verificador nao confere).')
    return digitos


def formatar_cpf(cpf: str | None) -> str:
    digitos = re.sub(r"\D", "", str(cpf or ""))
    if len(digitos) != 11:
        return str(cpf or "")
    return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"


# Valores --------------------------------------------------------------------------------


def para_centavos(valor) -> int:
    """Valor em reais -> centavos. Aceita numero (55000.5) ou texto ("55.000,50", "R$ 1.234,56",
    "55000.50"). Sempre positivo: o que importa e quanto saiu para o socio."""
    if isinstance(valor, bool):
        raise ValidationError(f"Valor invalido: {valor!r}.")
    if isinstance(valor, (int, float, Decimal)):
        numero = Decimal(str(valor))
    else:
        texto = re.sub(r"[^\d,.\-]", "", str(valor or ""))
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        elif texto.count(".") > 1:
            texto = texto.replace(".", "")
        try:
            numero = Decimal(texto)
        except InvalidOperation:
            raise ValidationError(f'Valor invalido: "{valor}". Use, por exemplo, 55000.00 ou "55.000,00".') from None
    centavos = int((abs(numero) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if centavos <= 0:
        raise ValidationError(f'Valor invalido: "{valor}" (tem que ser maior que zero).')
    return centavos


def formatar_reais(centavos: int | None) -> str:
    valor = Decimal(int(centavos or 0)) / 100
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def retencao_estimada(centavos: int) -> int:
    return int((Decimal(int(centavos)) * ALIQUOTA_RETENCAO).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class SociosService:
    def __init__(
        self,
        socio_repository: SocioRepository,
        empresa_repository: EmpresaRepository,
        periodo_repository: PeriodoRepository,
        audit_service: AuditService | None = None,
        session_service: SessionService | None = None,
    ) -> None:
        self.socio_repository = socio_repository
        self.empresa_repository = empresa_repository
        self.periodo_repository = periodo_repository
        self.audit_service = audit_service
        self.session_service = session_service

    # Cadastro dos socios ---------------------------------------------------------------

    def listar_socios(self, empresa_id: int | None = None, somente_ativos: bool = False) -> list[dict]:
        return [self._decorar_socio(s) for s in self.socio_repository.list_socios(empresa_id, somente_ativos)]

    def obter_socio(self, socio_id: int) -> dict:
        socio = self.socio_repository.get_socio(int(socio_id))
        if not socio:
            raise ValidationError("Socio nao encontrado.")
        return self._decorar_socio(socio)

    def cadastrar_socio(self, empresa_id: int, nome: str, cpf, observacao: str | None = None) -> int:
        empresa = self._empresa(empresa_id)
        nome = self._nome(nome)
        cpf = normalizar_cpf(cpf)
        if self.socio_repository.get_socio_by_cpf(empresa["id"], cpf):
            raise ValidationError(f"A empresa {empresa['codigo_empresa']} ja tem um socio com o CPF {formatar_cpf(cpf)}.")
        socio_id = self.socio_repository.create_socio(empresa["id"], nome, cpf, self._texto(observacao))
        self._log("SOCIO_CADASTRADO", socio_id, f"Socio {nome} cadastrado.", empresa)
        return socio_id

    def atualizar_socio(
        self, socio_id: int, nome: str, cpf, ativo: bool = True, observacao: str | None = None
    ) -> None:
        socio = self.obter_socio(socio_id)
        nome = self._nome(nome)
        cpf = normalizar_cpf(cpf)
        outro = self.socio_repository.get_socio_by_cpf(socio["empresa_id"], cpf)
        if outro and outro["id"] != socio["id"]:
            raise ValidationError(f"A empresa ja tem outro socio com o CPF {formatar_cpf(cpf)}.")
        self.socio_repository.update_socio(socio["id"], nome, cpf, bool(ativo), self._texto(observacao))
        self._log("SOCIO_ALTERADO", socio["id"], f"Socio {nome} alterado.", self._empresa(socio["empresa_id"]))

    def excluir_socio(self, socio_id: int) -> None:
        socio = self.obter_socio(socio_id)
        self.socio_repository.delete_socio(socio["id"])
        self._log("SOCIO_EXCLUIDO", socio["id"], f"Socio {socio['nome']} excluido.", self._empresa(socio["empresa_id"]))

    def importar_socios(self, linhas: list[dict]) -> dict:
        """Cadastra (ou atualiza o nome de) varios socios de uma vez. Cada linha:
        {codigo_empresa, nome, cpf}. Linhas com problema ficam em 'erros' e nao param as outras."""
        criados = atualizados = 0
        erros: list[str] = []
        for numero, linha in enumerate(linhas, start=1):
            try:
                codigo = str(linha.get("codigo_empresa") or "").strip()
                if codigo.endswith(".0"):
                    codigo = codigo[:-2]  # planilha que guardou o codigo como numero
                empresa = self.empresa_repository.get_by_code(int(codigo)) if codigo.isdigit() else None
                if not empresa:
                    raise ValidationError(f'empresa "{codigo}" nao encontrada')
                nome = self._nome(linha.get("nome"))
                cpf = normalizar_cpf(linha.get("cpf"))
                existente = self.socio_repository.get_socio_by_cpf(empresa["id"], cpf)
                if existente:
                    if existente["nome"] != nome:
                        self.socio_repository.update_socio(
                            existente["id"], nome, cpf, bool(existente["ativo"]), existente.get("observacao")
                        )
                        atualizados += 1
                else:
                    self.socio_repository.create_socio(empresa["id"], nome, cpf, None)
                    criados += 1
            except ValidationError as exc:
                erros.append(f"Linha {numero}: {exc}")
        if criados or atualizados:
            self._log("SOCIOS_IMPORTADOS", None, f"Socios importados: {criados} novos, {atualizados} atualizados.")
        return {"criados": criados, "atualizados": atualizados, "erros": erros}

    def importar_planilha(self, caminho: str | Path) -> dict:
        """Planilha (.xlsx) ou CSV com as colunas codigo da empresa, nome e CPF (a primeira linha
        e o cabecalho; a ordem das colunas pode variar)."""
        return self.importar_socios(ler_planilha_socios(caminho))

    # Revisao dos extratos -------------------------------------------------------------

    def registrar_revisao(
        self,
        empresa_id: int,
        periodo_id: int,
        pagamentos: list[dict] | None,
        *,
        documento_id: int | None = None,
        arquivo: str | None = None,
        resultado: str = RESULTADO_REVISADO,
        resumo: str | None = None,
        rodada_id: int | None = None,
    ) -> dict:
        """O que o Claude achou num extrato. pagamentos: [{cpf (ou socio_id), valor, data,
        descricao}] - so o que SAIU da conta da empresa para o socio. Lista vazia = revisou e nao
        achou nada. resultado 'nao_deu' = nao conseguiu ler o extrato (diga o motivo em resumo).
        Revisar de novo o mesmo extrato substitui a revisao anterior. Devolve o total do mes por
        socio e os alertas da competencia."""
        empresa = self._empresa(empresa_id)
        periodo = self._periodo(periodo_id)
        resultado = str(resultado or "").strip().lower()
        if resultado not in RESULTADOS_REVISAO:
            raise ValidationError(f"Resultado invalido. Use um de: {', '.join(RESULTADOS_REVISAO)}.")
        arquivo = self._texto(arquivo)
        resumo = self._texto(resumo)
        if resultado == RESULTADO_NAO_DEU and not resumo:
            raise ValidationError("Diga em 'resumo' por que nao deu para revisar o extrato.")
        socios = {s["cpf"]: s for s in self.socio_repository.list_socios(empresa["id"])}
        por_id = {s["id"]: s for s in socios.values()}
        if not socios:
            raise ValidationError(
                f"A empresa {empresa['codigo_empresa']} nao tem socio cadastrado. Cadastre os socios antes de revisar."
            )

        itens = []
        for pagamento in pagamentos or []:
            socio = None
            if pagamento.get("socio_id") is not None:
                socio = por_id.get(int(pagamento["socio_id"]))
            elif pagamento.get("cpf"):
                socio = socios.get(normalizar_cpf(pagamento["cpf"]))
            if socio is None:
                raise ValidationError(
                    f"Pagamento para quem nao e socio cadastrado da empresa {empresa['codigo_empresa']}: "
                    f"{pagamento.get('cpf') or pagamento.get('socio_id')}. Use o CPF de 'socios' da empresa."
                )
            itens.append(
                (
                    socio["id"],
                    self._texto(pagamento.get("data")),
                    self._texto(pagamento.get("descricao")),
                    para_centavos(pagamento.get("valor")),
                )
            )
        if resultado == RESULTADO_NAO_DEU and itens:
            raise ValidationError("Revisao que nao deu certo nao leva pagamentos.")

        with self.socio_repository.db_manager.connect():
            self.socio_repository.delete_revisoes_do_extrato(empresa["id"], periodo["id"], documento_id, arquivo)
            revisao_id = self.socio_repository.create_revisao(
                empresa["id"], periodo["id"], documento_id, arquivo, resultado, resumo, self._user_id(), rodada_id
            )
            for socio_id, data, descricao, valor in itens:
                self.socio_repository.add_movimento(revisao_id, socio_id, data, descricao, valor)
            alertas = self._recalcular_alertas(empresa["id"], periodo["id"])
            totais = self.socio_repository.totais_por_socio(empresa["id"], periodo["id"])

        competencia = f"{periodo['mes']:02d}/{periodo['ano']}"
        self._log(
            "EXTRATO_REVISADO_SOCIOS",
            revisao_id,
            f"Extrato revisado (socios) em {competencia}: {len(itens)} pagamento(s) a socios.",
            empresa,
            periodo,
        )
        return {
            "revisao_id": revisao_id,
            "empresa": f"{empresa['codigo_empresa']} - {empresa['nome_empresa']}",
            "competencia": competencia,
            "pagamentos_registrados": len(itens),
            "total_do_mes_por_socio": [
                {
                    "socio": por_id[socio_id]["nome"],
                    "cpf": formatar_cpf(por_id[socio_id]["cpf"]),
                    "total": formatar_reais(total),
                    "passou_do_limite": total > LIMITE_CENTAVOS,
                }
                for socio_id, total in sorted(totais.items(), key=lambda kv: -kv[1])
                if socio_id in por_id
            ],
            "alertas": [self._decorar_alerta(a) for a in alertas],
        }

    def _recalcular_alertas(self, empresa_id: int, periodo_id: int) -> list[dict]:
        """Soma o mes de cada socio (todos os extratos revisados da empresa) e abre, atualiza ou
        tira o alerta. Alerta resolvido cujo total mudou volta a ficar a resolver."""
        totais = self.socio_repository.totais_por_socio(empresa_id, periodo_id)
        existentes = {a["socio_id"]: a for a in self.socio_repository.list_alertas_da_competencia(empresa_id, periodo_id)}
        for socio_id, total in totais.items():
            alerta = existentes.pop(socio_id, None)
            if total > LIMITE_CENTAVOS:
                if alerta is None:
                    self.socio_repository.create_alerta(empresa_id, periodo_id, socio_id, total)
                elif int(alerta["total_centavos"]) != total:
                    self.socio_repository.update_alerta_total(alerta["id"], total, reabrir=alerta["status"] != STATUS_ABERTO)
            elif alerta is not None:
                self._tirar_alerta(alerta, total)
        for alerta in existentes.values():  # socio que deixou de ter pagamento no mes
            self._tirar_alerta(alerta, 0)
        return [
            a for a in self.socio_repository.list_alertas(periodo_id=periodo_id) if a["empresa_id"] == empresa_id
        ]

    def _tirar_alerta(self, alerta: dict, total: int) -> None:
        if alerta["status"] == STATUS_ABERTO:
            self.socio_repository.delete_alerta(alerta["id"])
        else:  # ja foi tratado: fica no historico, com o total novo
            self.socio_repository.update_alerta_total(alerta["id"], total, reabrir=False)

    # Consultas --------------------------------------------------------------------------

    def extratos_para_revisar(self, periodo_id: int, incluir_revisados: bool = False) -> dict:
        """Extratos que chegaram (Recebido) na competencia, por empresa, com os socios da empresa
        e se o extrato ja foi revisado. Empresas com extrato e sem socio cadastrado vem a parte."""
        periodo = self._periodo(periodo_id)
        revisoes: dict[tuple, dict] = {}
        for revisao in self.socio_repository.list_revisoes(periodo_id=periodo["id"]):
            revisoes.setdefault((revisao["empresa_id"], revisao["documento_id"]), revisao)
        socios_por_empresa: dict[int, list[dict]] = {}
        for socio in self.socio_repository.list_socios(somente_ativos=True):
            socios_por_empresa.setdefault(socio["empresa_id"], []).append(socio)

        empresas: dict[int, dict] = {}
        sem_socios: dict[int, dict] = {}
        pendentes = revisados = 0
        for extrato in self.socio_repository.list_extratos_recebidos(periodo["id"]):
            socios = socios_por_empresa.get(extrato["empresa_id"])
            if not socios:
                sem = sem_socios.setdefault(
                    extrato["empresa_id"],
                    {"codigo_empresa": extrato["codigo_empresa"], "nome_empresa": extrato["nome_empresa"], "extratos": 0},
                )
                sem["extratos"] += 1
                continue
            revisao = revisoes.get((extrato["empresa_id"], extrato["documento_id"]))
            if revisao:
                revisados += 1
            else:
                pendentes += 1
            if revisao and not incluir_revisados:
                continue
            empresa = empresas.setdefault(
                extrato["empresa_id"],
                {
                    "empresa_id": extrato["empresa_id"],
                    "codigo_empresa": extrato["codigo_empresa"],
                    "nome_empresa": extrato["nome_empresa"],
                    "pasta_documentos": extrato.get("diretorio_documentos"),
                    "socios": [{"socio_id": s["id"], "nome": s["nome"], "cpf": formatar_cpf(s["cpf"])} for s in socios],
                    "extratos": [],
                },
            )
            empresa["extratos"].append(
                {
                    "documento_id": extrato["documento_id"],
                    "tipo": extrato["nome_tipo"],
                    "nome_documento": extrato["nome_documento"],
                    "arquivo": extrato.get("arquivo"),
                    "revisado": bool(revisao),
                    "revisado_em": revisao["revisado_em"] if revisao else None,
                    "resultado": revisao["resultado"] if revisao else None,
                }
            )
        return {
            "competencia": f"{periodo['mes']:02d}/{periodo['ano']}",
            "limite": formatar_reais(LIMITE_CENTAVOS),
            "extratos_pendentes": pendentes,
            "extratos_revisados": revisados,
            "empresas": list(empresas.values()),
            "empresas_sem_socio_cadastrado": list(sem_socios.values()),
        }

    def listar_revisoes(self, periodo_id: int | None = None, empresa_id: int | None = None) -> list[dict]:
        revisoes = self.socio_repository.list_revisoes(periodo_id, empresa_id)
        for revisao in revisoes:
            revisao["competencia"] = f"{revisao['mes']:02d}/{revisao['ano']}"
            revisao["total_formatado"] = formatar_reais(revisao["total_centavos"])
        return revisoes

    def listar_alertas(self, periodo_id: int | None = None, status: str | None = None) -> list[dict]:
        if status and status not in STATUS_ALERTA:
            raise ValidationError(f"Situacao invalida. Use um de: {', '.join(STATUS_ALERTA)}.")
        return [self._decorar_alerta(a) for a in self.socio_repository.list_alertas(periodo_id, status)]

    def obter_alerta(self, alerta_id: int, com_pagamentos: bool = True) -> dict:
        alerta = self.socio_repository.get_alerta(int(alerta_id))
        if not alerta:
            raise ValidationError("Alerta nao encontrado.")
        alerta = self._decorar_alerta(alerta)
        if com_pagamentos:
            alerta["pagamentos"] = [
                {
                    "data": m.get("data"),
                    "descricao": m.get("descricao"),
                    "valor": formatar_reais(m["valor_centavos"]),
                    "valor_centavos": m["valor_centavos"],
                    "arquivo": m.get("arquivo"),
                    "extrato": m.get("nome_documento"),
                }
                for m in self.socio_repository.list_movimentos(alerta["empresa_id"], alerta["periodo_id"], alerta["socio_id"])
            ]
        return alerta

    def resolver_alerta(self, alerta_id: int, status: str, observacao: str | None = None) -> dict:
        status = str(status or "").strip().lower()
        if status not in STATUS_ALERTA:
            raise ValidationError(f"Situacao invalida. Use um de: {', '.join(STATUS_ALERTA)}.")
        alerta = self.obter_alerta(alerta_id, com_pagamentos=False)
        self.socio_repository.set_alerta_status(alerta["id"], status, self._texto(observacao), self._user_id())
        self._log(
            "ALERTA_SOCIO_" + status.upper(),
            alerta["id"],
            f"Retirada de {alerta['nome_socio']} em {alerta['competencia']} ({alerta['total']}): {STATUS_LABELS[status].lower()}.",
            self._empresa(alerta["empresa_id"]),
        )
        return self.obter_alerta(alerta["id"], com_pagamentos=False)

    def contar_alertas_abertos(self) -> int:
        return len(self.socio_repository.list_alertas(status=STATUS_ABERTO))

    # Apoio --------------------------------------------------------------------------------

    @staticmethod
    def _decorar_socio(socio: dict) -> dict:
        socio["cpf_formatado"] = formatar_cpf(socio["cpf"])
        socio["ativo"] = bool(socio.get("ativo"))
        return socio

    @staticmethod
    def _decorar_alerta(alerta: dict) -> dict:
        total = int(alerta["total_centavos"])
        alerta["competencia"] = f"{alerta['mes']:02d}/{alerta['ano']}"
        alerta["total"] = formatar_reais(total)
        alerta["retencao_estimada"] = formatar_reais(retencao_estimada(total))
        alerta["acima_do_limite"] = formatar_reais(max(total - LIMITE_CENTAVOS, 0))
        alerta["cpf_formatado"] = formatar_cpf(alerta.get("cpf"))
        alerta["status_label"] = STATUS_LABELS.get(alerta["status"], alerta["status"])
        return alerta

    def _empresa(self, empresa_id: int) -> dict:
        empresa = self.empresa_repository.get_by_id(int(empresa_id))
        if not empresa:
            raise ValidationError("Empresa nao encontrada.")
        return empresa

    def _periodo(self, periodo_id: int) -> dict:
        periodo = self.periodo_repository.get_by_id(int(periodo_id))
        if not periodo:
            raise ValidationError("Competencia nao encontrada.")
        return periodo

    @staticmethod
    def _nome(nome) -> str:
        nome = " ".join(str(nome or "").split())
        if not nome:
            raise ValidationError("Informe o nome do socio.")
        return nome

    @staticmethod
    def _texto(valor) -> str | None:
        texto = str(valor or "").strip()
        return texto or None

    def _user_id(self) -> int | None:
        return self.session_service.get_user_id() if self.session_service else None

    def _log(self, acao: str, entidade_id: int | None, descricao: str, empresa: dict | None = None, periodo: dict | None = None) -> None:
        if not self.audit_service:
            return
        self.audit_service.log(
            acao,
            "socio",
            entidade_id,
            descricao,
            empresa_id=empresa["id"] if empresa else None,
            empresa_nome=empresa["nome_empresa"] if empresa else None,
            periodo_ano=periodo["ano"] if periodo else None,
            periodo_mes=periodo["mes"] if periodo else None,
        )


# Planilha de socios -------------------------------------------------------------------

_COLUNAS = {
    "codigo_empresa": ("codigo", "código", "cod", "empresa", "codigo empresa", "código empresa", "codigo_empresa"),
    "nome": ("nome", "socio", "sócio", "nome do socio", "nome do sócio"),
    "cpf": ("cpf",),
}


def _coluna(cabecalho: str) -> str | None:
    texto = " ".join(str(cabecalho or "").strip().casefold().replace("_", " ").split())
    for campo, nomes in _COLUNAS.items():
        if texto in {n.replace("_", " ") for n in nomes}:
            return campo
    return None


def ler_planilha_socios(caminho: str | Path) -> list[dict]:
    caminho = Path(caminho)
    if not caminho.exists():
        raise ValidationError(f"Arquivo nao encontrado: {caminho}")
    if caminho.suffix.lower() in (".xlsx", ".xlsm"):
        try:
            from openpyxl import load_workbook
        except ImportError as exc:  # pragma: no cover - openpyxl vem com o sistema
            raise ValidationError("A biblioteca openpyxl nao esta instalada.") from exc
        planilha = load_workbook(caminho, read_only=True, data_only=True).active
        linhas = [["" if v is None else str(v) for v in linha] for linha in planilha.iter_rows(values_only=True)]
    else:
        texto = caminho.read_text(encoding="utf-8-sig", errors="replace")
        separador = ";" if texto.count(";") >= texto.count(",") else ","
        linhas = list(csv.reader(texto.splitlines(), delimiter=separador))
    linhas = [linha for linha in linhas if any(str(c).strip() for c in linha)]
    if not linhas:
        raise ValidationError("A planilha esta vazia.")
    mapa = {i: _coluna(c) for i, c in enumerate(linhas[0])}
    if not {"codigo_empresa", "nome", "cpf"}.issubset(set(mapa.values())):
        raise ValidationError(
            "A primeira linha da planilha precisa ter as colunas: Codigo (da empresa), Nome e CPF."
        )
    resultado = []
    for linha in linhas[1:]:
        registro = {campo: str(linha[i]).strip() for i, campo in mapa.items() if campo and i < len(linha)}
        resultado.append(registro)
    return resultado
