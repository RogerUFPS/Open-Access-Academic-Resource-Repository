"""Aplicación HTTP de AuditCompressor."""

from __future__ import annotations

import datetime as dt
import logging
import threading
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel

from . import __version__
from .config import SERVICE_NAME, ConfigurationError, Settings, get_settings
from .history import MAX_PAGE_SIZE, read_audit_history
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


@app.get("/history", dependencies=[Depends(require_api_key)])
def read_history(
    settings: Annotated[Settings, Depends(get_settings)],
    start_date: dt.date,
    end_date: dt.date,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    """Auditoría archivada en [start_date, end_date), combinando todos sus snapshots."""
    try:
        snapshot_range = SnapshotRange.from_dates(start_date, end_date)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    try:
        page = read_audit_history(settings, snapshot_range, limit, offset)
    except ConfigurationError as exc:
        logger.error("Consulta histórica no disponible: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El servicio de archivado no está configurado.",
        ) from exc
    except SnapshotIntegrityError as exc:
        logger.error("Snapshot corrupto en la consulta %s: %s", snapshot_range.snapshot_id, exc)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail="Un snapshot del rango no superó la verificación de integridad.",
        ) from exc
    return {"count": page.count, "limit": limit, "offset": offset, "results": page.results}
