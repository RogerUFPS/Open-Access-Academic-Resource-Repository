"""Utilidades compartidas por los tests: datos de auditoría y almacenamiento en memoria."""

import base64
import datetime as dt
import hashlib
import json
from pathlib import Path

import duckdb

from app.config import ArchiveSettings

UTC = dt.timezone.utc
START = dt.datetime(2025, 1, 1, tzinfo=UTC)
END = dt.datetime(2025, 7, 1, tzinfo=UTC)
MICROSECOND = dt.timedelta(microseconds=1)
TEST_KEY = base64.b64encode(bytes(range(32))).decode()

ARCHIVE = ArchiveSettings(
    schema="main",
    table="audit",
    timestamp_column="timestamp",
    primary_key="id",
    prefix="auditlog",
    compression="zstd",
    json_columns=("changes",),
)


def audit_connection() -> duckdb.DuckDBPyConnection:
    """Tabla ``audit`` con filas justo fuera y dentro de [START, END)."""
    connection = duckdb.connect()
    connection.execute("SET TimeZone = 'UTC'")
    connection.execute('CREATE TABLE audit (id INTEGER, "timestamp" TIMESTAMPTZ, changes VARCHAR)')
    connection.executemany(
        "INSERT INTO audit VALUES (?, ?, ?)",
        [
            (1, START - MICROSECOND, '{"before": "start"}'),
            (4, END - MICROSECOND, '{"last": "inside"}'),
            (2, START, None),
            (3, START + dt.timedelta(days=30), '{"nested": {"a": [1, 2]}}'),
            (5, END, '{"after": "end"}'),
        ],
    )
    return connection


class FakeStorage:
    """Mismo contrato que SnapshotStorage, en memoria.

    ``corrupt`` simula un objeto alterado en el almacenamiento.
    """

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.corrupt = False
        self.downloaded: list[str] = []

    def upload_file(self, path: Path, key: str) -> None:
        content = path.read_bytes()
        self.objects[key] = content + b"corrupt" if self.corrupt else content

    def download_file(self, key: str, path: Path) -> None:
        self.downloaded.append(key)
        path.write_bytes(self.objects[key])

    def sha256(self, key: str) -> str:
        return hashlib.sha256(self.objects[key]).hexdigest()

    def put_json(self, key: str, data: dict) -> None:
        self.objects[key] = json.dumps(data).encode("utf-8")

    def get_json(self, key: str) -> dict:
        return json.loads(self.objects[key])

    def list_keys(self, prefix: str) -> list[str]:
        return sorted(key for key in self.objects if key.startswith(prefix))
