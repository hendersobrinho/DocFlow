from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.app_context import ApplicationServices
from documentos_empresa_app.qt_ui.dialogs.about_dialog import AboutDialog
from documentos_empresa_app.qt_ui.dialogs.backup_settings_dialog import BackupSettingsDialog
from documentos_empresa_app.qt_ui.brand import LOGO_HORIZONTAL_NEGATIVO, TAGLINE, brand_pixmap
from documentos_empresa_app.qt_ui.dialogs.database_connection_dialog import prompt_database_connection_qt
from documentos_empresa_app.qt_ui.dialogs.help_content import DEFAULT_HELP_TOPIC_ID
from documentos_empresa_app.qt_ui.dialogs.help_dialog import HelpDialog
from documentos_empresa_app.qt_ui.dialogs.update_dialog import UpdateDialog
from documentos_empresa_app.qt_ui.icons import app_icon
from documentos_empresa_app.qt_ui.pages.atencao_page import AtencaoPage
from documentos_empresa_app.qt_ui.pages.cobrancas_page import CobrancasPage
from documentos_empresa_app.qt_ui.pages.configuracoes_page import ConfiguracoesPage
from documentos_empresa_app.qt_ui.pages.dashboard_page import DashboardPage
from documentos_empresa_app.qt_ui.pages.documentos_page import DocumentosPage
from documentos_empresa_app.qt_ui.pages.empresas_page import EmpresasPage
from documentos_empresa_app.qt_ui.pages.envios_page import EnviosPage
from documentos_empresa_app.qt_ui.pages.ficha_page import FichaEmpresaPage
from documentos_empresa_app.qt_ui.pages.logs_page import LogsPage
from documentos_empresa_app.qt_ui.pages.panorama_page import PanoramaPage
from documentos_empresa_app.qt_ui.pages.usuarios_page import UsuariosPage
from documentos_empresa_app.qt_ui.theme import ThemeManager
from documentos_empresa_app.qt_ui.widgets.common import make_button, SinglePageStackedWidget
from documentos_empresa_app.qt_ui.workers import BlockingTaskRunner, CallableWorker
from documentos_empresa_app.utils.auto_backup import (
    load_auto_backup_settings,
    mark_auto_backup_created,
    save_auto_backup_settings,
    should_run_auto_backup,
)
from documentos_empresa_app.services.database_maintenance_service import BACKUP_EXTENSION
from documentos_empresa_app.services.mudancas_service import MudancasService
from documentos_empresa_app.services.update_service import UpdateService, can_self_update
from documentos_empresa_app.utils.backup_encryption import is_encrypted_backup
from documentos_empresa_app.utils.common import APP_NAME, APP_TITLE, ValidationError
from documentos_empresa_app.utils.helpers import (
    load_backup_encryption_password,
    open_directory_in_file_manager,
    save_login_preferences,
)


SIDEBAR_WIDTH = 230
NOVIDADES_INTERVALO_MS = 15000  # de quanto em quanto tempo olha se alguem de fora gravou no banco

# Mapeia o titulo de cada pagina (usado em page_defs, dentro de _build_main_area)
# pro topico correspondente do manual (F1) - ver qt_ui/dialogs/help_content.py.
PAGE_TOPIC_IDS = {
    "Painel": "dashboard",
    "Panorama": "panorama",
    "Cobranças": "cobrancas",
    "Precisa de atenção": "atencao",
    "Empresas": "empresas",
    "Ficha da empresa": "ficha",
    "Documentos": "documentos",
    "Configurações": "configuracoes",
    "Envios automáticos": "envios",
    "Usuários": "usuarios",
    "Histórico de ações": "logs",
}

NAV_SECTION_ACOMPANHAMENTO = "ACOMPANHAMENTO"
NAV_SECTION_CADASTROS = "CADASTROS"
NAV_SECTION_ADMINISTRACAO = "ADMINISTRAÇÃO"


