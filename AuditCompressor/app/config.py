"""Configuración inmutable del servicio obtenida desde variables de entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

SERVICE_NAME = "audit-compressor"


@dataclass(frozen=True, slots=True)
class Settings:
    # Las conexiones a PostgreSQL, RustFS y el cifrado se agregarán aquí
    # cuando exista código que las use (ver .env.example).
    api_key: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(api_key=os.getenv("AUDIT_COMPRESSOR_API_KEY", "").strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
