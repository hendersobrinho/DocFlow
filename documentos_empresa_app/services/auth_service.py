from __future__ import annotations

from documentos_empresa_app.database.repositories import UsuarioRepository
from documentos_empresa_app.utils.common import ValidationError
from documentos_empresa_app.utils.security import verify_password


class AuthService:
    def __init__(self, usuario_repository: UsuarioRepository) -> None:
        self.usuario_repository = usuario_repository

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
