"""Única fuente de conexiones DuckDB del servicio y utilidades SQL compartidas."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import duckdb

from .config import ConfigurationError, DatabaseSettings

POSTGRES_CATALOG = "pg"
PARQUET_KEY_NAME = "audit_snapshot_key"


def sql_literal(value: str) -> str:
    """Literal SQL para sentencias que DuckDB no permite parametrizar."""
    return "'" + value.replace("'", "''") + "'"


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def timestamp_literal(value: dt.datetime) -> str:
    return f"TIMESTAMPTZ {sql_literal(value.isoformat())}"


ENCRYPTION_CONFIG = f"{{footer_key: {sql_literal(PARQUET_KEY_NAME)}}}"


def read_parquet_sql(path: Path, encrypted: bool) -> str:
    """SELECT sobre un Parquet local; si está cifrado usa la clave registrada."""
    options = f", encryption_config = {ENCRYPTION_CONFIG}" if encrypted else ""
    return f"SELECT * FROM read_parquet({sql_literal(str(path))}{options})"


def register_parquet_key(connection: duckdb.DuckDBPyConnection, key: str) -> None:
    """Registra la clave de cifrado solo en la memoria de esta conexión.

    El error de DuckDB podría citar la sentencia con la clave: se reemplaza
    por uno propio sin encadenarlo.
    """
    try:
        connection.execute(
            f"PRAGMA add_parquet_key({sql_literal(PARQUET_KEY_NAME)}, {sql_literal(key)})"
        )
    except duckdb.Error:
        raise ConfigurationError("DuckDB rechazó AUDIT_ENCRYPTION_KEY.") from None


@contextmanager
def postgres_session(
    database: DatabaseSettings, read_only: bool = True
) -> Iterator[duckdb.DuckDBPyConnection]:
    """Conexión con PostgreSQL adjunto como ``pg``, en modo READ_ONLY por defecto.

    Solo el offload abre una sesión con escritura. Las credenciales viajan en un
    SECRET temporal en memoria, nunca en la cadena de conexión ni en los logs.
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
        mode = ", READ_ONLY" if read_only else ""
        connection.execute(
            f"ATTACH '' AS {POSTGRES_CATALOG} (TYPE postgres, SECRET audit_postgres{mode})"
        )
        yield connection
    finally:
        connection.close()
