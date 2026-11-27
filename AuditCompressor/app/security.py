"""Autenticación server-to-server mediante API Key."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from .config import Settings, get_settings

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(
    api_key: Annotated[str | None, Security(API_KEY_HEADER)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Dependencia para endpoints internos.

    Falla cerrado: sin AUDIT_COMPRESSOR_API_KEY configurada, ningún endpoint
    protegido queda accesible.
    """
    if not settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AUDIT_COMPRESSOR_API_KEY no está configurada.",
        )
    if api_key is None or not secrets.compare_digest(api_key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key inválida.",
        )
