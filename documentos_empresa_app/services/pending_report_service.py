from __future__ import annotations

from pathlib import Path

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font
except ImportError:  # pragma: no cover - depende do ambiente local
    Workbook = None
    Font = None

from documentos_empresa_app.database.repositories import (
    DocumentoRepository,
    EmpresaRepository,
    PeriodoRepository,
    StatusRepository,
)
from documentos_empresa_app.utils.common import ValidationError, count_months_between, format_period_label, month_key


class PendingReportService:
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

    def list_pending_rows(
        self,
        company_ids: list[int] | None,
        start_period_id: int,
        end_period_id: int,
    ) -> dict:
        periodos = self._get_periods_between(start_period_id, end_period_id)
        companies = self._resolve_companies(company_ids)

        rows: list[dict] = []
        pending_company_ids: set[int] = set()
        period_ids = [periodo["id"] for periodo in periodos]

        for company in companies:
            documentos = self.documento_repository.list_by_company(company["id"])
            if not documentos:
                continue

            document_ids = [documento["id"] for documento in documentos]
            statuses = {
                (row["documento_empresa_id"], row["periodo_id"]): row["status"] or ""
                for row in self.status_repository.list_for_documents_and_periods(document_ids, period_ids)
            }
            closures = {
                row["documento_empresa_id"]: row["fechamento"]
                for row in self.status_repository.list_earliest_closures(document_ids)
            }

            for documento in documentos:
                closure_key = closures.get(documento["id"])
                for periodo in periodos:
                    current_key = month_key(periodo["ano"], periodo["mes"])
                    if closure_key is not None and current_key > closure_key:
                        continue

                    if statuses.get((documento["id"], periodo["id"]), "") != "Pendente":
                        continue

                    pending_company_ids.add(company["id"])
                    rows.append(
                        {
                            "codigo_empresa": company["codigo_empresa"],
                            "nome_empresa": company["nome_empresa"],
                            "ano": periodo["ano"],
                            "mes": periodo["mes"],
                            "periodo": periodo["label"],
                            "tipo_documento": documento["nome_tipo"],
                            "nome_documento": documento["nome_documento"],
                            "status": "Pendente",
                        }
                    )

        rows.sort(
            key=lambda item: (
                item["codigo_empresa"],
                item["ano"],
                item["mes"],
                item["tipo_documento"].casefold(),
                item["nome_documento"].casefold(),
            )
        )
        return {
            "companies": companies,
            "periodos": periodos,
            "rows": rows,
            "pending_company_count": len(pending_company_ids),
        }

    def export_pending_report(
        self,
        file_path: str,
        company_ids: list[int] | None,
        start_period_id: int,
        end_period_id: int,
    ) -> dict:
        report = self.list_pending_rows(company_ids, start_period_id, end_period_id)
        rows = report["rows"]
        if not rows:
            raise ValidationError("Nenhuma pendencia com status Pendente foi encontrada no filtro informado.")
        if Workbook is None:
            raise ValidationError("A biblioteca openpyxl nao esta instalada no ambiente.")

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Pendencias"

        headers = (
            "Codigo da empresa",
            "Nome da empresa",
            "Ano",
            "Mes",
            "Periodo",
            "Tipo do documento",
            "Documento pendente",
            "Status",
        )
        worksheet.append(headers)

        for cell in worksheet[1]:
            if Font is not None:
                cell.font = Font(bold=True)

        for row in rows:
            worksheet.append(
                (
                    row["codigo_empresa"],
                    row["nome_empresa"],
                    row["ano"],
                    row["mes"],
                    row["periodo"],
                    row["tipo_documento"],
                    row["nome_documento"],
                    row["status"],
                )
            )

        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions
        widths = {
            "A": 18,
            "B": 36,
            "C": 10,
            "D": 10,
            "E": 22,
            "F": 24,
            "G": 38,
            "H": 14,
        }
        for column, width in widths.items():
            worksheet.column_dimensions[column].width = width

        workbook.save(Path(file_path))
        return {
            "rows": len(rows),
            "company_count": len(report["companies"]),
            "pending_company_count": report["pending_company_count"],
            "period_count": len(report["periodos"]),
        }

    def _get_periods_between(self, start_period_id: int, end_period_id: int) -> list[dict]:
        start_period = self.periodo_repository.get_by_id(start_period_id)
        end_period = self.periodo_repository.get_by_id(end_period_id)
        if not start_period or not end_period:
            raise ValidationError("Selecione um periodo inicial e um periodo final validos.")

        start_key = month_key(start_period["ano"], start_period["mes"])
        end_key = month_key(end_period["ano"], end_period["mes"])
        if start_key > end_key:
            raise ValidationError("O periodo inicial nao pode ser maior que o periodo final.")
        if count_months_between(
            start_period["ano"],
            start_period["mes"],
            end_period["ano"],
            end_period["mes"],
        ) > 12:
            raise ValidationError("O relatorio permite no maximo 12 meses por vez.")

        periodos = self.periodo_repository.list_between(
            start_period["ano"],
            start_period["mes"],
            end_period["ano"],
            end_period["mes"],
        )
        if not periodos:
            raise ValidationError("Nao existem periodos gerados para o intervalo informado.")

        for periodo in periodos:
            periodo["label"] = format_period_label(periodo["ano"], periodo["mes"])
        return periodos

    def _resolve_companies(self, company_ids: list[int] | None) -> list[dict]:
        if not company_ids:
            return self.empresa_repository.list_all(active_only=False)

        resolved_companies: list[dict] = []
        seen_ids: set[int] = set()
        for company_id in company_ids:
            try:
                company_id_int = int(company_id)
            except (TypeError, ValueError) as exc:
                raise ValidationError("Selecione empresas validas para gerar o relatorio.") from exc
            if company_id_int in seen_ids:
                continue
            company = self.empresa_repository.get_by_id(company_id_int)
            if not company:
                raise ValidationError("Uma das empresas selecionadas nao foi encontrada.")
            seen_ids.add(company_id_int)
            resolved_companies.append(company)

        resolved_companies.sort(key=lambda item: (item["codigo_empresa"], item["nome_empresa"].casefold()))
        return resolved_companies
