"""Offload: borrar de PostgreSQL los registros de un snapshot ya archivado.

Solo se borra después de comprobar que la copia archivada existe, está intacta,
se puede leer y coincide fila a fila con lo que se va a borrar. Ante cualquier
duda no se borra nada.
"""

from __future__ import annotations

import datetime as dt
import logging
import tempfile
from dataclasses import dataclass
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
    timestamp_literal,
)
from .manifest import MANIFEST_NAME, Manifest, is_snapshot_id
from .snapshots import download_verified, postgres_relation, snapshot_key
from .storage import SnapshotStorage

logger = logging.getLogger(__name__)

OFFLOAD_NAME = "offload.json"
OFFLOAD_FORMAT_VERSION = 1


class SnapshotNotFoundError(LookupError):
    """No existe un snapshot completo (con manifest) con ese identificador."""


class OffloadVerificationError(RuntimeError):
    """La copia archivada no respalda el borrado; PostgreSQL no se modificó."""


class OffloadDisabledError(RuntimeError):
    """La fuente está configurada con offload: false; nunca se borra de PostgreSQL."""



@dataclass(frozen=True, slots=True)
class OffloadReceipt:
    """Constancia de que los registros del snapshot ya no están en PostgreSQL."""

    snapshot_id: str
    offloaded_at: dt.datetime
    deleted_rows: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_version": OFFLOAD_FORMAT_VERSION,
            "snapshot_id": self.snapshot_id,
            "offloaded_at": self.offloaded_at.isoformat(),
            "deleted_rows": self.deleted_rows,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OffloadReceipt":
        version = data.get("format_version")
        if version != OFFLOAD_FORMAT_VERSION:
            raise ValueError(f"Versión de constancia de offload no soportada: {version!r}.")
        return cls(
            snapshot_id=data["snapshot_id"],
            offloaded_at=dt.datetime.fromisoformat(data["offloaded_at"]),
            deleted_rows=data["deleted_rows"],
        )


@dataclass(frozen=True, slots=True)
class OffloadResult:
    receipt: OffloadReceipt
    already_offloaded: bool



def _verify_and_delete(
    connection: duckdb.DuckDBPyConnection,
    relation: str,
    table_ref: str,
    source: SourceSettings,
    manifest: Manifest,
    archived: str,
) -> int:
    """Pasos 3 a 5 en una sola transacción: lo comparado es exactamente lo borrado.

    ``archived`` es una subconsulta entre paréntesis con todas las filas del snapshot.

    Devuelve las filas borradas. Cualquier diferencia revierte la transacción.
    """
    timestamp = quote_identifier(source.timestamp_column)
    primary_key = quote_identifier(source.primary_key)
    in_range = (
        f"{timestamp} >= {timestamp_literal(manifest.range.start)} "
        f"AND {timestamp} < {timestamp_literal(manifest.range.end)}"
    )
    current = f"(SELECT * FROM {relation} WHERE {in_range})"

    connection.execute("BEGIN TRANSACTION")
    try:
        # Paso 3: la copia se descifra y tiene las filas que declara el manifest.
        try:
            archived_rows = connection.execute(f"SELECT count(*) FROM {archived}").fetchone()[0]
        except duckdb.Error as exc:
            raise OffloadVerificationError(
                "No se pudo descifrar o leer el snapshot con la clave actual."
            ) from exc
        if archived_rows != manifest.row_count:
            raise OffloadVerificationError(
                f"El snapshot tiene {archived_rows} filas y el manifest declara "
                f"{manifest.row_count}."
            )

        current_rows = connection.execute(f"SELECT count(*) FROM {current}").fetchone()[0]
        if current_rows == 0:
            # Un offload anterior ya borró el rango, pero no llegó a dejar constancia.
            deleted = 0
        else:
            # Paso 4: ninguna fila de un lado falta o difiere en el otro.
            missing, unexpected = connection.execute(
                f"SELECT (SELECT count(*) FROM "
                f"(SELECT * FROM {archived} EXCEPT ALL SELECT * FROM {current})), "
                f"(SELECT count(*) FROM "
                f"(SELECT * FROM {current} EXCEPT ALL SELECT * FROM {archived}))"
            ).fetchone()
            if missing or unexpected:
                raise OffloadVerificationError(
                    f"La copia no coincide con PostgreSQL: {missing} filas archivadas no están "
                    f"igual en la base y {unexpected} filas de la base no están en el snapshot."
                )
            # Paso 5: solo los registros del snapshot, todo o nada.
            deleted = connection.execute(
                f"DELETE FROM {table_ref} WHERE {in_range} "
                f"AND {primary_key} IN (SELECT {primary_key} FROM {archived})"
            ).fetchone()[0]
            if deleted != manifest.row_count:
                raise OffloadVerificationError(
                    f"Se iban a borrar {deleted} filas y el snapshot tiene {manifest.row_count}."
                )
        connection.execute("COMMIT")
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    return deleted


