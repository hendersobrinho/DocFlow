"""Banco PostgreSQL para os testes.

Cada teste recebe um schema proprio e descartavel dentro do banco de testes, entao os
testes nao enxergam os dados uns dos outros. O banco e apontado por
DOCFLOW_TEST_DATABASE_URL (padrao: banco 'docflow_test' no servidor local, com o usuario
do sistema operacional) e e criado automaticamente se o usuario tiver permissao. Sem um
servidor acessivel, os testes que dependem do banco sao pulados.
"""

from __future__ import annotations

import os
import unittest
import uuid

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from documentos_empresa_app.database.connection import DatabaseManager

TEST_DATABASE_URL_ENV_VAR = "DOCFLOW_TEST_DATABASE_URL"
DEFAULT_TEST_DATABASE_URL = "dbname=docflow_test"

_database_ready: bool | None = None
_unavailable_reason = ""


def get_test_database_url() -> str:
    return os.environ.get(TEST_DATABASE_URL_ENV_VAR) or DEFAULT_TEST_DATABASE_URL


def _ensure_test_database() -> None:
    global _database_ready, _unavailable_reason
    if _database_ready is not None:
        return

    conninfo = get_test_database_url()
    try:
        psycopg.connect(conninfo, connect_timeout=5).close()
        _database_ready = True
        return
    except psycopg.OperationalError as exc:
        first_error = exc

    dbname = conninfo_to_dict(conninfo).get("dbname")
    try:
        maintenance_conninfo = make_conninfo(conninfo, dbname="postgres")
        with psycopg.connect(maintenance_conninfo, autocommit=True, connect_timeout=5) as connection:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
        _database_ready = True
    except psycopg.Error:
        _database_ready = False
        _unavailable_reason = (
            f"PostgreSQL de testes indisponivel ({TEST_DATABASE_URL_ENV_VAR}={conninfo}): {first_error}"
        )


def create_test_database_manager(testcase: unittest.TestCase) -> DatabaseManager:
    """Cria um schema exclusivo para o teste e devolve um DatabaseManager apontando para
    ele. O schema e removido (e a conexao fechada) ao final do teste."""
    _ensure_test_database()
    if not _database_ready:
        raise unittest.SkipTest(_unavailable_reason)

    conninfo = get_test_database_url()
    schema = f"test_{uuid.uuid4().hex[:16]}"
    with psycopg.connect(conninfo, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))

    db_manager = DatabaseManager(conninfo, schema=schema)

    def cleanup() -> None:
        db_manager.close()
        with psycopg.connect(conninfo, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))

    testcase.addCleanup(cleanup)
    return db_manager
