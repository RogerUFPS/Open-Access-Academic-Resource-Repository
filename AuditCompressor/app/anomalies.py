"""Anomalías: registros que aparecen en el rango de un semestre ya archivado y borrado.

- Duplicados (su id ya está en el archivo): se eliminan; se conserva la versión
  archivada, que es la primera.
- Nuevos (su id no está en el archivo): el usuario decide comprimirlos dentro
  del semestre como una parte más del snapshot, o eliminarlos.

Todo se compara contra el contenido real de RustFS (hash verificado) y cada
borrado ocurre en una transacción: ante cualquier diferencia no se borra nada.
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import duckdb

from .config import Settings, SourceSettings
from .duckdb_session import (
    POSTGRES_CATALOG,
    postgres_session,
    quote_identifier,
    read_parquet_sql,
    register_parquet_key,
)
from .manifest import MANIFEST_NAME, Manifest, SnapshotFile, is_snapshot_id
from .offload import OFFLOAD_NAME, OffloadVerificationError, SnapshotNotFoundError
from .snapshots import (
    SnapshotIntegrityError,
    download_verified,
    postgres_relation,
    range_condition,
    sha256_file,
    snapshot_key,
    write_parquet,
)
from .storage import SnapshotStorage

logger = logging.getLogger(__name__)

SAMPLE_SIZE = 50


class SnapshotNotOffloadedError(RuntimeError):
    """El semestre todavía no tiene offload: sus filas no son anomalías."""


class ExpectedRowsMismatchError(RuntimeError):
    """La cantidad de registros cambió desde que el usuario los revisó."""


@dataclass(frozen=True, slots=True)
class DuplicatePurge:
    snapshot_id: str
    deleted_rows: int
    sample_ids: list[Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "deleted_rows": self.deleted_rows,
            "sample_ids": self.sample_ids,
        }


@dataclass(frozen=True, slots=True)
class LeftoverResolution:
    snapshot_id: str
    action: str
    compressed_rows: int
    removed_rows: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "action": self.action,
            "compressed_rows": self.compressed_rows,
            "removed_rows": self.removed_rows,
        }


def list_closed_snapshots(storage: SnapshotStorage, source: SourceSettings) -> list[Manifest]:
    """Snapshots con offload: solo se listan archivos, no se descarga ningún Parquet."""
    keys = storage.list_keys(f"{source.prefix}/")
    closed = sorted(
        key.rsplit("/", 2)[1] for key in keys if key.endswith(f"/{OFFLOAD_NAME}")
    )
    return [
        Manifest.from_dict(storage.get_json(snapshot_key(source, snapshot_id, MANIFEST_NAME)))
        for snapshot_id in closed
    ]


def closed_manifest(
    storage: SnapshotStorage, source: SourceSettings, snapshot_id: str
) -> Manifest:
    if not is_snapshot_id(snapshot_id):
        raise ValueError(f"Identificador de snapshot inválido: {snapshot_id!r}.")
    keys = set(storage.list_keys(f"{source.prefix}/{snapshot_id}/"))
    manifest_key = snapshot_key(source, snapshot_id, MANIFEST_NAME)
    if manifest_key not in keys:
        raise SnapshotNotFoundError(f"No existe el snapshot {source.name}/{snapshot_id}.")
    if snapshot_key(source, snapshot_id, OFFLOAD_NAME) not in keys:
        raise SnapshotNotOffloadedError(
            f"El snapshot {source.name}/{snapshot_id} todavía no tiene offload."
        )
    return Manifest.from_dict(storage.get_json(manifest_key))


def _archived_ids(
    storage: SnapshotStorage, source: SourceSettings, manifest: Manifest, directory: Path
) -> str:
    """Subconsulta con los ids de todas las partes del snapshot, ya verificadas."""
    primary_key = quote_identifier(source.primary_key)
    reads = [
        f"SELECT {primary_key} FROM ("
        + read_parquet_sql(
            download_verified(storage, file, directory / f"{index:04d}.parquet"),
            manifest.encrypted,
        )
        + ")"
        for index, file in enumerate(manifest.files)
    ]
    return "(" + " UNION ALL ".join(reads) + ")"


def _count(connection: duckdb.DuckDBPyConnection, table_ref: str, condition: str) -> int:
    return connection.execute(f"SELECT count(*) FROM {table_ref} WHERE {condition}").fetchone()[0]


def _ensure_expected(found: int, expected: int) -> None:
    if found != expected:
        raise ExpectedRowsMismatchError(
            f"Hay {found} registros y se esperaban {expected}: vuelva a revisarlos."
        )


def _in_transaction(connection: duckdb.DuckDBPyConnection, work):
    connection.execute("BEGIN TRANSACTION")
    try:
        result = work()
        connection.execute("COMMIT")
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    return result


def purge_duplicates(
    connection: duckdb.DuckDBPyConnection,
    table_ref: str,
    storage: SnapshotStorage,
    source: SourceSettings,
    snapshot_id: str,
) -> DuplicatePurge:
    """Elimina del rango los registros cuyo id ya está archivado (gana la versión archivada)."""
    manifest = closed_manifest(storage, source, snapshot_id)
    primary_key = quote_identifier(source.primary_key)
    with tempfile.TemporaryDirectory(prefix="audit-duplicates-") as directory:
        archived = _archived_ids(storage, source, manifest, Path(directory))
        condition = f"{range_condition(source, manifest.range)} AND {primary_key} IN {archived}"

        def work():
            sample = [
                row_id
                for (row_id,) in connection.execute(
                    f"SELECT {primary_key} FROM {table_ref} WHERE {condition} "
                    f"ORDER BY {primary_key} LIMIT {SAMPLE_SIZE}"
                ).fetchall()
            ]
            deleted = connection.execute(f"DELETE FROM {table_ref} WHERE {condition}").fetchone()[0]
            return sample, deleted

        sample, deleted = _in_transaction(connection, work)
    if deleted:
        logger.warning(
            "Anomalía %s/%s: %s duplicados eliminados (ya estaban archivados)",
            source.name, snapshot_id, deleted,
        )
    return DuplicatePurge(snapshot_id=snapshot_id, deleted_rows=deleted, sample_ids=sample)


def delete_leftovers(
    connection: duckdb.DuckDBPyConnection,
    table_ref: str,
    storage: SnapshotStorage,
    source: SourceSettings,
    snapshot_id: str,
    expected_rows: int,
) -> LeftoverResolution:
    """Elimina, sin archivar, los registros del rango que el usuario revisó."""
    manifest = closed_manifest(storage, source, snapshot_id)
    in_range = range_condition(source, manifest.range)

    def work():
        _ensure_expected(_count(connection, table_ref, in_range), expected_rows)
        return connection.execute(f"DELETE FROM {table_ref} WHERE {in_range}").fetchone()[0]

    deleted = _in_transaction(connection, work)
    logger.warning("Anomalía %s/%s eliminada: %s registros", source.name, snapshot_id, deleted)
    return LeftoverResolution(snapshot_id, "delete", compressed_rows=0, removed_rows=deleted)


def compress_leftovers(
    connection: duckdb.DuckDBPyConnection,
    relation: str,
    table_ref: str,
    storage: SnapshotStorage,
    source: SourceSettings,
    snapshot_id: str,
    expected_rows: int,
) -> LeftoverResolution:
    """Comprime los registros nuevos como una parte más del snapshot y los borra.

    Los duplicados se descartan (ya están archivados). Orden: parte nueva →
    manifest → borrado. Si el borrado falla, esos ids ya figuran en el archivo y
    la siguiente ejecución los trata como duplicados: nunca se pierden ni se repiten.
    """
    manifest = closed_manifest(storage, source, snapshot_id)
    primary_key = quote_identifier(source.primary_key)
    in_range = range_condition(source, manifest.range)
    _ensure_expected(_count(connection, table_ref, in_range), expected_rows)

    with tempfile.TemporaryDirectory(prefix="audit-compress-") as directory:
        archived = _archived_ids(storage, source, manifest, Path(directory))
        new_rows_query = (
            f"SELECT * FROM {relation} WHERE {in_range} AND {primary_key} NOT IN {archived}"
        )
        part_path = None
        name = f"part-{len(manifest.files) + 1:04d}.parquet"
        local = Path(directory) / name
        compressed = write_parquet(
            connection, f"{new_rows_query} ORDER BY {primary_key}", source, local, encrypted=True
        )
        if compressed:
            part = SnapshotFile(
                key=snapshot_key(source, snapshot_id, name),
                sha256=sha256_file(local),
                size=local.stat().st_size,
                row_count=compressed,
            )
            storage.upload_file(local, part.key)
            if storage.sha256(part.key) != part.sha256:
                raise SnapshotIntegrityError(f"El SHA-256 almacenado no coincide para {part.key}.")
            updated = replace(manifest, files=(*manifest.files, part), encrypted=True)
            storage.put_json(snapshot_key(source, snapshot_id, MANIFEST_NAME), updated.to_dict())
            part_path = local

        def work():
            _ensure_expected(_count(connection, table_ref, in_range), expected_rows)
            if part_path is not None:
                stored = f"({read_parquet_sql(part_path, True)})"
                missing, unexpected = connection.execute(
                    f"SELECT (SELECT count(*) FROM (SELECT * FROM {stored} "
                    f"EXCEPT ALL {new_rows_query})), "
                    f"(SELECT count(*) FROM ({new_rows_query} EXCEPT ALL SELECT * FROM {stored}))"
                ).fetchone()
                if missing or unexpected:
                    raise OffloadVerificationError(
                        "La parte comprimida no coincide con los registros de PostgreSQL."
                    )
            removed = connection.execute(
                f"DELETE FROM {table_ref} WHERE {in_range}"
            ).fetchone()[0]
            _ensure_expected(removed, expected_rows)
            return removed

        removed = _in_transaction(connection, work)
    logger.warning(
        "Anomalía %s/%s comprimida: %s nuevos archivados, %s registros retirados",
        source.name, snapshot_id, compressed, removed,
    )
    return LeftoverResolution(snapshot_id, "compress", compressed_rows=compressed, removed_rows=removed)


def closed_snapshots(settings: Settings, source: SourceSettings) -> list[Manifest]:
    return list_closed_snapshots(SnapshotStorage.from_settings(settings.storage), source)


def remove_duplicates(settings: Settings, source: SourceSettings, snapshot_id: str) -> DuplicatePurge:
    encryption_key = settings.require_encryption_key()
    storage = SnapshotStorage.from_settings(settings.storage)
    with postgres_session(settings.database, read_only=False) as connection:
        register_parquet_key(connection, encryption_key)
        table_ref = f"{POSTGRES_CATALOG}.{source.qualified_table}"
        return purge_duplicates(connection, table_ref, storage, source, snapshot_id)


def resolve_leftovers(
    settings: Settings, source: SourceSettings, snapshot_id: str, action: str, expected_rows: int
) -> LeftoverResolution:
    """Ejecuta la decisión del usuario sobre los registros nuevos de una anomalía."""
    storage = SnapshotStorage.from_settings(settings.storage)
    table_ref = f"{POSTGRES_CATALOG}.{source.qualified_table}"
    if action == "delete":
        with postgres_session(settings.database, read_only=False) as connection:
            return delete_leftovers(
                connection, table_ref, storage, source, snapshot_id, expected_rows
            )
    encryption_key = settings.require_encryption_key()
    with postgres_session(settings.database, read_only=False) as connection:
        register_parquet_key(connection, encryption_key)
        relation = postgres_relation(connection, source)
        return compress_leftovers(
            connection, relation, table_ref, storage, source, snapshot_id, expected_rows
        )
