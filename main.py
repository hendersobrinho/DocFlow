from __future__ import annotations

from datetime import datetime
import sys
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox

from documentos_empresa_app.app_context import build_application_services
from documentos_empresa_app.database.connection import DatabaseError, DatabaseManager
from documentos_empresa_app.qt_ui.dialogs.database_connection_dialog import (
    ensure_database_connection_qt,
    prompt_database_connection_qt,
)
from documentos_empresa_app.qt_ui.dialogs.change_password_dialog import ChangePasswordDialog
from documentos_empresa_app.qt_ui.icons import app_icon
from documentos_empresa_app.qt_ui.login_window import LoginWindow
from documentos_empresa_app.qt_ui.main_window import MainWindow
from documentos_empresa_app.qt_ui.splash_screen import SplashScreen
from documentos_empresa_app.qt_ui.theme import ThemeManager
from documentos_empresa_app.utils.common import APP_NAME, ValidationError
from documentos_empresa_app.utils.database_settings import resolve_database_conninfo
from documentos_empresa_app.utils.helpers import (
    load_login_preferences,
    purge_removed_feature_settings,
    save_login_preferences,
)


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
    purge_removed_feature_settings()
    ThemeManager.instance().apply(app)

    splash = SplashScreen()
    splash.show_animated()

    while True:
        splash.show_message("Verificando banco de dados...", 0.08)
        conninfo = resolve_database_conninfo()
        if conninfo is None:
            # Primeira vez neste computador: a tela de carregamento fica sempre por cima e
            # esconderia o aviso e a configuracao do banco - parecia travado em "Verificando".
            splash.hide()
            conninfo = ensure_database_connection_qt()
            if conninfo is None:
                splash.close()
                return
            splash.show_animated()

        try:
            splash.show_message("Conectando ao banco de dados...", 0.2)
            services = build_application_services(conninfo)
            # Meses do ano atual (e do proximo, a partir de novembro) sempre prontos.
            services.periodo_service.ensure_operational_years()
        except DatabaseError as exc:
            splash.hide()
            detail = str(exc).strip() or exc.__class__.__name__
            QMessageBox.critical(
                None,
                APP_NAME,
                f"Nao foi possivel conectar ao banco de dados:\n{DatabaseManager(conninfo).display_name}"
                f"\n\n{detail}\n\nRevise os dados de conexao para continuar.",
            )
            new_conninfo = prompt_database_connection_qt()
            if new_conninfo is None:
                splash.close()
                return
            splash.show_animated()
            continue

        while True:
            services.session_service.logout()
            splash.show_message("Restaurando sessão...", 0.32)
            authenticated_user = try_restore_saved_login(services)
            if authenticated_user is None:
                splash.close()
                login = LoginWindow(services)
                login.exec()
                if login.authenticated_user is None:
                    if login.change_database_requested:
                        services.database_maintenance_service.db_manager.close()
                        splash.show_animated()
                        break
                    return

            if services.session_service.must_change_password():
                splash.close()
                change_dialog = ChangePasswordDialog(services)
                change_dialog.exec()
                if not change_dialog.password_changed:
                    splash.show_animated()
                    continue

            # Depois do login a tela de carregamento volta e fica ate o sistema estar pronto.
            splash.show_animated()
            splash.show_message("Abrindo o sistema...", 0.4)
            window = MainWindow(
                services,
                on_progress=lambda texto, fracao: splash.show_message(texto, 0.4 + fracao * 0.55),
            )
            splash.finish(window)
            app.exec()
            if window.logout_requested:
                continue
            if window.restart_requested:
                services.database_maintenance_service.db_manager.close()
                splash.show_animated()
                break
            return


if __name__ == "__main__":
    main()
