"""Registro versionado de modelos remotos y resolución segura de secretos."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ModelConfigurationError(RuntimeError):
    """Indica que un modelo existe pero su endpoint remoto no está configurado."""


@dataclass(frozen=True, slots=True)
class ModelDefinition:
    name: str
    aliases: tuple[str, ...]
    served_model: str
    checkpoint: str
    base_url_env: str
    api_key_env: str
    deployment: dict[str, Any]
    request_options: dict[str, Any]

    @property
    def public_names(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)

    def configured(self) -> bool:
        return bool(os.getenv(self.base_url_env, "").strip()) and bool(
            os.getenv(self.api_key_env, "").strip()
        )

    def endpoint(self) -> tuple[str, str]:
        base_url = os.getenv(self.base_url_env, "").strip().rstrip("/")
        api_key = os.getenv(self.api_key_env, "").strip()
        missing = [
            variable
            for variable, value in (
                (self.base_url_env, base_url),
                (self.api_key_env, api_key),
            )
            if not value
        ]
        if missing:
            raise ModelConfigurationError(
                f"Falta configurar {', '.join(missing)} para el modelo {self.name}."
            )
        return base_url, api_key


class ModelRegistry:
    def __init__(self, path: Path):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"No fue posible leer el registro de modelos: {path}") from exc

        if payload.get("schema_version") != 1:
            raise RuntimeError("Versión no soportada del registro de modelos.")
        definitions: list[ModelDefinition] = []
        names: dict[str, ModelDefinition] = {}
        for raw in payload.get("models", []):
            definition = ModelDefinition(
                name=str(raw["name"]),
                aliases=tuple(str(alias) for alias in raw.get("aliases", [])),
                served_model=str(raw["served_model"]),
                checkpoint=str(raw["checkpoint"]),
                base_url_env=str(raw["base_url_env"]),
                api_key_env=str(raw["api_key_env"]),
                deployment=dict(raw.get("deployment", {})),
                request_options=dict(raw.get("request_options", {})),
            )
            for public_name in definition.public_names:
                if public_name in names:
                    raise RuntimeError(f"Nombre de modelo duplicado: {public_name}")
                names[public_name] = definition
            definitions.append(definition)
        if not definitions:
            raise RuntimeError("El registro debe declarar al menos un modelo.")

        self.path = path
        self.definitions = tuple(definitions)
        self.default_model = str(payload.get("default_model", ""))
        self._by_name = names
        if self.default_model not in self._by_name:
            raise RuntimeError("default_model no existe en el registro de modelos.")

    def get(self, name: str) -> ModelDefinition:
        try:
            return self._by_name[name]
        except KeyError as exc:
            raise ValueError("El modelo no está declarado en el registro.") from exc

    def contains(self, name: str) -> bool:
        return name in self._by_name

    def status(self) -> list[dict[str, Any]]:
        return [
            {
                "name": item.name,
                "aliases": list(item.aliases),
                "served_model": item.served_model,
                "checkpoint": item.checkpoint,
                "configured": item.configured(),
            }
            for item in self.definitions
        ]