def offload_snapshot(
    connection: duckdb.DuckDBPyConnection,
    relation: str,
    table_ref: str,
    storage: SnapshotStorage,
    source: SourceSettings,
    snapshot_id: str,
    now: dt.datetime,
) -> OffloadResult:
    """Borra de ``table_ref`` los registros del snapshot, tras verificarlo por completo.

    ``relation`` es la fuente tal como se archivó (con inet normalizado);
    ``table_ref`` es la tabla real donde se borra. La conexión debe tener
    registrada la clave de cifrado.
    """
    if not is_snapshot_id(snapshot_id):
        raise ValueError(f"Identificador de snapshot inválido: {snapshot_id!r}.")
    if not source.offload:
        raise OffloadDisabledError(f"La fuente {source.name} no permite offload.")
    keys = set(storage.list_keys(f"{source.prefix}/{snapshot_id}/"))
    receipt_key = snapshot_key(source, snapshot_id, OFFLOAD_NAME)
    if receipt_key in keys:
        return OffloadResult(OffloadReceipt.from_dict(storage.get_json(receipt_key)), True)

    # Paso 1: solo un snapshot completo (con manifest) respalda un borrado.
    manifest_key = snapshot_key(source, snapshot_id, MANIFEST_NAME)
    if manifest_key not in keys:
        raise SnapshotNotFoundError(f"No existe el snapshot {source.name}/{snapshot_id}.")
    manifest = Manifest.from_dict(storage.get_json(manifest_key))
    if manifest.table != source.qualified_table:
        raise OffloadVerificationError(
            f"El snapshot pertenece a {manifest.table}, no a {source.qualified_table}."
        )

    with tempfile.TemporaryDirectory(prefix="audit-offload-") as directory:
        # Paso 2: SHA-256 del contenido que hay hoy en RustFS.
        reads = [
            read_parquet_sql(
                download_verified(storage, file, Path(directory) / f"{index:04d}.parquet"),
                manifest.encrypted,
            )
            for index, file in enumerate(manifest.files)
        ]
        archived = "(" + " UNION ALL BY NAME ".join(reads) + ")"
        deleted = _verify_and_delete(connection, relation, table_ref, source, manifest, archived)

    # Paso 6: constancia junto al snapshot; el manifest no se modifica.
    receipt = OffloadReceipt(snapshot_id=snapshot_id, offloaded_at=now, deleted_rows=deleted)
    storage.put_json(receipt_key, receipt.to_dict())
    logger.warning(
        "Offload %s/%s: %s filas borradas de %s",
        source.name, snapshot_id, deleted, source.qualified_table,
    )
    return OffloadResult(receipt, False)


def offload(
    settings: Settings, source: SourceSettings, snapshot_id: str, now: dt.datetime | None = None
) -> OffloadResult:
    """Offload contra PostgreSQL real: la única sesión de AuditCompressor con escritura."""
    now = now or dt.datetime.now(dt.timezone.utc)
    encryption_key = settings.require_encryption_key()
    storage = SnapshotStorage.from_settings(settings.storage)
    with postgres_session(settings.database, read_only=False) as connection:
        register_parquet_key(connection, encryption_key)
        relation = postgres_relation(connection, source)
        table_ref = f"{POSTGRES_CATALOG}.{source.qualified_table}"
        return offload_snapshot(
            connection, relation, table_ref, storage, source, snapshot_id, now
        )
