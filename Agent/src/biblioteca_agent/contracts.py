"""Contratos HTTP y de respuesta final del agente."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .config import settings
from .model_registry import ModelRegistry


model_registry = ModelRegistry(settings.model_registry_path)


class QueryRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=4000)
    model_name: str = Field(default=model_registry.default_model, min_length=1, max_length=120)

    @field_validator("model_name")
    @classmethod
    def safe_model_name(cls, value: str) -> str:
        if not all(char.isalnum() or char in "._:/-" for char in value):
            raise ValueError("Nombre de modelo inválido.")
        if not model_registry.contains(value):
            raise ValueError("El modelo no está declarado en el registro.")
        return value


class ProgramSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int
    nombre: str = Field(min_length=1)
    puntuacion: float = Field(ge=0, le=1)
    razon: str = Field(min_length=1)


class SearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plataforma_id: int | None
    plataforma: str = Field(min_length=1)
    cadena: str = Field(min_length=1)
    justificacion: str = Field(min_length=1)


class UnappliedFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plataforma_id: int | None
    plataforma: str = Field(min_length=1)
    filtro: str = Field(min_length=1)


class RecommendationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    estado: Literal["ok", "fuera_de_tema", "informacion_insuficiente", "error_sistema"]
    mensaje: str | None
    programas_seleccionados: list[ProgramSelection]
    busquedas: list[SearchResult]
    filtros_no_aplicados: list[UnappliedFilter]

    @model_validator(mode="after")
    def validate_message(self) -> "RecommendationResponse":
        if self.estado == "ok" and self.mensaje is not None:
            raise ValueError("mensaje debe ser null cuando estado es ok.")
        if self.estado != "ok" and not self.mensaje:
            raise ValueError("mensaje es obligatorio cuando estado no es ok.")
        return self
