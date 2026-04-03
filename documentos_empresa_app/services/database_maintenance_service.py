from __future__ import annotations

from pathlib import Path
import sqlite3

from documentos_empresa_app.database.connection import DatabaseManager
from documentos_empresa_app.utils.common import ValidationError


class DatabaseMaintenanceService:
    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db_manager = db_manager
        self.db_path = db_manager.db_path

    def create_backup(self, target_path: str | Path) -> dict:
        destination = self._normalize_target_path(target_path)
        if destination.resolve() == self.db_path.resolve():
            raise ValidationError("Escolha um arquivo diferente do banco atual para gerar o backup.")

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with self.db_manager.connect() as source_connection:
                with sqlite3.connect(destination) as backup_connection:
                    source_connection.backup(backup_connection)
        except (OSError, sqlite3.Error) as exc:
            raise ValidationError("Nao foi possivel gerar o backup do banco de dados.") from exc

        return {
            "path": str(destination),
            "size_bytes": destination.stat().st_size,
        }

    def restore_backup(self, source_path: str | Path) -> dict:
        source = self._normalize_existing_file(source_path)
        if source.resolve() == self.db_path.resolve():
            raise ValidationError("Selecione um arquivo de backup diferente do banco que ja esta em uso.")

        self._validate_sqlite_file(source)
        try:
            with sqlite3.connect(source) as source_connection:
                with self.db_manager.connect() as destination_connection:
                    source_connection.backup(destination_connection)
        except sqlite3.Error as exc:
            raise ValidationError("Nao foi possivel restaurar o backup selecionado.") from exc

        return {
            "path": str(source),
            "size_bytes": source.stat().st_size,
        }

    def _normalize_target_path(self, raw_path: str | Path) -> Path:
        normalized = Path(str(raw_path or "").strip()).expanduser()
        if not normalized.name:
            raise ValidationError("Informe o arquivo de destino para o backup.")
        return normalized

    def _normalize_existing_file(self, raw_path: str | Path) -> Path:
        normalized = self._normalize_target_path(raw_path)
        if not normalized.exists() or not normalized.is_file():
            raise ValidationError("O arquivo de backup selecionado nao foi encontrado.")
        return normalized

    def _validate_sqlite_file(self, file_path: Path) -> None:
        try:
            with sqlite3.connect(file_path) as connection:
                connection.execute("PRAGMA schema_version").fetchone()
        except sqlite3.Error as exc:
            raise ValidationError("O arquivo selecionado nao parece ser um banco SQLite valido.") from exc
