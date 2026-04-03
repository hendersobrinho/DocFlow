from __future__ import annotations

try:
    from openpyxl import load_workbook
except ImportError:  # pragma: no cover - depende do ambiente local
    load_workbook = None

from documentos_empresa_app.services.documento_service import DocumentoService
from documentos_empresa_app.services.empresa_service import EmpresaService
from documentos_empresa_app.services.tipo_service import TipoService
from documentos_empresa_app.utils.common import ValidationError


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

    def import_empresas(self, file_path: str) -> dict:
        workbook = self._load_workbook(file_path)
        worksheet = workbook.active

        imported = 0
        failed = 0
        errors: list[str] = []

        for row_number, row in enumerate(worksheet.iter_rows(min_row=1, values_only=True), start=1):
            codigo = row[0] if len(row) > 0 else None
            nome = row[1] if len(row) > 1 else None

            if codigo is None and nome is None:
                continue

            try:
                self.empresa_service.create_empresa(codigo, nome or "")
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

        for row_number, row in enumerate(worksheet.iter_rows(min_row=1, values_only=True), start=1):
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

        return {"imported": imported, "failed": failed, "errors": errors}

    def _load_workbook(self, file_path: str):
        if load_workbook is None:
            raise ValidationError("A biblioteca openpyxl nao esta instalada no ambiente.")
        try:
            return load_workbook(file_path, read_only=True, data_only=True)
        except Exception as exc:
            raise ValidationError("Nao foi possivel abrir o arquivo Excel informado.") from exc
