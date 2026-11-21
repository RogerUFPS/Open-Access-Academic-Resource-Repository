"""Configuración inmutable del servicio obtenida desde variables de entorno."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESOURCES_DIR = PROJECT_ROOT / "resources"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


def _boolean(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.casefold() in {"1", "true", "yes"}


def _csv(name: str) -> tuple[str, ...]:
    return tuple(value.strip() for value in os.getenv(name, "").split(",") if value.strip())


def _json_object(name: str) -> dict[str, Any]:
    raw = os.getenv(name, "{}").strip() or "{}"
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{name} debe contener un objeto JSON válido.") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{name} debe contener un objeto JSON.")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    api_key: str
    model_name: str
    model_aliases: tuple[str, ...]
    model_checkpoint: str
    served_model: str
    vllm_base_url: str
    vllm_api_key: str
    vllm_request_options: dict[str, Any]
    max_concurrency: int
    concurrency_wait_seconds: float
    script_timeout_seconds: int
    vllm_max_tokens: int
    vllm_request_timeout_seconds: int
    auto_index_rag: bool
    rag_path: Path

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            api_key=os.getenv("AGENT_API_KEY", ""),
            model_name=os.getenv("AGENT_MODEL_NAME", "qwen").strip(),
            model_aliases=_csv("AGENT_MODEL_ALIASES"),
            model_checkpoint=os.getenv("MODEL_CHECKPOINT", "Qwen/Qwen3-8B-AWQ").strip(),
            served_model=os.getenv("VLLM_SERVED_MODEL", "biblioteca-qwen3-8b").strip(),
            vllm_base_url=os.getenv("AGENT_VLLM_BASE_URL", "").strip().rstrip("/"),
            vllm_api_key=os.getenv("AGENT_VLLM_API_KEY", "").strip(),
            vllm_request_options=_json_object("VLLM_REQUEST_OPTIONS_JSON"),
            max_concurrency=max(1, int(os.getenv("AGENT_MAX_CONCURRENCY", "8"))),
            concurrency_wait_seconds=max(
                0.05, float(os.getenv("AGENT_CONCURRENCY_WAIT_SECONDS", "1.0"))
            ),
            script_timeout_seconds=max(1, int(os.getenv("SCRIPT_TIMEOUT_SECONDS", "20"))),
            vllm_max_tokens=max(128, int(os.getenv("VLLM_MAX_TOKENS", "384"))),
            vllm_request_timeout_seconds=max(
                30, int(os.getenv("VLLM_REQUEST_TIMEOUT_SECONDS", "300"))
            ),
            auto_index_rag=_boolean("AUTO_INDEX_RAG", True),
            rag_path=Path(
                os.getenv("RAG_DB_PATH", str(PROJECT_ROOT / "data" / "rag.sqlite3"))
            ),
        )


settings = Settings.from_env()
