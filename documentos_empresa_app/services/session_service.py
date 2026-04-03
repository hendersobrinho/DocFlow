from __future__ import annotations


class SessionService:
    def __init__(self) -> None:
        self.current_user: dict | None = None

    def login(self, user: dict) -> None:
        self.current_user = {
            "id": user["id"],
            "username": user["username"],
            "tipo_usuario": user["tipo_usuario"],
            "ativa": user["ativa"],
        }

    def logout(self) -> None:
        self.current_user = None

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
        self.login(user)
