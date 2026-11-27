"""Archivado semestral automático de la auditoría en AuditCompressor.

El Backend decide QUÉ semestres están pendientes (por la fecha del registro más
antiguo) y envía órdenes con fechas. Nunca transporta registros ni borra
auditoría: comprimir, verificar, hacer offload y descartar duplicados lo hace
AuditCompressor. Los registros nuevos que aparecen en semestres ya cerrados
(anomalías) no se tocan: los decide el usuario.
"""

import datetime as dt
import logging
from dataclasses import dataclass
from html import escape
from zoneinfo import ZoneInfo

import httpx
from auditlog.models import LogEntry
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from apps.account.models import SuperadminAuditEvent, User

logger = logging.getLogger(__name__)

# Fuente de AuditCompressor → modelo cuyo registro más antiguo marca lo pendiente.
SOURCES = {
    "auditlog": LogEntry,
    "superadmin_events": SuperadminAuditEvent,
}


class ArchiveServiceError(Exception):
    """AuditCompressor no está disponible: no tiene sentido seguir con la ejecución."""


class SemesterArchiveError(Exception):
    """Un semestre concreto no se pudo procesar; los demás continúan."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def archive_timezone() -> ZoneInfo:
    return ZoneInfo(settings.AUDIT_ARCHIVE_TIMEZONE)


@dataclass(frozen=True)
class Semester:
    """Semestre calendario [start, end) a medianoche en la zona de la institución."""

    start: dt.date
    end: dt.date
    timezone: dt.tzinfo

    @classmethod
    def containing(cls, moment: dt.datetime, timezone: dt.tzinfo) -> "Semester":
        local = moment.astimezone(timezone)
        if local.month <= 6:
            return cls(dt.date(local.year, 1, 1), dt.date(local.year, 7, 1), timezone)
        return cls(dt.date(local.year, 7, 1), dt.date(local.year + 1, 1, 1), timezone)

    def _utc(self, day: dt.date) -> dt.datetime:
        return dt.datetime.combine(day, dt.time.min, tzinfo=self.timezone).astimezone(dt.timezone.utc)

    @property
    def start_utc(self) -> dt.datetime:
        return self._utc(self.start)

    @property
    def end_utc(self) -> dt.datetime:
        return self._utc(self.end)

    @property
    def snapshot_id(self) -> str:
        """Mismo formato que SnapshotRange.snapshot_id de AuditCompressor."""
        return f"{self.start_utc:%Y%m%dT%H%M%SZ}_{self.end_utc:%Y%m%dT%H%M%SZ}"

    @property
    def label(self) -> str:
        return f"{self.start.year}-{'I' if self.start.month == 1 else 'II'}"


class AuditCompressorOrchestrator:
    """Órdenes de archivado hacia AuditCompressor (cliente server-to-server)."""

    # 500: error inesperado en ese semestre (p. ej. la base rechazó el borrado);
    # no debe detener el resto de semestres ni de fuentes.
    _SEMESTER_ERRORS = {409, 422, 500, 502}

    def __init__(self, transport: httpx.BaseTransport | None = None):
        url = settings.AUDIT_COMPRESSOR_URL.rstrip("/")
        api_key = settings.AUDIT_COMPRESSOR_API_KEY
        if not url or not api_key:
            raise ArchiveServiceError("AuditCompressor no está configurado.")
        self._http = httpx.Client(
            base_url=url,
            headers={"X-API-Key": api_key},
            # Archivar u offload de un semestre completo puede tardar.
            timeout=httpx.Timeout(settings.AUDIT_COMPRESSOR_TIMEOUT_SECONDS * 10, connect=5),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self._http.close()

    def _post(self, path: str, **kwargs) -> httpx.Response:
        try:
            return self._http.post(path, **kwargs)
        except httpx.HTTPError as exc:
            raise ArchiveServiceError("No se pudo contactar a AuditCompressor.") from exc

    def _json(self, response: httpx.Response, path: str) -> dict:
        if response.status_code in {200, 201}:
            return response.json()
        if response.status_code in self._SEMESTER_ERRORS:
            try:
                detail = response.json().get("detail", "")
            except ValueError:
                detail = ""
            raise SemesterArchiveError(
                f"{path}: HTTP {response.status_code} {detail}".strip(), response.status_code
            )
        raise ArchiveServiceError(f"{path}: HTTP {response.status_code}")

    def sources(self) -> dict[str, bool]:
        """Fuente → si permite offload (borrar de PostgreSQL tras archivar)."""
        try:
            response = self._http.get("/sources")
        except httpx.HTTPError as exc:
            raise ArchiveServiceError("No se pudo contactar a AuditCompressor.") from exc
        data = self._json(response, "/sources")
        return {item["name"]: item["offload"] for item in data["sources"]}

    def archive(self, source: str, semester: Semester) -> dict:
        path = f"/sources/{source}/snapshots"
        response = self._post(
            path,
            json={"start_date": semester.start.isoformat(), "end_date": semester.end.isoformat()},
        )
        return self._json(response, path)

    def offload(self, source: str, snapshot_id: str) -> dict | None:
        """Respuesta del offload, o None si el snapshot todavía no existe."""
        path = f"/sources/{source}/snapshots/{snapshot_id}/offload"
        response = self._post(path)
        if response.status_code == 404:
            return None
        return self._json(response, path)

    def purge_duplicates(self, source: str, snapshot_id: str) -> dict:
        path = f"/sources/{source}/snapshots/{snapshot_id}/purge-duplicates"
        return self._json(self._post(path), path)


def new_report() -> dict[str, list[dict]]:
    return {"pending": [], "duplicates_deleted": []}


def _archive_only(client, source, semester: Semester) -> None:
    """Fuente sin offload: se comprime una vez y los registros siguen en PostgreSQL."""
    try:
        client.archive(source, semester)
        logger.info("Semestre %s %s comprimido (sin offload)", source, semester.label)
    except SemesterArchiveError as exc:
        if exc.status_code != 409:
            raise
        # 409 por solapamiento: el semestre ya está archivado.


def _process_semester(client, source, model, semester: Semester, report, offload=True) -> None:
    if not offload:
        _archive_only(client, source, semester)
        return
    snapshot_id = semester.snapshot_id
    result = client.offload(source, snapshot_id)
    if result is None:
        client.archive(source, semester)
        client.offload(source, snapshot_id)
        logger.info("Semestre %s %s comprimido y descargado de PostgreSQL", source, semester.label)
        return
    if not result.get("already_offloaded"):
        logger.info("Semestre %s %s descargado de PostgreSQL", source, semester.label)
        return

    # Semestre ya cerrado con registros: anomalía. Los duplicados se descartan
    # (gana la versión archivada); los nuevos esperan la decisión del usuario.
    duplicates = client.purge_duplicates(source, snapshot_id)
    entry = {"source": source, "semester": semester.label, "snapshot_id": snapshot_id}
    if duplicates["deleted_rows"]:
        report["duplicates_deleted"].append({
            **entry,
            "deleted_rows": duplicates["deleted_rows"],
            "sample_ids": duplicates["sample_ids"],
        })
    pending = model.objects.filter(
        timestamp__gte=semester.start_utc, timestamp__lt=semester.end_utc
    ).count()
    if pending:
        report["pending"].append({**entry, "records": pending})
        logger.warning(
            "Anomalía en %s %s: %s registros esperan decisión", source, semester.label, pending
        )


def run_audit_archive(client, now: dt.datetime, report: dict) -> dict[str, list[str]]:
    """Procesa, por fuente y en orden, cada semestre cerrado hace más del margen.

    El cursor avanza siempre al siguiente semestre, salga bien o mal, así que un
    semestre con problemas no bloquea a los demás. Lo encontrado se agrega a
    ``report`` (también si la ejecución se interrumpe).
    """
    timezone = archive_timezone()
    grace = dt.timedelta(days=settings.AUDIT_ARCHIVE_GRACE_DAYS)
    # Solo semestres terminados hace al menos ``grace``: evita anomalías por registros tardíos.
    cutoff = Semester.containing(now - grace, timezone).start_utc
    offload_policy = client.sources()
    summary: dict[str, list[str]] = {}
    for source, model in SOURCES.items():
        processed = summary.setdefault(source, [])
        if source not in offload_policy:
            logger.error("La fuente %s no está configurada en AuditCompressor", source)
            continue
        cursor = None
        while True:
            pending = model.objects.filter(timestamp__lt=cutoff)
            if cursor is not None:
                pending = pending.filter(timestamp__gte=cursor)
            oldest = pending.order_by("timestamp").values_list("timestamp", flat=True).first()
            if oldest is None:
                break
            semester = Semester.containing(oldest, timezone)
            try:
                _process_semester(
                    client, source, model, semester, report, offload_policy[source]
                )
                processed.append(semester.snapshot_id)
            except SemesterArchiveError as exc:
                logger.error("Semestre %s %s no procesado: %s", source, semester.label, exc)
            cursor = semester.end_utc
    return summary


def report_recipients() -> list[str]:
    addresses = []
    for address in User.objects.filter(is_superadmin=True, is_active=True).values_list(
        "email", flat=True
    ):
        try:
            validate_email(address)
        except ValidationError:
            continue
        addresses.append(address)
    return addresses


def report_email_html(report: dict) -> str:
    sections = []
    if report["pending"]:
        items = "".join(
            f"<li><strong>{escape(item['source'])}</strong>, semestre {escape(item['semester'])}: "
            f"{item['records']} registros</li>"
            for item in report["pending"]
        )
        sections.append(
            "<p>Se encontraron auditorías en semestres ya comprimidos, probablemente por "
            "cambios manuales en la base de datos. Decida en el módulo de auditoría si se "
            "comprimen dentro del semestre o se eliminan:</p>"
            f"<ul>{items}</ul>"
        )
    if report["duplicates_deleted"]:
        items = "".join(
            f"<li><strong>{escape(item['source'])}</strong>, semestre {escape(item['semester'])}: "
            f"{item['deleted_rows']} registros. Ids (muestra): "
            f"{escape(', '.join(str(row_id) for row_id in item['sample_ids']))}</li>"
            for item in report["duplicates_deleted"]
        )
        sections.append(
            "<p>Se eliminaron automáticamente registros duplicados que ya estaban "
            "archivados (se conserva la versión archivada):</p>"
            f"<ul>{items}</ul>"
        )
    return "".join(sections)
