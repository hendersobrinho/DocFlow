from __future__ import annotations

from documentos_empresa_app.services.collection_service import CollectionService
from documentos_empresa_app.services.panorama_service import PanoramaService

MONTH_STATUS_OVERDUE = "mes_em_atraso"

UI_SITUATION_LABELS = {
    MONTH_STATUS_OVERDUE: "Em atraso",
    PanoramaService.SITUATION_COM_PENDENCIA: "Com pendência",
    PanoramaService.SITUATION_EM_ANDAMENTO: "Em andamento",
    PanoramaService.SITUATION_NAO_INICIADA: "Dentro do prazo",
    PanoramaService.SITUATION_SEM_DOCUMENTOS: "Sem documentos",
    PanoramaService.SITUATION_CONCLUIDA: "Concluída",
    PanoramaService.SITUATION_SEM_COBRANCA: "Sem cobrança",
}

UI_SITUATION_PRIORITIES = {
    MONTH_STATUS_OVERDUE: 0,
    PanoramaService.SITUATION_COM_PENDENCIA: 1,
    PanoramaService.SITUATION_EM_ANDAMENTO: 2,
    PanoramaService.SITUATION_NAO_INICIADA: 3,
    PanoramaService.SITUATION_SEM_DOCUMENTOS: 4,
    PanoramaService.SITUATION_CONCLUIDA: 5,
    PanoramaService.SITUATION_SEM_COBRANCA: 6,
}

COLLECTION_UP_TO_DATE_LABEL = "Em dia"


