"""Contratos HTTP y de respuesta final del agente."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .config import settings
from .model import model


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=3, max_length=4000)
    previous_prompt: str = Field(default="", max_length=4000)
    previous_topic: str = Field(default="", max_length=4000)
    catalog_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    return_analysis: bool = False
    model_name: str = Field(default=model.name, min_length=1, max_length=120)

    @field_validator("model_name")
    @classmethod
    def safe_model_name(cls, value: str) -> str:
        if not all(char.isalnum() or char in "._:/-" for char in value):
            raise ValueError("Nombre de modelo inválido.")
        if not model.accepts(value):
            raise ValueError("El modelo solicitado no está servido por esta réplica.")
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
        if self.estado in {"fuera_de_tema", "error_sistema"} and (
            self.programas_seleccionados or self.busquedas or self.filtros_no_aplicados
        ):
            raise ValueError("Un rechazo o error no puede incluir recomendaciones.")
        if self.estado == "ok" and self.mensaje is not None:
            raise ValueError("mensaje debe ser null cuando estado es ok.")
        if self.estado == "ok" and not self.programas_seleccionados:
            raise ValueError(
                "programas_seleccionados no puede estar vacío cuando estado es ok."
            )
        if self.estado == "ok" and not self.busquedas:
            raise ValueError("busquedas no puede estar vacío cuando estado es ok.")
        if self.estado != "ok" and not self.mensaje:
            raise ValueError("mensaje es obligatorio cuando estado no es ok.")
        return self
