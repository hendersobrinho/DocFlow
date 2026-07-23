from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.icons import app_icon
from documentos_empresa_app.qt_ui.widgets.common import make_button
from documentos_empresa_app.utils.common import APP_NAME, DEFAULT_DB_NAME, ValidationError
from documentos_empresa_app.utils.helpers import (
    ensure_config_dir,
    get_install_root_directory,
    is_database_path_usable,
    load_config,
    save_config,
)
from documentos_empresa_app.utils.resources import get_executable_directory
from documentos_empresa_app.utils.storage import (
    build_database_path,
    create_database_directory,
    is_path_within_directory,
)


class DatabasePathDialog(QDialog):
    def __init__(self, initial_dir: Path, default_filename: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.result: Path | None = None

        self.setWindowTitle(f"{APP_NAME} - Banco de dados")
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(640)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        instructions = QLabel(
            "Escolha a pasta onde o banco SQLite sera salvo.\n"
            "Se precisar, voce pode criar uma nova pasta antes de confirmar."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        grid.addWidget(QLabel("Pasta de destino"), 0, 0, 1, 3)
        self.folder_edit = QLineEdit(str(initial_dir))
        self.folder_edit.textChanged.connect(self._update_preview)
        grid.addWidget(self.folder_edit, 1, 0)
        choose_button = make_button("Escolher pasta")
        choose_button.clicked.connect(self.choose_folder)
        grid.addWidget(choose_button, 1, 1)
        create_button = make_button("Criar pasta")
        create_button.clicked.connect(self.create_folder)
        grid.addWidget(create_button, 1, 2)

        grid.addWidget(QLabel("Nome do arquivo do banco"), 2, 0, 1, 3)
        self.filename_edit = QLineEdit(default_filename)
        self.filename_edit.setMaximumWidth(280)
        self.filename_edit.textChanged.connect(self._update_preview)
        grid.addWidget(self.filename_edit, 3, 0)
        grid.setColumnStretch(0, 1)
        layout.addLayout(grid)

        layout.addWidget(QLabel("Caminho final"))
        self.preview_label = QLabel("")
        self.preview_label.setObjectName("Muted")
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel_button = make_button("Cancelar", "quiet")
        cancel_button.clicked.connect(self.cancel)
        buttons.addWidget(cancel_button)
        confirm_button = make_button("Confirmar", "primary")
        confirm_button.clicked.connect(self.confirm)
        buttons.addWidget(confirm_button)
        layout.addLayout(buttons)

        self._update_preview()

    def choose_folder(self) -> None:
        initial_dir = Path(self.folder_edit.text()).expanduser()
        if not initial_dir.exists():
            initial_dir = get_install_root_directory()
        selected = QFileDialog.getExistingDirectory(
            self, "Escolha a pasta onde o banco sera salvo", str(initial_dir)
        )
        if selected:
            self.folder_edit.setText(selected)

    def create_folder(self) -> None:
        base_folder = self.folder_edit.text().strip() or str(get_install_root_directory())
        folder_name, confirmed = QInputDialog.getText(
            self, f"{APP_NAME} - Criar pasta", "Informe o nome da nova pasta:"
        )
        if not confirmed:
            return
        try:
            created_folder = create_database_directory(base_folder, folder_name)
        except ValidationError as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))
            return
        except OSError:
            QMessageBox.critical(self, APP_NAME, "Nao foi possivel criar a pasta no local informado.")
            return

        self.folder_edit.setText(str(created_folder))
        QMessageBox.information(self, APP_NAME, f"Pasta criada com sucesso em:\n{created_folder}")

    def confirm(self) -> None:
        try:
            db_path = build_database_path(self.folder_edit.text(), self.filename_edit.text(), DEFAULT_DB_NAME)
        except ValidationError as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))
            return

        if getattr(sys, "frozen", False) and is_path_within_directory(db_path, get_executable_directory()):
            QMessageBox.critical(
                self,
                APP_NAME,
                "Escolha uma pasta fora da instalacao do programa para salvar o banco.\n\n"
                "Isso protege os dados durante atualizacoes ou reinstalacoes.",
            )
            return

        if not is_database_path_usable(db_path):
            QMessageBox.critical(
                self,
                APP_NAME,
                "O local informado para o banco nao pode ser usado.\n\n"
                "Escolha outra pasta ou crie uma nova pasta.",
            )
            return

        self.result = db_path
        self.accept()

    def cancel(self) -> None:
        should_cancel = (
            QMessageBox.question(
                self,
                APP_NAME,
                "Nenhum local foi selecionado para o banco de dados.\n\n"
                "Deseja cancelar a abertura do programa?",
            )
            == QMessageBox.StandardButton.Yes
        )
        if should_cancel:
            self.result = None
            self.reject()

    def _update_preview(self) -> None:
        try:
            preview_path = build_database_path(
                self.folder_edit.text(), self.filename_edit.text(), DEFAULT_DB_NAME
            )
            self.preview_label.setText(str(preview_path))
        except ValidationError:
            self.preview_label.setText("")


def prompt_database_path_qt(parent: QWidget | None = None) -> Path | None:
    ensure_config_dir()
    dialog = DatabasePathDialog(get_install_root_directory(), DEFAULT_DB_NAME, parent)
    dialog.exec()

    if dialog.result is None:
        return None

    config = load_config()
    config["db_path"] = str(dialog.result)
    save_config(config)
    return dialog.result


def ensure_database_path_qt(parent: QWidget | None = None) -> Path | None:
    config = load_config()
    db_path = config.get("db_path")
    if db_path and is_database_path_usable(db_path):
        return Path(db_path)
    if db_path and not is_database_path_usable(db_path):
        QMessageBox.warning(
            parent,
            APP_NAME,
            "O caminho salvo para o banco de dados nao esta acessivel.\n\n"
            "Escolha um novo local para continuar.",
        )

    QMessageBox.information(
        parent,
        APP_NAME,
        "Selecione onde o banco SQLite sera armazenado.\n\n"
        "A janela ja sera aberta na raiz do disco principal.\n"
        "Se voce fechar sem escolher, o sistema pedira confirmacao antes de sair.",
    )
    return prompt_database_path_qt(parent)
