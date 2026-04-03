from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import messagebox

from documentos_empresa_app.app_context import build_application_services
from documentos_empresa_app.ui.login_window import LoginWindow
from documentos_empresa_app.ui.main_window import MainWindow
from documentos_empresa_app.utils.common import APP_NAME, ValidationError
from documentos_empresa_app.utils.helpers import (
    ensure_database_path,
    load_login_preferences,
    prompt_database_path,
    save_login_preferences,
)


def try_restore_saved_login(services) -> dict | None:
    preferences = load_login_preferences()
    remembered_token = preferences["remembered_token"]
    if not remembered_token:
        return None

    try:
        user = services.auth_service.authenticate_with_remembered_session(remembered_token)
    except ValidationError:
        services.auth_service.revoke_remembered_session(remembered_token)
        save_login_preferences(
            preferences["username"],
            remember_credential=False,
            remembered_token=None,
        )
        return None

    services.session_service.login(user, remembered_token=remembered_token)
    return user


def main() -> None:
    while True:
        bootstrap = tk.Tk()
        bootstrap.withdraw()
        db_path = ensure_database_path(parent=bootstrap)
        bootstrap.destroy()
        if db_path is None:
            return

        try:
            services = build_application_services(db_path)
        except sqlite3.OperationalError:
            recovery_root = tk.Tk()
            recovery_root.withdraw()
            messagebox.showerror(
                APP_NAME,
                (
                    f"Nao foi possivel abrir o banco de dados em:\n{db_path}\n\n"
                    "Escolha outro local para continuar."
                ),
                parent=recovery_root,
            )
            new_path = prompt_database_path(parent=recovery_root)
            recovery_root.destroy()
            if new_path is None:
                return
            continue

        while True:
            services.session_service.logout()
            authenticated_user = try_restore_saved_login(services)
            if authenticated_user is None:
                login = LoginWindow(services)
                login.mainloop()
                if login.authenticated_user is None:
                    return

            app = MainWindow(db_path, services)
            app.mainloop()
            if app.logout_requested:
                continue
            if app.restart_requested:
                break
            return


if __name__ == "__main__":
    main()
