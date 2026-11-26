"""Modelo de un snapshot: su período, sus archivos y el manifest que lo describe."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import asdict, dataclass
from typing import Any

MANIFEST_FORMAT_VERSION = 1
MANIFEST_NAME = "manifest.json"
# Formato de SnapshotRange.snapshot_id; impide rutas arbitrarias en el bucket.
SNAPSHOT_ID_PATTERN = r"^\d{8}T\d{6}Z_\d{8}T\d{6}Z$"
_SNAPSHOT_ID = re.compile(SNAPSHOT_ID_PATTERN)


def is_snapshot_id(value: str) -> bool:
    return bool(_SNAPSHOT_ID.fullmatch(value))


@dataclass(frozen=True, slots=True)
class SnapshotRange:
    """Período semiabierto [start, end), normalizado a UTC."""

    start: dt.datetime
    end: dt.datetime

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("start y end deben incluir zona horaria.")
        if self.start >= self.end:
            raise ValueError("start debe ser anterior a end.")
        object.__setattr__(self, "start", self.start.astimezone(dt.timezone.utc))
        object.__setattr__(self, "end", self.end.astimezone(dt.timezone.utc))

    @classmethod
    def from_dates(cls, start: dt.date, end: dt.date) -> "SnapshotRange":
        """Rango desde la medianoche UTC de start hasta la medianoche UTC de end."""
        return cls(
            start=dt.datetime.combine(start, dt.time.min, tzinfo=dt.timezone.utc),
            end=dt.datetime.combine(end, dt.time.min, tzinfo=dt.timezone.utc),
        )

    @property
    def snapshot_id(self) -> str:
        return f"{self.start:%Y%m%dT%H%M%SZ}_{self.end:%Y%m%dT%H%M%SZ}"

    def overlaps(self, other: "SnapshotRange") -> bool:
        return self.start < other.end and other.start < self.end

    def ensure_closed(self, now: dt.datetime) -> None:
        """Un período en curso todavía puede recibir registros."""
        if self.end > now:
            raise ValueError("No se puede archivar un período que aún no ha terminado.")


@dataclass(frozen=True, slots=True)
class SnapshotFile:
    key: str
    sha256: str
    size: int
    row_count: int


@dataclass(frozen=True, slots=True)
class Manifest:
    """Metadata persistente de un snapshot.

    Se escribe solo después de verificar todos sus archivos en RustFS: su
    existencia indica que el snapshot es válido. Las consultas deben leer los
    archivos listados aquí, nunca los objetos sueltos del prefijo.
    """

    snapshot_id: str
    table: str
    timestamp_column: str
    range: SnapshotRange
    created_at: dt.datetime
    files: tuple[SnapshotFile, ...]
    encrypted: bool = False

    @property
    def row_count(self) -> int:
        return sum(file.row_count for file in self.files)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_version": MANIFEST_FORMAT_VERSION,
            "snapshot_id": self.snapshot_id,
            "table": self.table,
            "timestamp_column": self.timestamp_column,
            "start": self.range.start.isoformat(),
            "end": self.range.end.isoformat(),
            "created_at": self.created_at.isoformat(),
            "row_count": self.row_count,
            "encrypted": self.encrypted,
            "files": [asdict(file) for file in self.files],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Manifest":
        version = data.get("format_version")
        if version != MANIFEST_FORMAT_VERSION:
            raise ValueError(f"Versión de manifest no soportada: {version!r}.")
        return cls(
            snapshot_id=data["snapshot_id"],
            table=data["table"],
            timestamp_column=data["timestamp_column"],
            range=SnapshotRange(
                dt.datetime.fromisoformat(data["start"]),
                dt.datetime.fromisoformat(data["end"]),
            ),
            created_at=dt.datetime.fromisoformat(data["created_at"]),
            files=tuple(SnapshotFile(**file) for file in data["files"]),
            encrypted=data["encrypted"],
        )
