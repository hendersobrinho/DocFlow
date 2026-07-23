from __future__ import annotations

from datetime import datetime
import gc
from pathlib import Path
import re
import sqlite3

from documentos_empresa_app.database.connection import DatabaseManager
from documentos_empresa_app.utils.common import ValidationError

REQUIRED_APPLICATION_TABLES = {
    "empresas",
    "tipos_documento",
    "documentos_empresa",
    "periodos",
    "status_documento_mensal",
    "usuarios",
}


class DatabaseMaintenanceService:
    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db_manager = db_manager
        self.db_path = db_manager.db_path

    def create_backup(self, target_path: str | Path) -> dict:
        destination = self._normalize_target_path(target_path)
        if destination.resolve() == self.db_path.resolve():
            raise ValidationError("Escolha um arquivo diferente do banco atual para gerar o backup.")

        backup_connection: sqlite3.Connection | None = None
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with self.db_manager.connect() as source_connection:
                backup_connection = sqlite3.connect(destination)
                source_connection.backup(backup_connection)
                backup_connection.commit()
        except (OSError, sqlite3.Error) as exc:
            raise ValidationError("Nao foi possivel gerar o backup do banco de dados.") from exc
        finally:
            if backup_connection is not None:
                backup_connection.close()
                backup_connection = None
            gc.collect()

        return {
            "path": str(destination),
            "size_bytes": destination.stat().st_size,
        }

    def create_timestamped_backup(
        self,
        target_directory: str | Path,
        *,
        when: datetime | None = None,
        prefix: str | None = None,
        keep_last: int | None = None,
    ) -> dict:
        directory = Path(str(target_directory or "").strip()).expanduser()
        if not directory.name:
            raise ValidationError("Informe a pasta de destino para o backup automatico.")

        backup_time = when or datetime.now()
        backup_prefix = self._normalize_backup_prefix(prefix or self.db_path.stem)
        backup_path = directory / f"{backup_prefix}_auto_backup_{backup_time:%Y%m%d_%H%M%S}.db"
        result = self.create_backup(backup_path)
        result["removed_backups"] = []
        if keep_last is not None:
            result["removed_backups"] = self.prune_timestamped_backups(
                directory,
                prefix=backup_prefix,
                keep_last=keep_last,
            )
        return result

    def prune_timestamped_backups(self, directory: str | Path, *, prefix: str | None = None, keep_last: int) -> list[str]:
        keep_count = max(1, int(keep_last))
        backup_prefix = self._normalize_backup_prefix(prefix or self.db_path.stem)
        backup_directory = Path(directory).expanduser()
        if not backup_directory.exists():
            return []

        backup_files = sorted(
            backup_directory.glob(f"{backup_prefix}_auto_backup_*.db"),
            key=lambda path: path.name,
            reverse=True,
        )
        removed_paths: list[str] = []
        for backup_file in backup_files[keep_count:]:
            try:
                backup_file.unlink()
            except OSError:
                continue
            removed_paths.append(str(backup_file))
        return removed_paths

    def restore_backup(self, source_path: str | Path) -> dict:
        source = self._normalize_existing_file(source_path)
        if source.resolve() == self.db_path.resolve():
            raise ValidationError("Selecione um arquivo de backup diferente do banco que ja esta em uso.")

        self._validate_sqlite_file(source)
        source_connection: sqlite3.Connection | None = None
        try:
            source_connection = sqlite3.connect(source)
            with source_connection:
                with self.db_manager.connect() as destination_connection:
                    source_connection.backup(destination_connection)
        except sqlite3.Error as exc:
            raise ValidationError("Nao foi possivel restaurar o backup selecionado.") from exc
        finally:
            if source_connection is not None:
                source_connection.close()
                source_connection = None
            gc.collect()

        self.optimize_database()

        return {
            "path": str(source),
            "size_bytes": source.stat().st_size,
        }

    def optimize_database(self) -> dict:
        with self.db_manager.connect() as connection:
            connection.execute("PRAGMA optimize")
            page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
            free_pages = int(connection.execute("PRAGMA freelist_count").fetchone()[0])

        return {
            "optimized": True,
            "page_count": page_count,
            "free_pages": free_pages,
        }

    def _normalize_target_path(self, raw_path: str | Path) -> Path:
        normalized = Path(str(raw_path or "").strip()).expanduser()
        if not normalized.name:
            raise ValidationError("Informe o arquivo de destino para o backup.")
        return normalized

    def _normalize_backup_prefix(self, raw_prefix: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(raw_prefix).strip())
        return normalized.strip("._-") or "docflow"

    def _normalize_existing_file(self, raw_path: str | Path) -> Path:
        normalized = self._normalize_target_path(raw_path)
        if not normalized.exists() or not normalized.is_file():
            raise ValidationError("O arquivo de backup selecionado nao foi encontrado.")
        return normalized

    def _validate_sqlite_file(self, file_path: Path) -> None:
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(file_path)
            connection.execute("PRAGMA schema_version").fetchone()
            available_tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            if not REQUIRED_APPLICATION_TABLES.issubset(available_tables):
                raise ValidationError(
                    "O arquivo selecionado nao pertence a este sistema ou esta com estrutura incompleta."
                )
        except sqlite3.Error as exc:
            raise ValidationError("O arquivo selecionado nao parece ser um banco SQLite valido.") from exc
        finally:
            if connection is not None:
                connection.close()
