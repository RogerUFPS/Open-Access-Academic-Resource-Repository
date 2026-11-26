"""Aplicación HTTP de AuditCompressor."""

from __future__ import annotations

import datetime as dt
import logging
import threading
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel

from . import __version__
from .config import SERVICE_NAME, ConfigurationError, Settings, get_settings
from .manifest import SnapshotRange
from .security import require_api_key
from .snapshots import SnapshotConflictError, SnapshotIntegrityError, archive_audit_range

logger = logging.getLogger(__name__)

app = FastAPI(title="AuditCompressor", version=__version__)

# Un archivado a la vez: dos órdenes simultáneas sobre rangos solapados podrían
# superar ambas la comprobación de solapamiento. Suficiente con un único
# proceso (uvicorn --workers 1, como en el Dockerfile).
_archive_lock = threading.Lock()


class SnapshotRequest(BaseModel):
    """Período [start_date, end_date) en días completos UTC."""

    start_date: dt.date
    end_date: dt.date


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness sin autenticación; no depende de PostgreSQL ni de RustFS."""
    return {"status": "ok", "service": SERVICE_NAME}


@app.post(
    "/snapshots",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key)],
)
def create_snapshot(
    request: SnapshotRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    """Archiva en RustFS la auditoría del período y devuelve su manifest."""
    now = dt.datetime.now(dt.timezone.utc)
    try:
        snapshot_range = SnapshotRange.from_dates(request.start_date, request.end_date)
        snapshot_range.ensure_closed(now)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    if not _archive_lock.acquire(blocking=False):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Ya hay un archivado en curso; reintentar más tarde.",
        )
    try:
        manifest = archive_audit_range(settings, snapshot_range, now)
    except SnapshotConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ConfigurationError as exc:
        logger.error("Archivado no disponible: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El servicio de archivado no está configurado.",
        ) from exc
    except SnapshotIntegrityError as exc:
        logger.error("Snapshot %s no verificado: %s", snapshot_range.snapshot_id, exc)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail="El snapshot almacenado no superó la verificación de integridad.",
        ) from exc
    finally:
        _archive_lock.release()
    return manifest.to_dict()
