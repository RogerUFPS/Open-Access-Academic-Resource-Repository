"""Cliente HTTP de AuditCompressor para consultar auditoría archivada.

Solo lectura: el Backend nunca crea snapshots ni ejecuta offload. La API Key
es server-to-server y nunca se incluye en respuestas ni mensajes de error.
"""

import datetime as dt
from dataclasses import dataclass

import httpx
from django.conf import settings


class ArchiveUnavailable(Exception):
    """AuditCompressor no está configurado, no responde o rechazó la consulta."""


class ArchiveIntegrityError(Exception):
    """Un snapshot del rango no superó la verificación de integridad."""


@dataclass(frozen=True)
class ArchivePage:
    count: int
    results: list[dict]


class AuditArchiveClient:
    def __init__(self, transport: httpx.BaseTransport | None = None):
        url = settings.AUDIT_COMPRESSOR_URL.rstrip("/")
        api_key = settings.AUDIT_COMPRESSOR_API_KEY
        if not url or not api_key:
            raise ArchiveUnavailable("AuditCompressor no está configurado.")
        self._http = httpx.Client(
            base_url=url,
            headers={"X-API-Key": api_key},
            timeout=httpx.Timeout(settings.AUDIT_COMPRESSOR_TIMEOUT_SECONDS, connect=5),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self._http.close()

    def history(
        self, source: str, start_date: dt.date, end_date: dt.date, limit: int, offset: int
    ) -> ArchivePage:
        """Registros archivados de ``source`` en [start_date, end_date)."""
        try:
            response = self._http.get(
                f"/sources/{source}/history",
                params={
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "limit": limit,
                    "offset": offset,
                },
            )
        except httpx.HTTPError as exc:
            raise ArchiveUnavailable("No se pudo contactar a AuditCompressor.") from exc
        if response.status_code == 502:
            raise ArchiveIntegrityError("Un snapshot del rango no superó la verificación.")
        if response.status_code != 200:
            raise ArchiveUnavailable(f"AuditCompressor respondió HTTP {response.status_code}.")
        try:
            data = response.json()
            return ArchivePage(count=int(data["count"]), results=list(data["results"]))
        except (ValueError, KeyError, TypeError) as exc:
            raise ArchiveUnavailable("AuditCompressor devolvió una respuesta inválida.") from exc
