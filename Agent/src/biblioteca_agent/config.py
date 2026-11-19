"""Configuración inmutable del servicio obtenida desde variables de entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESOURCES_DIR = PROJECT_ROOT / "resources"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
DEFAULT_MODEL_REGISTRY = PROJECT_ROOT / "config" / "models.json"


def _boolean(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.casefold() in {"1", "true", "yes"}


@dataclass(frozen=True, slots=True)
class Settings:
    api_key: str
    model_registry_path: Path
    max_concurrency: int
    concurrency_wait_seconds: float
    script_timeout_seconds: int
    vllm_max_tokens: int
    vllm_request_timeout_seconds: int
    max_tool_rounds: int
    auto_index_rag: bool
    rag_path: Path

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            api_key=os.getenv("AGENT_API_KEY", ""),
            model_registry_path=Path(
                os.getenv("AGENT_MODEL_REGISTRY", str(DEFAULT_MODEL_REGISTRY))
            ),
            max_concurrency=max(1, int(os.getenv("AGENT_MAX_CONCURRENCY", "8"))),
            concurrency_wait_seconds=max(
                0.05, float(os.getenv("AGENT_CONCURRENCY_WAIT_SECONDS", "1.0"))
            ),
            script_timeout_seconds=max(1, int(os.getenv("SCRIPT_TIMEOUT_SECONDS", "20"))),
            vllm_max_tokens=max(128, int(os.getenv("VLLM_MAX_TOKENS", "384"))),
            vllm_request_timeout_seconds=max(
                30, int(os.getenv("VLLM_REQUEST_TIMEOUT_SECONDS", "300"))
            ),
            max_tool_rounds=max(4, int(os.getenv("MAX_TOOL_ROUNDS", "16"))),
            auto_index_rag=_boolean("AUTO_INDEX_RAG", True),
            rag_path=Path(
                os.getenv("RAG_DB_PATH", str(PROJECT_ROOT / "data" / "rag.sqlite3"))
            ),
        )


settings = Settings.from_env()
