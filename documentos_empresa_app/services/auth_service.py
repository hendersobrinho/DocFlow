from __future__ import annotations

from documentos_empresa_app.database.repositories import RememberedSessionRepository, UsuarioRepository
from documentos_empresa_app.utils.common import ValidationError
from documentos_empresa_app.utils.security import (
    generate_remember_secret,
    generate_remember_selector,
    hash_remember_secret,
    verify_password,
    verify_remember_secret,
)


class AuthService:
    def __init__(
        self,
        usuario_repository: UsuarioRepository,
        remembered_session_repository: RememberedSessionRepository | None = None,
    ) -> None:
        self.usuario_repository = usuario_repository
        self.remembered_session_repository = remembered_session_repository

    def authenticate(self, username: str, password: str) -> dict:
        username_value = str(username).strip()
        password_value = str(password)

        if not username_value or not password_value:
            raise ValidationError("Informe nome de usuario e senha para entrar.")

        user = self.usuario_repository.get_by_username(username_value, include_password=True)
        if not user or not verify_password(password_value, user["senha_hash"]):
            raise ValidationError("Usuario ou senha incorretos.")
        if not user["ativa"]:
            raise ValidationError("Esse usuario esta inativo e nao pode fazer login.")
        user.pop("senha_hash", None)
        return user

    def authenticate_with_remembered_session(self, raw_token: str) -> dict:
        selector, secret = self._parse_remembered_token(raw_token)
        if not self.remembered_session_repository:
            raise ValidationError("Login lembrado nao esta habilitado.")

        remembered_session = self.remembered_session_repository.get_by_selector(selector)
        if not remembered_session or not verify_remember_secret(secret, remembered_session["token_hash"]):
            raise ValidationError("Credencial lembrada invalida.")

        user = self.usuario_repository.get_by_id(remembered_session["usuario_id"])
        if not user or not user["ativa"]:
            self.remembered_session_repository.delete_by_selector(selector)
            raise ValidationError("Esse usuario nao pode mais usar a credencial lembrada.")

        self.remembered_session_repository.touch(remembered_session["id"])
        return user

    def create_remembered_session(self, user_id: int) -> str:
        if not self.remembered_session_repository:
            raise ValidationError("Login lembrado nao esta habilitado.")

        user = self.usuario_repository.get_by_id(user_id)
        if not user:
            raise ValidationError("Usuario nao encontrado.")
        if not user["ativa"]:
            raise ValidationError("Esse usuario esta inativo e nao pode usar login lembrado.")

        selector = generate_remember_selector()
        secret = generate_remember_secret()
        self.remembered_session_repository.create(user_id, selector, hash_remember_secret(secret))
        return f"{selector}.{secret}"

    def revoke_remembered_session(self, raw_token: str | None) -> None:
        if not raw_token or not self.remembered_session_repository:
            return
        try:
            selector, _secret = self._parse_remembered_token(raw_token)
        except ValidationError:
            return
        self.remembered_session_repository.delete_by_selector(selector)

    def revoke_user_remembered_sessions(self, user_id: int) -> None:
        if not self.remembered_session_repository:
            return
        self.remembered_session_repository.delete_by_user(user_id)

    def _parse_remembered_token(self, raw_token: str) -> tuple[str, str]:
        token_text = str(raw_token).strip()
        selector, separator, secret = token_text.partition(".")
        if not selector or not separator or not secret:
            raise ValidationError("Credencial lembrada invalida.")
        return selector, secret
