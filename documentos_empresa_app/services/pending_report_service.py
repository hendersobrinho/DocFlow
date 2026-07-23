from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
import textwrap
import unicodedata

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font
except ImportError:  # pragma: no cover - depende do ambiente local
    Workbook = None
    Font = None

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover - depende do ambiente local
    Image = None
    ImageDraw = None
    ImageFont = None

from documentos_empresa_app.database.repositories import (
    DocumentoRepository,
    EmpresaRepository,
    PeriodoRepository,
    StatusRepository,
)
from documentos_empresa_app.utils.common import (
    APP_NAME,
    ValidationError,
    build_chargeable_closure_key_map,
    count_months_between,
    format_period_label,
    is_chargeable_period,
    month_key,
    normalize_type_occurrence_rule,
)
from documentos_empresa_app.utils.resources import get_packaging_icon_path, get_runtime_base_path


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
        company_id_list = [company["id"] for company in companies]
        documentos = self.documento_repository.list_by_company_ids(company_id_list)
        documentos_by_company: dict[int, list[dict]] = {}
        for documento in documentos:
            documentos_by_company.setdefault(documento["empresa_id"], []).append(documento)

        document_ids = [documento["id"] for documento in documentos]
        statuses = {
            (row["documento_empresa_id"], row["periodo_id"]): row["status"] or ""
            for row in self.status_repository.list_for_documents_and_periods(document_ids, period_ids)
        }
        closures = self._get_closure_key_map(documentos)

        for company in companies:
            company_documents = documentos_by_company.get(company["id"], [])
            if not company_documents:
                continue

            for documento in company_documents:
                closure_key = closures.get(documento["id"])
                occurrence_rule = normalize_type_occurrence_rule(documento.get("regra_ocorrencia"))
                for periodo in periodos:
                    current_key = month_key(periodo["ano"], periodo["mes"])
                    if not is_chargeable_period(occurrence_rule, periodo["mes"]):
                        continue
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
        export_context = self._build_export_context(company_ids, start_period_id, end_period_id)
        report = export_context["report"]
        rows = export_context["rows"]
        if Workbook is None:
            raise ValidationError("A biblioteca openpyxl nao esta instalada no ambiente.")

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Pendencias"

        headers = (
            "Codigo da empresa",
            "Empresa",
            "Periodo",
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
                    row["periodo"],
                    row["nome_documento"],
                    row["status"],
                )
            )

        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions
        widths = {
            "A": 18,
            "B": 36,
            "C": 22,
            "D": 38,
            "E": 14,
        }
        for column, width in widths.items():
            worksheet.column_dimensions[column].width = width

        workbook.save(Path(file_path))
        return self._build_export_result(report)

    def export_pending_report_pdf(
        self,
        file_path: str,
        company_ids: list[int] | None,
        start_period_id: int,
        end_period_id: int,
    ) -> dict:
        if Image is None or ImageDraw is None or ImageFont is None:
            raise ValidationError("A biblioteca Pillow nao esta instalada no ambiente.")
        export_context = self._build_export_context(company_ids, start_period_id, end_period_id)
        pdf_bytes = _PendingReportPdfBuilder().build(export_context)
        Path(file_path).write_bytes(pdf_bytes)
        return self._build_export_result(export_context["report"])

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

        seen_ids: set[int] = set()
        for company_id in company_ids:
            try:
                company_id_int = int(company_id)
            except (TypeError, ValueError) as exc:
                raise ValidationError("Selecione empresas validas para gerar o relatorio.") from exc
            seen_ids.add(company_id_int)

        resolved_companies = self.empresa_repository.list_by_ids(sorted(seen_ids))
        if len(resolved_companies) != len(seen_ids):
            raise ValidationError("Uma das empresas selecionadas nao foi encontrada.")

        resolved_companies.sort(key=lambda item: (item["codigo_empresa"], item["nome_empresa"].casefold()))
        return resolved_companies

    def _get_closure_key_map(self, documentos: list[dict]) -> dict[int, int]:
        document_ids = [documento["id"] for documento in documentos]
        occurrence_by_document = {
            documento["id"]: normalize_type_occurrence_rule(documento.get("regra_ocorrencia"))
            for documento in documentos
        }
        closure_rows = self.status_repository.list_closures_for_documents(document_ids)
        return build_chargeable_closure_key_map(closure_rows, occurrence_by_document)

    def _build_export_context(
        self,
        company_ids: list[int] | None,
        start_period_id: int,
        end_period_id: int,
    ) -> dict:
        report = self.list_pending_rows(company_ids, start_period_id, end_period_id)
        rows = report["rows"]
        if not rows:
            raise ValidationError("Nenhuma pendencia com status Pendente foi encontrada no filtro informado.")

        periodos = report["periodos"]
        start_label = periodos[0]["label"]
        end_label = periodos[-1]["label"]
        period_label = start_label if start_label == end_label else f"{start_label} ate {end_label}"
        companies = report["companies"]
        if company_ids:
            if len(companies) == 1:
                company_label = f'{companies[0]["codigo_empresa"]} - {companies[0]["nome_empresa"]}'
            else:
                company_label = f"{len(companies)} empresas selecionadas"
        else:
            company_label = f"Todas as empresas ({len(companies)})"

        return {
            "report": report,
            "rows": rows,
            "period_label": period_label,
            "company_label": company_label,
            "generated_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
        }

    def _build_export_result(self, report: dict) -> dict:
        return {
            "rows": len(report["rows"]),
            "company_count": len(report["companies"]),
            "pending_company_count": report["pending_company_count"],
            "period_count": len(report["periodos"]),
        }


