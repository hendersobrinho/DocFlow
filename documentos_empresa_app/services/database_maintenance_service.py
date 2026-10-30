from __future__ import annotations

from datetime import datetime
import gzip
import json
from pathlib import Path
import re
import sqlite3

from documentos_empresa_app.database.connection import DatabaseError, DatabaseManager
from documentos_empresa_app.database.schema import (
    APPLICATION_TABLES,
    apply_data_normalizations,
    reset_identity_sequences,
    seed_default_data,
)
from documentos_empresa_app.utils.backup_encryption import (
    MAGIC_HEADER,
    decrypt_backup_bytes,
    encrypt_backup_bytes,
)
from documentos_empresa_app.utils.common import ValidationError

REQUIRED_APPLICATION_TABLES = {
    "empresas",
    "tipos_documento",
    "documentos_empresa",
    "periodos",
    "status_documento_mensal",
    "usuarios",
}

BACKUP_FORMAT = "docflow-backup"
BACKUP_FORMAT_VERSION = 1
BACKUP_EXTENSION = ".dfbak"
GZIP_HEADER = b"\x1f\x8b"
# Backups gerados antes da migracao para o PostgreSQL eram o proprio arquivo do SQLite -
# a restauracao continua aceitando esses arquivos, o que tambem serve para importar os
# dados de uma instalacao antiga.
SQLITE_HEADER = b"SQLite format 3\x00"

INTEGER_TYPES = {"smallint", "integer", "bigint"}
FLOAT_TYPES = {"real", "double precision", "numeric"}


