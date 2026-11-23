"""Repositorio de solo lectura para el snapshot público de Biblioteca."""

from __future__ import annotations

import fcntl
import json
import os
import re
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .config import PROJECT_ROOT


DEFAULT_CACHE = PROJECT_ROOT / "data" / "backend_snapshot.json"


def _validate_snapshot(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Versión de snapshot no soportada.")
    for key in ("programas", "areas", "filtros", "plataformas", "revistas"):
        if not isinstance(data.get(key), list):
            raise ValueError(f"El snapshot no contiene una lista válida en '{key}'.")
    return data


def _load_file(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        return _validate_snapshot(json.load(source))


def _resolved_cache_path() -> Path:
    cache_path = Path(os.getenv("AGENT_BACKEND_CACHE_PATH", str(DEFAULT_CACHE))).resolve()
    if PROJECT_ROOT.resolve() not in cache_path.parents:
        raise ValueError("AGENT_BACKEND_CACHE_PATH debe estar dentro de la carpeta Agent.")
    return cache_path


def clear_backend_snapshot_cache() -> None:
    cache_path = _resolved_cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = cache_path.with_suffix(f"{cache_path.suffix}.lock")
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        cache_path.unlink(missing_ok=True)
        cache_path.with_suffix(f"{cache_path.suffix}.etag").unlink(missing_ok=True)


def _backend_snapshot(url: str) -> dict[str, Any]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("AGENT_BACKEND_SNAPSHOT_URL debe ser una URL HTTP(S) absoluta.")
    cache_path = _resolved_cache_path()
    ttl = max(0, int(os.getenv("AGENT_BACKEND_CACHE_TTL", "300")))
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = cache_path.with_suffix(f"{cache_path.suffix}.lock")
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if cache_path.exists() and time.time() - cache_path.stat().st_mtime < ttl:
            return _load_file(cache_path)
        etag_path = cache_path.with_suffix(f"{cache_path.suffix}.etag")
        headers = {"Accept": "application/json"}
        if cache_path.exists() and etag_path.exists():
            etag = etag_path.read_text(encoding="utf-8").strip()
            if etag:
                headers["If-None-Match"] = etag
        try:
            with urlopen(Request(url, headers=headers), timeout=5) as response:
                if int(response.headers.get("Content-Length", "0") or 0) > 50_000_000:
                    raise ValueError("El snapshot del backend excede 50 MB.")
                raw = response.read(50_000_001)
                if len(raw) > 50_000_000:
                    raise ValueError("El snapshot del backend excede 50 MB.")
                data = _validate_snapshot(json.loads(raw.decode("utf-8")))
                response_etag = response.headers.get("ETag", "")
        except HTTPError as exc:
            if exc.code == 304 and cache_path.exists():
                os.utime(cache_path, None)
                return _load_file(cache_path)
            raise ValueError(f"El backend respondió HTTP {exc.code}.") from exc
        except URLError as exc:
            raise ValueError("No fue posible conectar con el snapshot del backend.") from exc
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=cache_path.parent, delete=False
        ) as temporary:
            json.dump(data, temporary, ensure_ascii=False, separators=(",", ":"))
            temporary_path = Path(temporary.name)
        temporary_path.replace(cache_path)
        etag_path.write_text(response_etag, encoding="utf-8")
        return data


def load_snapshot() -> dict[str, Any]:
    configured = os.getenv("AGENT_CATALOG_SNAPSHOT")
    backend_url = os.getenv("AGENT_BACKEND_SNAPSHOT_URL", "").strip()
    if backend_url and not configured:
        return _backend_snapshot(backend_url)
    if not configured:
        raise ValueError("Catálogo no configurado: el Backend debe sincronizar un snapshot o configure una fuente explícita.")
    path = Path(configured).resolve()
    if PROJECT_ROOT.resolve() not in path.parents:
        raise ValueError("AGENT_CATALOG_SNAPSHOT debe estar dentro de la carpeta Agent.")
    return _load_file(path)


def journal_matches(journal: dict[str, Any], filters: dict[str, Any], catalog: list[dict]) -> bool:
    by_id = {str(item["id"]): item for item in catalog}
    for filter_id, value in filters.items():
        definition = by_id.get(str(filter_id))
        if definition is None:
            raise ValueError(f"Filtro inexistente: {filter_id}")
        key = definition["clave"]
        if definition["tipo"] == "lista":
            if not isinstance(value, list) or not value or any(not isinstance(item, str) for item in value):
                raise ValueError(f"El filtro {filter_id} requiere una lista no vacía.")
            invalid = sorted(set(value) - set(definition["valores_validos"]))
            if invalid:
                raise ValueError(f"Valores inválidos para el filtro {filter_id}: {invalid}")
        elif not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{4}", value):
            raise ValueError(f"El filtro {filter_id} requiere el formato AAAA-AAAA.")
        if key == "idioma" and not set(value).intersection(journal.get("idiomas", [])):
            return False
        if key == "tipo_documento" and not set(value).intersection(journal.get("tipos_documento", [])):
            return False
        if key == "fecha_publicacion":
            start, end = (int(part) for part in value.split("-", 1))
            if start > end:
                raise ValueError(f"El rango del filtro {filter_id} está invertido.")
            published = journal.get("fecha_publicacion")
            if not published:
                return False
            year = int(published[:4])
            if year < start or year > min(end, date.today().year):
                return False
    return True
