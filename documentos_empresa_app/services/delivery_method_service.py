from __future__ import annotations

import sqlite3

from documentos_empresa_app.database.repositories import DeliveryMethodRepository, DocumentoRepository
from documentos_empresa_app.services.audit_service import AuditService
from documentos_empresa_app.services.session_service import SessionService
from documentos_empresa_app.utils.common import ValidationError, normalize_delivery_methods, parse_delivery_methods


class DeliveryMethodService:
    def __init__(
        self,
        delivery_method_repository: DeliveryMethodRepository,
        documento_repository: DocumentoRepository,
        audit_service: AuditService | None = None,
        session_service: SessionService | None = None,
    ) -> None:
        self.delivery_method_repository = delivery_method_repository
        self.documento_repository = documento_repository
        self.audit_service = audit_service
        self.session_service = session_service

    def list_methods(self) -> list[dict]:
        return self.delivery_method_repository.list_all()

    def get_method(self, method_id: int) -> dict:
        method = self.delivery_method_repository.get_by_id(method_id)
        if not method:
            raise ValidationError("Meio de recebimento nao encontrado.")
        return method

    def create_method(self, nome_meio: str) -> int:
        nome = self._normalize_name(nome_meio)
        if self.delivery_method_repository.get_by_name(nome):
            raise ValidationError("Ja existe um meio de recebimento com esse nome.")
        try:
            method_id = self.delivery_method_repository.create(nome)
        except sqlite3.IntegrityError as exc:
            raise ValidationError("Nao foi possivel cadastrar o meio de recebimento.") from exc

        self._log(
            "CADASTRO_MEIO_RECEBIMENTO",
            method_id,
            f'Usuario {self._actor_name()} cadastrou o meio de recebimento "{nome}".',
        )
        return method_id

    def update_method(self, method_id: int, nome_meio: str) -> int:
        current = self.get_method(method_id)
        nome = self._normalize_name(nome_meio)
        existing = self.delivery_method_repository.get_by_name(nome)
        if existing and existing["id"] != method_id:
            raise ValidationError("Ja existe um meio de recebimento com esse nome.")

        with self.delivery_method_repository.db_manager.connect():
            self.delivery_method_repository.update(method_id, nome)
            affected_documents = self._rename_method_in_documents(current["nome_meio"], nome)

        self._log(
            "EDICAO_MEIO_RECEBIMENTO",
            method_id,
            (
                f'Usuario {self._actor_name()} alterou o meio de recebimento '
                f'"{current["nome_meio"]}" para "{nome}". Documentos ajustados: {affected_documents}.'
            ),
        )
        return affected_documents

    def delete_method(self, method_id: int) -> int:
        method = self.get_method(method_id)
        affected_documents = self.count_documents_using(method["nome_meio"])
        self.delivery_method_repository.delete(method_id)
        self._log(
            "EXCLUSAO_MEIO_RECEBIMENTO",
            method_id,
            (
                f'Usuario {self._actor_name()} removeu o meio de recebimento "{method["nome_meio"]}" '
                f'da lista do sistema. Documentos ainda usando esse meio: {affected_documents}.'
            ),
        )
        return affected_documents

    def count_documents_using(self, nome_meio: str) -> int:
        target = self._normalize_name(nome_meio)
        total = 0
        for document in self.documento_repository.list_all():
            methods = parse_delivery_methods(document.get("meios_recebimento"))
            if any(item.casefold() == target.casefold() for item in methods):
                total += 1
        return total

    def _rename_method_in_documents(self, old_name: str, new_name: str) -> int:
        if old_name.casefold() == new_name.casefold():
            return 0

        affected = 0
        known_options = [item["nome_meio"] for item in self.delivery_method_repository.list_all()]
        for document in self.documento_repository.list_all():
            methods = parse_delivery_methods(document.get("meios_recebimento"), known_options=known_options)
            if not any(item.casefold() == old_name.casefold() for item in methods):
                continue

            updated_methods = [new_name if item.casefold() == old_name.casefold() else item for item in methods]
            normalized_methods = normalize_delivery_methods(updated_methods, known_options=known_options)
            if (document.get("meios_recebimento") or "") == (normalized_methods or ""):
                continue

            self.documento_repository.update_delivery_methods(document["id"], normalized_methods)
            affected += 1
        return affected

    def _normalize_name(self, nome_meio: str) -> str:
        normalized = str(nome_meio).strip()
        if not normalized:
            raise ValidationError("Informe o nome do meio de recebimento.")
        return normalized

    def _actor_name(self) -> str:
        if not self.session_service:
            return "Sistema"
        return self.session_service.get_username()

    def _log(self, acao: str, entidade_id: int, descricao: str) -> None:
        if self.audit_service:
            self.audit_service.log(
                acao,
                "meio_recebimento",
                entidade_id,
                descricao,
            )