class DatabaseMaintenanceService:
    """Backup logico do banco: exporta todas as tabelas do sistema para um JSON compactado
    (opcionalmente criptografado) e restaura a partir dele. Nao depende do pg_dump, entao
    funciona em qualquer maquina com o DocFlow instalado, mesmo sem as ferramentas do
    PostgreSQL."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db_manager = db_manager

    def create_backup(self, target_path: str | Path, password: str | None = None) -> dict:
        destination = self._normalize_target_path(target_path)
        normalized_password = str(password or "").strip()

        try:
            with self.db_manager.connect() as connection:
                # Todas as tabelas sao lidas no mesmo snapshot, para o backup ficar
                # consistente mesmo com outros usuarios gravando ao mesmo tempo.
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                payload = self._export_tables(connection)
        except DatabaseError as exc:
            raise ValidationError("Nao foi possivel gerar o backup do banco de dados.") from exc

        content = gzip.compress(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        if normalized_password:
            content = encrypt_backup_bytes(content, normalized_password)

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        except OSError as exc:
            raise ValidationError("Nao foi possivel gravar o arquivo de backup no local informado.") from exc

        return {
            "path": str(destination),
            "size_bytes": destination.stat().st_size,
            "encrypted": bool(normalized_password),
        }

    def create_timestamped_backup(
        self,
        target_directory: str | Path,
        *,
        when: datetime | None = None,
        prefix: str | None = None,
        keep_last: int | None = None,
        password: str | None = None,
    ) -> dict:
        directory = Path(str(target_directory or "").strip()).expanduser()
        if not directory.name:
            raise ValidationError("Informe a pasta de destino para o backup automatico.")

        backup_time = when or datetime.now()
        backup_prefix = self._normalize_backup_prefix(prefix or self.db_manager.database_name)
        backup_path = directory / f"{backup_prefix}_auto_backup_{backup_time:%Y%m%d_%H%M%S}{BACKUP_EXTENSION}"
        result = self.create_backup(backup_path, password=password)
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
        backup_prefix = self._normalize_backup_prefix(prefix or self.db_manager.database_name)
        backup_directory = Path(directory).expanduser()
        if not backup_directory.exists():
            return []

        backup_files = sorted(
            backup_directory.glob(f"{backup_prefix}_auto_backup_*{BACKUP_EXTENSION}"),
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

    def restore_backup(self, source_path: str | Path, password: str | None = None) -> dict:
        source = self._normalize_existing_file(source_path)
        try:
            raw = source.read_bytes()
        except OSError as exc:
            raise ValidationError("Nao foi possivel ler o arquivo de backup selecionado.") from exc

        plain_file: Path | None = source
        if raw.startswith(MAGIC_HEADER):
            normalized_password = str(password or "").strip()
            if not normalized_password:
                raise ValidationError("Este backup esta protegido por senha. Informe a senha para restaurar.")
            raw = decrypt_backup_bytes(raw, normalized_password)
            plain_file = None

        tables = self._read_backup_tables(raw, plain_file)
        if not REQUIRED_APPLICATION_TABLES.issubset(tables):
            raise ValidationError(
                "O arquivo selecionado nao pertence a este sistema ou esta com estrutura incompleta."
            )

        try:
            with self.db_manager.connect() as connection:
                self._import_tables(connection, tables)
        except (DatabaseError, ValueError, TypeError) as exc:
            detail = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
            raise ValidationError(f"Nao foi possivel restaurar o backup selecionado.\n\n{detail}") from exc

        self.optimize_database()

        return {
            "path": str(source),
            "size_bytes": source.stat().st_size,
        }

    def optimize_database(self) -> dict:
        """Atualiza as estatisticas usadas pelo planejador de consultas (o autovacuum do
        PostgreSQL ja cuida disso no dia a dia; aqui e chamado depois de uma restauracao,
        que reescreve todas as tabelas de uma vez)."""
        with self.db_manager.connect() as connection:
            for table in APPLICATION_TABLES:
                connection.execute(f"ANALYZE {table}")
            size_row = connection.execute("SELECT pg_database_size(current_database()) AS size").fetchone()

        return {
            "optimized": True,
            "database_size_bytes": int(size_row["size"]),
        }

    def _export_tables(self, connection) -> dict:
        tables: dict[str, dict] = {}
        for table in APPLICATION_TABLES:
            cursor = connection.execute(f"SELECT * FROM {table} ORDER BY 1")
            columns = [column.name for column in cursor.description]
            rows = [[row[column] for column in columns] for row in cursor.fetchall()]
            tables[table] = {"columns": columns, "rows": rows}
        return {
            "format": BACKUP_FORMAT,
            "version": BACKUP_FORMAT_VERSION,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "tables": tables,
        }

    def _import_tables(self, connection, tables: dict[str, dict]) -> None:
        connection.execute(f"TRUNCATE {', '.join(APPLICATION_TABLES)} RESTART IDENTITY CASCADE")
        for table in APPLICATION_TABLES:
            data = tables.get(table)
            if not data or not data["rows"]:
                continue
            column_types = self._table_column_types(connection, table)
            # Backups antigos podem nao ter colunas criadas depois (ficam com o valor
            # padrao) ou ter colunas que nao existem mais (sao ignoradas).
            columns = [column for column in data["columns"] if column in column_types]
            if not columns:
                continue
            source_indexes = [data["columns"].index(column) for column in columns]
            rows = [
                tuple(
                    self._coerce_value(row[index], column_types[column])
                    for index, column in zip(source_indexes, columns)
                )
                for row in data["rows"]
            ]
            placeholders = ", ".join("?" for _ in columns)
            connection.executemany(
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
                rows,
            )

        reset_identity_sequences(connection)
        apply_data_normalizations(connection)
        seed_default_data(connection)

    @staticmethod
    def _table_column_types(connection, table: str) -> dict[str, str]:
        rows = connection.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = ?
            """,
            (table,),
        ).fetchall()
        return {row["column_name"]: row["data_type"] for row in rows}

    @staticmethod
    def _coerce_value(value, data_type: str):
        """O SQLite aceita qualquer tipo em qualquer coluna; o PostgreSQL nao. Ajusta os
        valores vindos de bancos antigos ao tipo da coluna de destino."""
        if value is None:
            return None
        if data_type in INTEGER_TYPES:
            return int(value)
        if data_type in FLOAT_TYPES:
            return float(value)
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value if isinstance(value, str) else str(value)

    def _read_backup_tables(self, raw: bytes, plain_file: Path | None) -> dict[str, dict]:
        if raw.startswith(GZIP_HEADER):
            return self._read_json_backup(raw)
        if raw.startswith(SQLITE_HEADER):
            return self._read_sqlite_backup(raw, plain_file)
        raise ValidationError("O arquivo selecionado nao e um backup valido do DocFlow.")

    @staticmethod
    def _read_json_backup(raw: bytes) -> dict[str, dict]:
        try:
            payload = json.loads(gzip.decompress(raw).decode("utf-8"))
        except (OSError, EOFError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationError("O arquivo de backup esta corrompido ou incompleto.") from exc
        if not isinstance(payload, dict) or payload.get("format") != BACKUP_FORMAT:
            raise ValidationError("O arquivo selecionado nao e um backup valido do DocFlow.")
        if int(payload.get("version") or 0) > BACKUP_FORMAT_VERSION:
            raise ValidationError("Este backup foi gerado por uma versao mais nova do DocFlow.")
        tables = payload.get("tables")
        if not isinstance(tables, dict):
            raise ValidationError("O arquivo de backup esta corrompido ou incompleto.")
        return tables

    @staticmethod
    def _read_sqlite_backup(raw: bytes, plain_file: Path | None) -> dict[str, dict]:
        try:
            if plain_file is not None and Path(f"{plain_file}-wal").exists():
                # Banco antigo ainda com o arquivo -wal ao lado: parte dos dados pode estar
                # so no WAL, entao le direto do disco (somente leitura) em vez de usar a
                # copia em memoria.
                connection = sqlite3.connect(f"{plain_file.resolve().as_uri()}?mode=ro", uri=True)
            else:
                connection = sqlite3.connect(":memory:")
                connection.deserialize(_as_rollback_journal_database(raw))
        except sqlite3.Error as exc:
            raise ValidationError("O arquivo selecionado nao parece ser um banco SQLite valido.") from exc
        try:
            available_tables = {
                str(row[0])
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            }
            tables: dict[str, dict] = {}
            for table in APPLICATION_TABLES:
                if table not in available_tables:
                    continue
                cursor = connection.execute(f"SELECT * FROM {table} ORDER BY 1")
                tables[table] = {
                    "columns": [description[0] for description in cursor.description],
                    "rows": [list(row) for row in cursor.fetchall()],
                }
            return tables
        except sqlite3.Error as exc:
            raise ValidationError("O arquivo selecionado nao parece ser um banco SQLite valido.") from exc
        finally:
            connection.close()

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


def _as_rollback_journal_database(raw: bytes) -> bytes:
    """O DocFlow antigo usava o SQLite em modo WAL, que fica gravado no cabecalho do
    arquivo (bytes 18 e 19 = 2). Um banco em modo WAL nao abre a partir da memoria, entao
    a copia e marcada como journal tradicional (= 1) antes de ser carregada."""
    if len(raw) > 19 and raw[18] == 2 and raw[19] == 2:
        patched = bytearray(raw)
        patched[18] = 1
        patched[19] = 1
        return bytes(patched)
    return raw
