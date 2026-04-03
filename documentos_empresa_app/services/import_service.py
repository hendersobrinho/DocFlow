from __future__ import annotations

import re
import unicodedata

try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font
except ImportError:  # pragma: no cover - depende do ambiente local
    Workbook = None
    Font = None
    load_workbook = None

from documentos_empresa_app.services.documento_service import DocumentoService
from documentos_empresa_app.services.empresa_service import EmpresaService
from documentos_empresa_app.services.tipo_service import TipoService
from documentos_empresa_app.utils.common import ValidationError


EMPRESA_IMPORT_LAYOUT = (
    {
        "index": 1,
        "field": "codigo_empresa",
        "label": "Codigo da empresa",
        "required": True,
        "example": "101",
    },
    {
        "index": 2,
        "field": "nome_empresa",
        "label": "Nome da empresa",
        "required": True,
        "example": "Empresa Exemplo Ltda",
    },
    {
        "index": 3,
        "field": "meios_recebimento",
        "label": "Meios de recebimento",
        "required": False,
        "example": "Email, Onvio",
    },
    {
        "index": 4,
        "field": "email_contato",
        "label": "Email de contato",
        "required": False,
        "example": "contato@empresa.com",
    },
    {
        "index": 5,
        "field": "nome_contato",
        "label": "Nome do contato",
        "required": False,
        "example": "Maria Silva",
    },
)

EMPRESA_IMPORT_HEADER_ALIASES = {
    0: {"codigo", "codigo_empresa", "codigo_da_empresa"},
    1: {"nome", "nome_empresa", "nome_da_empresa"},
    2: {"meios", "meio", "meios_recebimento", "meios_de_recebimento", "meio_de_recebimento"},
    3: {"email", "email_contato", "email_para_contato"},
    4: {"contato", "nome_contato", "nome_do_contato"},
}

DOCUMENTO_IMPORT_LAYOUT = (
    {
        "index": 1,
        "field": "nome_documento",
        "label": "Nome do documento",
        "required": True,
        "example": "Banco do Brasil",
    },
    {
        "index": 2,
        "field": "nome_tipo",
        "label": "Tipo do documento",
        "required": True,
        "example": "Extratos CC",
    },
)

DOCUMENTO_IMPORT_HEADER_ALIASES = {
    0: {"nome_documento", "documento", "nome", "nome_do_documento"},
    1: {"tipo", "nome_tipo", "tipo_documento", "tipo_do_documento"},
}

CADASTRO_COMPLETO_IMPORT_LAYOUT = (
    {
        "index": 1,
        "field": "codigo_empresa",
        "label": "Codigo da empresa",
        "required": True,
        "example": "101",
    },
    {
        "index": 2,
        "field": "nome_empresa",
        "label": "Nome da empresa",
        "required": True,
        "example": "Empresa Exemplo Ltda",
    },
    {
        "index": 3,
        "field": "meios_recebimento",
        "label": "Meios de recebimento",
        "required": False,
        "example": "Email, Onvio",
    },
    {
        "index": 4,
        "field": "email_contato",
        "label": "Email de contato",
        "required": False,
        "example": "contato@empresa.com",
    },
    {
        "index": 5,
        "field": "nome_contato",
        "label": "Nome do contato",
        "required": False,
        "example": "Maria Silva",
    },
    {
        "index": 6,
        "field": "nome_documento",
        "label": "Nome do documento",
        "required": False,
        "example": "Banco do Brasil",
    },
    {
        "index": 7,
        "field": "nome_tipo",
        "label": "Tipo do documento",
        "required": False,
        "example": "Extratos CC",
    },
)

CADASTRO_COMPLETO_IMPORT_HEADER_ALIASES = {
    0: EMPRESA_IMPORT_HEADER_ALIASES[0],
    1: EMPRESA_IMPORT_HEADER_ALIASES[1],
    2: EMPRESA_IMPORT_HEADER_ALIASES[2],
    3: EMPRESA_IMPORT_HEADER_ALIASES[3],
    4: EMPRESA_IMPORT_HEADER_ALIASES[4],
    5: DOCUMENTO_IMPORT_HEADER_ALIASES[0],
    6: DOCUMENTO_IMPORT_HEADER_ALIASES[1],
}

