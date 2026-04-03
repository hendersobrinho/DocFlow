from __future__ import annotations

import sqlite3

from documentos_empresa_app.database.repositories import UsuarioRepository
from documentos_empresa_app.services.auth_service import AuthService
from documentos_empresa_app.services.audit_service import AuditService
from documentos_empresa_app.services.session_service import SessionService
from documentos_empresa_app.utils.common import ValidationError
from documentos_empresa_app.utils.security import hash_password


VALID_USER_TYPES = {"admin", "comum"}


class UserService:
    def __init__(
        self,
        usuario_repository: UsuarioRepository,
        session_service: SessionService,
        audit_service: AuditService | None = None,
        auth_service: AuthService | None = None,
    ) -> None:
        self.usuario_repository = usuario_repository
        self.session_service = session_service
        self.audit_service = audit_service
        self.auth_service = auth_service

    def list_users(self) -> list[dict]:
        self._ensure_admin()
        return self.usuario_repository.list_all()

    def get_user(self, user_id: int) -> dict:
        self._ensure_admin()
        user = self.usuario_repository.get_by_id(user_id)
        if not user:
            raise ValidationError("Usuario nao encontrado.")
        return user

    def create_user(self, username: str, password: str, tipo_usuario: str, ativo: bool = True) -> int:
        self._ensure_admin()
        normalized_username = self._normalize_username(username)
        normalized_password = self._normalize_new_password(password)
        normalized_tipo = self._normalize_tipo(tipo_usuario)

        try:
            with self.usuario_repository.db_manager.connect():
                if self.usuario_repository.get_by_username(normalized_username):
                    raise ValidationError("Ja existe um usuario com esse nome.")
                user_id = self.usuario_repository.create(
                    normalized_username,
                    hash_password(normalized_password),
                    normalized_tipo,
                    1 if ativo else 0,
                )
                if self.audit_service:
                    self.audit_service.log(
                        "CRIACAO_USUARIO",
                        "usuario",
                        user_id,
                        (
                            f'Usuario {self.session_service.get_username()} cadastrou o usuario '
                            f'"{normalized_username}" como {normalized_tipo}.'
                        ),
                    )
        except sqlite3.IntegrityError as exc:
            raise ValidationError("Nao foi possivel cadastrar o usuario.") from exc
        return user_id

    def update_user(
        self,
        user_id: int,
        username: str,
        tipo_usuario: str,
        ativo: bool,
        password: str | None = None,
    ) -> None:
        self._ensure_admin()
        user = self._get_existing_user(user_id)
        normalized_username = self._normalize_username(username)
        normalized_tipo = self._normalize_tipo(tipo_usuario)
        ativo_int = 1 if ativo else 0
        should_revoke_remembered_sessions = not bool(ativo_int)

        with self.usuario_repository.db_manager.connect():
            existing = self.usuario_repository.get_by_username(normalized_username)
            if existing and existing["id"] != user_id:
                raise ValidationError("Ja existe um usuario com esse nome.")

            self._validate_self_change_rules(user, normalized_tipo, ativo_int)
            self._validate_admin_guardrails(user, normalized_tipo, ativo_int)
            self.usuario_repository.update(user_id, normalized_username, normalized_tipo, ativo_int)

            if password is not None and str(password).strip():
                self.usuario_repository.update_password(user_id, hash_password(self._normalize_new_password(password)))
                should_revoke_remembered_sessions = True
                if self.audit_service:
                    self.audit_service.log(
                        "ALTERACAO_SENHA_USUARIO",
                        "usuario",
                        user_id,
                        (
                            f'Usuario {self.session_service.get_username()} alterou a senha do usuario '
                            f'"{normalized_username}".'
                        ),
                    )

            if user["username"] != normalized_username or user["tipo_usuario"] != normalized_tipo:
                if self.audit_service:
                    self.audit_service.log(
                        "EDICAO_USUARIO",
                        "usuario",
                        user_id,
                        (
                            f'Usuario {self.session_service.get_username()} atualizou o usuario "{user["username"]}" '
                            f'para username "{normalized_username}" e tipo "{normalized_tipo}".'
                        ),
                    )

            if user["ativa"] != ativo_int and self.audit_service:
                acao = "REATIVACAO_USUARIO" if ativo_int else "INATIVACAO_USUARIO"
                descricao = (
                    f'Usuario {self.session_service.get_username()} reativou o usuario "{normalized_username}".'
                    if ativo_int
                    else f'Usuario {self.session_service.get_username()} inativou o usuario "{normalized_username}".'
                )
                self.audit_service.log(acao, "usuario", user_id, descricao)

            updated_user = self.usuario_repository.get_by_id(user_id)

        if should_revoke_remembered_sessions and self.auth_service:
            self.auth_service.revoke_user_remembered_sessions(user_id)
        if updated_user:
            self.session_service.refresh_user(updated_user)

    def _ensure_admin(self) -> None:
        if not self.session_service.is_admin():
            raise ValidationError("Apenas usuarios admin podem gerenciar usuarios.")

    def _get_existing_user(self, user_id: int) -> dict:
        user = self.usuario_repository.get_by_id(user_id)
        if not user:
            raise ValidationError("Usuario nao encontrado.")
        return user

    def _normalize_username(self, username: str) -> str:
        normalized = str(username).strip()
        if not normalized:
            raise ValidationError("O nome de usuario nao pode ficar vazio.")
        return normalized

    def _normalize_new_password(self, password: str) -> str:
        normalized = str(password)
        if not normalized.strip():
            raise ValidationError("A senha nao pode ficar vazia.")
        return normalized

    def _normalize_tipo(self, tipo_usuario: str) -> str:
        normalized = str(tipo_usuario).strip().lower()
        if normalized not in VALID_USER_TYPES:
            raise ValidationError("Selecione um tipo de usuario valido.")
        return normalized

    def _validate_self_change_rules(self, user: dict, tipo_usuario: str, ativo: int) -> None:
        current_user_id = self.session_service.get_user_id()
        if current_user_id != user["id"]:
            return
        if not ativo:
            raise ValidationError("Voce nao pode inativar o proprio usuario durante a sessao atual.")
        if user["tipo_usuario"] == "admin" and tipo_usuario != "admin":
            raise ValidationError("Voce nao pode remover o proprio perfil admin durante a sessao atual.")

    def _validate_admin_guardrails(self, user: dict, tipo_usuario: str, ativo: int) -> None:
        was_active_admin = user["tipo_usuario"] == "admin" and bool(user["ativa"])
        will_remain_active_admin = tipo_usuario == "admin" and bool(ativo)
        if not was_active_admin or will_remain_active_admin:
            return
        if self.usuario_repository.count_admins(active_only=True) <= 1:
            raise ValidationError("O sistema precisa manter pelo menos um usuario admin ativo.")
