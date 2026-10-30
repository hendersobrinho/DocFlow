from __future__ import annotations

import psycopg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QWidget,
)

from documentos_empresa_app.qt_ui.widgets.brand_dialog import BrandDialog, add_password_toggle
from documentos_empresa_app.qt_ui.widgets.common import make_button
from documentos_empresa_app.utils.common import APP_NAME
from documentos_empresa_app.utils.database_settings import (
    DATABASE_URL_ENV_VAR,
    SSL_MODES,
    build_conninfo,
    get_database_url_from_env,
    load_database_settings,
    load_legacy_sqlite_path,
    normalize_database_settings,
    resolve_database_conninfo,
    save_database_settings,
)

TEST_CONNECT_TIMEOUT_SECONDS = 5
SSL_MODE_LABELS = {
    "prefer": "Usar SSL se o servidor oferecer",
    "disable": "Sem SSL",
    "require": "Exigir SSL",
}


class DatabaseConnectionDialog(BrandDialog):
    def __init__(self, settings: dict, parent: QWidget | None = None) -> None:
        super().__init__(
            "Conexão com o banco",
            "Os dados do DocFlow ficam num servidor PostgreSQL. Informe onde ele está - "
            "as tabelas são criadas sozinhas na primeira conexão.",
            panel_width=320,
            parent=parent,
        )
        self.result: dict | None = None

        self.setWindowTitle(f"{APP_NAME} - Banco de dados")
        self.setMinimumSize(880, 600)

        self.add_heading("Onde estão os dados", "O banco precisa já existir no servidor.")

        self.host_edit = QLineEdit(settings["host"])
        self.host_edit.setPlaceholderText("localhost (vazio = este computador)")
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(settings["port"])
        self.port_spin.setMinimumWidth(110)
        server_row = QWidget()
        server_layout = QHBoxLayout(server_row)
        server_layout.setContentsMargins(0, 0, 0, 0)
        server_layout.setSpacing(8)
        server_layout.addWidget(self.host_edit, 1)
        server_layout.addWidget(self.port_spin)
        self.host_edit.setMinimumHeight(40)
        self.port_spin.setMinimumHeight(40)
        self.add_field("Servidor e porta", server_row)

        self.dbname_edit = QLineEdit(settings["dbname"])
        self.add_field("Banco de dados", self.dbname_edit)

        credentials = QWidget()
        grid = QGridLayout(credentials)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        self.user_edit = QLineEdit(settings["user"])
        self.user_edit.setPlaceholderText("vazio = usuário do sistema")
        self.password_edit = QLineEdit(settings["password"])
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        add_password_toggle(self.password_edit)
        for column, (label, widget) in enumerate((("Usuário", self.user_edit), ("Senha", self.password_edit))):
            caption = QLabel(label)
            caption.setObjectName("FieldLabel")
            grid.addWidget(caption, 0, column)
            widget.setMinimumHeight(40)
            grid.addWidget(widget, 1, column)
        self.add_widget(credentials)
        self.form_layout.addSpacing(8)

        self.sslmode_combo = QComboBox()
        for mode in SSL_MODES:
            self.sslmode_combo.addItem(SSL_MODE_LABELS[mode], mode)
        self.sslmode_combo.setCurrentIndex(max(0, self.sslmode_combo.findData(settings["sslmode"])))
        self.add_field("Conexão segura", self.sslmode_combo)

        if get_database_url_from_env():
            self.show_message(
                f"A variável de ambiente {DATABASE_URL_ENV_VAR} está definida neste computador "
                "e tem prioridade sobre os dados salvos aqui.",
                "info",
            )
        self.add_message_area()
        self.form_layout.addStretch(1)

        buttons = QHBoxLayout()
        test_button = make_button("Testar conexão")
        test_button.clicked.connect(self.test_connection)
        buttons.addWidget(test_button)
        buttons.addStretch(1)
        cancel_button = make_button("Cancelar", "quiet")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(cancel_button)
        confirm_button = make_button("Salvar e conectar", "primary")
        confirm_button.setDefault(True)
        confirm_button.clicked.connect(self.confirm)
        buttons.addWidget(confirm_button)
        self.form_layout.addLayout(buttons)

    def current_settings(self) -> dict:
        return normalize_database_settings(
            {
                "host": self.host_edit.text(),
                "port": self.port_spin.value(),
                "dbname": self.dbname_edit.text(),
                "user": self.user_edit.text(),
                "password": self.password_edit.text(),
                "sslmode": self.sslmode_combo.currentData(),
            }
        )

    def test_connection(self) -> None:
        settings = self._validated_settings()
        if settings is None:
            return
        error = self._try_connect(settings)
        if error:
            self.show_message(f"Não foi possível conectar ao banco.\n{error}")
            return
        self.show_message(f'Conexão com "{settings["dbname"]}" funcionando.', "success")

    def confirm(self) -> None:
        settings = self._validated_settings()
        if settings is None:
            return
        error = self._try_connect(settings)
        if error:
            answer = QMessageBox.question(
                self,
                APP_NAME,
                f"Não foi possível conectar com esses dados.\n\n{error}\n\nDeseja salvar mesmo assim?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.result = settings
        self.accept()

    def _validated_settings(self) -> dict | None:
        settings = self.current_settings()
        if not settings["dbname"]:
            self.show_message("Informe o nome do banco de dados.")
            self.dbname_edit.setFocus()
            return None
        return settings

    @staticmethod
    def _try_connect(settings: dict) -> str | None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            with psycopg.connect(build_conninfo(settings), connect_timeout=TEST_CONNECT_TIMEOUT_SECONDS) as connection:
                connection.execute("SELECT 1")
        except psycopg.Error as exc:
            return str(exc).strip() or exc.__class__.__name__
        finally:
            QApplication.restoreOverrideCursor()
        return None


def prompt_database_connection_qt(parent: QWidget | None = None) -> str | None:
    """Abre o dialogo ja preenchido com a conexao salva; devolve a nova conninfo (ja
    salva na configuracao local) ou None se o usuario cancelar."""
    dialog = DatabaseConnectionDialog(load_database_settings(), parent)
    dialog.exec()
    if dialog.result is None:
        return None
    save_database_settings(dialog.result)
    return resolve_database_conninfo()


def ensure_database_connection_qt(parent: QWidget | None = None) -> str | None:
    conninfo = resolve_database_conninfo()
    if conninfo:
        return conninfo

    message = "Configure o acesso ao banco de dados PostgreSQL para continuar."
    legacy_path = load_legacy_sqlite_path()
    if legacy_path:
        message = (
            "O DocFlow agora guarda os dados em um servidor PostgreSQL.\n\n"
            "Configure o acesso ao banco para continuar. Depois, para trazer os dados que "
            "estavam no banco antigo, use o menu Banco > Restaurar backup... e selecione o "
            f"arquivo:\n{legacy_path}"
        )
    QMessageBox.information(parent, APP_NAME, message)
    return prompt_database_connection_qt(parent)
