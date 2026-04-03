from __future__ import annotations

import sqlite3

from documentos_empresa_app.database.repositories import TipoRepository
from documentos_empresa_app.utils.common import ValidationError
from documentos_empresa_app.utils.type_names import canonicalize_tipo_name


class TipoService:
    def __init__(self, tipo_repository: TipoRepository) -> None:
        self.tipo_repository = tipo_repository

    def list_tipos(self) -> list[dict]:
        return self.tipo_repository.list_all()

    def get_tipo(self, tipo_id: int) -> dict:
        tipo = self.tipo_repository.get_by_id(tipo_id)
        if not tipo:
            raise ValidationError("Tipo de documento nao encontrado.")
        return tipo

    def get_or_create_tipo(self, nome_tipo: str) -> dict:
        tipo, _created = self.ensure_tipo(nome_tipo)
        return tipo

    def ensure_tipo(self, nome_tipo: str) -> tuple[dict, bool]:
        nome = self._normalize_name(nome_tipo)
        existing = self.tipo_repository.get_by_name(nome)
        if existing:
            return existing, False
        tipo_id = self.create_tipo(nome)
        return self.get_tipo(tipo_id), True

    def create_tipo(self, nome_tipo: str) -> int:
        nome = self._normalize_name(nome_tipo)
        if self.tipo_repository.get_by_name(nome):
            raise ValidationError("Ja existe um tipo com esse nome.")
        try:
            return self.tipo_repository.create(nome)
        except sqlite3.IntegrityError as exc:
            raise ValidationError("Nao foi possivel cadastrar o tipo.") from exc

    def update_tipo(self, tipo_id: int, nome_tipo: str) -> None:
        self.get_tipo(tipo_id)
        nome = self._normalize_name(nome_tipo)
        existing = self.tipo_repository.get_by_name(nome)
        if existing and existing["id"] != tipo_id:
            raise ValidationError("Ja existe um tipo com esse nome.")
        self.tipo_repository.update(tipo_id, nome)

    def delete_tipo(self, tipo_id: int) -> None:
        self.get_tipo(tipo_id)
        if self.tipo_repository.is_in_use(tipo_id):
            raise ValidationError("Nao e possivel excluir um tipo que esta em uso.")
        self.tipo_repository.delete(tipo_id)

    def _normalize_name(self, nome_tipo: str) -> str:
        normalized = canonicalize_tipo_name(nome_tipo)
        if not normalized:
            raise ValidationError("O nome do tipo nao pode ficar vazio.")
        return normalized
