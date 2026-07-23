from __future__ import annotations

from calendar import monthrange
from datetime import date

from documentos_empresa_app.database.repositories import (
    CollectionConfigRepository,
    DocumentoRepository,
    EmpresaRepository,
    PeriodoRepository,
    StatusRepository,
)
from documentos_empresa_app.utils.common import (
    ValidationError,
    build_chargeable_closure_key_map,
    format_period_label,
    is_chargeable_period,
    month_key,
    normalize_type_occurrence_rule,
    parse_delivery_methods,
)


class CollectionService:
    PHASE_EM_COBRANCA = "em_cobranca"
    PHASE_EM_ATRASO = "em_atraso"

    PHASE_LABELS = {
        PHASE_EM_COBRANCA: "Em cobranca",
        PHASE_EM_ATRASO: "Em atraso",
    }

    def __init__(
        self,
        collection_config_repository: CollectionConfigRepository,
        empresa_repository: EmpresaRepository,
        documento_repository: DocumentoRepository,
        periodo_repository: PeriodoRepository,
        status_repository: StatusRepository,
    ) -> None:
        self.collection_config_repository = collection_config_repository
        self.empresa_repository = empresa_repository
        self.documento_repository = documento_repository
        self.periodo_repository = periodo_repository
        self.status_repository = status_repository

    def get_global_settings(self) -> dict:
        settings = self.collection_config_repository.get_settings()
        return {
            "inicio_cobranca_dia": settings["inicio_cobranca_dia"],
            "encerramento_cobranca_dia": settings["encerramento_cobranca_dia"],
            "alerta_apos_dias": settings["alerta_apos_dias"],
        }

    def update_global_settings(
        self,
        inicio_cobranca_dia,
        encerramento_cobranca_dia,
        alerta_apos_dias,
    ) -> dict:
        normalized = self._normalize_rule_values(
            inicio_cobranca_dia,
            encerramento_cobranca_dia,
            alerta_apos_dias,
            allow_blank=False,
        )
        self.collection_config_repository.upsert_settings(
            normalized["inicio_cobranca_dia"],
            normalized["encerramento_cobranca_dia"],
            normalized["alerta_apos_dias"],
        )
        return self.get_global_settings()

    def get_company_settings(self, company_id: int) -> dict:
        company = self.empresa_repository.get_by_id(company_id)
        if not company:
            raise ValidationError("Empresa nao encontrada.")
        return self._extract_company_settings(company)

    def update_company_settings(
        self,
        company_id: int,
        inicio_cobranca_dia,
        encerramento_cobranca_dia,
        alerta_apos_dias,
    ) -> dict:
        company = self.empresa_repository.get_by_id(company_id)
        if not company:
            raise ValidationError("Empresa nao encontrada.")

        normalized = self._normalize_rule_values(
            inicio_cobranca_dia,
            encerramento_cobranca_dia,
            alerta_apos_dias,
            allow_blank=True,
        )
        effective = self._merge_settings(self.get_global_settings(), normalized)
        self._validate_rule_range(
            effective["inicio_cobranca_dia"],
            effective["encerramento_cobranca_dia"],
            effective["alerta_apos_dias"],
        )
        self.empresa_repository.update_collection_settings(
            company_id,
            normalized["inicio_cobranca_dia"],
            normalized["encerramento_cobranca_dia"],
            normalized["alerta_apos_dias"],
        )
        return self.get_company_settings(company_id)

    def validate_company_settings_values(
        self,
        inicio_cobranca_dia,
        encerramento_cobranca_dia,
        alerta_apos_dias,
    ) -> dict:
        normalized = self._normalize_rule_values(
            inicio_cobranca_dia,
            encerramento_cobranca_dia,
            alerta_apos_dias,
            allow_blank=True,
        )
        effective = self._merge_settings(self.get_global_settings(), normalized)
        self._validate_rule_range(
            effective["inicio_cobranca_dia"],
            effective["encerramento_cobranca_dia"],
            effective["alerta_apos_dias"],
        )
        return normalized

    def build_collection_queue(
        self,
        reference_date: date | None = None,
        active_only: bool = True,
    ) -> dict:
        today = reference_date or date.today()
        global_settings = self.get_global_settings()
        companies = self.empresa_repository.list_all(active_only=active_only)
        company_ids = [company["id"] for company in companies]
        documents = self.documento_repository.list_by_company_ids(company_ids)
        documents_by_company: dict[int, list[dict]] = {}
        for document in documents:
            documents_by_company.setdefault(document["empresa_id"], []).append(document)

        periodos = self.periodo_repository.list_all()
        period_ids = [periodo["id"] for periodo in periodos]
        document_ids = [document["id"] for document in documents]
        statuses = {
            (row["documento_empresa_id"], row["periodo_id"]): row
            for row in self.status_repository.list_for_documents_and_periods(document_ids, period_ids)
        }
        closures = self._get_closure_key_map(documents)

        period_items: list[dict] = []

        for company in companies:
            company_documents = documents_by_company.get(company["id"], [])
            if not company_documents:
                continue

            company_settings = self._merge_settings(global_settings, self._extract_company_settings(company))
            for periodo in periodos:
                window = self._build_collection_window(periodo["ano"], periodo["mes"], company_settings)
                if today < window["inicio"]:
                    continue

                pending_documents: list[dict] = []
                for document in company_documents:
                    if not self._is_document_chargeable(document, periodo, closures.get(document["id"])):
                        continue

                    status_row = statuses.get((document["id"], periodo["id"]))
                    status = (status_row["status"] or "") if status_row else ""
                    if status in {"Recebido", "Encerrado"}:
                        continue

                    pending_documents.append(
                        {
                            "documento_id": document["id"],
                            "tipo_documento": document["nome_tipo"],
                            "nome_documento": document["nome_documento"],
                            "status": status or "Nao iniciado",
                            "meios_recebimento": parse_delivery_methods(document.get("meios_recebimento")),
                            "updated_at": status_row.get("updated_at") if status_row else None,
                            "periodo_id": periodo["id"],
                            "periodo_label": format_period_label(periodo["ano"], periodo["mes"]),
                        }
                    )

                if not pending_documents:
                    continue

                phase_key = self.PHASE_EM_ATRASO if today > window["fim"] else self.PHASE_EM_COBRANCA
                days_after_end = max((today - window["fim"]).days, 0) if phase_key == self.PHASE_EM_ATRASO else 0
                alert_ready = phase_key == self.PHASE_EM_ATRASO and days_after_end >= window["alerta_apos_dias"]
                period_label = format_period_label(periodo["ano"], periodo["mes"])

                period_items.append(
                    {
                        "empresa_id": company["id"],
                        "codigo_empresa": company["codigo_empresa"],
                        "nome_empresa": company["nome_empresa"],
                        "empresa_ativa": company["ativa"],
                        "email_contato": company.get("email_contato") or "",
                        "nome_contato": company.get("nome_contato") or "",
                        "periodo_id": periodo["id"],
                        "periodo_label": period_label,
                        "phase_key": phase_key,
                        "phase_label": self.PHASE_LABELS[phase_key],
                        "documents": pending_documents,
                        "document_count": len(pending_documents),
                        "window_start": window["inicio"],
                        "window_end": window["fim"],
                        "alerta_apos_dias": window["alerta_apos_dias"],
                        "days_after_end": days_after_end,
                        "alert_ready": alert_ready,
                        "settings_source": "empresa" if self._company_has_custom_settings(company) else "global",
                    }
                )

        items = self._group_company_items(period_items)
        summary = {
            "total": len(items),
            self.PHASE_EM_COBRANCA: sum(1 for item in items if item["phase_key"] == self.PHASE_EM_COBRANCA),
            self.PHASE_EM_ATRASO: sum(1 for item in items if item["phase_key"] == self.PHASE_EM_ATRASO),
            "alert_ready": sum(1 for item in items if item["alert_ready"]),
        }

        items.sort(
            key=lambda item: (
                0 if item["alert_ready"] else 1,
                0 if item["phase_key"] == self.PHASE_EM_ATRASO else 1,
                -item["days_after_end"],
                item["codigo_empresa"],
            )
        )
        return {
            "reference_date": today,
            "items": items,
            "summary": summary,
            "global_settings": global_settings,
        }

    def _group_company_items(self, period_items: list[dict]) -> list[dict]:
        grouped: dict[int, dict] = {}
        for period_item in period_items:
            company_item = grouped.get(period_item["empresa_id"])
            if company_item is None:
                company_item = {
                    "empresa_id": period_item["empresa_id"],
                    "codigo_empresa": period_item["codigo_empresa"],
                    "nome_empresa": period_item["nome_empresa"],
                    "empresa_ativa": period_item["empresa_ativa"],
                    "email_contato": period_item["email_contato"],
                    "nome_contato": period_item["nome_contato"],
                    "period_items": [],
                    "document_count": 0,
                    "period_count": 0,
                    "days_after_end": 0,
                    "alert_ready": False,
                    "settings_source": period_item["settings_source"],
                }
                grouped[period_item["empresa_id"]] = company_item

            company_item["period_items"].append(period_item)
            company_item["document_count"] += period_item["document_count"]
            company_item["period_count"] += 1
            company_item["days_after_end"] = max(company_item["days_after_end"], period_item["days_after_end"])
            company_item["alert_ready"] = company_item["alert_ready"] or period_item["alert_ready"]

        items: list[dict] = []
        for company_item in grouped.values():
            company_item["period_items"].sort(key=lambda item: item["periodo_id"])
            company_item["phase_key"] = (
                self.PHASE_EM_ATRASO
                if any(item["phase_key"] == self.PHASE_EM_ATRASO for item in company_item["period_items"])
                else self.PHASE_EM_COBRANCA
            )
            company_item["phase_label"] = self.PHASE_LABELS[company_item["phase_key"]]
            company_item["primary_period"] = self._pick_primary_period(company_item["period_items"])
            company_item["primary_period_id"] = company_item["primary_period"]["periodo_id"]
            company_item["primary_period_label"] = company_item["primary_period"]["periodo_label"]
            company_item["window_start"] = company_item["primary_period"]["window_start"]
            company_item["window_end"] = company_item["primary_period"]["window_end"]
            company_item["alerta_apos_dias"] = company_item["primary_period"]["alerta_apos_dias"]
            company_item["period_summary"] = self._build_period_summary(company_item["period_items"])
            company_item["documents"] = [
                {**document, "periodo_label": period_item["periodo_label"], "periodo_id": period_item["periodo_id"]}
                for period_item in company_item["period_items"]
                for document in period_item["documents"]
            ]
            company_item["suggested_channel"] = self._resolve_suggested_channel(
                company_item,
                company_item["documents"],
            )
            items.append(company_item)
        return items

    def build_email_draft(self, item: dict) -> dict:
        if not item.get("email_contato"):
            raise ValidationError("A empresa selecionada nao possui email de contato cadastrado.")

        contact_name = item.get("nome_contato") or item["nome_empresa"]
        subject = f'Documentos em aberto - {item["nome_empresa"]}'
        body_lines = [
            f"Olá, {contact_name}.",
            "",
            "Espero que esteja bem.",
            "",
            (
                f'Gostariamos de compartilhar a relacao atualizada de documentos em aberto da empresa '
                f'{item["codigo_empresa"]} - {item["nome_empresa"]}.'
            ),
            "",
        ]
        if item["phase_key"] == self.PHASE_EM_ATRASO:
            body_lines.append(
                "Ha itens fora do prazo previsto e, quando aplicavel, tambem registros de meses anteriores."
            )
        else:
            body_lines.append("Segue abaixo a relacao atualizada dos itens que seguem em acompanhamento.")
        body_lines.extend(["", "Documentos em aberto por periodo:", ""])
        for period_item in item["period_items"]:
            body_lines.append(f'{period_item["periodo_label"]} - {period_item["phase_label"]}')
            for document in period_item["documents"]:
                body_lines.append(f'- {document["nome_documento"]} ({document["status"]})')
            body_lines.append("")
        body_lines.extend(
            [
                "Quando possivel, pedimos a gentileza de nos informar uma previsao ou nos encaminhar um retorno sobre esses itens.",
                "",
                "Agradecemos desde ja pela atencao.",
            ]
        )
        return {
            "to": item["email_contato"],
            "subject": subject,
            "body": "\n".join(body_lines),
        }

    def build_whatsapp_message(self, item: dict) -> str:
        contact_name = item.get("nome_contato") or item["nome_empresa"]
        lines = [
            f"Olá, {contact_name}. Tudo bem?",
            "",
            "Espero que esteja bem.",
            "",
            f'Segue a relacao de documentos em aberto de {item["codigo_empresa"]} - {item["nome_empresa"]}:',
            "",
        ]
        for period_item in item["period_items"]:
            lines.append(f'{period_item["periodo_label"]}:')
            lines.extend(f'- {document["nome_documento"]}' for document in period_item["documents"])
            lines.append("")
        lines.extend(
            [
                "",
                "Quando possivel, poderia nos confirmar o recebimento e, se necessario, nos informar uma previsao?",
                "",
                "Agradecemos pela atencao.",
            ]
        )
        return "\n".join(lines)

    def _pick_primary_period(self, period_items: list[dict]) -> dict:
        overdue_items = [item for item in period_items if item["phase_key"] == self.PHASE_EM_ATRASO]
        target_items = overdue_items or period_items
        return sorted(target_items, key=lambda item: (item["periodo_id"], -item["days_after_end"]))[0]

    def _build_period_summary(self, period_items: list[dict]) -> str:
        if len(period_items) == 1:
            return period_items[0]["periodo_label"]
        first_label = period_items[0]["periodo_label"]
        last_label = period_items[-1]["periodo_label"]
        return f"{first_label} ate {last_label} ({len(period_items)} meses)"

    def _extract_company_settings(self, company: dict) -> dict:
        return {
            "inicio_cobranca_dia": company.get("cobranca_inicio_dia"),
            "encerramento_cobranca_dia": company.get("cobranca_fim_dia"),
            "alerta_apos_dias": company.get("cobranca_alerta_dias"),
        }

    def _company_has_custom_settings(self, company: dict) -> bool:
        return any(
            company.get(field) is not None
            for field in ("cobranca_inicio_dia", "cobranca_fim_dia", "cobranca_alerta_dias")
        )

    def _normalize_rule_values(
        self,
        inicio_cobranca_dia,
        encerramento_cobranca_dia,
        alerta_apos_dias,
        *,
        allow_blank: bool,
    ) -> dict:
        normalized = {
            "inicio_cobranca_dia": self._parse_optional_int(inicio_cobranca_dia, "Dia inicial da cobranca", allow_blank),
            "encerramento_cobranca_dia": self._parse_optional_int(
                encerramento_cobranca_dia,
                "Dia final da cobranca",
                allow_blank,
            ),
            "alerta_apos_dias": self._parse_optional_int(
                alerta_apos_dias,
                "Dias para alerta",
                allow_blank,
                minimum=0,
            ),
        }
        if not allow_blank:
            self._validate_rule_range(
                normalized["inicio_cobranca_dia"],
                normalized["encerramento_cobranca_dia"],
                normalized["alerta_apos_dias"],
            )
        return normalized

    def _parse_optional_int(
        self,
        value,
        field_label: str,
        allow_blank: bool,
        *,
        minimum: int = 1,
    ) -> int | None:
        normalized = str(value or "").strip()
        if not normalized:
            if allow_blank:
                return None
            raise ValidationError(f"Informe {field_label.lower()}.")
        try:
            parsed = int(normalized)
        except ValueError as exc:
            raise ValidationError(f"{field_label} deve ser um numero inteiro.") from exc
        if parsed < minimum:
            raise ValidationError(f"{field_label} nao pode ser menor que {minimum}.")
        if minimum >= 1 and parsed > 31:
            raise ValidationError(f"{field_label} nao pode ser maior que 31.")
        return parsed

    def _validate_rule_range(self, inicio_cobranca_dia: int, encerramento_cobranca_dia: int, alerta_apos_dias: int) -> None:
        if inicio_cobranca_dia > encerramento_cobranca_dia:
            raise ValidationError("O dia inicial da cobranca nao pode ser maior que o dia final.")
        if alerta_apos_dias < 0:
            raise ValidationError("Os dias para alerta nao podem ser negativos.")

    def _merge_settings(self, global_settings: dict, company_settings: dict) -> dict:
        return {
            "inicio_cobranca_dia": company_settings.get("inicio_cobranca_dia")
            if company_settings.get("inicio_cobranca_dia") is not None
            else global_settings["inicio_cobranca_dia"],
            "encerramento_cobranca_dia": company_settings.get("encerramento_cobranca_dia")
            if company_settings.get("encerramento_cobranca_dia") is not None
            else global_settings["encerramento_cobranca_dia"],
            "alerta_apos_dias": company_settings.get("alerta_apos_dias")
            if company_settings.get("alerta_apos_dias") is not None
            else global_settings["alerta_apos_dias"],
        }

    def _build_collection_window(self, year: int, month: int, settings: dict) -> dict:
        target_month = month + 1
        target_year = year
        if target_month == 13:
            target_month = 1
            target_year += 1

        last_day = monthrange(target_year, target_month)[1]
        start_day = min(settings["inicio_cobranca_dia"], last_day)
        end_day = min(settings["encerramento_cobranca_dia"], last_day)
        start_date = date(target_year, target_month, start_day)
        end_date = date(target_year, target_month, end_day)
        return {
            "inicio": start_date,
            "fim": end_date,
            "alerta_apos_dias": settings["alerta_apos_dias"],
        }

    def _resolve_suggested_channel(self, company: dict, pending_documents: list[dict]) -> str:
        available_methods: list[str] = []
        for document in pending_documents:
            available_methods.extend(document["meios_recebimento"])
        available_set = {item.casefold(): item for item in available_methods}
        if company.get("email_contato"):
            return "Email"
        if "whatsapp" in available_set:
            return "WhatsApp"
        if available_methods:
            return available_methods[0]
        if company.get("email_contato"):
            return "Email"
        return "Manual"

    def _is_document_chargeable(self, document: dict, periodo: dict, closure_key: int | None) -> bool:
        occurrence_rule = normalize_type_occurrence_rule(document.get("regra_ocorrencia"))
        if not is_chargeable_period(occurrence_rule, periodo["mes"]):
            return False
        current_key = month_key(periodo["ano"], periodo["mes"])
        return closure_key is None or current_key <= closure_key

    def _get_closure_key_map(self, documents: list[dict]) -> dict[int, int]:
        document_ids = [document["id"] for document in documents]
        occurrence_by_document = {
            document["id"]: normalize_type_occurrence_rule(document.get("regra_ocorrencia"))
            for document in documents
        }
        closure_rows = self.status_repository.list_closures_for_documents(document_ids)
        return build_chargeable_closure_key_map(closure_rows, occurrence_by_document)
