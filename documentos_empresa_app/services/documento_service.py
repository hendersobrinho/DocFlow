from __future__ import annotations

from documentos_empresa_app.database.repositories import DocumentoRepository, EmpresaRepository, TipoRepository
from documentos_empresa_app.services.audit_service import AuditService
from documentos_empresa_app.services.session_service import SessionService
from documentos_empresa_app.utils.common import ValidationError, normalize_delivery_methods


class DocumentoService:
    def __init__(
        self,
        documento_repository: DocumentoRepository,
        empresa_repository: EmpresaRepository,
        tipo_repository: TipoRepository,
        audit_service: AuditService | None = None,
        session_service: SessionService | None = None,
    ) -> None:
        self.documento_repository = documento_repository
        self.empresa_repository = empresa_repository
        self.tipo_repository = tipo_repository
        self.audit_service = audit_service
        self.session_service = session_service

    def list_documentos_empresa(self, empresa_id: int) -> list[dict]:
        self._ensure_empresa(empresa_id)
        return self.documento_repository.list_by_company(empresa_id)

    def get_documento(self, documento_id: int) -> dict:
        documento = self.documento_repository.get_by_id(documento_id)
        if not documento:
            raise ValidationError("Documento nao encontrado.")
        return documento

    def list_document_name_suggestions(self, tipo_documento_id: int | None = None, search: str = "") -> list[str]:
        if tipo_documento_id is not None:
            self._ensure_tipo(tipo_documento_id)
        return self.documento_repository.list_distinct_system_names(tipo_documento_id=tipo_documento_id, search=search)

    def list_system_document_names(self, tipo_documento_id: int | None = None, search: str = "") -> list[dict]:
        if tipo_documento_id is not None:
            self._ensure_tipo(tipo_documento_id)
        return self.documento_repository.list_system_names(tipo_documento_id=tipo_documento_id, search=search)

    def get_system_document_name(self, name_id: int) -> dict:
        system_name = self.documento_repository.get_system_name_by_id(name_id)
        if not system_name:
            raise ValidationError("Nome padrao de documento nao encontrado.")
        return system_name

    def create_system_document_name(self, tipo_documento_id: int, nome_documento: str) -> int:
        nome = self._normalize_name(nome_documento)
        with self.documento_repository.db_manager.connect():
            tipo = self._ensure_tipo(tipo_documento_id)
            if self.documento_repository.find_duplicate_system_name(tipo_documento_id, nome):
                raise ValidationError("Ja existe um nome padrao cadastrado para esse tipo.")

            name_id = self.documento_repository.create_system_name(tipo_documento_id, nome)
            self._log(
                "CADASTRO_DOCUMENTO_PADRAO",
                "nome_documento_padrao",
                name_id,
                (
                    f'Usuario {self._actor_name()} cadastrou o nome padrao "{nome}" '
                    f'para o tipo "{tipo["nome_tipo"]}".'
                ),
            )
        return name_id

    def update_system_document_name(self, name_id: int, tipo_documento_id: int, nome_documento: str) -> None:
        nome = self._normalize_name(nome_documento)
        with self.documento_repository.db_manager.connect():
            current = self.get_system_document_name(name_id)
            old_tipo = self._ensure_tipo(current["tipo_documento_id"])
            new_tipo = self._ensure_tipo(tipo_documento_id)

            duplicate = self.documento_repository.find_duplicate_system_name(
                tipo_documento_id,
                nome,
                ignore_id=name_id,
            )
            if duplicate:
                raise ValidationError("Ja existe um nome padrao cadastrado para esse tipo.")

            self.documento_repository.update_system_name(name_id, tipo_documento_id, nome)
            self._log(
                "EDICAO_DOCUMENTO_PADRAO",
                "nome_documento_padrao",
                name_id,
                (
                    f'Usuario {self._actor_name()} alterou o nome padrao "{current["nome_documento"]}" '
                    f'do tipo "{old_tipo["nome_tipo"]}" para "{nome}" no tipo "{new_tipo["nome_tipo"]}".'
                ),
            )

    def delete_system_document_name(self, name_id: int) -> None:
        with self.documento_repository.db_manager.connect():
            current = self.get_system_document_name(name_id)
            self.documento_repository.delete_system_name(name_id)
            self._log(
                "EXCLUSAO_DOCUMENTO_PADRAO",
                "nome_documento_padrao",
                name_id,
                (
                    f'Usuario {self._actor_name()} removeu o nome padrao "{current["nome_documento"]}" '
                    f'do tipo "{current["nome_tipo"]}".'
                ),
            )

    def create_documento(
        self,
        empresa_id: int,
        tipo_documento_id: int,
        nome_documento: str,
        meios_recebimento: list[str] | tuple[str, ...] | str | None = None,
    ) -> int:
        nome = self._normalize_name(nome_documento)
        meios = self._normalize_delivery_methods(meios_recebimento)
        with self.documento_repository.db_manager.connect():
            empresa = self._ensure_empresa(empresa_id)
            tipo = self._ensure_tipo(tipo_documento_id)

            if self.documento_repository.find_duplicate(empresa_id, tipo_documento_id, nome):
                raise ValidationError("Ja existe um documento com esse nome para a empresa e tipo informados.")

            documento_id = self.documento_repository.create(empresa_id, tipo_documento_id, meios, nome)
            details = [
                f'Usuario {self._actor_name()} cadastrou o documento "{nome}" '
                f'para a empresa "{empresa["nome_empresa"]}" no tipo "{tipo["nome_tipo"]}".'
            ]
            if meios:
                details.append(f"Meios de recebimento: {meios}.")
            self._log(
                "CADASTRO_DOCUMENTO",
                "documento",
                documento_id,
                " ".join(details),
                empresa_id=empresa["id"],
                empresa_nome=empresa["nome_empresa"],
            )
        return documento_id

    def update_documento(
        self,
        documento_id: int,
        tipo_documento_id: int,
        nome_documento: str,
        meios_recebimento: list[str] | tuple[str, ...] | str | None = None,
    ) -> None:
        nome = self._normalize_name(nome_documento)
        meios = self._normalize_delivery_methods(meios_recebimento)
        with self.documento_repository.db_manager.connect():
            documento = self.get_documento(documento_id)
            old_tipo = self._ensure_tipo(documento["tipo_documento_id"])
            new_tipo = self._ensure_tipo(tipo_documento_id)
            empresa = self._ensure_empresa(documento["empresa_id"])

            duplicate = self.documento_repository.find_duplicate(
                documento["empresa_id"],
                tipo_documento_id,
                nome,
                ignore_id=documento_id,
            )
            if duplicate:
                raise ValidationError("Ja existe um documento com esse nome para a empresa e tipo informados.")

            self.documento_repository.update(documento_id, tipo_documento_id, meios, nome)
            if documento["nome_documento"] != nome:
                self._log(
                    "EDICAO_DOCUMENTO",
                    "documento",
                    documento_id,
                    (
                        f'Usuario {self._actor_name()} alterou o documento "{documento["nome_documento"]}" '
                        f'para "{nome}" na empresa "{empresa["nome_empresa"]}".'
                    ),
                    empresa_id=empresa["id"],
                    empresa_nome=empresa["nome_empresa"],
                )
            if (documento.get("meios_recebimento") or "") != (meios or ""):
                self._log(
                    "EDICAO_DOCUMENTO",
                    "documento",
                    documento_id,
                    (
                        f'Usuario {self._actor_name()} alterou os meios de recebimento do documento "{nome}" '
                        f'de "{documento.get("meios_recebimento") or "-"}" para "{meios or "-"}".'
                    ),
                    empresa_id=empresa["id"],
                    empresa_nome=empresa["nome_empresa"],
                )
            if old_tipo["id"] != new_tipo["id"]:
                self._log(
                    "ALTERACAO_TIPO_DOCUMENTO",
                    "documento",
                    documento_id,
                    (
                        f'Usuario {self._actor_name()} alterou o tipo do documento "{nome}" '
                        f'de "{old_tipo["nome_tipo"]}" para "{new_tipo["nome_tipo"]}".'
                    ),
                    empresa_id=empresa["id"],
                    empresa_nome=empresa["nome_empresa"],
                )

    def delete_documento(self, documento_id: int) -> None:
        with self.documento_repository.db_manager.connect():
            documento = self.get_documento(documento_id)
            empresa = self._ensure_empresa(documento["empresa_id"])
            self.documento_repository.delete(documento_id)
            self._log(
                "EXCLUSAO_DOCUMENTO",
                "documento",
                documento_id,
                f'Usuario {self._actor_name()} excluiu o documento "{documento["nome_documento"]}".',
                empresa_id=empresa["id"],
                empresa_nome=empresa["nome_empresa"],
            )

    def delete_documentos(self, documento_ids: list[int]) -> None:
        valid_ids = [int(doc_id) for doc_id in documento_ids]
        with self.documento_repository.db_manager.connect():
            documentos = []
            for documento_id in valid_ids:
                documentos.append(self.get_documento(documento_id))
            self.documento_repository.delete_many(valid_ids)
            for documento in documentos:
                empresa = self._ensure_empresa(documento["empresa_id"])
                self._log(
                    "EXCLUSAO_DOCUMENTO",
                    "documento",
                    documento["id"],
                    f'Usuario {self._actor_name()} excluiu o documento "{documento["nome_documento"]}".',
                    empresa_id=empresa["id"],
                    empresa_nome=empresa["nome_empresa"],
                )

    def _ensure_empresa(self, empresa_id: int) -> dict:
        empresa = self.empresa_repository.get_by_id(empresa_id)
        if not empresa:
            raise ValidationError("Empresa nao encontrada.")
        return empresa

    def _ensure_tipo(self, tipo_documento_id: int) -> dict:
        tipo = self.tipo_repository.get_by_id(tipo_documento_id)
        if not tipo:
            raise ValidationError("Tipo de documento nao encontrado.")
        return tipo

    def _normalize_name(self, nome_documento: str) -> str:
        normalized = str(nome_documento).strip()
        if not normalized:
            raise ValidationError("O nome do documento nao pode ficar vazio.")
        return normalized

    def _normalize_delivery_methods(self, methods: list[str] | tuple[str, ...] | str | None) -> str | None:
        return normalize_delivery_methods(methods)

    def _actor_name(self) -> str:
        if not self.session_service:
            return "Sistema"
        return self.session_service.get_username()

    def _log(
        self,
        acao: str,
        entidade: str,
        entidade_id: int,
        descricao: str,
        empresa_id: int | None = None,
        empresa_nome: str | None = None,
    ) -> None:
        if self.audit_service:
            self.audit_service.log(
                acao,
                entidade,
                entidade_id,
                descricao,
                empresa_id=empresa_id,
                empresa_nome=empresa_nome,
            )
