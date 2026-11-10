from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMarginsF, QRectF, QSizeF, Qt
from PySide6.QtGui import QColor, QFont, QPageLayout, QPageSize, QPainter, QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import QWidget

from documentos_empresa_app.services.report_html import FOOTER_TEXT, MUTED, PAGE_BACKGROUND, TEXT

PAGE_MARGIN_MM = 12.0
FOOTER_HEIGHT = 26.0  # em pixels de tela (96 dpi) - faixa do rodape com o numero da pagina
SCREEN_DPI = 96.0


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
    # Sem isto, no tema escuro o texto herda a cor clara do aplicativo e some no papel.
    document.setDefaultStyleSheet(f"body {{ color: {TEXT}; }}")
    document.setHtml(html)
    return document


def _render(html: str, printer: QPrinter, background: str = PAGE_BACKGROUND) -> None:
    """Desenha o documento pagina a pagina: fundo do sistema na folha inteira, o conteudo e,
    embaixo, 'DocFlow - pagina X de N'. O texto continua vetorial (selecionavel no PDF)."""
    document = _document(html)
    painter = QPainter()
    if not painter.begin(printer):
        raise RuntimeError("Não foi possível começar a imprimir. Verifique a impressora.")
    try:
        scale = printer.resolution() / SCREEN_DPI
        page = printer.pageRect(QPrinter.Unit.DevicePixel)
        paper = printer.paperRect(QPrinter.Unit.DevicePixel)
        page_width = page.width() / scale
        content_height = page.height() / scale - FOOTER_HEIGHT
        document.setPageSize(QSizeF(page_width, content_height))
        pages = max(document.pageCount(), 1)

        footer_font = QFont()
        footer_font.setPixelSize(11)  # em pixels logicos: o painter ja esta escalado
        for index in range(pages):
            if index:
                printer.newPage()
            # Fundo na folha inteira (o painter comeca na area imprimivel, dentro das margens).
            painter.fillRect(
                QRectF(-page.x(), -page.y(), paper.width(), paper.height()), QColor(background)
            )
            painter.save()
            painter.scale(scale, scale)
            painter.save()
            painter.setClipRect(QRectF(0, 0, page_width, content_height))
            painter.translate(0, -index * content_height)
            document.drawContents(painter, QRectF(0, index * content_height, page_width, content_height))
            painter.restore()
            painter.setFont(footer_font)
            painter.setPen(QColor(MUTED))
            painter.drawText(
                QRectF(0, content_height, page_width, FOOTER_HEIGHT),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                f"{FOOTER_TEXT}  ·  página {index + 1} de {pages}",
            )
            painter.restore()
    finally:
        painter.end()


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
    _render(html, printer)
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
    _render(html, printer)
    return True
