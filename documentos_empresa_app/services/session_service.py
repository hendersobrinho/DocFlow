from __future__ import annotations


class SessionService:
    def __init__(self) -> None:
        self.current_user: dict | None = None
        self.remembered_token: str | None = None

    def login(self, user: dict, remembered_token: str | None = None) -> None:
        self.current_user = {
            "id": user["id"],
            "username": user["username"],
            "tipo_usuario": user["tipo_usuario"],
            "ativa": user["ativa"],
        }
        self.remembered_token = remembered_token

    def logout(self) -> None:
        self.current_user = None
        self.remembered_token = None

    def is_authenticated(self) -> bool:
        return self.current_user is not None

    def is_admin(self) -> bool:
        return bool(self.current_user and self.current_user.get("tipo_usuario") == "admin")

    def get_user_id(self) -> int | None:
        if not self.current_user:
            return None
        return int(self.current_user["id"])

    def get_username(self) -> str:
        if not self.current_user:
            return "Desconhecido"
        return str(self.current_user["username"])

    def refresh_user(self, user: dict) -> None:
        if not self.current_user or self.current_user["id"] != user["id"]:
            return
        self.login(user, remembered_token=self.remembered_token)

    def get_remembered_token(self) -> str | None:
        return self.remembered_token
