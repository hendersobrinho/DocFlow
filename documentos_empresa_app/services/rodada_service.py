from __future__ import annotations

from datetime import datetime, timedelta, timezone

from documentos_empresa_app.database.repositories import EmpresaRepository, RodadaRepository
from documentos_empresa_app.services.audit_service import AuditService
from documentos_empresa_app.services.session_service import SessionService
from documentos_empresa_app.utils.common import ValidationError

STATUS_EM_ANDAMENTO = "em_andamento"
STATUS_CONCLUIDA = "concluida"
STATUS_COM_FALHAS = "concluida_com_falhas"
STATUS_INTERROMPIDA = "interrompida"
STATUS_LABELS = {
    STATUS_EM_ANDAMENTO: "Em andamento",
    STATUS_CONCLUIDA: "Concluída",
    STATUS_COM_FALHAS: "Concluída com falhas",
    STATUS_INTERROMPIDA: "Interrompida",
}
TIPOS_OCORRENCIA = ("falha", "aviso", "info")
# Uma rodada que ficou "em andamento" por mais tempo que isso parou no meio (o Claude
# caiu, a conexao fechou...). Ela aparece como interrompida.
LIMITE_RODADA_HORAS = 6
# Por quantos dias uma rodada com problema continua em "Precisa de atencao".
DIAS_ALERTA_RODADA = 7


class RodadaService:
    """Cada passada do Claude pelas cobrancas e uma rodada: quando comecou e terminou, o
    que foi feito (verificacoes e cobrancas ficam ligadas a ela) e o que deu errado."""

    def __init__(
        self,
        rodada_repository: RodadaRepository,
        empresa_repository: EmpresaRepository,
        audit_service: AuditService | None = None,
        session_service: SessionService | None = None,
    ) -> None:
        self.rodada_repository = rodada_repository
        self.empresa_repository = empresa_repository
        self.audit_service = audit_service
        self.session_service = session_service

    def iniciar(self, origem: str = "claude") -> dict:
        origem = str(origem or "").strip() or "claude"
        rodada_id = self.rodada_repository.create(origem, self._user_id())
        self._log("RODADA_INICIADA", rodada_id, f"Rodada {rodada_id} iniciada ({origem}).")
        return self.obter(rodada_id)

    def registrar_ocorrencia(self, rodada_id: int, tipo: str, mensagem: str, empresa_id: int | None = None) -> dict:
        tipo = str(tipo or "").strip().lower()
        if tipo not in TIPOS_OCORRENCIA:
            raise ValidationError(f"Tipo de ocorrencia invalido. Use um de: {', '.join(TIPOS_OCORRENCIA)}.")
        mensagem = str(mensagem or "").strip()
        if not mensagem:
            raise ValidationError("Descreva a ocorrencia.")
        rodada = self._get(rodada_id)
        if rodada["status"] != STATUS_EM_ANDAMENTO:
            raise ValidationError(f"A rodada {rodada_id} ja foi finalizada.")
        if empresa_id is not None and not self.empresa_repository.get_by_id(empresa_id):
            raise ValidationError("Empresa nao encontrada.")
        ocorrencia_id = self.rodada_repository.add_ocorrencia(rodada_id, empresa_id, tipo, mensagem)
        return {"ocorrencia_id": ocorrencia_id, "rodada_id": rodada_id, "tipo": tipo}

    def finalizar(self, rodada_id: int, resumo: str | None = None) -> dict:
        rodada = self._get(rodada_id)
        if rodada["status"] != STATUS_EM_ANDAMENTO:
            raise ValidationError(f"A rodada {rodada_id} ja foi finalizada.")
        status = STATUS_COM_FALHAS if int(rodada["falhas"] or 0) else STATUS_CONCLUIDA
        resumo = str(resumo or "").strip() or None
        self.rodada_repository.finish(rodada_id, status, resumo)
        self._log("RODADA_FINALIZADA", rodada_id, f"Rodada {rodada_id} finalizada: {STATUS_LABELS[status].lower()}.")
        return self.obter(rodada_id)

    def obter(self, rodada_id: int) -> dict:
        rodada = self._decorate(self._get(rodada_id))
        rodada["ocorrencias"] = self.rodada_repository.list_ocorrencias([rodada_id])
        return rodada

    def listar(self, limite: int = 30, com_ocorrencias: bool = True) -> list[dict]:
        rodadas = [self._decorate(r) for r in self.rodada_repository.list_recent(limite)]
        if com_ocorrencias and rodadas:
            por_rodada: dict[int, list[dict]] = {}
            for ocorrencia in self.rodada_repository.list_ocorrencias([r["id"] for r in rodadas]):
                por_rodada.setdefault(ocorrencia["rodada_id"], []).append(ocorrencia)
            for rodada in rodadas:
                rodada["ocorrencias"] = por_rodada.get(rodada["id"], [])
        return rodadas

    def rodadas_com_problema(self, limite: int = 30, dias: int = DIAS_ALERTA_RODADA) -> list[dict]:
        """Rodadas recentes que falharam ou pararam no meio (as antigas ficam so no historico)."""
        corte = (datetime.now(timezone.utc) - timedelta(days=dias)).strftime("%Y-%m-%d %H:%M:%S")
        return [
            r
            for r in self.listar(limite)
            if r["status_efetivo"] in (STATUS_COM_FALHAS, STATUS_INTERROMPIDA) and str(r["iniciada_em"]) >= corte
        ]

    def _decorate(self, rodada: dict) -> dict:
        status = rodada["status"]
        if status == STATUS_EM_ANDAMENTO and self._is_stale(rodada.get("iniciada_em")):
            status = STATUS_INTERROMPIDA
        rodada["status_efetivo"] = status
        rodada["status_label"] = STATUS_LABELS[status]
        return rodada

    @staticmethod
    def _is_stale(iniciada_em) -> bool:
        try:
            inicio = datetime.strptime(str(iniciada_em)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return False
        return datetime.now(timezone.utc) - inicio > timedelta(hours=LIMITE_RODADA_HORAS)

    def _get(self, rodada_id: int) -> dict:
        rodada = self.rodada_repository.get(int(rodada_id))
        if not rodada:
            raise ValidationError("Rodada nao encontrada.")
        return rodada

    def _user_id(self) -> int | None:
        return self.session_service.get_user_id() if self.session_service else None

    def _log(self, acao: str, rodada_id: int, descricao: str) -> None:
        if self.audit_service:
            self.audit_service.log(acao, "rodada", rodada_id, descricao)
