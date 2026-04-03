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

    def import_empresas(self, file_path: str) -> dict:
        workbook = self._load_workbook(file_path)
        worksheet = workbook.active

        imported = 0
        failed = 0
        errors: list[str] = []
        started_data_block = False

        for row_number, row in enumerate(worksheet.iter_rows(min_row=1, values_only=True), start=1):
            if self._is_empty_row(row):
                continue
            if not started_data_block and self._looks_like_empresa_header(row):
                started_data_block = True
                continue

            codigo = row[0] if len(row) > 0 else None
            nome = row[1] if len(row) > 1 else None
            meios = row[2] if len(row) > 2 else None
            email = row[3] if len(row) > 3 else None
            contato = row[4] if len(row) > 4 else None

            try:
                self.empresa_service.create_empresa(codigo, nome or "", meios, email, contato)
                imported += 1
            except ValidationError as exc:
                failed += 1
                errors.append(f"Linha {row_number}: {exc}")
            started_data_block = True

        return {"imported": imported, "failed": failed, "errors": errors}

    def import_documentos(self, file_path: str, empresa_id: int) -> dict:
        workbook = self._load_workbook(file_path)
        worksheet = workbook.active

        imported = 0
        failed = 0
        errors: list[str] = []
        started_data_block = False

        for row_number, row in enumerate(worksheet.iter_rows(min_row=1, values_only=True), start=1):
            if self._is_empty_row(row):
                continue
            if not started_data_block and self._looks_like_documento_header(row):
                started_data_block = True
                continue

            nome_documento = row[0] if len(row) > 0 else None
            nome_tipo = row[1] if len(row) > 1 else None

            if nome_documento is None and nome_tipo is None:
                continue

            try:
                if nome_tipo is None or str(nome_tipo).strip() == "":
                    raise ValidationError("O tipo do documento deve ser informado.")
                tipo = self.tipo_service.get_or_create_tipo(str(nome_tipo))
                self.documento_service.create_documento(empresa_id, tipo["id"], str(nome_documento or ""))
                imported += 1
            except ValidationError as exc:
                failed += 1
                errors.append(f"Linha {row_number}: {exc}")
            started_data_block = True

        return {"imported": imported, "failed": failed, "errors": errors}

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
        matches = 0
        for index, aliases in EMPRESA_IMPORT_HEADER_ALIASES.items():
            if len(row) <= index:
                continue
            if self._normalize_header_value(row[index]) in aliases:
                matches += 1
        return matches >= 2

    def _looks_like_documento_header(self, row) -> bool:
        matches = 0
        for index, aliases in DOCUMENTO_IMPORT_HEADER_ALIASES.items():
            if len(row) <= index:
                continue
            if self._normalize_header_value(row[index]) in aliases:
                matches += 1
        return matches >= 2

    def _normalize_header_value(self, value) -> str:
        raw = str(value or "").strip()
        normalized = unicodedata.normalize("NFKD", raw)
        normalized = "".join(char for char in normalized if not unicodedata.combining(char))
        normalized = normalized.casefold()
        normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
        return normalized.strip("_")
