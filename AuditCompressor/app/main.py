"""Aplicación HTTP de AuditCompressor."""

from __future__ import annotations

from fastapi import FastAPI

from . import __version__
from .config import SERVICE_NAME

app = FastAPI(title="AuditCompressor", version=__version__)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness sin autenticación; no depende de PostgreSQL ni de RustFS."""
    return {"status": "ok", "service": SERVICE_NAME}