class _PendingReportPdfBuilder:
    SCALE = 2
    PDF_RESOLUTION = 150.0 * SCALE
    PAGE_WIDTH = 1684 * SCALE
    PAGE_HEIGHT = 1191 * SCALE
    MARGIN_X = 72 * SCALE
    MARGIN_Y = 60 * SCALE
    HEADER_HEIGHT = 122 * SCALE
    SUMMARY_HEIGHT = 88 * SCALE
    TABLE_HEADER_HEIGHT = 42 * SCALE
    ROW_PADDING_X = 14 * SCALE
    ROW_PADDING_Y = 14 * SCALE
    TITLE_COLOR = "#183250"
    BODY_TEXT = "#24313F"
    MUTED_TEXT = "#66727D"
    BORDER_COLOR = "#D7DEE5"
    HEADER_BG = "#F5F8FC"
    SUMMARY_BG = "#F8FAFC"
    STRIPE_BG = "#FBFCFE"
    TABLE_HEADER_BG = "#2F629F"
    TABLE_HEADER_TEXT = "#FFFFFF"
    PROGRAM_BG = "#E9F1FB"
    TABLE_COLUMNS = (
        ("empresa", "Empresa", 340 * SCALE, "bold"),
        ("periodo", "Periodo", 190 * SCALE, "regular"),
        ("quantidade", "Qtd.", 78 * SCALE, "bold"),
        ("pendencias", "Documentos pendentes", 932 * SCALE, "regular"),
    )

    def build(self, export_context: dict) -> bytes:
        grouped_rows = self._group_rows(export_context["rows"])
        pages: list[Image.Image] = []
        page_number = 1
        page = self._new_page()
        draw = ImageDraw.Draw(page)
        fonts = self._load_fonts()
        logo = self._load_logo()
        next_row_top = self._draw_page_header(draw, page, export_context, page_number, fonts, logo)

        for row_index, row in enumerate(grouped_rows):
            wrapped_row = self._wrap_row(draw, row, fonts)
            row_height = self._calculate_row_height(wrapped_row)
            if next_row_top + row_height > self.PAGE_HEIGHT - self.MARGIN_Y:
                pages.append(page.convert("RGB"))
                page_number += 1
                page = self._new_page()
                draw = ImageDraw.Draw(page)
                next_row_top = self._draw_page_header(draw, page, export_context, page_number, fonts, logo)

            self._draw_row(draw, wrapped_row, next_row_top, row_height, row_index, fonts)
            next_row_top += row_height

        pages.append(page.convert("RGB"))
        output_buffer = BytesIO()
        pages[0].save(output_buffer, "PDF", resolution=self.PDF_RESOLUTION, save_all=True, append_images=pages[1:])
        return output_buffer.getvalue()

    def _group_rows(self, rows: list[dict]) -> list[dict]:
        grouped_rows: list[dict] = []
        current_group: dict | None = None

        for row in rows:
            group_key = (row["codigo_empresa"], row["nome_empresa"], row["periodo"])
            if current_group is None or current_group["group_key"] != group_key:
                current_group = {
                    "group_key": group_key,
                    "empresa": f'{row["codigo_empresa"]} - {row["nome_empresa"]}',
                    "periodo": row["periodo"],
                    "pendencias": [],
                }
                grouped_rows.append(current_group)

            current_group["pendencias"].append(row["nome_documento"])

        return grouped_rows

    def _new_page(self) -> Image.Image:
        return Image.new("RGB", (self.PAGE_WIDTH, self.PAGE_HEIGHT), "white")

    def _load_fonts(self) -> dict[str, ImageFont.FreeTypeFont | ImageFont.ImageFont]:
        regular_candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            "DejaVuSans.ttf",
        ]
        bold_candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
            "DejaVuSans-Bold.ttf",
        ]
        return {
            "title": self._load_font(regular_candidates, 40 * self.SCALE, bold_candidates),
            "program": self._load_font(bold_candidates, 24 * self.SCALE),
            "section": self._load_font(bold_candidates, 18 * self.SCALE),
            "body": self._load_font(regular_candidates, 16 * self.SCALE),
            "body_bold": self._load_font(bold_candidates, 16 * self.SCALE),
            "small": self._load_font(regular_candidates, 13 * self.SCALE),
            "small_bold": self._load_font(bold_candidates, 13 * self.SCALE),
            "metric": self._load_font(bold_candidates, 28 * self.SCALE),
        }

    def _load_font(
        self,
        candidates: list[str],
        size: int,
        fallback_candidates: list[str] | None = None,
    ) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        for candidate in candidates + (fallback_candidates or []):
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                continue
        return ImageFont.load_default()

    def _load_logo(self) -> Image.Image | None:
        logo_path = get_packaging_icon_path(get_runtime_base_path())
        if not logo_path.exists():
            return None
        try:
            logo = Image.open(logo_path).convert("RGBA")
        except OSError:
            return None
        return logo

    def _draw_page_header(
        self,
        draw: ImageDraw.ImageDraw,
        page: Image.Image,
        export_context: dict,
        page_number: int,
        fonts: dict,
        logo: Image.Image | None,
    ) -> int:
        scale = self.SCALE
        content_width = self.PAGE_WIDTH - (self.MARGIN_X * 2)
        header_bottom = self.MARGIN_Y + self.HEADER_HEIGHT
        draw.rounded_rectangle(
            (self.MARGIN_X, self.MARGIN_Y, self.MARGIN_X + content_width, header_bottom),
            radius=24 * scale,
            fill=self.HEADER_BG,
            outline=self.BORDER_COLOR,
            width=2 * scale,
        )

        if logo is not None:
            logo_copy = logo.copy()
            logo_copy.thumbnail((72 * scale, 72 * scale))
            logo_x = self.MARGIN_X + (20 * scale)
            logo_y = self.MARGIN_Y + (24 * scale)
            page.paste(logo_copy, (logo_x, logo_y), logo_copy)
            text_x = logo_x + logo_copy.width + (18 * scale)
        else:
            text_x = self.MARGIN_X + (24 * scale)

        badge_right = self.MARGIN_X + content_width - (24 * scale)
        badge_left = badge_right - (170 * scale)
        badge_top = self.MARGIN_Y + (18 * scale)
        badge_bottom = badge_top + (34 * scale)
        draw.rounded_rectangle(
            (badge_left, badge_top, badge_right, badge_bottom),
            radius=16 * scale,
            fill=self.PROGRAM_BG,
            outline=None,
        )
        draw.text(
            (badge_left + (16 * scale), badge_top + (8 * scale)),
            _safe_pdf_text(APP_NAME),
            font=fonts["program"],
            fill=self.TITLE_COLOR,
        )

        draw.text(
            (text_x, self.MARGIN_Y + (20 * scale)),
            _safe_pdf_text("Relatorio de Pendencias"),
            font=fonts["title"],
            fill=self.TITLE_COLOR,
        )
        draw.text(
            (text_x, self.MARGIN_Y + (68 * scale)),
            _safe_pdf_text(f'Periodo analisado: {export_context["period_label"]}'),
            font=fonts["body"],
            fill=self.BODY_TEXT,
        )
        draw.text(
            (text_x, self.MARGIN_Y + (92 * scale)),
            _safe_pdf_text(f'Empresas: {export_context["company_label"]}'),
            font=fonts["body"],
            fill=self.BODY_TEXT,
        )
        page_text = _safe_pdf_text(f"Pagina {page_number}  |  Gerado em {export_context['generated_at']}")
        text_box = draw.textbbox((0, 0), page_text, font=fonts["small"])
        draw.text(
            (self.MARGIN_X + content_width - (text_box[2] - text_box[0]) - (24 * scale), self.MARGIN_Y + (92 * scale)),
            page_text,
            font=fonts["small"],
            fill=self.MUTED_TEXT,
        )

        summary_top = header_bottom + (20 * scale)
        cards = (
            ("Empresas no filtro", str(len(export_context["report"]["companies"]))),
            ("Empresas com pendencias", str(export_context["report"]["pending_company_count"])),
            ("Pendencias listadas", str(len(export_context["rows"]))),
            ("Meses no relatorio", str(len(export_context["report"]["periodos"]))),
        )
        gap = 18 * scale
        card_width = int((content_width - (gap * 3)) / 4)
        for index, (label, value) in enumerate(cards):
            x = self.MARGIN_X + (index * (card_width + gap))
            self._draw_summary_card(draw, x, summary_top, card_width, label, value, fonts)

        table_top = summary_top + self.SUMMARY_HEIGHT + (18 * scale)
        self._draw_table_header(draw, table_top, fonts)
        return table_top + self.TABLE_HEADER_HEIGHT

    def _draw_summary_card(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        top_y: int,
        width: int,
        label: str,
        value: str,
        fonts: dict,
    ) -> None:
        scale = self.SCALE
        bottom_y = top_y + self.SUMMARY_HEIGHT
        draw.rounded_rectangle(
            (x, top_y, x + width, bottom_y),
            radius=20 * scale,
            fill=self.SUMMARY_BG,
            outline=self.BORDER_COLOR,
            width=2 * scale,
        )
        draw.text((x + (18 * scale), top_y + (16 * scale)), _safe_pdf_text(label), font=fonts["small_bold"], fill=self.MUTED_TEXT)
        draw.text((x + (18 * scale), top_y + (42 * scale)), _safe_pdf_text(value), font=fonts["metric"], fill=self.TITLE_COLOR)

    def _draw_table_header(self, draw: ImageDraw.ImageDraw, top_y: int, fonts: dict) -> None:
        scale = self.SCALE
        table_width = sum(width for _key, _label, width, _font in self.TABLE_COLUMNS)
        draw.rounded_rectangle(
            (self.MARGIN_X, top_y, self.MARGIN_X + table_width, top_y + self.TABLE_HEADER_HEIGHT),
            radius=14 * scale,
            fill=self.TABLE_HEADER_BG,
            outline=self.TABLE_HEADER_BG,
        )
        current_x = self.MARGIN_X
        for _key, label, width, _font in self.TABLE_COLUMNS:
            draw.text(
                (current_x + self.ROW_PADDING_X, top_y + (11 * scale)),
                _safe_pdf_text(label),
                font=fonts["small_bold"],
                fill=self.TABLE_HEADER_TEXT,
            )
            current_x += width

    def _wrap_row(self, draw: ImageDraw.ImageDraw, row: dict, fonts: dict) -> dict[str, list[str]]:
        values = {
            "empresa": _safe_pdf_text(row["empresa"]),
            "periodo": _safe_pdf_text(row["periodo"]),
            "quantidade": str(len(row["pendencias"])),
            "pendencias": row["pendencias"],
        }
        wrapped: dict[str, list[str]] = {}
        for key, _label, width, _font in self.TABLE_COLUMNS:
            if key == "pendencias":
                wrapped[key] = self._wrap_pendencias(draw, values[key], fonts["body"], width - (self.ROW_PADDING_X * 2))
                continue
            font = fonts["body_bold"] if key in {"empresa", "quantidade"} else fonts["body"]
            wrapped[key] = self._wrap_text(draw, values[key], font, width - (self.ROW_PADDING_X * 2))
        return wrapped

    def _wrap_pendencias(
        self,
        draw: ImageDraw.ImageDraw,
        pendencias: list[str],
        font,
        width: int,
    ) -> list[str]:
        lines: list[str] = []
        for pending_index, pending in enumerate(pendencias, start=1):
            wrapped_pending = self._wrap_text(draw, _safe_pdf_text(f"{pending_index}. {pending}"), font, width)
            lines.extend(wrapped_pending)
        return lines or [""]

    def _wrap_text(self, draw: ImageDraw.ImageDraw, value: str, font, width: int) -> list[str]:
        normalized = " ".join(str(value).split())
        if not normalized:
            return [""]
        words = normalized.split(" ")
        lines: list[str] = []
        current_line = ""
        for word in words:
            candidate = word if not current_line else f"{current_line} {word}"
            if draw.textlength(candidate, font=font) <= width:
                current_line = candidate
                continue
            if current_line:
                lines.append(current_line)
                current_line = word
                continue
            pieces = textwrap.wrap(
                word,
                width=max(4, int(width / (11 * self.SCALE))),
                break_long_words=True,
                break_on_hyphens=False,
            )
            if pieces:
                lines.extend(pieces[:-1])
                current_line = pieces[-1]
        if current_line:
            lines.append(current_line)
        return lines or [normalized]

    def _calculate_row_height(self, wrapped_row: dict[str, list[str]]) -> float:
        line_count = max(len(lines) for lines in wrapped_row.values())
        return max(50 * self.SCALE, (line_count * 24 * self.SCALE) + (self.ROW_PADDING_Y * 2))

    def _draw_row(
        self,
        draw: ImageDraw.ImageDraw,
        wrapped_row: dict[str, list[str]],
        top_y: float,
        row_height: float,
        row_index: int,
        fonts: dict,
    ) -> None:
        scale = self.SCALE
        table_width = sum(width for _key, _label, width, _font in self.TABLE_COLUMNS)
        fill_color = self.STRIPE_BG if row_index % 2 == 0 else None
        draw.rounded_rectangle(
            (self.MARGIN_X, top_y, self.MARGIN_X + table_width, top_y + row_height),
            radius=12 * scale,
            fill=fill_color,
            outline=self.BORDER_COLOR,
            width=2 * scale,
        )

        current_x = self.MARGIN_X
        for key, _label, width, font_weight in self.TABLE_COLUMNS:
            font = fonts["body_bold"] if font_weight == "bold" else fonts["body"]
            text_y = top_y + self.ROW_PADDING_Y
            for line_index, line in enumerate(wrapped_row[key]):
                draw.text(
                    (current_x + self.ROW_PADDING_X, text_y + (line_index * 24 * scale)),
                    line,
                    font=font,
                    fill=self.BODY_TEXT,
                )
            current_x += width
            if current_x < self.MARGIN_X + table_width:
                draw.line(
                    ((current_x, top_y + (10 * scale)), (current_x, top_y + row_height - (10 * scale))),
                    fill=self.BORDER_COLOR,
                    width=1 * scale,
                )


def _safe_pdf_text(value: str) -> str:
    normalized = " ".join(str(value or "").split())
    try:
        normalized.encode("latin-1")
        return normalized
    except UnicodeEncodeError:
        ascii_value = unicodedata.normalize("NFKD", normalized).encode("ascii", "ignore").decode("ascii")
        return ascii_value or normalized
