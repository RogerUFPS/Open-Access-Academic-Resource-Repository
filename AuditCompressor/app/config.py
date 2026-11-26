"""Configuración inmutable del servicio obtenida desde variables de entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

SERVICE_NAME = "audit-compressor"


class ConfigurationError(RuntimeError):
    """Falta configuración obligatoria para una operación."""


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
        """Falla nombrando las variables ausentes, nunca sus valores."""
        missing = [
            variable
            for variable, value in (
                ("DATABASE_HOST", self.host),
                ("DATABASE_NAME", self.name),
                ("DATABASE_USER", self.user),
                ("DATABASE_PASSWORD", self.password),
            )
            if not value
        ]
        if missing:
            raise ConfigurationError(f"Faltan variables de entorno: {', '.join(missing)}.")


@dataclass(frozen=True, slots=True)
class Settings:
    api_key: str
    database: DatabaseSettings

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            api_key=os.getenv("AUDIT_COMPRESSOR_API_KEY", "").strip(),
            database=DatabaseSettings.from_env(),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
