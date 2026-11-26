"""Exportación de un rango de auditoría a Parquet."""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass
from pathlib import Path

import duckdb

from .config import DatabaseSettings
from .duckdb_session import POSTGRES_CATALOG, postgres_session, sql_literal

# Tabla de django-auditlog; apps.audit.AuditLog es un proxy sobre ella.
AUDIT_SOURCE = f"{POSTGRES_CATALOG}.public.auditlog_logentry"
TIMESTAMP_COLUMN = "timestamp"
PRIMARY_KEY_COLUMN = "id"
_HASH_CHUNK_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class SnapshotRange:
    """Período semiabierto [start, end) en UTC."""

    start: dt.datetime
    end: dt.datetime

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("start y end deben incluir zona horaria.")
        if self.start >= self.end:
            raise ValueError("start debe ser anterior a end.")

    @classmethod
    def from_dates(cls, start: dt.date, end: dt.date) -> "SnapshotRange":
        """Rango desde la medianoche UTC de start hasta la medianoche UTC de end."""
        return cls(
            start=dt.datetime.combine(start, dt.time.min, tzinfo=dt.timezone.utc),
            end=dt.datetime.combine(end, dt.time.min, tzinfo=dt.timezone.utc),
        )

    def ensure_closed(self, now: dt.datetime) -> None:
        """Un período en curso todavía puede recibir registros."""
        if self.end > now:
            raise ValueError("No se puede archivar un período que aún no ha terminado.")


@dataclass(frozen=True, slots=True)
class ExportResult:
    path: Path
    row_count: int
    sha256: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _timestamp_literal(value: dt.datetime) -> str:
    return f"TIMESTAMPTZ {sql_literal(value.isoformat())}"


def export_range(
    connection: duckdb.DuckDBPyConnection,
    source: str,
    snapshot_range: SnapshotRange,
    destination: Path,
) -> int:
    """Escribe en Parquet las filas de ``source`` dentro del rango y devuelve cuántas.

    Escribe primero en un archivo temporal para no dejar un Parquet incompleto
    con el nombre definitivo si la copia falla.
    """
    if destination.exists():
        raise FileExistsError(f"El destino ya existe: {destination}")
    partial = destination.with_name(f"{destination.name}.partial")
    query = (
        f'SELECT * FROM {source} '
        f'WHERE "{TIMESTAMP_COLUMN}" >= {_timestamp_literal(snapshot_range.start)} '
        f'AND "{TIMESTAMP_COLUMN}" < {_timestamp_literal(snapshot_range.end)} '
        f'ORDER BY "{PRIMARY_KEY_COLUMN}"'
    )
    try:
        connection.execute(
            f"COPY ({query}) TO {sql_literal(str(partial))} (FORMAT parquet, COMPRESSION zstd)"
        )
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)
    return connection.execute(
        f"SELECT count(*) FROM read_parquet({sql_literal(str(destination))})"
    ).fetchone()[0]


def export_audit_range(
    database: DatabaseSettings,
    snapshot_range: SnapshotRange,
    destination: Path,
    now: dt.datetime | None = None,
) -> ExportResult:
    """Exporta la auditoría de PostgreSQL (solo lectura) del rango a un Parquet local."""
    snapshot_range.ensure_closed(now or dt.datetime.now(dt.timezone.utc))
    with postgres_session(database) as connection:
        row_count = export_range(connection, AUDIT_SOURCE, snapshot_range, destination)
    return ExportResult(path=destination, row_count=row_count, sha256=sha256_file(destination))
