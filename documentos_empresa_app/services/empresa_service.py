from __future__ import annotations

from pathlib import Path
import re
import sqlite3

from documentos_empresa_app.database.repositories import EmpresaRepository
from documentos_empresa_app.services.audit_service import AuditService
from documentos_empresa_app.services.session_service import SessionService
from documentos_empresa_app.utils.common import (
    ValidationError,
    normalize_delivery_methods,
)


class EmpresaService:
    def __init__(
        self,
        empresa_repository: EmpresaRepository,
        audit_service: AuditService | None = None,
        session_service: SessionService | None = None,
    ) -> None:
        self.empresa_repository = empresa_repository
        self.audit_service = audit_service
        self.session_service = session_service

    def list_empresas(self, active_only: bool = False) -> list[dict]:
        return self.empresa_repository.list_all(active_only=active_only)

    def get_empresa(self, empresa_id: int) -> dict:
        empresa = self.empresa_repository.get_by_id(empresa_id)
        if not empresa:
            raise ValidationError("Empresa nao encontrada.")
        return empresa

    def get_empresa_by_code(self, codigo_empresa, active_only: bool = False) -> dict | None:
        try:
            codigo = int(str(codigo_empresa).strip())
        except ValueError:
            return None
        return self.empresa_repository.get_by_code(codigo, active_only=active_only)

    def create_empresa(
        self,
        codigo_empresa,
        nome_empresa: str,
        meios_recebimento: list[str] | tuple[str, ...] | str | None = None,
        email_contato: str | None = None,
        nome_contato: str | None = None,
    ) -> int:
        codigo = self._parse_codigo(codigo_empresa)
        nome = self._normalize_name(nome_empresa, "O nome da empresa nao pode ficar vazio.")
        meios = self._normalize_delivery_methods(meios_recebimento)
        email = self._normalize_optional_email(email_contato)
        contato = self._normalize_optional_text(nome_contato)

        try:
            with self.empresa_repository.db_manager.connect():
                if self.empresa_repository.get_by_code(codigo):
                    raise ValidationError("Ja existe uma empresa cadastrada com esse codigo.")
                empresa_id = self.empresa_repository.create(codigo, nome, meios, email, contato)
                self._log(
                    "CADASTRO_EMPRESA",
                    "empresa",
                    empresa_id,
                    self._build_company_description("cadastrou", nome, codigo, meios, email, contato),
                    empresa_id=empresa_id,
                    empresa_nome=nome,
                )
        except sqlite3.IntegrityError as exc:
            raise ValidationError("Nao foi possivel cadastrar a empresa.") from exc
        return empresa_id

    def update_empresa_nome(self, empresa_id: int, nome_empresa: str) -> None:
        empresa = self.get_empresa(empresa_id)
        self.update_empresa(
            empresa_id,
            nome_empresa,
            empresa.get("meios_recebimento"),
            empresa.get("email_contato"),
            empresa.get("nome_contato"),
        )

    def update_empresa(
        self,
        empresa_id: int,
        nome_empresa: str,
        meios_recebimento: list[str] | tuple[str, ...] | str | None = None,
        email_contato: str | None = None,
        nome_contato: str | None = None,
    ) -> None:
        nome = self._normalize_name(nome_empresa, "O nome da empresa nao pode ficar vazio.")
        meios = self._normalize_delivery_methods(meios_recebimento)
        email = self._normalize_optional_email(email_contato)
        contato = self._normalize_optional_text(nome_contato)

        with self.empresa_repository.db_manager.connect():
            empresa = self.get_empresa(empresa_id)
            self.empresa_repository.update_details(empresa_id, nome, meios, email, contato)

            changes = []
            if empresa["nome_empresa"] != nome:
                changes.append(f'nome: "{empresa["nome_empresa"]}" -> "{nome}"')
            if (empresa.get("meios_recebimento") or "") != (meios or ""):
                changes.append(
                    f'meios de recebimento: "{empresa.get("meios_recebimento") or "-"}" -> "{meios or "-"}"'
                )
            if (empresa.get("email_contato") or "") != (email or ""):
                changes.append(f'email: "{empresa.get("email_contato") or "-"}" -> "{email or "-"}"')
            if (empresa.get("nome_contato") or "") != (contato or ""):
                changes.append(f'contato: "{empresa.get("nome_contato") or "-"}" -> "{contato or "-"}"')

            if changes:
                self._log(
                    "EDICAO_EMPRESA",
                    "empresa",
                    empresa_id,
                    (
                        f'Usuario {self._actor_name()} atualizou a empresa "{nome}". '
                        f'Alteracoes: {"; ".join(changes)}.'
                    ),
                    empresa_id=empresa_id,
                    empresa_nome=nome,
                )

    def set_empresa_ativa(self, empresa_id: int, ativa: bool) -> None:
        ativo_int = 1 if ativa else 0
        with self.empresa_repository.db_manager.connect():
            empresa = self.get_empresa(empresa_id)
            self.empresa_repository.update_active(empresa_id, ativo_int)
            if empresa["ativa"] != ativo_int:
                acao = "REATIVACAO_EMPRESA" if ativa else "INATIVACAO_EMPRESA"
                descricao = (
                    f'Usuario {self._actor_name()} reativou a empresa "{empresa["nome_empresa"]}".'
                    if ativa
                    else f'Usuario {self._actor_name()} inativou a empresa "{empresa["nome_empresa"]}".'
                )
                self._log(
                    acao,
                    "empresa",
                    empresa_id,
                    descricao,
                    empresa_id=empresa_id,
                    empresa_nome=empresa["nome_empresa"],
                )

    def set_empresa_directory(self, empresa_id: int, diretorio_documentos: str | None) -> None:
        normalized_directory = self._normalize_optional_directory(diretorio_documentos)
        with self.empresa_repository.db_manager.connect():
            empresa = self.get_empresa(empresa_id)
            previous_directory = empresa.get("diretorio_documentos")
            if (previous_directory or "") == (normalized_directory or ""):
                return

            self.empresa_repository.update_directory(empresa_id, normalized_directory)
            previous_label = previous_directory or "-"
            current_label = normalized_directory or "-"
            self._log(
                "EDICAO_EMPRESA",
                "empresa",
                empresa_id,
                (
                    f'Usuario {self._actor_name()} atualizou a pasta vinculada da empresa '
                    f'"{empresa["nome_empresa"]}" de "{previous_label}" para "{current_label}".'
                ),
                empresa_id=empresa_id,
                empresa_nome=empresa["nome_empresa"],
            )

    def delete_empresa(self, empresa_id: int) -> None:
        with self.empresa_repository.db_manager.connect():
            empresa = self.get_empresa(empresa_id)
            self.empresa_repository.delete(empresa_id)
            self._log(
                "EXCLUSAO_EMPRESA",
                "empresa",
                empresa_id,
                f'Usuario {self._actor_name()} excluiu a empresa "{empresa["nome_empresa"]}".',
                empresa_id=empresa_id,
                empresa_nome=empresa["nome_empresa"],
            )

    def _parse_codigo(self, codigo_empresa) -> int:
        if isinstance(codigo_empresa, bool):
            raise ValidationError("O codigo da empresa deve ser um numero inteiro.")
        try:
            return int(str(codigo_empresa).strip())
        except ValueError:
            try:
                numeric_value = float(str(codigo_empresa).strip())
            except ValueError as exc:
                raise ValidationError("O codigo da empresa deve ser um numero inteiro.") from exc

            if not numeric_value.is_integer():
                raise ValidationError("O codigo da empresa deve ser um numero inteiro.")
            return int(numeric_value)

    def _normalize_name(self, value: str, error_message: str) -> str:
        normalized = str(value).strip()
        if not normalized:
            raise ValidationError(error_message)
        return normalized

    def _normalize_delivery_methods(self, methods: list[str] | tuple[str, ...] | str | None) -> str | None:
        return normalize_delivery_methods(methods)

    def _normalize_optional_email(self, email: str | None) -> str | None:
        normalized = self._normalize_optional_text(email)
        if not normalized:
            return None
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", normalized):
            raise ValidationError("Informe um email valido ou deixe o campo em branco.")
        return normalized

    def _normalize_optional_text(self, value: str | None) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    def _normalize_optional_directory(self, value: str | None) -> str | None:
        normalized = self._normalize_optional_text(value)
        if not normalized:
            return None
        return str(Path(normalized).expanduser())

    def _build_company_description(
        self,
        action_text: str,
        nome_empresa: str,
        codigo_empresa: int,
        meios_recebimento: str | None,
        email_contato: str | None,
        nome_contato: str | None,
    ) -> str:
        details = [f'Usuario {self._actor_name()} {action_text} a empresa "{nome_empresa}" de codigo {codigo_empresa}.']
        if meios_recebimento:
            details.append(f"Meios de recebimento: {meios_recebimento}.")
        if email_contato:
            details.append(f"Email: {email_contato}.")
        if nome_contato:
            details.append(f"Contato: {nome_contato}.")
        return " ".join(details)

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
