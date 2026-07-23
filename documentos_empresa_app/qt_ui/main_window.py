from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.app_context import ApplicationServices
from documentos_empresa_app.qt_ui.dialogs.about_dialog import AboutDialog
from documentos_empresa_app.qt_ui.dialogs.backup_settings_dialog import BackupSettingsDialog
from documentos_empresa_app.qt_ui.icons import app_icon
from documentos_empresa_app.qt_ui.pages.controle_page import ControlePage
from documentos_empresa_app.qt_ui.pages.dashboard_page import DashboardPage
from documentos_empresa_app.qt_ui.pages.documentos_page import DocumentosPage
from documentos_empresa_app.qt_ui.pages.empresas_page import EmpresasPage
from documentos_empresa_app.qt_ui.pages.logs_page import LogsPage
from documentos_empresa_app.qt_ui.pages.panorama_page import PanoramaPage
from documentos_empresa_app.qt_ui.pages.revisao_page import RevisaoPage
from documentos_empresa_app.qt_ui.pages.usuarios_page import UsuariosPage
from documentos_empresa_app.qt_ui.theme import ThemeManager
from documentos_empresa_app.qt_ui.widgets.common import make_button
from documentos_empresa_app.utils.auto_backup import (
    load_auto_backup_settings,
    mark_auto_backup_created,
    save_auto_backup_settings,
    should_run_auto_backup,
)
from documentos_empresa_app.utils.common import APP_NAME, ValidationError
from documentos_empresa_app.utils.helpers import open_directory_in_file_manager, save_login_preferences

SIDEBAR_WIDTH = 230


