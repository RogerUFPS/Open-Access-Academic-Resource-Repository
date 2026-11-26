"""Consulta histórica: auditoría archivada de un rango, leída de sus snapshots."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from .config import ArchiveSettings, Settings
from .duckdb_session import sql_literal, timestamp_literal
from .manifest import Manifest, SnapshotFile, SnapshotRange
from .snapshots import SnapshotIntegrityError, list_manifests, sha256_file
from .storage import SnapshotStorage

MAX_PAGE_SIZE = 1000


@dataclass(frozen=True, slots=True)
class HistoryPage:
    count: int
    results: list[dict[str, Any]]


def snapshots_for(
    storage: SnapshotStorage, archive: ArchiveSettings, snapshot_range: SnapshotRange
) -> list[Manifest]:
    manifests = [
        manifest
        for manifest in list_manifests(storage, archive)
        if manifest.range.overlaps(snapshot_range)
    ]
    return sorted(manifests, key=lambda manifest: manifest.range.start)


def _download_verified(storage: SnapshotStorage, file: SnapshotFile, path: Path) -> Path:
    """Descarga el archivo y lo verifica antes de leerlo: se consulta lo verificado."""
    storage.download_file(file.key, path)
    if sha256_file(path) != file.sha256:
        raise SnapshotIntegrityError(f"El SHA-256 almacenado no coincide para {file.key}.")
    return path


def _row_to_json(
    columns: list[str], row: tuple[Any, ...], json_columns: tuple[str, ...]
) -> dict[str, Any]:
    return {
        column: json.loads(value) if column in json_columns and isinstance(value, str) else value
        for column, value in zip(columns, row)
    }


def query_history(
    storage: SnapshotStorage,
    archive: ArchiveSettings,
    snapshot_range: SnapshotRange,
    limit: int,
    offset: int,
) -> HistoryPage:
    """Registros archivados en [start, end), ordenados por fecha y clave primaria.

    Los snapshots que se cruzan con el rango se combinan en una sola consulta;
    quien llama no conoce cómo están divididos.
    """
    if not 1 <= limit <= MAX_PAGE_SIZE or offset < 0:
        raise ValueError(f"limit debe estar entre 1 y {MAX_PAGE_SIZE} y offset no ser negativo.")
    files = [file for manifest in snapshots_for(storage, archive, snapshot_range) for file in manifest.files]
    if not files:
        return HistoryPage(count=0, results=[])

    timestamp = f'"{archive.timestamp_column}"'
    where = (
        f"{timestamp} >= {timestamp_literal(snapshot_range.start)} "
        f"AND {timestamp} < {timestamp_literal(snapshot_range.end)}"
    )
    with tempfile.TemporaryDirectory(prefix="audit-history-") as directory:
        paths = [
            _download_verified(storage, file, Path(directory) / f"{index:04d}.parquet")
            for index, file in enumerate(files)
        ]
        source = (
            "read_parquet(["
            + ", ".join(sql_literal(str(path)) for path in paths)
            + "], union_by_name = true)"
        )
        connection = duckdb.connect()
        try:
            connection.execute("SET TimeZone = 'UTC'")
            count = connection.execute(f"SELECT count(*) FROM {source} WHERE {where}").fetchone()[0]
            # La fecha sale como texto ISO 8601 en UTC, lista para JSON.
            cursor = connection.execute(
                f"SELECT * REPLACE (strftime({timestamp}, '%Y-%m-%dT%H:%M:%S.%f') || '+00:00' "
                f"AS {timestamp}) FROM {source} WHERE {where} "
                f'ORDER BY {timestamp}, "{archive.primary_key}" '
                f"LIMIT {int(limit)} OFFSET {int(offset)}"
            )
            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchall()
        finally:
            connection.close()
    return HistoryPage(
        count=count,
        results=[_row_to_json(columns, row, archive.json_columns) for row in rows],
    )


def read_audit_history(
    settings: Settings, snapshot_range: SnapshotRange, limit: int, offset: int
) -> HistoryPage:
    storage = SnapshotStorage.from_settings(settings.storage)
    return query_history(storage, settings.archive, snapshot_range, limit, offset)
