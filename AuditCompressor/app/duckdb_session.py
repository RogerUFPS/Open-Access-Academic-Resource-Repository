"""Única fuente de conexiones DuckDB del servicio."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from contextlib import contextmanager

import duckdb

from .config import DatabaseSettings

POSTGRES_CATALOG = "pg"


def sql_literal(value: str) -> str:
    """Literal SQL para sentencias que DuckDB no permite parametrizar."""
    return "'" + value.replace("'", "''") + "'"


def timestamp_literal(value: dt.datetime) -> str:
    return f"TIMESTAMPTZ {sql_literal(value.isoformat())}"


@contextmanager
def postgres_session(database: DatabaseSettings) -> Iterator[duckdb.DuckDBPyConnection]:
    """Conexión con PostgreSQL adjunto en modo READ_ONLY como ``pg``.

    Las credenciales viajan en un SECRET temporal en memoria, nunca en la cadena
    de conexión ni en los logs.
    """
    database.ensure_complete()
    connection = duckdb.connect()
    try:
        connection.execute("SET TimeZone = 'UTC'")
        connection.load_extension("postgres")
        connection.execute(
            "CREATE TEMPORARY SECRET audit_postgres (TYPE postgres, "
            f"HOST {sql_literal(database.host)}, PORT {database.port}, "
            f"DATABASE {sql_literal(database.name)}, USER {sql_literal(database.user)}, "
            f"PASSWORD {sql_literal(database.password)})"
        )
        connection.execute(
            f"ATTACH '' AS {POSTGRES_CATALOG} (TYPE postgres, SECRET audit_postgres, READ_ONLY)"
        )
        yield connection
    finally:
        connection.close()
