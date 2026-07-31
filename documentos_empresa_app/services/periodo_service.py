from __future__ import annotations

from documentos_empresa_app.database.repositories import PeriodoRepository
from documentos_empresa_app.utils.common import ValidationError, count_months_between, format_period_label


class PeriodoService:
    def __init__(self, periodo_repository: PeriodoRepository) -> None:
        self.periodo_repository = periodo_repository

    def list_periodos(self) -> list[dict]:
        periodos = self.periodo_repository.list_all()
        for periodo in periodos:
            periodo["label"] = format_period_label(periodo["ano"], periodo["mes"])
        return periodos

    def get_periodo(self, periodo_id: int) -> dict:
        periodo = self.periodo_repository.get_by_id(periodo_id)
        if not periodo:
            raise ValidationError("Periodo nao encontrado.")
        periodo["label"] = format_period_label(periodo["ano"], periodo["mes"])
        return periodo

    def list_available_years(self) -> list[int]:
        return self.periodo_repository.list_years()

    def get_or_create_periodo(self, ano, mes) -> dict:
        """Devolve o periodo do mes/ano informado, gerando o ano inteiro (generate_year e
        idempotente) se aquele mes ainda nao existir - usado pelo "dar baixa" via chat pra
        nunca esbarrar num beco sem saida so porque o calendario daquele ano nao foi gerado."""
        ano_int = self._parse_year(ano)
        try:
            mes_int = int(mes)
        except (TypeError, ValueError) as exc:
            raise ValidationError("Mes invalido (use um valor entre 1 e 12).") from exc
        if not 1 <= mes_int <= 12:
            raise ValidationError("Mes invalido (use um valor entre 1 e 12).")

        periodo = self.periodo_repository.get_by_year_month(ano_int, mes_int)
        if periodo is None:
            self.generate_year(ano_int)
            periodo = self.periodo_repository.get_by_year_month(ano_int, mes_int)
        periodo["label"] = format_period_label(periodo["ano"], periodo["mes"])
        return periodo

    def generate_year(self, ano) -> dict:
        ano_int = self._parse_year(ano)
        created = 0
        existing = 0
        for mes in range(1, 13):
            if self.periodo_repository.exists(ano_int, mes):
                existing += 1
                continue
            self.periodo_repository.create(ano_int, mes)
            created += 1
        return {"ano": ano_int, "created": created, "existing": existing}

    def delete_year(self, ano) -> dict:
        ano_int = self._parse_year(ano)
        deleted = self.periodo_repository.delete_year(ano_int)
        return {"ano": ano_int, "deleted": deleted}

    def get_periods_between(self, start_period_id: int, end_period_id: int) -> list[dict]:
        start_period = self.get_periodo(start_period_id)
        end_period = self.get_periodo(end_period_id)

        start_key = start_period["ano"] * 100 + start_period["mes"]
        end_key = end_period["ano"] * 100 + end_period["mes"]
        if start_key > end_key:
            raise ValidationError("O periodo inicial nao pode ser maior que o periodo final.")
        if count_months_between(
            start_period["ano"],
            start_period["mes"],
            end_period["ano"],
            end_period["mes"],
        ) > 12:
            raise ValidationError("A consulta permite no maximo 12 meses por vez.")

        periodos = self.periodo_repository.list_between(
            start_period["ano"],
            start_period["mes"],
            end_period["ano"],
            end_period["mes"],
        )

        for periodo in periodos:
            periodo["label"] = format_period_label(periodo["ano"], periodo["mes"])
        return periodos

    def _parse_year(self, ano) -> int:
        try:
            ano_int = int(str(ano).strip())
        except ValueError as exc:
            raise ValidationError("Informe um ano valido com 4 digitos.") from exc

        if ano_int < 1900 or ano_int > 3000:
            raise ValidationError("Informe um ano valido com 4 digitos.")
        return ano_int
