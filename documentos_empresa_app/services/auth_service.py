from __future__ import annotations

from datetime import datetime, timedelta, timezone

from documentos_empresa_app.database.repositories import RememberedSessionRepository, UsuarioRepository
from documentos_empresa_app.utils.common import ValidationError
from documentos_empresa_app.utils.security import (
    generate_remember_secret,
    generate_remember_selector,
    hash_remember_secret,
    verify_password,
    verify_remember_secret,
)

REMEMBER_SESSION_MAX_AGE_DAYS = 60


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

    def authenticate_with_remembered_session(self, raw_token: str) -> tuple[dict, str]:
        selector, secret = self._parse_remembered_token(raw_token)
        if not self.remembered_session_repository:
            raise ValidationError("Login lembrado nao esta habilitado.")

        with self.remembered_session_repository.db_manager.connect():
            remembered_session = self.remembered_session_repository.get_by_selector(selector)
            if not remembered_session or not verify_remember_secret(secret, remembered_session["token_hash"]):
                raise ValidationError("Credencial lembrada invalida.")

            if self._is_remembered_session_expired(remembered_session):
                self.remembered_session_repository.delete_by_selector(selector)
                raise ValidationError("Credencial lembrada expirada. Faca login novamente.")

            user = self.usuario_repository.get_by_id(remembered_session["usuario_id"])
            if not user or not user["ativa"]:
                self.remembered_session_repository.delete_by_selector(selector)
                raise ValidationError("Esse usuario nao pode mais usar a credencial lembrada.")

            refreshed_token = self._rotate_remembered_session(user["id"], selector)
        return user, refreshed_token

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

    def _rotate_remembered_session(self, user_id: int, previous_selector: str) -> str:
        selector = generate_remember_selector()
        secret = generate_remember_secret()
        self.remembered_session_repository.create(user_id, selector, hash_remember_secret(secret))
        self.remembered_session_repository.delete_by_selector(previous_selector)
        return f"{selector}.{secret}"

    def _is_remembered_session_expired(self, remembered_session: dict) -> bool:
        last_activity = remembered_session.get("ultimo_uso_em") or remembered_session.get("criado_em")
        if not last_activity:
            return True

        activity_at = self._parse_timestamp(last_activity)
        expiration_limit = datetime.now(timezone.utc) - timedelta(days=REMEMBER_SESSION_MAX_AGE_DAYS)
        return activity_at < expiration_limit

    def _parse_timestamp(self, raw_value: str) -> datetime:
        return datetime.strptime(str(raw_value), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