IMPORT_COMPANY_CREATED = "created"
IMPORT_COMPANY_UPDATED = "updated"
IMPORT_COMPANY_REUSED = "reused"
IMPORT_COMPANY_OUTCOME_PRIORITY = {
    IMPORT_COMPANY_REUSED: 1,
    IMPORT_COMPANY_UPDATED: 2,
    IMPORT_COMPANY_CREATED: 3,
}


class ImportService:
    def __init__(
        self,
        empresa_service: EmpresaService,
        tipo_service: TipoService,
        documento_service: DocumentoService,
    ) -> None:
        self.empresa_service = empresa_service
        self.tipo_service = tipo_service
        self.documento_service = documento_service

    def get_empresa_import_layout(self) -> tuple[dict, ...]:
        return EMPRESA_IMPORT_LAYOUT

    def get_documento_import_layout(self) -> tuple[dict, ...]:
        return DOCUMENTO_IMPORT_LAYOUT

    def get_cadastro_completo_import_layout(self) -> tuple[dict, ...]:
        return CADASTRO_COMPLETO_IMPORT_LAYOUT

    def export_empresa_template(self, file_path: str) -> dict:
        return self._export_template(
            file_path,
            worksheet_title="Empresas",
            layout=EMPRESA_IMPORT_LAYOUT,
        )

    def export_documento_template(self, file_path: str) -> dict:
        return self._export_template(
            file_path,
            worksheet_title="Documentos",
            layout=DOCUMENTO_IMPORT_LAYOUT,
        )

    def export_cadastro_completo_template(self, file_path: str) -> dict:
        return self._export_template(
            file_path,
            worksheet_title="Cadastros completos",
            layout=CADASTRO_COMPLETO_IMPORT_LAYOUT,
        )

    def import_empresas(self, file_path: str) -> dict:
        workbook = self._load_workbook(file_path)
        worksheet = workbook.active

        imported = 0
        failed = 0
        errors: list[str] = []

        for row_number, row in self._iter_data_rows(worksheet, self._looks_like_empresa_header):
            try:
                self._import_empresa_row(row)
                imported += 1
            except ValidationError as exc:
                failed += 1
                errors.append(f"Linha {row_number}: {exc}")

        return {"imported": imported, "failed": failed, "errors": errors}

    def import_documentos(self, file_path: str, empresa_id: int) -> dict:
        workbook = self._load_workbook(file_path)
        worksheet = workbook.active

        imported = 0
        failed = 0
        errors: list[str] = []

        for row_number, row in self._iter_data_rows(worksheet, self._looks_like_documento_header):
            try:
                nome_documento = self._get_row_value(row, 0)
                nome_tipo = self._get_row_value(row, 1)
                self._import_documento_row(empresa_id, nome_documento, nome_tipo)
                imported += 1
            except ValidationError as exc:
                failed += 1
                errors.append(f"Linha {row_number}: {exc}")

        return {"imported": imported, "failed": failed, "errors": errors}

    def import_cadastros_completos(self, file_path: str) -> dict:
        workbook = self._load_workbook(file_path)
        worksheet = workbook.active

        processed_rows = 0
        documents_imported = 0
        failed = 0
        errors: list[str] = []
        company_outcomes: dict[int, str] = {}
        created_type_ids: set[int] = set()
        current_company: dict | None = None
        db_manager = self.empresa_service.empresa_repository.db_manager

        for row_number, row in self._iter_data_rows(worksheet, self._looks_like_cadastro_completo_header):
            next_company: dict | None = None
            try:
                with db_manager.connect():
                    company, outcome = self._resolve_company_for_complete_row(row, current_company)

                    nome_documento = self._get_row_value(row, 5)
                    nome_tipo = self._get_row_value(row, 6)

                    if self._row_has_values((nome_documento, nome_tipo)):
                        _, tipo_created, tipo_id = self._import_documento_row(
                            company["id"],
                            nome_documento,
                            nome_tipo,
                        )
                        if tipo_created:
                            created_type_ids.add(tipo_id)
                        documents_imported += 1

                    self._register_company_outcome(company_outcomes, company["id"], outcome)
                    processed_rows += 1
                    next_company = company
            except ValidationError as exc:
                failed += 1
                errors.append(f"Linha {row_number}: {exc}")
                continue

            current_company = next_company

        companies_created = self._count_company_outcomes(company_outcomes, IMPORT_COMPANY_CREATED)
        companies_updated = self._count_company_outcomes(company_outcomes, IMPORT_COMPANY_UPDATED)
        companies_reused = self._count_company_outcomes(company_outcomes, IMPORT_COMPANY_REUSED)

        return {
            "processed_rows": processed_rows,
            "companies_created": companies_created,
            "companies_updated": companies_updated,
            "companies_reused": companies_reused,
            "documents_imported": documents_imported,
            "types_created": len(created_type_ids),
            "failed": failed,
            "errors": errors,
        }

    def _load_workbook(self, file_path: str):
        if load_workbook is None:
            raise ValidationError("A biblioteca openpyxl nao esta instalada no ambiente.")
        try:
            return load_workbook(file_path, read_only=True, data_only=True)
        except Exception as exc:
            raise ValidationError("Nao foi possivel abrir o arquivo Excel informado.") from exc

    def _export_template(
        self,
        file_path: str,
        *,
        worksheet_title: str,
        layout: tuple[dict, ...],
    ) -> dict:
        if Workbook is None:
            raise ValidationError("A biblioteca openpyxl nao esta instalada no ambiente.")

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = worksheet_title

        headers = [item["label"] for item in layout]
        examples = [item["example"] for item in layout]
        worksheet.append(headers)
        worksheet.append(examples)

        if Font is not None:
            for cell in worksheet[1]:
                cell.font = Font(bold=True)

        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions

        for index, item in enumerate(layout, start=1):
            column_letter = worksheet.cell(row=1, column=index).column_letter
            width = max(len(item["label"]), len(item["example"]), 18) + 2
            worksheet.column_dimensions[column_letter].width = min(width, 42)

        workbook.save(file_path)
        return {
            "path": file_path,
            "columns": len(layout),
            "example_row": examples,
        }

    def _is_empty_row(self, row) -> bool:
        return all(value is None or str(value).strip() == "" for value in row)

    def _looks_like_empresa_header(self, row) -> bool:
        return self._looks_like_header(row, EMPRESA_IMPORT_HEADER_ALIASES, minimum_matches=2)

    def _looks_like_documento_header(self, row) -> bool:
        return self._looks_like_header(row, DOCUMENTO_IMPORT_HEADER_ALIASES, minimum_matches=2)

    def _looks_like_cadastro_completo_header(self, row) -> bool:
        return self._looks_like_header(row, CADASTRO_COMPLETO_IMPORT_HEADER_ALIASES, minimum_matches=3)

    def _looks_like_header(self, row, aliases_by_index: dict[int, set[str]], *, minimum_matches: int) -> bool:
        matches = 0
        for index, aliases in aliases_by_index.items():
            if len(row) <= index:
                continue
            if self._normalize_header_value(row[index]) in aliases:
                matches += 1
        return matches >= minimum_matches

    def _iter_data_rows(self, worksheet, header_checker):
        started_data_block = False
        for row_number, row in enumerate(worksheet.iter_rows(min_row=1, values_only=True), start=1):
            if self._is_empty_row(row):
                continue
            if not started_data_block and header_checker(row):
                started_data_block = True
                continue
            started_data_block = True
            yield row_number, row

    def _import_empresa_row(self, row) -> int:
        codigo = self._get_row_value(row, 0)
        nome = self._get_row_value(row, 1)
        meios = self._get_row_value(row, 2)
        email = self._get_row_value(row, 3)
        contato = self._get_row_value(row, 4)
        return self.empresa_service.create_empresa(codigo, nome or "", meios, email, contato)

    def _import_documento_row(self, empresa_id: int, nome_documento, nome_tipo) -> tuple[int, bool, int]:
        if not self._has_value(nome_documento):
            raise ValidationError("O nome do documento deve ser informado.")
        if not self._has_value(nome_tipo):
            raise ValidationError("O tipo do documento deve ser informado.")

        tipo, tipo_created = self.tipo_service.ensure_tipo(str(nome_tipo))
        documento_id = self.documento_service.create_documento(empresa_id, tipo["id"], str(nome_documento or ""))
        return documento_id, tipo_created, tipo["id"]

    def _resolve_company_for_complete_row(self, row, current_company: dict | None) -> tuple[dict, str]:
        codigo = self._get_row_value(row, 0)
        nome = self._get_row_value(row, 1)
        meios = self._get_row_value(row, 2)
        email = self._get_row_value(row, 3)
        contato = self._get_row_value(row, 4)
        company_values = (codigo, nome, meios, email, contato)

        if self._has_value(codigo):
            return self._get_or_create_company_for_import(codigo, nome, meios, email, contato)

        if self._row_has_values(company_values):
            raise ValidationError("Informe o codigo da empresa para identificar o cadastro completo.")

        if current_company is None:
            raise ValidationError(
                "Informe o codigo e o nome da empresa na primeira linha de cada bloco de documentos."
            )

        return current_company, IMPORT_COMPANY_REUSED

    def _get_or_create_company_for_import(
        self,
        codigo,
        nome,
        meios,
        email,
        contato,
    ) -> tuple[dict, str]:
        existing = self.empresa_service.get_empresa_by_code(codigo, active_only=False)
        if not existing:
            if not self._has_value(nome):
                raise ValidationError("O nome da empresa deve ser informado para novos cadastros.")
            company_id = self.empresa_service.create_empresa(codigo, str(nome or ""), meios, email, contato)
            return self.empresa_service.get_empresa(company_id), IMPORT_COMPANY_CREATED

        updated_name = self._coalesce_row_value(nome, existing["nome_empresa"])
        updated_meios = self._coalesce_row_value(meios, existing.get("meios_recebimento"))
        updated_email = self._coalesce_row_value(email, existing.get("email_contato"))
        updated_contato = self._coalesce_row_value(contato, existing.get("nome_contato"))

        if self._company_needs_update(existing, updated_name, updated_meios, updated_email, updated_contato):
            self.empresa_service.update_empresa(
                existing["id"],
                updated_name,
                updated_meios,
                updated_email,
                updated_contato,
            )
            return self.empresa_service.get_empresa(existing["id"]), IMPORT_COMPANY_UPDATED

        return existing, IMPORT_COMPANY_REUSED

    def _company_needs_update(
        self,
        company: dict,
        nome_empresa: str,
        meios_recebimento: str | None,
        email_contato: str | None,
        nome_contato: str | None,
    ) -> bool:
        return any(
            (
                company["nome_empresa"] != nome_empresa,
                (company.get("meios_recebimento") or None) != (meios_recebimento or None),
                (company.get("email_contato") or None) != (email_contato or None),
                (company.get("nome_contato") or None) != (nome_contato or None),
            )
        )

    def _register_company_outcome(self, outcomes: dict[int, str], company_id: int, status: str) -> None:
        current_status = outcomes.get(company_id)
        if current_status is None:
            outcomes[company_id] = status
            return
        if IMPORT_COMPANY_OUTCOME_PRIORITY[status] > IMPORT_COMPANY_OUTCOME_PRIORITY[current_status]:
            outcomes[company_id] = status

    def _count_company_outcomes(self, outcomes: dict[int, str], status: str) -> int:
        return sum(1 for current_status in outcomes.values() if current_status == status)

    def _get_row_value(self, row, index: int):
        if len(row) <= index:
            return None
        return row[index]

    def _row_has_values(self, values) -> bool:
        return any(self._has_value(value) for value in values)

    def _has_value(self, value) -> bool:
        return value is not None and str(value).strip() != ""

    def _coalesce_row_value(self, value, fallback):
        if not self._has_value(value):
            return fallback
        normalized = str(value).strip()
        return normalized or fallback

    def _normalize_header_value(self, value) -> str:
        raw = str(value or "").strip()
        normalized = unicodedata.normalize("NFKD", raw)
        normalized = "".join(char for char in normalized if not unicodedata.combining(char))
        normalized = normalized.casefold()
        normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
        return normalized.strip("_")
