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
from .contracts import model_registry
from .model_registry import ModelConfigurationError
from .runtime import AgentRuntime


runtime = AgentRuntime()


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
    return {
        "status": "ok",
        "provider": "vllm",
        "default_model": model_registry.default_model,
        "max_concurrency": settings.max_concurrency,
        "active_requests": runtime.active_requests,
        "rag_documents": await asyncio.to_thread(runtime.rag.count),
    }


@app.get("/ping")
async def ping():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    unavailable = [item["name"] for item in model_registry.status() if not item["configured"]]
    if unavailable:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Hay modelos remotos sin credenciales o URL.",
                "models": unavailable,
            },
        )
    return {"status": "ready", "models": model_registry.status()}


def _catalog_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    configured_file = os.getenv("AGENT_CATALOG_SNAPSHOT", "").strip()
    backend_url = os.getenv("AGENT_BACKEND_SNAPSHOT_URL", "").strip()
    source = "archivo_configurado" if configured_file else "backend_publico" if backend_url else "ejemplo"
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
    try:
        await asyncio.wait_for(
            runtime.request_slots.acquire(),
            timeout=settings.concurrency_wait_seconds,
        )
    except TimeoutError as exc:
        raise HTTPException(
            status_code=429,
            detail="La réplica está atendiendo su máximo de consultas concurrentes.",
            headers={"Retry-After": str(max(1, round(settings.concurrency_wait_seconds)))},
        ) from exc
    runtime.active_requests += 1
    try:
        try:
            return await runtime.run(request)
        except ModelConfigurationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        runtime.active_requests -= 1
        runtime.request_slots.release()


@app.get("/v1/models", dependencies=[Depends(authenticate)])
async def list_models():
    return {
        "provider": "vllm",
        "modelo_predeterminado": model_registry.default_model,
        "modelos": model_registry.status(),
    }