class MainWindow(QMainWindow):
    def __init__(self, services: ApplicationServices, on_progress=None) -> None:
        """on_progress(texto, fracao 0-1): chamado enquanto as telas sao montadas, para a
        tela de carregamento mostrar o andamento."""
        super().__init__()
        self.services = services
        self._on_progress = on_progress
        self.logout_requested = False
        self.restart_requested = False
        self.nav_buttons: dict[int, QPushButton] = {}
        self.pages: list[QWidget] = []
        self.page_topic_ids: list[str] = []
        self._dirty_pages: set[int] = set()
        self.help_dialog: HelpDialog | None = None

        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(app_icon())
        self.resize(1440, 880)
        self.setMinimumSize(1100, 720)

        self.help_shortcut = QShortcut(QKeySequence(Qt.Key.Key_F1), self)
        self.help_shortcut.activated.connect(self.open_help)
        # F5 recarrega tudo do banco (o que o Claude ou outro computador gravou), sem fechar.
        self.refresh_shortcut = QShortcut(QKeySequence(Qt.Key.Key_F5), self)
        self.refresh_shortcut.activated.connect(self.atualizar_tudo)
        self.mudancas = MudancasService(self.services.database_maintenance_service.db_manager)

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._build_sidebar(root_layout)
        self._build_main_area(root_layout)

        QTimer.singleShot(800, self.run_auto_backup_if_due)
        # De tempos em tempos olha se alguem de fora gravou no banco e avisa no botao Atualizar.
        self.novidades_timer = QTimer(self)
        self.novidades_timer.setInterval(NOVIDADES_INTERVALO_MS)
        self.novidades_timer.timeout.connect(self._verificar_novidades)
        self.novidades_timer.start()
        if can_self_update():
            QTimer.singleShot(5000, self.check_updates_in_background)

        # A janela aparece primeiro e os dados entram logo em seguida: a primeira carga (fila
        # de cobranca, Painel) leva quase um segundo e nao precisa segurar a tela.
        self._select_page(0)
        QTimer.singleShot(0, self.refresh_all_tabs)

    # Layout

    def _build_sidebar(self, root_layout: QHBoxLayout) -> None:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        root_layout.addWidget(sidebar)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 18, 12, 18)
        layout.setSpacing(4)

        # Logo horizontal em negativo (a barra lateral e navy nos dois temas).
        logo = QLabel()
        logo.setObjectName("SidebarLogo")
        logo.setContentsMargins(10, 2, 0, 6)
        pixmap = brand_pixmap(LOGO_HORIZONTAL_NEGATIVO, 34)
        if pixmap.isNull():
            logo.setText(APP_NAME)
            logo.setStyleSheet("color: white; font-size: 15pt; font-weight: 600;")
        else:
            logo.setPixmap(pixmap)
        logo.setToolTip(TAGLINE)
        layout.addWidget(logo)
        layout.addSpacing(4)

        self.nav_layout = layout
        layout.addStretch(1)

        # Aparece quando a verificacao em segundo plano acha uma versao nova no GitHub.
        self.update_info = None
        self.update_button = make_button("Nova versão disponível", "update")
        self.update_button.setVisible(False)
        self.update_button.clicked.connect(self.open_update_dialog)
        layout.addWidget(self.update_button)

        self.refresh_button = make_button("Atualizar (F5)", "quiet")
        self.refresh_button.setToolTip(
            "Recarrega as telas com o que está no banco agora: o que o Claude, o robô ou outro "
            "computador gravou. Não precisa fechar o DocFlow."
        )
        self.refresh_button.clicked.connect(self.atualizar_tudo)
        layout.addWidget(self.refresh_button)

        tools_row = QHBoxLayout()
        tools_row.setSpacing(6)
        tools_row.addWidget(self._build_database_button(), 1)
        tools_row.addWidget(self._build_help_button(), 1)
        layout.addLayout(tools_row)

        self.theme_button = make_button("Modo claro", "quiet")
        self.theme_button.clicked.connect(self._toggle_theme)
        layout.addWidget(self.theme_button)
        self._sync_theme_button()

        self.user_label = QLabel("")
        self.user_label.setObjectName("SidebarFooter")
        self.user_label.setWordWrap(True)
        layout.addWidget(self.user_label)

        db_manager = self.services.database_maintenance_service.db_manager
        database_label = QLabel(f"Banco: {db_manager.database_name}")
        database_label.setObjectName("SidebarFooter")
        database_label.setToolTip(db_manager.display_name)
        layout.addWidget(database_label)

        logout_button = make_button("Sair", "danger")
        logout_button.setToolTip("Encerrar a sessão e voltar para o login")
        logout_button.clicked.connect(self.logout)
        layout.addWidget(logout_button)

    def _build_database_button(self) -> QPushButton:
        database_button = make_button("Banco", "sidebar")
        database_menu = QMenu(database_button)
        database_menu.addAction("Fazer backup agora...", self.backup_database)
        database_menu.addAction("Backup automático...", self.configure_auto_backup)
        database_menu.addAction("Abrir pasta dos backups automáticos", self.open_auto_backup_directory)
        database_menu.addSeparator()
        restore_action = database_menu.addAction("Restaurar backup...", self.restore_database)
        restore_action.setEnabled(self.services.session_service.is_admin())
        switch_db_action = database_menu.addAction("Trocar banco de dados...", self.trocar_banco_de_dados)
        switch_db_action.setEnabled(self.services.session_service.is_admin())
        database_button.setMenu(database_menu)
        return database_button

    def _build_help_button(self) -> QPushButton:
        help_button = make_button("Ajuda", "sidebar")
        help_menu = QMenu(help_button)
        help_menu.addAction("Manual desta tela (F1)", self.open_help)
        help_menu.addAction("Verificar atualizações...", self.check_updates_now)
        help_menu.addAction("Sobre o DocFlow...", lambda: AboutDialog(self).exec())
        help_button.setMenu(help_menu)
        return help_button

    def _build_main_area(self, root_layout: QHBoxLayout) -> None:
        main_area = QWidget()
        root_layout.addWidget(main_area, 1)
        layout = QVBoxLayout(main_area)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(12)

        self.stack = SinglePageStackedWidget()
        layout.addWidget(self.stack, 1)

        is_admin = self.services.session_service.is_admin()
        specs = [
            (NAV_SECTION_ACOMPANHAMENTO, "Painel", None,
             lambda: DashboardPage(self.services, self.refresh_all_tabs, on_navigate=self.navigate_to)),
            (NAV_SECTION_ACOMPANHAMENTO, "Panorama", "panorama_page",
             lambda: PanoramaPage(self.services, self.refresh_all_tabs, on_open_ficha=self.open_company_ficha)),
            (NAV_SECTION_ACOMPANHAMENTO, "Cobranças", "cobrancas_page",
             lambda: CobrancasPage(self.services, self.refresh_all_tabs, on_open_ficha=self.open_company_ficha)),
            (NAV_SECTION_ACOMPANHAMENTO, "Precisa de atenção", "atencao_page",
             lambda: AtencaoPage(self.services, self.refresh_all_tabs, on_open_ficha=self.open_company_ficha)),
            (NAV_SECTION_CADASTROS, "Empresas", None,
             lambda: EmpresasPage(self.services, self.refresh_all_tabs, on_open_ficha=self.open_company_ficha)),
            (NAV_SECTION_CADASTROS, "Ficha da empresa", "ficha_page",
             lambda: FichaEmpresaPage(self.services, self.refresh_all_tabs)),
            (NAV_SECTION_CADASTROS, "Documentos", None, lambda: DocumentosPage(self.services, self.refresh_all_tabs)),
        ]
        if is_admin:
            specs += [
                (NAV_SECTION_ADMINISTRACAO, "Configurações", None,
                 lambda: ConfiguracoesPage(self.services, self.refresh_all_tabs)),
                (NAV_SECTION_ADMINISTRACAO, "Envios automáticos", None,
                 lambda: EnviosPage(self.services, self.refresh_all_tabs)),
                (NAV_SECTION_ADMINISTRACAO, "Usuários", None, lambda: UsuariosPage(self.services, self.refresh_all_tabs)),
                (NAV_SECTION_ADMINISTRACAO, "Histórico de ações", None,
                 lambda: LogsPage(self.services, self.refresh_all_tabs)),
            ]
        page_defs: list[tuple[str, str, QWidget]] = []
        for numero, (section, title, attribute, factory) in enumerate(specs):
            if self._on_progress:
                self._on_progress(f"Preparando {title}...", numero / len(specs))
            page = factory()
            if attribute:
                setattr(self, attribute, page)
            page_defs.append((section, title, page))

        insert_at = 2
        current_section = None
        for index, (section, title, page) in enumerate(page_defs):
            if section != current_section:
                current_section = section
                section_label = QLabel(section)
                section_label.setObjectName("NavSection")
                self.nav_layout.insertWidget(insert_at, section_label)
                insert_at += 1
            self.pages.append(page)
            self.page_topic_ids.append(PAGE_TOPIC_IDS.get(title, DEFAULT_HELP_TOPIC_ID))
            self.stack.addWidget(page)
            button = make_button(title)
            button.setObjectName("NavButton")
            button.clicked.connect(lambda _checked=False, i=index: self._select_page(i))
            self.nav_layout.insertWidget(insert_at, button)
            insert_at += 1
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
        self.theme_button.setText("Modo claro" if mode == "dark" else "Modo escuro")

    def open_help(self) -> None:
        """Abre o manual (F1 ou menu Ajuda) ja na pagina correspondente a aba atual -
        ver PAGE_TOPIC_IDS e qt_ui/dialogs/help_content.py."""
        current_index = self.stack.currentIndex()
        topic_id = DEFAULT_HELP_TOPIC_ID
        if 0 <= current_index < len(self.page_topic_ids):
            topic_id = self.page_topic_ids[current_index]

        if self.help_dialog is None:
            self.help_dialog = HelpDialog(self)
        self.help_dialog.show_topic(topic_id)
        self.help_dialog.show()
        self.help_dialog.raise_()
        self.help_dialog.activateWindow()

    # Navegacao / atualizacao

    def navigate_to(self, titulo: str, acao: str | None = None) -> None:
        """Abre uma tela pelo titulo do menu. Em Cobrancas, 'acao' filtra uma etapa do funil
        ou, com "rodadas", abre a aba das rodadas do Claude."""
        if titulo not in PAGE_TOPIC_IDS:
            return
        for index, page in enumerate(self.pages):
            if self.nav_buttons[index].text().split(" (")[0] == titulo:
                self._select_page(index)
                break
        if titulo == "Cobranças" and acao:
            if acao == "rodadas":
                self.cobrancas_page.tabs.setCurrentIndex(3)
            else:
                self.cobrancas_page.show_action(acao)

    def open_company_ficha(
        self, company_id: int, documento_id: int | None = None, competencia: str | None = None
    ) -> None:
        """Abre a ficha da empresa; com documento (e competencia), ja deixa ele selecionado."""
        index = self.pages.index(self.ficha_page)
        self._select_page(index)
        self.ficha_page.open_company(company_id)
        if documento_id is not None:
            self.ficha_page.focus_document(documento_id, competencia)

    def refresh_all_tabs(self) -> None:
        """Atualiza a pagina visivel imediatamente; as demais sao marcadas para
        atualizar quando forem abertas (evita recarregar o app inteiro a cada acao)."""
        self._refresh_user_info()
        # O contador do menu vem depois da tela atual: quem clicou ve a resposta primeiro.
        QTimer.singleShot(0, self._refresh_attention_badge)
        current_index = self.stack.currentIndex()
        self._dirty_pages = {i for i in range(len(self.pages)) if i != current_index}
        if 0 <= current_index < len(self.pages):
            page = self.pages[current_index]
            if hasattr(page, "refresh_data"):
                page.refresh_data()

    def atualizar_tudo(self) -> None:
        """Le tudo do banco de novo (sem fechar o sistema): limpa os caches de leitura e
        recarrega a tela atual; as outras recarregam quando forem abertas."""
        self.mudancas.invalidar_caches()
        self.refresh_all_tabs()
        self.mudancas.marcar_visto()
        self._mostrar_novidades(False)

    def _verificar_novidades(self) -> None:
        if not self.isVisible() or QApplication.activeModalWidget() is not None:
            return
        if self.mudancas.ha_novidades():
            self._mostrar_novidades(True)

    def _mostrar_novidades(self, ha: bool) -> None:
        self.refresh_button.setText("Atualizar · há novidades (F5)" if ha else "Atualizar (F5)")
        self.refresh_button.setProperty("variant", "update" if ha else "quiet")
        self.refresh_button.style().unpolish(self.refresh_button)
        self.refresh_button.style().polish(self.refresh_button)

    def _refresh_attention_badge(self) -> None:
        """Mostra no menu quantos documentos e rodadas estao esperando uma pessoa."""
        index = self.pages.index(self.atencao_page)
        button = self.nav_buttons.get(index)
        if button is None:
            return
        try:
            total = len(self.services.cobranca_service.precisa_de_atencao()) + len(
                self.services.rodada_service.rodadas_com_problema(50)
            )
        except Exception:  # noqa: BLE001 - o contador nunca pode derrubar a janela
            total = 0
        button.setText(f"Precisa de atenção ({total})" if total else "Precisa de atenção")
        button.setProperty("alert", "true" if total else "false")
        button.style().unpolish(button)
        button.style().polish(button)

    def _refresh_user_info(self) -> None:
        user = self.services.session_service.current_user
        if not user:
            self.user_label.setText("Nenhum usuário conectado")
            return
        perfil = "administrador" if user["tipo_usuario"] == "admin" else "usuário comum"
        self.user_label.setText(f'Conectado como {user["username"]} ({perfil})')

    # Sessao

    def logout(self) -> None:
        answer = QMessageBox.question(
            self, APP_NAME, "Deseja encerrar a sessão atual e voltar para o login?"
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
        database_name = self.services.database_maintenance_service.db_manager.database_name
        file_path, _filter = QFileDialog.getSaveFileName(
            self,
            "Salvar backup do banco",
            str(self._backup_dialog_directory() / f"{database_name}_backup_{timestamp}{BACKUP_EXTENSION}"),
            f"Backup do DocFlow (*{BACKUP_EXTENSION});;Todos os arquivos (*.*)",
        )
        if not file_path:
            return

        backup_password = load_backup_encryption_password()
        runner = BlockingTaskRunner(self)
        runner.run(
            "Gerando backup do banco de dados...",
            lambda: self.services.database_maintenance_service.create_backup(file_path, password=backup_password),
            on_success=self._on_backup_created,
            on_error=lambda message: QMessageBox.critical(self, APP_NAME, message),
        )

    @staticmethod
    def _backup_dialog_directory() -> Path:
        directory = Path(load_auto_backup_settings()["directory"]).expanduser()
        return directory if directory.is_dir() else Path.home()

    def _on_backup_created(self, result: dict) -> None:
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
        QMessageBox.information(self, APP_NAME, f"Backup automático {state_label}.")

    def open_auto_backup_directory(self) -> None:
        settings = load_auto_backup_settings()
        backup_dir = Path(settings["directory"]).expanduser()
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            open_directory_in_file_manager(backup_dir)
        except (OSError, ValidationError) as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))

    def run_auto_backup_if_due(self) -> None:
        """Roda em thread de fundo, sem dialogo: o backup automatico deve ser
        silencioso (so avisa em caso de falha) e nao pode travar a interface."""
        settings = load_auto_backup_settings()
        if not should_run_auto_backup(settings):
            return

        backup_password = load_backup_encryption_password()
        self._auto_backup_thread = QThread(self)
        self._auto_backup_worker = CallableWorker(
            lambda: self.services.database_maintenance_service.create_timestamped_backup(
                settings["directory"], keep_last=settings["keep_last"], password=backup_password
            )
        )
        self._auto_backup_worker.moveToThread(self._auto_backup_thread)
        self._auto_backup_thread.started.connect(self._auto_backup_worker.run)
        self._auto_backup_worker.finished.connect(self._on_auto_backup_finished)
        self._auto_backup_worker.failed.connect(self._on_auto_backup_failed)
        self._auto_backup_worker.finished.connect(self._auto_backup_thread.quit)
        self._auto_backup_worker.failed.connect(self._auto_backup_thread.quit)
        self._auto_backup_thread.finished.connect(self._auto_backup_worker.deleteLater)
        self._auto_backup_thread.start()

    # Atualizacao automatica

    def check_updates_in_background(self) -> None:
        """Consulta o GitHub sem travar a tela; falha de internet fica so no log."""
        self.update_service = UpdateService()
        self._update_thread = QThread(self)
        self._update_worker = CallableWorker(self.update_service.check)
        self._update_worker.moveToThread(self._update_thread)
        self._update_thread.started.connect(self._update_worker.run)
        self._update_worker.finished.connect(self._on_update_checked)
        self._update_worker.finished.connect(self._update_thread.quit)
        self._update_worker.failed.connect(self._update_thread.quit)
        self._update_thread.finished.connect(self._update_worker.deleteLater)
        self._update_thread.start()

    def _on_update_checked(self, info) -> None:
        self.update_info = info
        if info is not None:
            self.update_button.setText(f"Atualizar para {info.versao}")
            self.update_button.setToolTip("Tem versão nova do DocFlow. Clique para ver o que mudou e atualizar.")
            self.update_button.setVisible(True)

    def check_updates_now(self) -> None:
        self.update_service = UpdateService()

        def ok(info) -> None:
            self._on_update_checked(info)
            if info is None:
                QMessageBox.information(
                    self, APP_NAME, f"Você já está na versão mais recente ({self.update_service.current_version})."
                )
            else:
                self.open_update_dialog()

        BlockingTaskRunner(self).run(
            "Procurando versão nova...",
            self.update_service.check,
            on_success=ok,
            on_error=lambda message: QMessageBox.warning(self, APP_NAME, message),
        )

    def open_update_dialog(self) -> None:
        if self.update_info is None:
            return
        dialog = UpdateDialog(self.update_service, self.update_info, self)
        dialog.exec()
        if dialog.installing:
            # O instalador espera o DocFlow fechar, instala e abre a versao nova.
            self.close()

    def _on_auto_backup_finished(self, result: dict) -> None:
        mark_auto_backup_created(result)

    def _on_auto_backup_failed(self, message: str) -> None:
        QMessageBox.warning(self, APP_NAME, f"Não foi possível gerar o backup automático.\n\n{message}")

    def restore_database(self) -> None:
        file_path, _filter = QFileDialog.getOpenFileName(
            self,
            "Selecionar backup para restaurar",
            str(self._backup_dialog_directory()),
            f"Backups do DocFlow (*{BACKUP_EXTENSION} *.db);;Todos os arquivos (*.*)",
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

        restore_password = None
        if is_encrypted_backup(Path(file_path)):
            restore_password = load_backup_encryption_password()
            if not restore_password:
                restore_password, confirmed = QInputDialog.getText(
                    self,
                    APP_NAME,
                    "Este backup esta protegido por senha. Informe a senha de criptografia:",
                    QLineEdit.EchoMode.Password,
                )
                if not confirmed or not restore_password:
                    return

        runner = BlockingTaskRunner(self)
        runner.run(
            "Restaurando backup do banco de dados...",
            lambda: self.services.database_maintenance_service.restore_backup(file_path, password=restore_password),
            on_success=self._on_backup_restored,
            on_error=lambda message: QMessageBox.critical(self, APP_NAME, message),
        )

    def _on_backup_restored(self, result: dict) -> None:
        QMessageBox.information(
            self,
            APP_NAME,
            "Backup restaurado com sucesso. O sistema será recarregado para aplicar os dados restaurados.",
        )
        self.restart_requested = True
        self.close()

    def trocar_banco_de_dados(self) -> None:
        """Aponta esta instalacao (deste usuario do sistema operacional) pra outro
        banco PostgreSQL - outro servidor ou outro banco no mesmo servidor - e reinicia
        o sistema com ele.
        Util pra montar setores/departamentos isolados numa mesma maquina/servidor de
        Area de Trabalho Remota: cada usuario do Windows/Linux tem sua propria config
        (%USERPROFILE%/AppData/Roaming/DocFlow ou equivalente), entao cada um pode
        apontar pro banco compartilhado do seu setor ou pra um banco proprio, sem
        misturar com os outros."""
        answer = QMessageBox.question(
            self,
            APP_NAME,
            "Trocar o banco de dados encerra a sessão atual e reabre o sistema já "
            "apontando para o banco escolhido (pode ser um banco existente ou um "
            "novo, vazio). Deseja continuar?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        new_conninfo = prompt_database_connection_qt(self)
        if new_conninfo is None:
            return

        self.restart_requested = True
        self.close()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        for page in self.pages:
            shutdown = getattr(page, "shutdown", None)
            if callable(shutdown):
                shutdown()
        self._wait_for_auto_backup_thread()
        update_thread = getattr(self, "_update_thread", None)
        if update_thread is not None and update_thread.isRunning():
            update_thread.wait(3000)
        super().closeEvent(event)

    def _wait_for_auto_backup_thread(self) -> None:
        """Aguarda o backup automatico em segundo plano terminar antes de fechar -
        destruir a QThread no meio de uma copia do banco poderia corromper o backup."""
        thread = getattr(self, "_auto_backup_thread", None)
        if thread is not None and thread.isRunning():
            thread.wait(15000)
