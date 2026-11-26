"""Consulta histórica: registros archivados de una fuente en un rango."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from .config import Settings, SourceSettings, parquet_encryption_key
from .duckdb_session import (
    ENCRYPTION_CONFIG,
    quote_identifier,
    register_parquet_key,
    sql_literal,
    timestamp_literal,
)
from .manifest import Manifest, SnapshotFile, SnapshotRange
from .snapshots import SnapshotIntegrityError, list_manifests, sha256_file
from .storage import SnapshotStorage

MAX_PAGE_SIZE = 1000


@dataclass(frozen=True, slots=True)
class HistoryPage:
    count: int
    results: list[dict[str, Any]]


def snapshots_for(
    storage: SnapshotStorage, source: SourceSettings, snapshot_range: SnapshotRange
) -> list[Manifest]:
    manifests = [
        manifest
        for manifest in list_manifests(storage, source)
        if manifest.range.overlaps(snapshot_range)
    ]
    return sorted(manifests, key=lambda manifest: manifest.range.start)


def _download_verified(storage: SnapshotStorage, file: SnapshotFile, path: Path) -> Path:
    """Descarga el archivo y lo verifica antes de leerlo: se consulta lo verificado."""
    storage.download_file(file.key, path)
    if sha256_file(path) != file.sha256:
        raise SnapshotIntegrityError(f"El SHA-256 almacenado no coincide para {file.key}.")
    return path


def _read_file(path: Path, encrypted: bool) -> str:
    options = f", encryption_config = {ENCRYPTION_CONFIG}" if encrypted else ""
    return f"SELECT * FROM read_parquet({sql_literal(str(path))}{options})"


def _row_to_json(
    columns: list[str], row: tuple[Any, ...], json_columns: tuple[str, ...]
) -> dict[str, Any]:
    return {
        column: json.loads(value) if column in json_columns and isinstance(value, str) else value
        for column, value in zip(columns, row)
    }


def query_history(
    storage: SnapshotStorage,
    source: SourceSettings,
    snapshot_range: SnapshotRange,
    limit: int,
    offset: int,
    encryption_key: str = "",
) -> HistoryPage:
    """Registros archivados en [start, end), ordenados por fecha y clave primaria.

    Los snapshots que se cruzan con el rango se combinan en una sola consulta;
    quien llama no conoce cómo están divididos. Cada archivo se descifra solo
    si su manifest indica que está cifrado.
    """
    if not 1 <= limit <= MAX_PAGE_SIZE or offset < 0:
        raise ValueError(f"limit debe estar entre 1 y {MAX_PAGE_SIZE} y offset no ser negativo.")
    files = [
        (file, manifest.encrypted)
        for manifest in snapshots_for(storage, source, snapshot_range)
        for file in manifest.files
    ]
    if not files:
        return HistoryPage(count=0, results=[])
    needs_key = any(encrypted for _, encrypted in files)
    if needs_key:
        encryption_key = parquet_encryption_key(encryption_key)

    timestamp = quote_identifier(source.timestamp_column)
    where = (
        f"{timestamp} >= {timestamp_literal(snapshot_range.start)} "
        f"AND {timestamp} < {timestamp_literal(snapshot_range.end)}"
    )
    with tempfile.TemporaryDirectory(prefix="audit-history-") as directory:
        reads = [
            _read_file(
                _download_verified(storage, file, Path(directory) / f"{index:04d}.parquet"),
                encrypted,
            )
            for index, (file, encrypted) in enumerate(files)
        ]
        relation = "(" + " UNION ALL BY NAME ".join(reads) + ")"
        connection = duckdb.connect()
        try:
            connection.execute("SET TimeZone = 'UTC'")
            if needs_key:
                register_parquet_key(connection, encryption_key)
            count = connection.execute(
                f"SELECT count(*) FROM {relation} WHERE {where}"
            ).fetchone()[0]
            # La fecha sale como texto ISO 8601 en UTC, lista para JSON.
            cursor = connection.execute(
                f"SELECT * REPLACE (strftime({timestamp}, '%Y-%m-%dT%H:%M:%S.%f') || '+00:00' "
                f"AS {timestamp}) FROM {relation} WHERE {where} "
                f"ORDER BY {timestamp}, {quote_identifier(source.primary_key)} "
                f"LIMIT {int(limit)} OFFSET {int(offset)}"
            )
            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchall()
        finally:
            connection.close()
    return HistoryPage(
        count=count,
        results=[_row_to_json(columns, row, source.json_columns) for row in rows],
    )


def read_history(
    settings: Settings,
    source: SourceSettings,
    snapshot_range: SnapshotRange,
    limit: int,
    offset: int,
) -> HistoryPage:
    storage = SnapshotStorage.from_settings(settings.storage)
    return query_history(
        storage, source, snapshot_range, limit, offset, settings.encryption_key
    )
