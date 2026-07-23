from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3


class DatabaseManager:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._active_connection: sqlite3.Connection | None = None
        self._connection_depth = 0

    @contextmanager
    def connect(self):
        if self._active_connection is not None:
            self._connection_depth += 1
            try:
                yield self._active_connection
            finally:
                self._connection_depth -= 1
            return

        connection = sqlite3.connect(self.db_path)
        self._configure_connection(connection)
        self._active_connection = connection
        self._connection_depth = 1
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            self._connection_depth = 0
            self._active_connection = None
            connection.close()

    def _configure_connection(self, connection: sqlite3.Connection) -> None:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA temp_store = MEMORY")
