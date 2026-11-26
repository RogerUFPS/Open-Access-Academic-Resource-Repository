"""Configuración del servicio: secretos desde el entorno y archivado desde config.yaml."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

SERVICE_NAME = "audit-compressor"
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "config.yaml"

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PREFIX = re.compile(r"^[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*$")
_COMPRESSIONS = frozenset({"zstd", "snappy", "gzip", "lz4", "brotli", "uncompressed"})


class ConfigurationError(RuntimeError):
    """Falta configuración obligatoria o es inválida."""


def _ensure_present(values: dict[str, str]) -> None:
    """Falla nombrando las variables ausentes, nunca sus valores."""
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ConfigurationError(f"Faltan variables de entorno: {', '.join(missing)}.")


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    host: str
    port: int
    name: str
    user: str
    password: str

    @classmethod
    def from_env(cls) -> "DatabaseSettings":
        return cls(
            host=os.getenv("DATABASE_HOST", "").strip(),
            port=int(os.getenv("DATABASE_PORT", "5432")),
            name=os.getenv("DATABASE_NAME", "").strip(),
            user=os.getenv("DATABASE_USER", "").strip(),
            password=os.getenv("DATABASE_PASSWORD", ""),
        )

    def ensure_complete(self) -> None:
        _ensure_present({
            "DATABASE_HOST": self.host,
            "DATABASE_NAME": self.name,
            "DATABASE_USER": self.user,
            "DATABASE_PASSWORD": self.password,
        })


@dataclass(frozen=True, slots=True)
class StorageSettings:
    endpoint: str
    bucket: str
    region: str
    access_key: str
    secret_key: str

    @classmethod
    def from_env(cls) -> "StorageSettings":
        return cls(
            endpoint=os.getenv("S3_ENDPOINT", "").strip(),
            bucket=os.getenv("S3_BUCKET", "").strip(),
            region=os.getenv("S3_REGION", "us-east-1").strip(),
            access_key=os.getenv("S3_ACCESS_KEY", "").strip(),
            secret_key=os.getenv("S3_SECRET_KEY", ""),
        )

    def ensure_complete(self) -> None:
        _ensure_present({
            "S3_ENDPOINT": self.endpoint,
            "S3_BUCKET": self.bucket,
            "S3_ACCESS_KEY": self.access_key,
            "S3_SECRET_KEY": self.secret_key,
        })


@dataclass(frozen=True, slots=True)
class ArchiveSettings:
    """Qué tabla se archiva y cómo se guardan sus snapshots."""

    schema: str
    table: str
    timestamp_column: str
    primary_key: str
    prefix: str
    compression: str

    def __post_init__(self) -> None:
        # Los identificadores se interpolan en SQL: solo nombres simples.
        for value in (self.schema, self.table, self.timestamp_column, self.primary_key):
            if not isinstance(value, str) or not _IDENTIFIER.match(value):
                raise ConfigurationError(f"Identificador inválido en config.yaml: {value!r}.")
        if not isinstance(self.prefix, str) or not _PREFIX.match(self.prefix):
            raise ConfigurationError(f"storage.prefix inválido: {self.prefix!r}.")
        if self.compression not in _COMPRESSIONS:
            raise ConfigurationError(f"parquet.compression no soportada: {self.compression!r}.")

    @property
    def qualified_table(self) -> str:
        return f"{self.schema}.{self.table}"

    @classmethod
    def from_yaml(cls, path: Path) -> "ArchiveSettings":
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            return cls(
                schema=data["audit"]["schema"],
                table=data["audit"]["table"],
                timestamp_column=data["audit"]["timestamp_column"],
                primary_key=data["audit"]["primary_key"],
                prefix=data["storage"]["prefix"],
                compression=data["parquet"]["compression"],
            )
        except FileNotFoundError as exc:
            raise ConfigurationError(f"No existe el archivo de configuración {path}.") from exc
        except (KeyError, TypeError, yaml.YAMLError) as exc:
            raise ConfigurationError(f"config.yaml incompleto o mal formado: {exc}") from exc


@dataclass(frozen=True, slots=True)
class Settings:
    api_key: str
    database: DatabaseSettings
    storage: StorageSettings
    archive: ArchiveSettings

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            api_key=os.getenv("AUDIT_COMPRESSOR_API_KEY", "").strip(),
            database=DatabaseSettings.from_env(),
            storage=StorageSettings.from_env(),
            archive=ArchiveSettings.from_yaml(CONFIG_PATH),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
