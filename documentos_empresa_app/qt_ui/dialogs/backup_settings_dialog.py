from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
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


class BackupSettingsDialog(QDialog):
    def __init__(self, settings: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.original_settings = normalize_auto_backup_settings(settings)
        self.result: dict | None = None

        self.setWindowTitle(f"{APP_NAME} - Backup automatico")
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self.enabled_check = QCheckBox("Ativar backup automatico")
        self.enabled_check.setChecked(self.original_settings["enabled"])
        self.enabled_check.toggled.connect(self._toggle_fields)
        layout.addWidget(self.enabled_check)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        grid.addWidget(QLabel("Pasta de backup"), 0, 0, 1, 3)
        self.directory_edit = QLineEdit(self.original_settings["directory"])
        grid.addWidget(self.directory_edit, 1, 0, 1, 2)
        self.choose_button = make_button("Escolher...")
        self.choose_button.clicked.connect(self.choose_directory)
        grid.addWidget(self.choose_button, 1, 2)

        grid.addWidget(QLabel("Intervalo em dias"), 2, 0)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(MIN_AUTO_BACKUP_INTERVAL_DAYS, MAX_AUTO_BACKUP_INTERVAL_DAYS)
        self.interval_spin.setValue(int(self.original_settings["interval_days"]))
        grid.addWidget(self.interval_spin, 3, 0)

        grid.addWidget(QLabel("Manter ultimos"), 2, 1)
        self.keep_last_spin = QSpinBox()
        self.keep_last_spin.setRange(MIN_AUTO_BACKUP_KEEP_LAST, MAX_AUTO_BACKUP_KEEP_LAST)
        self.keep_last_spin.setValue(int(self.original_settings["keep_last"]))
        grid.addWidget(self.keep_last_spin, 3, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)

        last_backup_at = self.original_settings.get("last_backup_at") or "Nunca"
        last_backup_path = self.original_settings.get("last_backup_path") or "-"
        info_at = QLabel(f"Ultimo backup: {last_backup_at}")
        info_at.setObjectName("Muted")
        layout.addWidget(info_at)
        info_path = QLabel(f"Arquivo: {last_backup_path}")
        info_path.setObjectName("Muted")
        info_path.setWordWrap(True)
        layout.addWidget(info_path)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel_button = make_button("Cancelar", "quiet")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(cancel_button)
        save_button = make_button("Salvar", "primary")
        save_button.clicked.connect(self.confirm)
        buttons.addWidget(save_button)
        layout.addLayout(buttons)

        self._toggle_fields()

    def choose_directory(self) -> None:
        initial_dir = Path(self.directory_edit.text()).expanduser()
        if not initial_dir.exists():
            initial_dir = Path.home()
        selected = QFileDialog.getExistingDirectory(
            self, "Escolha a pasta dos backups automaticos", str(initial_dir)
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
                QMessageBox.critical(self, APP_NAME, "Nao foi possivel criar ou acessar a pasta de backup.")
                return
            if not backup_dir.is_dir():
                QMessageBox.critical(self, APP_NAME, "Informe uma pasta valida para o backup automatico.")
                return

        self.result = settings
        self.accept()

    def _toggle_fields(self) -> None:
        enabled = self.enabled_check.isChecked()
        self.directory_edit.setEnabled(enabled)
        self.choose_button.setEnabled(enabled)
        self.interval_spin.setEnabled(enabled)
        self.keep_last_spin.setEnabled(enabled)
