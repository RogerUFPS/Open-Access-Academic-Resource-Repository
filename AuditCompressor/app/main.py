"""Aplicación HTTP de AuditCompressor."""

from __future__ import annotations

import datetime as dt
import logging
import threading
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Path, Query, status
from pydantic import BaseModel, Field

from . import __version__
from .anomalies import (
    ExpectedRowsMismatchError,
    SnapshotNotOffloadedError,
    closed_snapshots,
    remove_duplicates,
    resolve_leftovers,
)
from .config import (
    SERVICE_NAME,
    ConfigurationError,
    Settings,
    SourceSettings,
    UnknownSourceError,
    get_settings,
)
from .history import MAX_PAGE_SIZE, read_history
from .manifest import SNAPSHOT_ID_PATTERN, SnapshotRange
from .offload import (
    OffloadDisabledError,
    OffloadVerificationError,
    SnapshotNotFoundError,
    offload,
)
from .security import require_api_key
from .snapshots import SnapshotConflictError, SnapshotIntegrityError, archive_range

logger = logging.getLogger(__name__)

app = FastAPI(title="AuditCompressor", version=__version__)

# Un archivado u offload a la vez: dos órdenes simultáneas podrían superar
# ambas las comprobaciones previas. Suficiente con un único proceso
# (uvicorn --workers 1, como en el Dockerfile).
_archive_lock = threading.Lock()
_BUSY = "Ya hay un archivado u offload en curso; reintentar más tarde."

_NOT_CONFIGURED = "El servicio de archivado no está configurado."


class SnapshotRequest(BaseModel):
    """Período [start_date, end_date) en días completos de la zona configurada."""

    start_date: dt.date
    end_date: dt.date


def get_source(
    source_name: str, settings: Annotated[Settings, Depends(get_settings)]
) -> SourceSettings:
    try:
        return settings.source(source_name)
    except UnknownSourceError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


class LeftoversRequest(BaseModel):
    """Cantidad de registros que el usuario revisó antes de decidir."""

    expected_rows: int = Field(ge=0)


