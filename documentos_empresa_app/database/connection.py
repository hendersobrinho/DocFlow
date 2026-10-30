from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
import threading
import time

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

# Reexportados para que os services nao dependam diretamente do driver.
DatabaseError = psycopg.Error
IntegrityError = psycopg.IntegrityError
OperationalError = psycopg.OperationalError

CONNECT_TIMEOUT_SECONDS = 10
# Uma conexao parada ha mais tempo que isso e testada com um SELECT 1 antes de ser
# reaproveitada - o servidor (ou um firewall no caminho) pode ter derrubado a conexao
# ociosa, e e melhor descobrir isso fora de uma transacao do que no meio dela.
IDLE_CHECK_SECONDS = 60


@lru_cache(maxsize=2048)
def _translate_placeholders(query: str) -> str:
    """O codigo dos repositorios usa o estilo '?' (DB-API qmark); o psycopg usa '%s'.
    Converte '?' fora de literais e escapa todo '%' como '%%' (o psycopg interpreta '%'
    mesmo dentro de literais quando a query recebe parametros)."""
    translated: list[str] = []
    in_single_quote = False
    in_double_quote = False
    for char in query:
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote

        if char == "%":
            translated.append("%%")
        elif char == "?" and not in_single_quote and not in_double_quote:
            translated.append("%s")
        else:
            translated.append(char)
    return "".join(translated)


def _is_read_only_statement(query: str) -> bool:
    words = query.split(None, 1)
    return not words or words[0].upper() == "SELECT"


class PostgresConnection:
    """Envolve a conexao do psycopg mantendo a interface que os repositorios ja usavam
    (connection.execute(query, params) com placeholders '?')."""

    def __init__(self, raw_connection: psycopg.Connection, manager: DatabaseManager) -> None:
        self.raw = raw_connection
        self._manager = manager

    def execute(self, query: str, params: tuple | list | None = None) -> psycopg.Cursor:
        cursor = self.raw.cursor()
        read_only = _is_read_only_statement(query)
        if not read_only:
            self._manager.mark_written()
        if self._manager.is_nested() and not read_only:
            # No SQLite, um comando que falha (ex: violacao de UNIQUE) desfaz so aquele
            # comando. No PostgreSQL o erro aborta a transacao inteira - entao, quando a
            # escrita roda dentro de um bloco maior (services agrupam varias operacoes num
            # mesmo connect()), um savepoint isola o comando e o service pode tratar o
            # IntegrityError e continuar usando a transacao, como antes.
            # Os comandos de savepoint rodam em outro cursor para nao descartar o resultado
            # (ex: RETURNING id) do comando principal.
            self.raw.execute("SAVEPOINT docflow_statement")
            try:
                self._run(cursor, query, params)
            except psycopg.Error:
                if not self.raw.broken:
                    self.raw.execute("ROLLBACK TO SAVEPOINT docflow_statement")
                raise
            self.raw.execute("RELEASE SAVEPOINT docflow_statement")
        else:
            self._run(cursor, query, params)
        return cursor

    def executemany(self, query: str, params_list: list[tuple]) -> psycopg.Cursor:
        self._manager.mark_written()
        cursor = self.raw.cursor()
        cursor.executemany(_translate_placeholders(query), params_list)
        return cursor

    def commit(self) -> None:
        self.raw.commit()

    def rollback(self) -> None:
        self.raw.rollback()

    @staticmethod
    def _run(cursor: psycopg.Cursor, query: str, params: tuple | list | None) -> None:
        if params:
            cursor.execute(_translate_placeholders(query), params)
        else:
            cursor.execute(query)


class DatabaseManager:
    """Mantem uma unica conexao com o PostgreSQL, reaproveitada entre as chamadas.
    Algumas operacoes (backup, restauracao, importacao de planilha) rodam em QThreads de
    fundo para nao travar a interface; um RLock serializa o acesso entre threads (a mesma
    conexao nao pode ser usada por duas threads ao mesmo tempo) e preserva a reentrancia
    dentro da mesma thread: blocos connect() aninhados participam da mesma transacao, que
    e confirmada (ou desfeita) quando o bloco mais externo termina.

    'schema' opcional isola as tabelas num schema proprio (usado pelos testes)."""

    def __init__(self, conninfo: str, *, schema: str | None = None) -> None:
        self.conninfo = conninfo
        self.schema = schema
        self._raw_connection: psycopg.Connection | None = None
        self._active_connection: PostgresConnection | None = None
        self._connection_depth = 0
        self._last_used_at = 0.0
        self._lock = threading.RLock()
        # Sobe a cada escrita (e a cada transacao desfeita): os caches de leitura dos services
        # (ResultCache) comparam com este numero para saber se ainda valem.
        self.write_generation = 0

    @property
    def database_name(self) -> str:
        return str(conninfo_to_dict(self.conninfo).get("dbname") or "docflow")

    @property
    def display_name(self) -> str:
        """Identificacao do banco para a interface - nunca inclui a senha."""
        params = conninfo_to_dict(self.conninfo)
        host = params.get("host") or "localhost"
        port = params.get("port") or "5432"
        user = params.get("user")
        location = f"{host}:{port}/{self.database_name}"
        return f"{user}@{location}" if user else location

    def mark_written(self) -> None:
        self.write_generation += 1

    def is_nested(self) -> bool:
        return self._connection_depth > 1

    @contextmanager
    def connect(self):
        with self._lock:
            if self._active_connection is not None:
                self._connection_depth += 1
                try:
                    yield self._active_connection
                finally:
                    self._connection_depth -= 1
                return

            connection = PostgresConnection(self._acquire_raw_connection(), self)
            self._active_connection = connection
            self._connection_depth = 1
            try:
                yield connection
                connection.commit()
            except BaseException:
                self._safe_rollback(connection.raw)
                self.mark_written()  # o que foi lido dentro da transacao desfeita nao vale mais
                raise
            finally:
                self._connection_depth = 0
                self._active_connection = None
                self._last_used_at = time.monotonic()

    def close(self) -> None:
        with self._lock:
            if self._raw_connection is not None:
                self._raw_connection.close()
            self._raw_connection = None

    def test_connection(self) -> None:
        """Abre a conexao (ou reaproveita a atual) e roda um SELECT 1 - levanta
        OperationalError se o servidor nao estiver acessivel."""
        with self.connect() as connection:
            connection.execute("SELECT 1").fetchone()

    def _acquire_raw_connection(self) -> psycopg.Connection:
        raw = self._raw_connection
        if raw is not None and not raw.closed and not raw.broken:
            if time.monotonic() - self._last_used_at < IDLE_CHECK_SECONDS or self._is_alive(raw):
                return raw
        if raw is not None:
            raw.close()
        self._raw_connection = self._open_raw_connection()
        return self._raw_connection

    def _open_raw_connection(self) -> psycopg.Connection:
        raw = psycopg.connect(
            self.conninfo,
            row_factory=dict_row,
            connect_timeout=CONNECT_TIMEOUT_SECONDS,
            application_name="DocFlow",
        )
        if self.schema:
            raw.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(self.schema)))
            raw.commit()
        return raw

    @staticmethod
    def _is_alive(raw: psycopg.Connection) -> bool:
        try:
            raw.execute("SELECT 1")
            raw.rollback()
            return True
        except psycopg.Error:
            return False

    @staticmethod
    def _safe_rollback(raw: psycopg.Connection) -> None:
        if raw.closed or raw.broken:
            return
        try:
            raw.rollback()
        except psycopg.Error:
            pass
