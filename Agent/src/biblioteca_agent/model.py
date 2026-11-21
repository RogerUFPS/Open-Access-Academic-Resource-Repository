"""Configuración del único modelo servido por la réplica actual."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import settings


class ModelConfigurationError(RuntimeError):
    """La réplica no tiene un endpoint vLLM utilizable."""


@dataclass(frozen=True, slots=True)
class ModelDefinition:
    name: str
    aliases: tuple[str, ...]
    served_model: str
    checkpoint: str
    base_url: str
    api_key: str
    request_options: dict[str, Any]

    @property
    def public_names(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)

    def accepts(self, name: str) -> bool:
        return name in self.public_names

    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.served_model)

    def endpoint(self) -> tuple[str, str]:
        if not self.configured():
            raise ModelConfigurationError(
                "Falta configurar AGENT_VLLM_BASE_URL, AGENT_VLLM_API_KEY o "
                "VLLM_SERVED_MODEL para esta réplica."
            )
        return self.base_url, self.api_key

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "aliases": list(self.aliases),
            "served_model": self.served_model,
            "checkpoint": self.checkpoint,
            "configured": self.configured(),
        }


model = ModelDefinition(
    name=settings.model_name,
    aliases=settings.model_aliases,
    served_model=settings.served_model,
    checkpoint=settings.model_checkpoint,
    base_url=settings.vllm_base_url,
    api_key=settings.vllm_api_key,
    request_options=settings.vllm_request_options,
)