class PanoramaViewModel:
    """Deriva as linhas do Panorama/Dashboard a partir das visoes de servico.

    Logica portada da antiga PanoramaTab (tkinter): recorta a fila de cobranca
    ate o periodo selecionado, calcula pendencias anteriores, sobrepoe o status
    'mes em atraso' e ordena por prioridade de cobranca/situacao.
    """

    def __init__(self, services) -> None:
        self.services = services
        self.periods_by_id: dict[int, dict] = {}
        self.rows: list[dict] = []
        self.queue_by_company: dict[int, dict | None] = {}
        self.periodo: dict | None = None

    def load(self, period_id: int, active_only: bool) -> None:
        periodos = self.services.periodo_service.list_periodos()
        self.periods_by_id = {p["id"]: p for p in periodos}

        monthly_view = self.services.panorama_service.build_monthly_view(period_id, active_only=active_only)
        # So leitura: os itens sao copiados em _build_queue_item_until_selected_period.
        queue_view = self.services.collection_service.queue_snapshot(active_only=active_only)

        self.periodo = monthly_view.get("periodo")
        self.queue_by_company = {
            item["empresa_id"]: self._build_queue_item_until_selected_period(item, period_id)
            for item in queue_view["items"]
        }
        self.rows = self._merge_monthly_rows_with_queue(monthly_view["rows"], period_id)

    def count_month_statuses(self, rows: list[dict] | None = None) -> dict[str, int]:
        counts = {key: 0 for key in UI_SITUATION_LABELS}
        for row in rows if rows is not None else self.rows:
            counts[row["month_status_key"]] += 1
        return counts

    # Derivacao portada

    def _period_sort_key(self, period_id: int | None) -> int | None:
        if period_id is None:
            return None
        periodo = self.periods_by_id.get(period_id)
        if not periodo:
            return None
        return (periodo["ano"] * 100) + periodo["mes"]

    def _merge_monthly_rows_with_queue(self, rows: list[dict], selected_period_id: int) -> list[dict]:
        merged_rows: list[dict] = []
        selected_period_key = self._period_sort_key(selected_period_id)

        for row in rows:
            merged = dict(row)
            queue_item = self.queue_by_company.get(row["empresa_id"])
            previous_period_items = self._previous_period_items(queue_item, selected_period_key)
            merged["queue_item"] = queue_item
            merged["previous_period_items"] = previous_period_items
            merged["selected_period_collection_item"] = self._selected_period_collection_item(
                queue_item, selected_period_id
            )
            merged["month_status_key"] = self._row_month_status_key(merged)

            if not queue_item:
                merged["collection_status_key"] = "em_dia"
                merged["collection_status"] = COLLECTION_UP_TO_DATE_LABEL
            elif previous_period_items:
                merged["collection_status_key"] = CollectionService.PHASE_EM_ATRASO
                merged["collection_status"] = CollectionService.PHASE_LABELS[CollectionService.PHASE_EM_ATRASO]
            else:
                merged["collection_status_key"] = queue_item["phase_key"]
                merged["collection_status"] = queue_item["phase_label"]

            merged_rows.append(merged)

        merged_rows.sort(
            key=lambda item: (
                self._collection_priority(item["collection_status_key"]),
                UI_SITUATION_PRIORITIES.get(item["month_status_key"], 99),
                item["codigo_empresa"],
                item["nome_empresa"].casefold(),
            )
        )
        return merged_rows

    def _build_queue_item_until_selected_period(self, item: dict, selected_period_id: int) -> dict | None:
        selected_period_key = self._period_sort_key(selected_period_id)
        if selected_period_key is None:
            return None

        relevant_period_items = [
            {
                **period_item,
                "documents": [dict(document) for document in period_item["documents"]],
            }
            for period_item in item["period_items"]
            if (self._period_sort_key(period_item["periodo_id"]) or 0) <= selected_period_key
        ]
        if not relevant_period_items:
            return None

        relevant_period_items.sort(key=lambda period_item: self._period_sort_key(period_item["periodo_id"]) or 0)
        phase_key = (
            CollectionService.PHASE_EM_ATRASO
            if any(
                period_item["phase_key"] == CollectionService.PHASE_EM_ATRASO
                for period_item in relevant_period_items
            )
            else CollectionService.PHASE_EM_COBRANCA
        )
        primary_period = self._pick_primary_period(relevant_period_items)
        documents = [
            {
                **document,
                "periodo_id": period_item["periodo_id"],
                "periodo_label": period_item["periodo_label"],
            }
            for period_item in relevant_period_items
            for document in period_item["documents"]
        ]
        return {
            "empresa_id": item["empresa_id"],
            "codigo_empresa": item["codigo_empresa"],
            "nome_empresa": item["nome_empresa"],
            "empresa_ativa": item["empresa_ativa"],
            "email_contato": item["email_contato"],
            "nome_contato": item["nome_contato"],
            "period_items": relevant_period_items,
            "period_count": len(relevant_period_items),
            "document_count": len(documents),
            "documents": documents,
            "days_after_end": max(period_item["days_after_end"] for period_item in relevant_period_items),
            "alert_ready": any(period_item["alert_ready"] for period_item in relevant_period_items),
            "settings_source": item["settings_source"],
            "phase_key": phase_key,
            "phase_label": CollectionService.PHASE_LABELS[phase_key],
            "primary_period": primary_period,
            "primary_period_id": primary_period["periodo_id"],
            "primary_period_label": primary_period["periodo_label"],
            "window_start": primary_period["window_start"],
            "window_end": primary_period["window_end"],
            "alerta_apos_dias": primary_period["alerta_apos_dias"],
            "period_summary": self._build_period_summary(relevant_period_items),
            "suggested_channel": self._resolve_suggested_channel(item, documents),
        }

    def _previous_period_items(self, queue_item: dict | None, selected_period_key: int | None) -> list[dict]:
        if not queue_item or selected_period_key is None:
            return []
        return [
            period_item
            for period_item in queue_item["period_items"]
            if (self._period_sort_key(period_item["periodo_id"]) or 0) < selected_period_key
        ]

    def _selected_period_collection_item(self, queue_item: dict | None, selected_period_id: int) -> dict | None:
        if not queue_item:
            return None
        return next(
            (
                period_item
                for period_item in queue_item["period_items"]
                if period_item["periodo_id"] == selected_period_id
            ),
            None,
        )

    def _row_month_status_key(self, row: dict) -> str:
        selected_period_collection = row.get("selected_period_collection_item")
        if selected_period_collection and selected_period_collection["phase_key"] == CollectionService.PHASE_EM_ATRASO:
            return MONTH_STATUS_OVERDUE
        return row["situacao_key"]

    def _collection_priority(self, collection_status_key: str) -> int:
        if collection_status_key == CollectionService.PHASE_EM_ATRASO:
            return 0
        if collection_status_key == CollectionService.PHASE_EM_COBRANCA:
            return 1
        return 2

    def _pick_primary_period(self, period_items: list[dict]) -> dict:
        overdue_items = [item for item in period_items if item["phase_key"] == CollectionService.PHASE_EM_ATRASO]
        target_items = overdue_items or period_items
        return sorted(
            target_items,
            key=lambda item: (self._period_sort_key(item["periodo_id"]) or 0, -item["days_after_end"]),
        )[0]

    def _build_period_summary(self, period_items: list[dict]) -> str:
        if len(period_items) == 1:
            return period_items[0]["periodo_label"]
        first_label = period_items[0]["periodo_label"]
        last_label = period_items[-1]["periodo_label"]
        return f"{first_label} até {last_label} ({len(period_items)} meses)"

    def _resolve_suggested_channel(self, item: dict, documents: list[dict]) -> str:
        available_methods: list[str] = []
        for document in documents:
            available_methods.extend(document.get("meios_recebimento") or [])
        available_set = {method.casefold(): method for method in available_methods}
        if item.get("email_contato"):
            return "Email"
        if "whatsapp" in available_set:
            return "WhatsApp"
        if available_methods:
            return available_methods[0]
        return "Manual"
