"""Aplicación HTTP del agente."""

from __future__ import annotations

import asyncio
import os
import secrets
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException

from . import __version__
from .catalog import clear_backend_snapshot_cache, load_snapshot
from .config import settings
from .contracts import QueryRequest
from .model import ModelConfigurationError, model
from .runtime import AgentRuntime
from .request_context import catalog_path, analysis
from . import snapshots
from pydantic import BaseModel, Field


runtime = AgentRuntime()
gate_lock = asyncio.Lock()
accepting_requests = True
inflight = 0


class CatalogUpload(BaseModel):
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    snapshot: dict[str, Any]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await runtime.start()
    yield
    await runtime.stop()


app = FastAPI(
    title="Agente orientador de literatura",
    version=__version__,
    lifespan=lifespan,
)


def authenticate(x_api_key: str | None = Header(default=None)) -> None:
    if settings.api_key and (
        x_api_key is None or not secrets.compare_digest(x_api_key, settings.api_key)
    ):
        raise HTTPException(status_code=401, detail="API key inválida.")


@app.get("/health")
async def health():
    """Liveness mínima; no depende de modelos ni almacenamiento."""
    return {"status": "healthy"}


@app.get("/health/details")
async def health_details():
    return {
        "status": "ok",
        "provider": "vllm",
        "model": model.name,
        "max_concurrency": settings.max_concurrency,
        "active_requests": runtime.active_requests,
        "rag_documents": await asyncio.to_thread(runtime.rag.count),
    }


@app.get("/ping")
async def ping():
    return {"status": "healthy"}


@app.get("/ready")
async def ready():
    model_status = model.status()
    if not model_status["configured"]:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "La réplica no tiene un endpoint vLLM configurado.",
                "model": model.name,
            },
        )
    return {"status": "ready", "model": model_status}


def _catalog_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    configured_file = os.getenv("AGENT_CATALOG_SNAPSHOT", "").strip()
    backend_url = os.getenv("AGENT_BACKEND_SNAPSHOT_URL", "").strip()
    source = "archivo_configurado" if configured_file else "backend_publico" if backend_url else "no_configurado"
    return {
        "schema_version": snapshot["schema_version"],
        "fuente": source,
        "conteos": {
            key: len(snapshot[key])
            for key in ("programas", "areas", "filtros", "plataformas", "revistas")
        },
        "programas": [{"id": item["id"], "nombre": item["nombre"]} for item in snapshot["programas"]],
        "areas": [{"id": item["id"], "nombre": item["nombre"]} for item in snapshot["areas"]],
        "plataformas": [
            {"id": item["id"], "nombre": item["nombre"]} for item in snapshot["plataformas"]
        ],
    }


async def _read_catalog_summary() -> dict[str, Any]:
    try:
        snapshot = await asyncio.to_thread(load_snapshot)
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"No fue posible leer el catálogo ({type(exc).__name__}).",
        ) from exc
    return _catalog_summary(snapshot)


@app.get("/v1/catalog/summary", dependencies=[Depends(authenticate)])
async def catalog_summary():
    return await _read_catalog_summary()


@app.post("/v1/catalog/refresh", dependencies=[Depends(authenticate)])
async def refresh_catalog():
    await asyncio.to_thread(clear_backend_snapshot_cache)
    return await _read_catalog_summary()


@app.post("/v1/query", dependencies=[Depends(authenticate)])
async def run_query(request: QueryRequest):
    global inflight
    async with gate_lock:
        if not accepting_requests:
            raise HTTPException(status_code=503, detail="La réplica está drenando peticiones.", headers={"Retry-After": "10"})
        inflight += 1
    acquired = False
    path_token = analysis_token = None
    try:
        if request.catalog_digest:
            path = snapshots.path_for(request.catalog_digest)
            if not path.is_file():
                raise HTTPException(status_code=409, detail="Catálogo no sincronizado.")
            path_token = catalog_path.set(path)
        analysis_token = analysis.set({})
        try:
            await asyncio.wait_for(runtime.request_slots.acquire(), timeout=settings.concurrency_wait_seconds)
            acquired = True
        except TimeoutError as exc:
            raise HTTPException(status_code=429, detail="La réplica está ocupada.", headers={"Retry-After": "1"}) from exc
        runtime.active_requests += 1
        try:
            response = await runtime.run(request)
            if request.return_analysis:
                return {"respuesta": response, "analisis": analysis.get(), "modelo": model.name,
                    "catalog_digest": request.catalog_digest}
            return response
        except ModelConfigurationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        if acquired:
            runtime.active_requests -= 1
            runtime.request_slots.release()
        if path_token is not None:
            catalog_path.reset(path_token)
        if analysis_token is not None:
            analysis.reset(analysis_token)
        async with gate_lock:
            inflight -= 1


@app.get("/v1/catalog/snapshots/{digest}", dependencies=[Depends(authenticate)])
async def snapshot_status(digest: str):
    import re
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise HTTPException(status_code=422, detail="Hash inválido.")
    return {"available": snapshots.path_for(digest).is_file()}


@app.post("/v1/catalog/snapshots", dependencies=[Depends(authenticate)])
async def upload_snapshot(upload: CatalogUpload):
    try:
        await asyncio.to_thread(snapshots.install, upload.digest, upload.snapshot)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"available": True, "digest": upload.digest}


@app.get("/v1/control/status", dependencies=[Depends(authenticate)])
async def control_status():
    async with gate_lock:
        return {"model": model.name, "accepting_requests": accepting_requests, "inflight": inflight}


@app.post("/v1/control/drain", dependencies=[Depends(authenticate)])
async def drain():
    global accepting_requests
    async with gate_lock:
        accepting_requests = False
        return {"model": model.name, "accepting_requests": False, "inflight": inflight}


@app.post("/v1/control/resume", dependencies=[Depends(authenticate)])
async def resume():
    global accepting_requests
    async with gate_lock:
        accepting_requests = True
        return {"model": model.name, "accepting_requests": True, "inflight": inflight}


@app.get("/v1/models", dependencies=[Depends(authenticate)])
async def list_models():
    return {
        "provider": "vllm",
        "modelo_predeterminado": model.name,
        "modelos": [model.status()],
    }
