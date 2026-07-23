from __future__ import annotations

from documentos_empresa_app.database.repositories import (
    DocumentoRepository,
    EmpresaRepository,
    PeriodoRepository,
    StatusRepository,
)
from documentos_empresa_app.utils.common import (
    AUTO_STATUS_NAO_COBRAR,
    ValidationError,
    build_chargeable_closure_key_map,
    format_period_label,
    is_chargeable_period,
    month_key,
    normalize_type_occurrence_rule,
)


class PanoramaService:
    SITUATION_SEM_DOCUMENTOS = "sem_documentos"
    SITUATION_SEM_COBRANCA = "sem_cobranca"
    SITUATION_NAO_INICIADA = "nao_iniciada"
    SITUATION_EM_ANDAMENTO = "em_andamento"
    SITUATION_COM_PENDENCIA = "com_pendencia"
    SITUATION_CONCLUIDA = "concluida"

    SITUATION_LABELS = {
        SITUATION_SEM_DOCUMENTOS: "Sem documentos",
        SITUATION_SEM_COBRANCA: "Sem cobranca",
        SITUATION_NAO_INICIADA: "Nao iniciada",
        SITUATION_EM_ANDAMENTO: "Em andamento",
        SITUATION_COM_PENDENCIA: "Com pendencia",
        SITUATION_CONCLUIDA: "Concluida",
    }

    SITUATION_PRIORITIES = {
        SITUATION_COM_PENDENCIA: 0,
        SITUATION_EM_ANDAMENTO: 1,
        SITUATION_NAO_INICIADA: 2,
        SITUATION_SEM_DOCUMENTOS: 3,
        SITUATION_CONCLUIDA: 4,
        SITUATION_SEM_COBRANCA: 5,
    }

    MEANINGFUL_STATUSES = {"Recebido", "Pendente", "Encerrado"}

    def __init__(
        self,
        empresa_repository: EmpresaRepository,
        documento_repository: DocumentoRepository,
        periodo_repository: PeriodoRepository,
        status_repository: StatusRepository,
    ) -> None:
        self.empresa_repository = empresa_repository
        self.documento_repository = documento_repository
        self.periodo_repository = periodo_repository
        self.status_repository = status_repository

    def build_monthly_view(self, periodo_id: int, active_only: bool = False) -> dict:
        periodo = self.periodo_repository.get_by_id(periodo_id)
        if not periodo:
            raise ValidationError("Periodo nao encontrado.")
        periodo["label"] = format_period_label(periodo["ano"], periodo["mes"])
        previous_period = self._get_previous_period(periodo)

        companies = self.empresa_repository.list_all(active_only=active_only)
        company_ids = [company["id"] for company in companies]
        documentos = self.documento_repository.list_by_company_ids(company_ids)
        documentos_by_company: dict[int, list[dict]] = {}
        for documento in documentos:
            documentos_by_company.setdefault(documento["empresa_id"], []).append(documento)

        document_ids = [documento["id"] for documento in documentos]
        period_ids = [periodo_id]
        if previous_period:
            period_ids.append(previous_period["id"])
        statuses = {
            (row["documento_empresa_id"], row["periodo_id"]): row
            for row in self.status_repository.list_for_documents_and_periods(document_ids, period_ids)
        }
        closures = self._get_closure_key_map(documentos)

        rows = []
        for company in companies:
            company_documents = documentos_by_company.get(company["id"], [])
            row = self._build_company_row(
                company,
                periodo,
                company_documents,
                statuses,
                closures,
            )
            previous_row = (
                self._build_company_row(company, previous_period, company_documents, statuses, closures)
                if previous_period
                else None
            )
            self._attach_previous_progress(row, previous_period, previous_row)
            rows.append(row)

        rows.sort(
            key=lambda item: (
                self.SITUATION_PRIORITIES.get(item["situacao_key"], 99),
                item["codigo_empresa"],
                item["nome_empresa"].casefold(),
            )
        )

        summary = {key: 0 for key in self.SITUATION_LABELS}
        for row in rows:
            summary[row["situacao_key"]] += 1

        return {
            "periodo": periodo,
            "previous_period": previous_period,
            "rows": rows,
            "summary": summary,
        }

    def _get_previous_period(self, periodo: dict) -> dict | None:
        previous_year = periodo["ano"]
        previous_month = periodo["mes"] - 1
        if previous_month == 0:
            previous_year -= 1
            previous_month = 12
        previous_period = self.periodo_repository.get_by_year_month(previous_year, previous_month)
        if previous_period:
            previous_period["label"] = format_period_label(previous_period["ano"], previous_period["mes"])
        return previous_period

    def _attach_previous_progress(
        self,
        row: dict,
        previous_period: dict | None,
        previous_row: dict | None,
    ) -> None:
        row["previous_period_id"] = previous_period["id"] if previous_period else None
        row["previous_marcados"] = previous_row["marcados"] if previous_row else None
        row["previous_total_cobravel"] = previous_row["total_cobravel"] if previous_row else None
        row["previous_situacao"] = previous_row["situacao"] if previous_row else ""
        row["previous_situacao_key"] = previous_row["situacao_key"] if previous_row else ""

    def _build_company_row(
        self,
        company: dict,
        periodo: dict,
        documentos: list[dict],
        statuses: dict[tuple[int, int], dict],
        closures: dict[int, int],
    ) -> dict:
        total_cobravel = 0
        recebidos = 0
        pendentes = 0
        encerrados = 0
        ultima_marcacao_em: str | None = None
        ultima_marcacao_por = ""

        for documento in documentos:
            if not self._is_document_chargeable(documento, periodo, closures.get(documento["id"])):
                continue

            total_cobravel += 1
            status_row = statuses.get((documento["id"], periodo["id"]))
            status = status_row["status"] if status_row else ""
            if status == AUTO_STATUS_NAO_COBRAR:
                status = ""

            if status == "Recebido":
                recebidos += 1
            elif status == "Pendente":
                pendentes += 1
            elif status == "Encerrado":
                encerrados += 1

            if status in self.MEANINGFUL_STATUSES and status_row:
                updated_at = status_row.get("updated_at")
                if updated_at and (ultima_marcacao_em is None or updated_at > ultima_marcacao_em):
                    ultima_marcacao_em = updated_at
                    ultima_marcacao_por = status_row.get("updated_by_username") or ""

        marcados = recebidos + pendentes + encerrados
        faltando = max(total_cobravel - marcados, 0)
        total_documentos = len(documentos)
        situacao_key = self._resolve_situation(total_documentos, total_cobravel, pendentes, marcados, faltando)

        return {
            "empresa_id": company["id"],
            "codigo_empresa": company["codigo_empresa"],
            "nome_empresa": company["nome_empresa"],
            "ativa": company["ativa"],
            "total_documentos": total_documentos,
            "total_cobravel": total_cobravel,
            "recebidos": recebidos,
            "pendentes": pendentes,
            "encerrados": encerrados,
            "marcados": marcados,
            "faltando": faltando,
            "situacao_key": situacao_key,
            "situacao": self.SITUATION_LABELS[situacao_key],
            "ultima_marcacao_em": ultima_marcacao_em,
            "ultima_marcacao_por": ultima_marcacao_por,
        }

    def _resolve_situation(
        self,
        total_documentos: int,
        total_cobravel: int,
        pendentes: int,
        marcados: int,
        faltando: int,
    ) -> str:
        if total_documentos == 0:
            return self.SITUATION_SEM_DOCUMENTOS
        if total_cobravel == 0:
            return self.SITUATION_SEM_COBRANCA
        if pendentes > 0:
            return self.SITUATION_COM_PENDENCIA
        if faltando == 0:
            return self.SITUATION_CONCLUIDA
        if marcados > 0:
            return self.SITUATION_EM_ANDAMENTO
        return self.SITUATION_NAO_INICIADA

    def _is_document_chargeable(self, documento: dict, periodo: dict, closure_key: int | None) -> bool:
        occurrence_rule = normalize_type_occurrence_rule(documento.get("regra_ocorrencia"))
        if not is_chargeable_period(occurrence_rule, periodo["mes"]):
            return False

        current_key = month_key(periodo["ano"], periodo["mes"])
        return closure_key is None or current_key <= closure_key

    def _get_closure_key_map(self, documentos: list[dict]) -> dict[int, int]:
        document_ids = [documento["id"] for documento in documentos]
        occurrence_by_document = {
            documento["id"]: normalize_type_occurrence_rule(documento.get("regra_ocorrencia"))
            for documento in documentos
        }
        closure_rows = self.status_repository.list_closures_for_documents(document_ids)
        return build_chargeable_closure_key_map(closure_rows, occurrence_by_document)