class MainWindow(QMainWindow):
    def __init__(self, db_path: str | Path, services: ApplicationServices) -> None:
        super().__init__()
        self.db_path = Path(db_path)
        self.services = services
        self.logout_requested = False
        self.restart_requested = False
        self.nav_buttons: dict[int, QPushButton] = {}
        self.pages: list[QWidget] = []
        self._dirty_pages: set[int] = set()

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.resize(1440, 880)
        self.setMinimumSize(1100, 720)

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._build_sidebar(root_layout)
        self._build_main_area(root_layout)

        QTimer.singleShot(800, self.run_auto_backup_if_due)
        self.refresh_all_tabs()
        self._select_page(0)

    # Layout

    def _build_sidebar(self, root_layout: QHBoxLayout) -> None:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        root_layout.addWidget(sidebar)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 18, 12, 18)
        layout.setSpacing(4)

        title = QLabel(APP_NAME)
        title.setObjectName("SidebarTitle")
        layout.addWidget(title)
        layout.addSpacing(12)

        self.nav_layout = layout
        layout.addStretch(1)

        self.theme_button = make_button("Modo claro", "quiet")
        self.theme_button.clicked.connect(self._toggle_theme)
        layout.addWidget(self.theme_button)
        self._sync_theme_button()

        self.user_label = QLabel("")
        self.user_label.setObjectName("Muted")
        self.user_label.setWordWrap(True)
        layout.addWidget(self.user_label)

        logout_button = make_button("Logout", "danger")
        logout_button.clicked.connect(self.logout)
        layout.addWidget(logout_button)

    def _build_main_area(self, root_layout: QHBoxLayout) -> None:
        main_area = QWidget()
        root_layout.addWidget(main_area, 1)
        layout = QVBoxLayout(main_area)
        layout.setContentsMargins(20, 14, 20, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        db_label = QLabel(f"Banco: {self.db_path}")
        db_label.setObjectName("Muted")
        header.addWidget(db_label)
        header.addStretch(1)

        database_button = make_button("Banco")
        database_menu = QMenu(database_button)
        database_menu.addAction("Fazer backup...", self.backup_database)
        database_menu.addAction("Configurar backup automatico...", self.configure_auto_backup)
        database_menu.addAction("Abrir pasta de backup automatico", self.open_auto_backup_directory)
        database_menu.addSeparator()
        restore_action = database_menu.addAction("Restaurar backup...", self.restore_database)
        restore_action.setEnabled(self.services.session_service.is_admin())
        database_button.setMenu(database_menu)
        header.addWidget(database_button)

        help_button = make_button("Ajuda")
        help_menu = QMenu(help_button)
        help_menu.addAction("Sobre...", lambda: AboutDialog(self).exec())
        help_button.setMenu(help_menu)
        header.addWidget(help_button)
        layout.addLayout(header)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        self.controle_page = ControlePage(self.services, self.refresh_all_tabs)
        self.panorama_page = PanoramaPage(
            self.services, self.refresh_all_tabs, on_open_control=self.open_control_for_company_period
        )

        page_defs: list[tuple[str, QWidget]] = [
            ("Dashboard", DashboardPage(self.services, self.refresh_all_tabs)),
            ("Panorama", self.panorama_page),
            ("Controle", self.controle_page),
            ("Empresas", EmpresasPage(self.services, self.refresh_all_tabs)),
            ("Documentos", DocumentosPage(self.services, self.refresh_all_tabs)),
            ("Revisao de Documentos", RevisaoPage(self.services, self.refresh_all_tabs)),
        ]
        if self.services.session_service.is_admin():
            page_defs.append(("Usuarios", UsuariosPage(self.services, self.refresh_all_tabs)))
            page_defs.append(("Logs", LogsPage(self.services, self.refresh_all_tabs)))

        for index, (title, page) in enumerate(page_defs):
            self.pages.append(page)
            self.stack.addWidget(page)
            button = make_button(title)
            button.setObjectName("NavButton")
            button.clicked.connect(lambda _checked=False, i=index: self._select_page(i))
            self.nav_layout.insertWidget(2 + index, button)
            self.nav_buttons[index] = button

    def _select_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for button_index, button in self.nav_buttons.items():
            button.setProperty("active", "true" if button_index == index else "false")
            button.style().unpolish(button)
            button.style().polish(button)
        if index in self._dirty_pages:
            self._dirty_pages.discard(index)
            page = self.pages[index]
            if hasattr(page, "refresh_data"):
                page.refresh_data()

    def _toggle_theme(self) -> None:
        ThemeManager.instance().toggle()
        self._sync_theme_button()
        self.refresh_all_tabs()

    def _sync_theme_button(self) -> None:
        mode = ThemeManager.instance().mode
        self.theme_button.setText("☀ Modo claro" if mode == "dark" else "🌙 Modo escuro")

    # Navegacao / atualizacao

    def open_control_for_company_period(self, company_id: int, period_id: int) -> None:
        if self.controle_page.open_company_period(company_id, period_id):
            index = self.pages.index(self.controle_page)
            self._select_page(index)

    def refresh_all_tabs(self) -> None:
        """Atualiza a pagina visivel imediatamente; as demais sao marcadas para
        atualizar quando forem abertas (evita recarregar o app inteiro a cada acao)."""
        self._refresh_user_info()
        current_index = self.stack.currentIndex()
        self._dirty_pages = {i for i in range(len(self.pages)) if i != current_index}
        if 0 <= current_index < len(self.pages):
            page = self.pages[current_index]
            if hasattr(page, "refresh_data"):
                page.refresh_data()

    def _refresh_user_info(self) -> None:
        user = self.services.session_service.current_user
        if not user:
            self.user_label.setText("Usuario: nao autenticado")
            return
        self.user_label.setText(f'Usuario: {user["username"]} ({user["tipo_usuario"]})')

    # Sessao

    def logout(self) -> None:
        answer = QMessageBox.question(
            self, APP_NAME, "Deseja encerrar a sessao atual e voltar para o login?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        current_user = self.services.session_service.current_user
        current_username = current_user["username"] if current_user else ""
        self.services.auth_service.revoke_remembered_session(
            self.services.session_service.get_remembered_token()
        )
        save_login_preferences(current_username, remember_credential=False, remembered_token=None)
        self.logout_requested = True
        self.services.session_service.logout()
        self.close()

    # Banco

    def backup_database(self) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path, _filter = QFileDialog.getSaveFileName(
            self,
            "Salvar backup do banco",
            str(self.db_path.parent / f"{self.db_path.stem}_backup_{timestamp}.db"),
            "Banco SQLite (*.db);;Todos os arquivos (*.*)",
        )
        if not file_path:
            return

        try:
            result = self.services.database_maintenance_service.create_backup(file_path)
        except ValidationError as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))
            return

        QMessageBox.information(
            self,
            APP_NAME,
            f'Backup gerado com sucesso.\n\nArquivo: {result["path"]}\nTamanho: {result["size_bytes"]} bytes',
        )

    def configure_auto_backup(self) -> None:
        dialog = BackupSettingsDialog(load_auto_backup_settings(), self)
        dialog.exec()
        if dialog.result is None:
            return

        settings = save_auto_backup_settings(dialog.result)
        state_label = "ativado" if settings["enabled"] else "desativado"
        QMessageBox.information(self, APP_NAME, f"Backup automatico {state_label}.")

    def open_auto_backup_directory(self) -> None:
        settings = load_auto_backup_settings()
        backup_dir = Path(settings["directory"]).expanduser()
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            open_directory_in_file_manager(backup_dir)
        except (OSError, ValidationError) as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))

    def run_auto_backup_if_due(self) -> None:
        settings = load_auto_backup_settings()
        if not should_run_auto_backup(settings):
            return

        try:
            result = self.services.database_maintenance_service.create_timestamped_backup(
                settings["directory"], keep_last=settings["keep_last"]
            )
            mark_auto_backup_created(result)
        except ValidationError as exc:
            QMessageBox.warning(self, APP_NAME, f"Nao foi possivel gerar o backup automatico.\n\n{exc}")

    def restore_database(self) -> None:
        file_path, _filter = QFileDialog.getOpenFileName(
            self,
            "Selecionar backup para restaurar",
            str(self.db_path.parent),
            "Banco SQLite (*.db);;Todos os arquivos (*.*)",
        )
        if not file_path:
            return
        first = QMessageBox.question(
            self,
            APP_NAME,
            "A restauracao substituira os dados atuais do banco em uso.\n\nDeseja continuar?",
        )
        if first != QMessageBox.StandardButton.Yes:
            return
        second = QMessageBox.question(self, APP_NAME, "Confirma a restauracao definitiva desse backup?")
        if second != QMessageBox.StandardButton.Yes:
            return

        try:
            self.services.database_maintenance_service.restore_backup(file_path)
        except ValidationError as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))
            return

        QMessageBox.information(
            self,
            APP_NAME,
            "Backup restaurado com sucesso. O sistema sera recarregado para aplicar os dados restaurados.",
        )
        self.restart_requested = True
        self.close()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        for page in self.pages:
            shutdown = getattr(page, "shutdown", None)
            if callable(shutdown):
                shutdown()
        super().closeEvent(event)
