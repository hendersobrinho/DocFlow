from __future__ import annotations

from pathlib import Path

SUPPORTED_EXTENSIONS = {".pdf", ".xlsx", ".xls"}

# Limite defensivo contra arquivos manipulados pra causar consumo excessivo de memoria/CPU
# na extracao (ex: PDF/planilha com compressao desproporcional - "decompression bomb").
# Documentos legitimos de boleto/nota fiscal/extrato ficam bem abaixo disso.
MAX_EXTRACTABLE_FILE_SIZE_BYTES = 50 * 1024 * 1024


class DocumentExtractionError(Exception):
    """Erro ao extrair texto de um documento."""


class DocumentExtractionService:
    def is_supported(self, file_path: Path) -> bool:
        return Path(file_path).suffix.lower() in SUPPORTED_EXTENSIONS

    def extract_text(self, file_path: Path) -> str:
        path = Path(file_path)
        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise DocumentExtractionError(f"Tipo de arquivo nao suportado: {suffix}")

        self._check_file_size(path)

        if suffix == ".pdf":
            return self._extract_pdf_text(path)
        return self._extract_spreadsheet_text(path)

    def _check_file_size(self, file_path: Path) -> None:
        try:
            size_bytes = file_path.stat().st_size
        except OSError as exc:
            raise DocumentExtractionError(f"Nao foi possivel acessar o arquivo: {file_path.name}") from exc
        if size_bytes > MAX_EXTRACTABLE_FILE_SIZE_BYTES:
            raise DocumentExtractionError(
                f"Arquivo maior que o limite suportado ({MAX_EXTRACTABLE_FILE_SIZE_BYTES // (1024 * 1024)} MB): "
                f"{file_path.name}"
            )

    def _extract_pdf_text(self, file_path: Path) -> str:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise DocumentExtractionError("A biblioteca pypdf nao esta instalada.") from exc

        try:
            reader = PdfReader(str(file_path))
            pages_text = [page.extract_text() or "" for page in reader.pages]
        except Exception as exc:
            raise DocumentExtractionError(f"Nao foi possivel ler o PDF: {file_path.name}") from exc
        return "\n".join(pages_text)

    def _extract_spreadsheet_text(self, file_path: Path) -> str:
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise DocumentExtractionError("A biblioteca openpyxl nao esta instalada.") from exc

        try:
            workbook = load_workbook(str(file_path), read_only=True, data_only=True)
        except Exception as exc:
            raise DocumentExtractionError(f"Nao foi possivel ler a planilha: {file_path.name}") from exc

        try:
            lines: list[str] = []
            for sheet in workbook.worksheets:
                for row in sheet.iter_rows(values_only=True):
                    cell_values = [str(value) for value in row if value is not None]
                    if cell_values:
                        lines.append(" ".join(cell_values))
            return "\n".join(lines)
        finally:
            workbook.close()
