"""Adaptador seguro entre el modelo y las herramientas Python permitidas."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

from .config import PROJECT_ROOT, SCRIPTS_DIR, settings


SCRIPT_NAMES = (
    "normalize_text",
    "get_academic_programs",
    "get_knowledge_areas",
    "get_valid_filters",
    "get_areas_from_program",
    "get_programs_from_areas",
    "get_platforms_related_to_programs",
    "get_valid_sintaxis",
    "get_platform_journal_title_unified",
    "yake_extract_keywords",
)
ALLOWED_SCRIPTS = {name: SCRIPTS_DIR / f"{name}.py" for name in SCRIPT_NAMES}


def run_script(script_name: str, script_args: dict[str, Any]) -> dict[str, Any]:
    normalized_name = script_name.removeprefix("scripts/").removesuffix(".py")
    path = ALLOWED_SCRIPTS.get(normalized_name)
    if path is None:
        return {"error": "Script no permitido."}
    if not isinstance(script_args, dict):
        return {"error": "script_args debe ser un objeto JSON."}
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(PROJECT_ROOT / "src"),
        "LANG": "C.UTF-8",
    }
    for name in (
        "AGENT_CATALOG_SNAPSHOT",
        "AGENT_BACKEND_SNAPSHOT_URL",
        "AGENT_BACKEND_CACHE_PATH",
        "AGENT_BACKEND_CACHE_TTL",
    ):
        value = os.environ.get(name)
        if value:
            environment[name] = value
    process = subprocess.run(
        [sys.executable, str(path), "--json", json.dumps(script_args, ensure_ascii=False)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        timeout=settings.script_timeout_seconds,
        check=False,
        env=environment,
    )
    if len(process.stdout) > 1_000_000:
        return {"error": "La salida del script excedió el límite permitido."}
    try:
        output = json.loads(process.stdout)
    except json.JSONDecodeError:
        return {"error": "El script no devolvió JSON válido."}
    if process.returncode not in (0, 2) and "error" not in output:
        return {"error": "El script terminó de forma inesperada."}
    return output


SCRIPT_TOOL = {
    "type": "function",
    "function": {
        "name": "run_python_script",
        "description": "Ejecuta exclusivamente uno de los scripts Python permitidos por la skill.",
        "parameters": {
            "type": "object",
            "required": ["script_name", "script_args"],
            "properties": {
                "script_name": {
                    "type": "string",
                    "enum": [f"scripts/{name}.py" for name in ALLOWED_SCRIPTS],
                },
                "script_args": {"type": "object"},
            },
        },
    },
}

RAG_TOOL = {
    "type": "function",
    "function": {
        "name": "rag_search",
        "description": "Recupera ejemplos revisados; no reemplaza los catálogos activos.",
        "parameters": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 3},
            },
        },
    },
}
