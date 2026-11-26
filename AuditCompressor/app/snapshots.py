"""Creación de snapshots: exportación a Parquet, subida verificada y manifest."""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import tempfile
from pathlib import Path

import duckdb

from .config import Settings, SourceSettings
from .duckdb_session import (
    ENCRYPTION_CONFIG,
    POSTGRES_CATALOG,
    postgres_session,
    quote_identifier,
    register_parquet_key,
    sql_literal,
    timestamp_literal,
)
from .manifest import MANIFEST_NAME, Manifest, SnapshotFile, SnapshotRange
from .storage import SnapshotStorage

logger = logging.getLogger(__name__)

PART_NAME = "part-0001.parquet"
_HASH_CHUNK_BYTES = 8 * 1024 * 1024


class SnapshotConflictError(RuntimeError):
    """El rango se solapa con un snapshot ya archivado."""


class SnapshotIntegrityError(RuntimeError):
    """El objeto almacenado no coincide con el archivo generado."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def download_verified(storage: SnapshotStorage, file: SnapshotFile, path: Path) -> Path:
    """Descarga el archivo y comprueba su SHA-256: solo se usa lo verificado."""
    storage.download_file(file.key, path)
    if sha256_file(path) != file.sha256:
        raise SnapshotIntegrityError(f"El SHA-256 almacenado no coincide para {file.key}.")
    return path


def inet_as_postgres_text(column: str) -> str:
    """Expresión que muestra un inet como PostgreSQL: sin máscara si es una sola dirección.

    La extensión postgres de DuckDB lo entrega con máscara (172.27.0.5/32).
    """
    quoted = quote_identifier(column)
    return (
        f"CASE WHEN contains({quoted}, ':') THEN regexp_replace({quoted}, '/128$', '') "
        f"ELSE regexp_replace({quoted}, '/32$', '') END"
    )


def source_with_inet_text(table_ref: str, inet_columns: list[str]) -> str:
    if not inet_columns:
        return table_ref
    replacements = ", ".join(
        f"{inet_as_postgres_text(column)} AS {quote_identifier(column)}" for column in inet_columns
    )
    return f"(SELECT * REPLACE ({replacements}) FROM {table_ref})"


def postgres_relation(connection: duckdb.DuckDBPyConnection, source: SourceSettings) -> str:
    """Tabla de la fuente en PostgreSQL, con sus columnas inet en el texto original."""
    # schema y table ya están validados como identificadores simples.
    catalog_query = (
        "SELECT column_name FROM information_schema.columns "
        f"WHERE table_schema = '{source.schema}' AND table_name = '{source.table}' "
        "AND data_type = 'inet'"
    )
    inet_columns = [
        row[0]
        for row in connection.execute(
            f"SELECT * FROM postgres_query({sql_literal(POSTGRES_CATALOG)}, "
            f"{sql_literal(catalog_query)})"
        ).fetchall()
    ]
    return source_with_inet_text(f"{POSTGRES_CATALOG}.{source.qualified_table}", inet_columns)


def export_range(
    connection: duckdb.DuckDBPyConnection,
    relation: str,
    source: SourceSettings,
    snapshot_range: SnapshotRange,
    destination: Path,
    encrypted: bool = False,
) -> int:
    """Escribe en Parquet las filas de ``relation`` dentro del rango y devuelve cuántas.

    Con ``encrypted`` la conexión debe tener registrada la clave de cifrado.
    Escribe primero en un archivo temporal para no dejar un Parquet incompleto
    con el nombre definitivo si la copia falla.
    """
    if destination.exists():
        raise FileExistsError(f"El destino ya existe: {destination}")
    partial = destination.with_name(f"{destination.name}.partial")
    column = quote_identifier(source.timestamp_column)
    query = (
        f"SELECT * FROM {relation} "
        f"WHERE {column} >= {timestamp_literal(snapshot_range.start)} "
        f"AND {column} < {timestamp_literal(snapshot_range.end)} "
        f"ORDER BY {quote_identifier(source.primary_key)}"
    )
    copy_options = f"FORMAT parquet, COMPRESSION {source.compression}"
    read_options = ""
    if encrypted:
        copy_options += f", ENCRYPTION_CONFIG {ENCRYPTION_CONFIG}"
        read_options = f", encryption_config = {ENCRYPTION_CONFIG}"
    try:
        connection.execute(f"COPY ({query}) TO {sql_literal(str(partial))} ({copy_options})")
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)
    return connection.execute(
        f"SELECT count(*) FROM read_parquet({sql_literal(str(destination))}{read_options})"
    ).fetchone()[0]


def snapshot_key(source: SourceSettings, snapshot_id: str, name: str) -> str:
    return f"{source.prefix}/{snapshot_id}/{name}"


def list_manifests(storage: SnapshotStorage, source: SourceSettings) -> list[Manifest]:
    return [
        Manifest.from_dict(storage.get_json(key))
        for key in storage.list_keys(f"{source.prefix}/")
        if key.endswith(f"/{MANIFEST_NAME}")
    ]


def _ensure_no_overlap(
    storage: SnapshotStorage, source: SourceSettings, snapshot_range: SnapshotRange
) -> None:
    for manifest in list_manifests(storage, source):
        if manifest.range.overlaps(snapshot_range):
            raise SnapshotConflictError(
                f"El rango se solapa con el snapshot {manifest.snapshot_id}."
            )


def create_snapshot(
    connection: duckdb.DuckDBPyConnection,
    relation: str,
    storage: SnapshotStorage,
    source: SourceSettings,
    snapshot_range: SnapshotRange,
    now: dt.datetime,
) -> Manifest:
    """Exporta cifrado, sube y verifica el rango; escribe el manifest como último paso.

    La conexión debe tener registrada la clave de cifrado. El SHA-256 se calcula
    sobre el archivo cifrado, que es exactamente lo que se almacena.
    Si algo falla antes del manifest, el snapshot no existe y puede repetirse:
    los objetos huérfanos se sobrescriben con la misma clave.
    """
    _ensure_no_overlap(storage, source, snapshot_range)
    snapshot_id = snapshot_range.snapshot_id
    part_key = snapshot_key(source, snapshot_id, PART_NAME)

    with tempfile.TemporaryDirectory(prefix="audit-snapshot-") as directory:
        local = Path(directory) / PART_NAME
        row_count = export_range(
            connection, relation, source, snapshot_range, local, encrypted=True
        )
        part = SnapshotFile(
            key=part_key,
            sha256=sha256_file(local),
            size=local.stat().st_size,
            row_count=row_count,
        )
        storage.upload_file(local, part_key)

    if storage.sha256(part_key) != part.sha256:
        raise SnapshotIntegrityError(f"El SHA-256 almacenado no coincide para {part_key}.")

    manifest = Manifest(
        snapshot_id=snapshot_id,
        table=source.qualified_table,
        timestamp_column=source.timestamp_column,
        range=snapshot_range,
        created_at=now,
        files=(part,),
        encrypted=True,
    )
    # Reduce la ventana frente a otra ejecución simultánea sobre un rango solapado.
    _ensure_no_overlap(storage, source, snapshot_range)
    storage.put_json(snapshot_key(source, snapshot_id, MANIFEST_NAME), manifest.to_dict())
    logger.info(
        "Snapshot %s/%s creado con %s filas", source.name, snapshot_id, manifest.row_count
    )
    return manifest


def archive_range(
    settings: Settings,
    source: SourceSettings,
    snapshot_range: SnapshotRange,
    now: dt.datetime | None = None,
) -> Manifest:
    """Archiva en RustFS la fuente en el rango, leyendo PostgreSQL en solo lectura."""
    now = now or dt.datetime.now(dt.timezone.utc)
    snapshot_range.ensure_closed(now)
    encryption_key = settings.require_encryption_key()
    storage = SnapshotStorage.from_settings(settings.storage)
    with postgres_session(settings.database) as connection:
        register_parquet_key(connection, encryption_key)
        relation = postgres_relation(connection, source)
        return create_snapshot(connection, relation, storage, source, snapshot_range, now)