def _range_or_422(start_date: dt.date, end_date: dt.date, settings: Settings) -> SnapshotRange:
    try:
        return SnapshotRange.from_dates(start_date, end_date, settings.timezone)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness sin autenticación; no depende de PostgreSQL ni de RustFS."""
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/sources", dependencies=[Depends(require_api_key)])
def get_sources(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any]:
    """Fuentes configuradas y si permiten offload (borrar de PostgreSQL tras archivar)."""
    return {
        "sources": [
            {"name": source.name, "offload": source.offload}
            for source in settings.sources.values()
        ]
    }


@app.post(
    "/sources/{source_name}/snapshots",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key)],
)
def post_snapshot(
    request: SnapshotRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    source: Annotated[SourceSettings, Depends(get_source)],
) -> dict[str, Any]:
    """Archiva en RustFS los registros de la fuente en el período y devuelve su manifest."""
    now = dt.datetime.now(dt.timezone.utc)
    snapshot_range = _range_or_422(request.start_date, request.end_date, settings)
    try:
        snapshot_range.ensure_closed(now)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    if not _archive_lock.acquire(blocking=False):
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_BUSY)
    try:
        manifest = archive_range(settings, source, snapshot_range, now)
    except SnapshotConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ConfigurationError as exc:
        logger.error("Archivado no disponible: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NOT_CONFIGURED) from exc
    except SnapshotIntegrityError as exc:
        logger.error("Snapshot %s/%s no verificado: %s", source.name, snapshot_range.snapshot_id, exc)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail="El snapshot almacenado no superó la verificación de integridad.",
        ) from exc
    finally:
        _archive_lock.release()
    return manifest.to_dict()


@app.post(
    "/sources/{source_name}/snapshots/{snapshot_id}/offload",
    dependencies=[Depends(require_api_key)],
)
def post_offload(
    snapshot_id: Annotated[str, Path(pattern=SNAPSHOT_ID_PATTERN)],
    settings: Annotated[Settings, Depends(get_settings)],
    source: Annotated[SourceSettings, Depends(get_source)],
) -> dict[str, Any]:
    """Borra de PostgreSQL los registros del snapshot, solo si la copia queda verificada."""
    if not _archive_lock.acquire(blocking=False):
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_BUSY)
    try:
        result = offload(settings, source, snapshot_id)
    except SnapshotNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except OffloadDisabledError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except OffloadVerificationError as exc:
        logger.error("Offload %s/%s rechazado: %s", source.name, snapshot_id, exc)
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except SnapshotIntegrityError as exc:
        logger.error("Offload %s/%s con snapshot corrupto: %s", source.name, snapshot_id, exc)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail="El snapshot almacenado no superó la verificación de integridad.",
        ) from exc
    except ConfigurationError as exc:
        logger.error("Offload no disponible: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NOT_CONFIGURED) from exc
    finally:
        _archive_lock.release()
    return {**result.receipt.to_dict(), "already_offloaded": result.already_offloaded}


def _anomaly_errors(source: SourceSettings, snapshot_id: str, work):
    """Ejecuta una operación sobre una anomalía bajo el bloqueo y traduce sus errores."""
    if not _archive_lock.acquire(blocking=False):
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_BUSY)
    try:
        return work()
    except SnapshotNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (SnapshotNotOffloadedError, ExpectedRowsMismatchError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except OffloadVerificationError as exc:
        logger.error("Anomalía %s/%s no resuelta: %s", source.name, snapshot_id, exc)
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except SnapshotIntegrityError as exc:
        logger.error("Anomalía %s/%s con snapshot corrupto: %s", source.name, snapshot_id, exc)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail="El snapshot almacenado no superó la verificación de integridad.",
        ) from exc
    except ConfigurationError as exc:
        logger.error("Gestión de anomalías no disponible: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NOT_CONFIGURED) from exc
    finally:
        _archive_lock.release()


@app.get("/sources/{source_name}/closed-snapshots", dependencies=[Depends(require_api_key)])
def get_closed_snapshots(
    settings: Annotated[Settings, Depends(get_settings)],
    source: Annotated[SourceSettings, Depends(get_source)],
) -> dict[str, Any]:
    """Semestres ya archivados y borrados de PostgreSQL. No descarga ningún Parquet."""
    try:
        manifests = closed_snapshots(settings, source)
    except ConfigurationError as exc:
        logger.error("Listado de snapshots no disponible: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NOT_CONFIGURED) from exc
    return {
        "snapshots": [
            {
                "snapshot_id": manifest.snapshot_id,
                "start": manifest.range.start.isoformat(),
                "end": manifest.range.end.isoformat(),
            }
            for manifest in manifests
        ]
    }


@app.post(
    "/sources/{source_name}/snapshots/{snapshot_id}/purge-duplicates",
    dependencies=[Depends(require_api_key)],
)
def post_purge_duplicates(
    snapshot_id: Annotated[str, Path(pattern=SNAPSHOT_ID_PATTERN)],
    settings: Annotated[Settings, Depends(get_settings)],
    source: Annotated[SourceSettings, Depends(get_source)],
) -> dict[str, Any]:
    """Elimina registros de un semestre cerrado cuyo id ya está archivado."""
    result = _anomaly_errors(
        source, snapshot_id, lambda: remove_duplicates(settings, source, snapshot_id)
    )
    return result.to_dict()


@app.post(
    "/sources/{source_name}/snapshots/{snapshot_id}/leftovers/{action}",
    dependencies=[Depends(require_api_key)],
)
def post_resolve_leftovers(
    snapshot_id: Annotated[str, Path(pattern=SNAPSHOT_ID_PATTERN)],
    action: Annotated[str, Path(pattern="^(compress|delete)$")],
    request: LeftoversRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    source: Annotated[SourceSettings, Depends(get_source)],
) -> dict[str, Any]:
    """Comprime dentro del semestre o elimina los registros nuevos de una anomalía."""
    result = _anomaly_errors(
        source,
        snapshot_id,
        lambda: resolve_leftovers(settings, source, snapshot_id, action, request.expected_rows),
    )
    return result.to_dict()


@app.get("/sources/{source_name}/history", dependencies=[Depends(require_api_key)])
def get_history(
    settings: Annotated[Settings, Depends(get_settings)],
    source: Annotated[SourceSettings, Depends(get_source)],
    start_date: dt.date,
    end_date: dt.date,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    """Registros archivados de la fuente en [start_date, end_date), de todos sus snapshots."""
    snapshot_range = _range_or_422(start_date, end_date, settings)
    try:
        page = read_history(settings, source, snapshot_range, limit, offset)
    except ConfigurationError as exc:
        logger.error("Consulta histórica no disponible: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NOT_CONFIGURED) from exc
    except SnapshotIntegrityError as exc:
        logger.error("Snapshot corrupto en %s %s: %s", source.name, snapshot_range.snapshot_id, exc)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail="Un snapshot del rango no superó la verificación de integridad.",
        ) from exc
    return {"count": page.count, "limit": limit, "offset": offset, "results": page.results}
