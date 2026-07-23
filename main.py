from __future__ import annotations

from datetime import datetime
import sqlite3
import sys
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox

from documentos_empresa_app.app_context import build_application_services
from documentos_empresa_app.qt_ui.dialogs.database_path_dialog import (
    ensure_database_path_qt,
    prompt_database_path_qt,
)
from documentos_empresa_app.qt_ui.icons import app_icon
from documentos_empresa_app.qt_ui.license_window import LicenseWindow
from documentos_empresa_app.qt_ui.login_window import LoginWindow
from documentos_empresa_app.qt_ui.main_window import MainWindow
from documentos_empresa_app.qt_ui.theme import ThemeManager
from documentos_empresa_app.services.license_service import LicenseError, LicenseService
from documentos_empresa_app.utils.common import APP_NAME, ValidationError
from documentos_empresa_app.utils.helpers import load_login_preferences, save_login_preferences


def try_restore_saved_login(services) -> dict | None:
    preferences = load_login_preferences()
    remembered_token = preferences["remembered_token"]
    if not remembered_token:
        return None

    try:
        user, refreshed_token = services.auth_service.authenticate_with_remembered_session(remembered_token)
    except ValidationError:
        services.auth_service.revoke_remembered_session(remembered_token)
        save_login_preferences(
            preferences["username"],
            remember_credential=False,
            remembered_token=None,
        )
        return None

    save_login_preferences(
        user["username"],
        remember_credential=True,
        remembered_token=refreshed_token,
    )
    services.session_service.login(user, remembered_token=refreshed_token)
    return user


def ensure_local_license() -> bool:
    try:
        license_service = LicenseService()
    except LicenseError as exc:
        QMessageBox.critical(None, APP_NAME, str(exc))
        return False

    try:
        license_service.load_and_save_if_valid()
        return True
    except LicenseError as exc:
        if license_service.license_file_path.exists():
            status_message = (
                "A licenca encontrada neste computador esta invalida, expirada ou corrompida.\n"
                f"Detalhe: {exc}\n\n"
                "Cole ou importe uma nova licenca para continuar."
            )
        else:
            status_message = "Nenhuma licenca foi encontrada. Cole ou importe uma licenca para continuar."

    license_window = LicenseWindow(license_service, status_message=status_message)
    license_window.exec()
    return license_window.license_activated


def _install_exception_handler() -> None:
    """Registra excecoes nao tratadas em arquivo e avisa o usuario, em vez de
    deixar o aplicativo fechar silenciosamente."""
    from documentos_empresa_app.utils.common import CONFIG_DIR

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            log_path = CONFIG_DIR / "error.log"
            with open(log_path, "a", encoding="utf-8") as log_file:
                log_file.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}]\n{details}")
        except OSError:
            log_path = None
        print(details, file=sys.stderr)
        try:
            message = "Ocorreu um erro inesperado, mas o programa vai continuar."
            if log_path:
                message += f"\n\nDetalhes registrados em:\n{log_path}"
            QMessageBox.critical(None, APP_NAME, message)
        except Exception:
            pass

    sys.excepthook = handle_exception


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(app_icon())
    _install_exception_handler()
    ThemeManager.instance().apply(app)

    while True:
        db_path = ensure_database_path_qt()
        if db_path is None:
            return

        try:
            services = build_application_services(db_path)
        except sqlite3.OperationalError:
            QMessageBox.critical(
                None,
                APP_NAME,
                f"Nao foi possivel abrir o banco de dados em:\n{db_path}\n\nEscolha outro local para continuar.",
            )
            new_path = prompt_database_path_qt()
            if new_path is None:
                return
            continue

        if not ensure_local_license():
            return

        while True:
            services.session_service.logout()
            authenticated_user = try_restore_saved_login(services)
            if authenticated_user is None:
                login = LoginWindow(services)
                login.exec()
                if login.authenticated_user is None:
                    return

            window = MainWindow(db_path, services)
            window.show()
            app.exec()
            if window.logout_requested:
                continue
            if window.restart_requested:
                break
            return


if __name__ == "__main__":
    main()
