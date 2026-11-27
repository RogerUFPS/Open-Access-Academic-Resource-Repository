"""Configuración del servicio: secretos desde el entorno y archivado desde config.yaml."""

from __future__ import annotations

import base64
import binascii
import datetime as dt
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

SERVICE_NAME = "audit-compressor"
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "config.yaml"

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# Aparece en rutas de la API y como prefijo en RustFS.
_SOURCE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_COMPRESSIONS = frozenset({"zstd", "snappy", "gzip", "lz4", "brotli", "uncompressed"})


class ConfigurationError(RuntimeError):
    """Falta configuración obligatoria o es inválida."""


def _ensure_present(values: dict[str, str]) -> None:
    """Falla nombrando las variables ausentes, nunca sus valores."""
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ConfigurationError(f"Faltan variables de entorno: {', '.join(missing)}.")


def parquet_encryption_key(value: str) -> str:
    """Valida AUDIT_ENCRYPTION_KEY: 32 bytes aleatorios codificados en base64 (256 bits)."""
    _ensure_present({"AUDIT_ENCRYPTION_KEY": value})
    try:
        decoded = base64.b64decode(value, validate=True)
    except binascii.Error:
        decoded = b""
    if len(decoded) != 32:
        raise ConfigurationError("AUDIT_ENCRYPTION_KEY debe ser 32 bytes codificados en base64.")
    return value


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


class UnknownSourceError(LookupError):
    """La fuente pedida no está declarada en config.yaml."""


@dataclass(frozen=True, slots=True)
class SourceSettings:
    """Una tabla de auditoría archivable y dónde se guardan sus snapshots.

    El nombre identifica la fuente en la API y es su prefijo dentro del bucket.
    """

    name: str
    schema: str
    table: str
    timestamp_column: str
    primary_key: str
    compression: str
    json_columns: tuple[str, ...] = ()
    # False: se comprime pero nunca se borra de PostgreSQL (ni anomalías).
    offload: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _SOURCE_NAME.match(self.name):
            raise ConfigurationError(f"Nombre de fuente inválido en config.yaml: {self.name!r}.")
        if not isinstance(self.offload, bool):
            raise ConfigurationError(f"offload debe ser true o false en la fuente {self.name!r}.")
        # Los identificadores se interpolan en SQL: solo nombres simples.
        identifiers = (self.schema, self.table, self.timestamp_column, self.primary_key)
        for value in (*identifiers, *self.json_columns):
            if not isinstance(value, str) or not _IDENTIFIER.match(value):
                raise ConfigurationError(f"Identificador inválido en config.yaml: {value!r}.")
        if self.compression not in _COMPRESSIONS:
            raise ConfigurationError(f"parquet.compression no soportada: {self.compression!r}.")

    @property
    def prefix(self) -> str:
        return self.name

    @property
    def qualified_table(self) -> str:
        return f"{self.schema}.{self.table}"


def load_sources(path: Path) -> dict[str, SourceSettings]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        compression = data["parquet"]["compression"]
        declared = data["sources"]
        if not isinstance(declared, dict) or not declared:
            raise ConfigurationError("config.yaml debe declarar al menos una fuente en 'sources'.")
        return {
            name: SourceSettings(
                name=name,
                schema=source["schema"],
                table=source["table"],
                timestamp_column=source["timestamp_column"],
                primary_key=source["primary_key"],
                compression=compression,
                json_columns=tuple(source.get("json_columns", ())),
                offload=source.get("offload", True),
            )
            for name, source in declared.items()
        }
    except FileNotFoundError as exc:
        raise ConfigurationError(f"No existe el archivo de configuración {path}.") from exc
    except (KeyError, TypeError, AttributeError, yaml.YAMLError) as exc:
        raise ConfigurationError(f"config.yaml incompleto o mal formado: {exc}") from exc


def load_timezone(path: Path) -> dt.tzinfo:
    """Zona en la que empiezan y terminan los semestres (UTC si no se declara)."""
    try:
        name = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("timezone", "UTC")
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, TypeError, ValueError) as exc:
        raise ConfigurationError(f"timezone inválida en config.yaml: {exc}") from exc
    except FileNotFoundError as exc:
        raise ConfigurationError(f"No existe el archivo de configuración {path}.") from exc


@dataclass(frozen=True, slots=True)
class Settings:
    api_key: str
    database: DatabaseSettings
    storage: StorageSettings
    sources: dict[str, SourceSettings]
    encryption_key: str = ""
    timezone: dt.tzinfo = dt.timezone.utc

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            api_key=os.getenv("AUDIT_COMPRESSOR_API_KEY", "").strip(),
            database=DatabaseSettings.from_env(),
            storage=StorageSettings.from_env(),
            sources=load_sources(CONFIG_PATH),
            encryption_key=os.getenv("AUDIT_ENCRYPTION_KEY", "").strip(),
            timezone=load_timezone(CONFIG_PATH),
        )

    def source(self, name: str) -> SourceSettings:
        try:
            return self.sources[name]
        except KeyError:
            raise UnknownSourceError(f"La fuente {name!r} no existe.") from None

    def require_encryption_key(self) -> str:
        return parquet_encryption_key(self.encryption_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
