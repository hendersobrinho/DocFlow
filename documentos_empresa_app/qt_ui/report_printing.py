from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QPageLayout, QPageSize, QTextDocument
from PySide6.QtCore import QMarginsF
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import QWidget

PAGE_MARGIN_MM = 12.0


def _configure(printer: QPrinter) -> None:
    printer.setPageLayout(
        QPageLayout(
            QPageSize(QPageSize.PageSizeId.A4),
            QPageLayout.Orientation.Portrait,
            QMarginsF(PAGE_MARGIN_MM, PAGE_MARGIN_MM, PAGE_MARGIN_MM, PAGE_MARGIN_MM),
            QPageLayout.Unit.Millimeter,
        )
    )


def _document(html: str) -> QTextDocument:
    document = QTextDocument()
    document.setHtml(html)
    return document


def save_html_as_pdf(html: str, file_path: str | Path) -> Path:
    """Gera um PDF A4 com texto de verdade (selecionavel, nitido na impressao), quebrando
    paginas automaticamente."""
    target = Path(file_path)
    if target.suffix.lower() != ".pdf":
        target = target.with_suffix(".pdf")
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(target))
    _configure(printer)
    _document(html).print_(printer)
    return target


def print_html(html: str, parent: QWidget | None = None, title: str = "Imprimir") -> bool:
    """Abre a janela de impressao do sistema e imprime o conteudo. Devolve False se o
    usuario cancelar."""
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    _configure(printer)
    dialog = QPrintDialog(printer, parent)
    dialog.setWindowTitle(title)
    if dialog.exec() != QPrintDialog.DialogCode.Accepted:
        return False
    _document(html).print_(printer)
    return True
