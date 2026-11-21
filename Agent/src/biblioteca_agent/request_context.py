"""Contextos por petición; nunca compartir catálogo o análisis entre usuarios."""
from contextvars import ContextVar

catalog_path = ContextVar("catalog_path", default=None)
analysis = ContextVar("analysis", default=None)
