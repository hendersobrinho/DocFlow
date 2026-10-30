from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.icons import app_icon
from documentos_empresa_app.qt_ui.widgets.common import make_button
from documentos_empresa_app.utils.auto_backup import (
    MAX_AUTO_BACKUP_INTERVAL_DAYS,
    MAX_AUTO_BACKUP_KEEP_LAST,
    MIN_AUTO_BACKUP_INTERVAL_DAYS,
    MIN_AUTO_BACKUP_KEEP_LAST,
    normalize_auto_backup_settings,
)
from documentos_empresa_app.utils.common import APP_NAME
from documentos_empresa_app.utils.helpers import load_backup_encryption_password, save_backup_encryption_password

SECTION_TITLE_STYLE = "font-weight: 600; font-size: 10.5pt;"


class BackupSettingsDialog(QDialog):
    def __init__(self, settings: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.original_settings = normalize_auto_backup_settings(settings)
        self.result: dict | None = None

        self.setWindowTitle(f"{APP_NAME} - Backup automático")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(600, 420)
        self.resize(640, 900)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        outer_layout.addWidget(scroll_area, 1)

        content = QWidget()
        scroll_area.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        intro = QLabel(
            "Gera uma copia do banco de dados sozinho, sem precisar clicar em \"Fazer backup...\" "
            "toda vez. Importante: isso so roda enquanto o programa esta aberto - ao abrir o "
            "DocFlow, se já passou do intervalo configurado desde o último backup, um novo e "
            "gerado na hora, em segundo plano, sem travar a tela."
        )
        intro.setObjectName("Muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.enabled_check = QCheckBox("Ativar backup automático")
        self.enabled_check.setChecked(self.original_settings["enabled"])
        self.enabled_check.toggled.connect(self._toggle_fields)
        layout.addWidget(self.enabled_check)

        layout.addWidget(self._separator())

        layout.addWidget(self._section_title("Onde salvar"))
        directory_row = QHBoxLayout()
        directory_row.setSpacing(10)
        self.directory_edit = QLineEdit(self.original_settings["directory"])
        directory_row.addWidget(self.directory_edit, 1)
        self.choose_button = make_button("Escolher...")
        self.choose_button.clicked.connect(self.choose_directory)
        directory_row.addWidget(self.choose_button)
        layout.addLayout(directory_row)

        layout.addWidget(self._section_title("Com que frequencia"))
        interval_row = QHBoxLayout()
        interval_row.setSpacing(10)
        interval_row.addWidget(QLabel("Gerar um novo backup a cada"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(MIN_AUTO_BACKUP_INTERVAL_DAYS, MAX_AUTO_BACKUP_INTERVAL_DAYS)
        self.interval_spin.setValue(int(self.original_settings["interval_days"]))
        self.interval_spin.setSuffix(" dia(s)")
        interval_row.addWidget(self.interval_spin)
        interval_row.addStretch(1)
        layout.addLayout(interval_row)
        interval_hint = QLabel(
            "Contado a partir do último backup (automático ou manual) - não e um horário fixo do "
            "dia, e sim \"faz um novo quando tiver passado esse tanto de tempo\"."
        )
        interval_hint.setObjectName("Muted")
        interval_hint.setWordWrap(True)
        layout.addWidget(interval_hint)

        layout.addWidget(self._section_title("Quantos guardar"))
        keep_last_row = QHBoxLayout()
        keep_last_row.setSpacing(10)
        keep_last_row.addWidget(QLabel("Manter os"))
        self.keep_last_spin = QSpinBox()
        self.keep_last_spin.setRange(MIN_AUTO_BACKUP_KEEP_LAST, MAX_AUTO_BACKUP_KEEP_LAST)
        self.keep_last_spin.setValue(int(self.original_settings["keep_last"]))
        self.keep_last_spin.setSuffix(" backup(s) mais recente(s)")
        keep_last_row.addWidget(self.keep_last_spin)
        keep_last_row.addStretch(1)
        layout.addLayout(keep_last_row)
        keep_last_hint = QLabel(
            "Backups automáticos mais antigos que esse número são apagados sozinhos dessa pasta pra "
            "não ocupar espaço em disco sem limite. Backups feitos manualmente (botão \"Fazer "
            "backup...\") ou guardados em outra pasta nunca são apagados por essa regra."
        )
        keep_last_hint.setObjectName("Muted")
        keep_last_hint.setWordWrap(True)
        layout.addWidget(keep_last_hint)

        layout.addWidget(self._separator())

        layout.addWidget(self._section_title("Protecao com senha (opcional)"))
        self.password_edit = QLineEdit(load_backup_encryption_password() or "")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Deixe em branco para não criptografar os backups")
        layout.addWidget(self.password_edit)
        password_hint = QLabel(
            "Se preenchida, essa senha passa a valer para TODOS os backups deste computador (os "
            "automáticos daqui e também os manuais do botão \"Fazer backup...\"), e será exigida "
            "para restaurar qualquer um deles depois. Guarde-a em lugar seguro: se for perdida, os "
            "backups criptografados ficam irrecuperáveis - não tem como abrir sem a senha."
        )
        password_hint.setObjectName("Muted")
        password_hint.setWordWrap(True)
        layout.addWidget(password_hint)

        layout.addWidget(self._separator())

        layout.addWidget(self._section_title("Situação atual"))
        status_text = "Ativado" if self.original_settings["enabled"] else "Desativado"
        status_label = QLabel(f"Backup automático: {status_text}")
        layout.addWidget(status_label)
        info_at = QLabel(f"Último backup gerado: {self._format_timestamp(self.original_settings.get('last_backup_at'))}")
        info_at.setObjectName("Muted")
        layout.addWidget(info_at)
        info_path = QLabel(f"Arquivo: {self.original_settings.get('last_backup_path') or '-'}")
        info_path.setObjectName("Muted")
        info_path.setWordWrap(True)
        layout.addWidget(info_path)

        outer_layout.addWidget(self._separator())

        buttons_row = QWidget()
        buttons_layout = QHBoxLayout(buttons_row)
        buttons_layout.setContentsMargins(20, 12, 20, 16)
        buttons_layout.addStretch(1)
        cancel_button = make_button("Cancelar", "quiet")
        cancel_button.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_button)
        save_button = make_button("Salvar", "primary")
        save_button.clicked.connect(self.confirm)
        buttons_layout.addWidget(save_button)
        outer_layout.addWidget(buttons_row)

        self._toggle_fields()

    def _section_title(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(SECTION_TITLE_STYLE)
        return label

    def _separator(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        return line

    def _format_timestamp(self, raw_value: str | None) -> str:
        if not raw_value:
            return "Nunca"
        try:
            return datetime.fromisoformat(raw_value).strftime("%d/%m/%Y %H:%M")
        except ValueError:
            return raw_value

    def choose_directory(self) -> None:
        initial_dir = Path(self.directory_edit.text()).expanduser()
        if not initial_dir.exists():
            initial_dir = Path.home()
        selected = QFileDialog.getExistingDirectory(
            self, "Escolha a pasta dos backups automáticos", str(initial_dir)
        )
        if selected:
            self.directory_edit.setText(selected)

    def confirm(self) -> None:
        settings = normalize_auto_backup_settings(
            {
                "enabled": self.enabled_check.isChecked(),
                "directory": self.directory_edit.text(),
                "interval_days": self.interval_spin.value(),
                "keep_last": self.keep_last_spin.value(),
                "last_backup_at": self.original_settings.get("last_backup_at"),
                "last_backup_path": self.original_settings.get("last_backup_path"),
            }
        )

        if settings["enabled"]:
            backup_dir = Path(settings["directory"]).expanduser()
            try:
                backup_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                QMessageBox.critical(self, APP_NAME, "Não foi possível criar ou acessar a pasta de backup.")
                return
            if not backup_dir.is_dir():
                QMessageBox.critical(self, APP_NAME, "Informe uma pasta válida para o backup automático.")
                return

        save_backup_encryption_password(self.password_edit.text())
        self.result = settings
        self.accept()

    def _toggle_fields(self) -> None:
        enabled = self.enabled_check.isChecked()
        self.directory_edit.setEnabled(enabled)
        self.choose_button.setEnabled(enabled)
        self.interval_spin.setEnabled(enabled)
        self.keep_last_spin.setEnabled(enabled)
