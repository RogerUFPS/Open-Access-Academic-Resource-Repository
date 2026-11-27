import datetime as dt
import ipaddress
import math
import re

from auditlog.models import LogEntry
from auditlog.registry import auditlog
from django.contrib.contenttypes.models import ContentType
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, NotFound
from rest_framework.response import Response
from rest_framework.utils.urls import remove_query_param, replace_query_param
from rest_framework.views import APIView

from apps.account.models import SuperadminAuditEvent
from apps.account.session_security import client_ip
from apps.core.pagination import CustomPageNumberPagination
from .archive_client import (
    ArchiveConflict,
    ArchiveIntegrityError,
    ArchiveUnavailable,
    AuditArchiveClient,
)
from .filters import AuditLogFilter
from .models import AuditLog
from .permissions import ArchiveAnomalyPermission
from .serializers import (
    ArchiveAnomalySerializer,
    ArchivedAuditPageSerializer,
    ArchivedAuditQuerySerializer,
    AuditActionSerializer,
    AuditLogDetailSerializer,
    AuditLogListSerializer,
    AuditResourceSerializer,
    ResolveArchiveAnomalySerializer,
    SuperadminEventSerializer,
)


@extend_schema_view(
    list=extend_schema(
        tags=["Auditoría"],
        summary="Listar registros de auditoría",
        description=(
            "Consulta el historial paginado de auditoría de todas las tablas y modelos de la base de datos. "
            "Permite auditar creaciones, actualizaciones y eliminaciones. "
            "Si las modificaciones se realizaron sin un usuario autenticado (sin cuentas creadas previamente), "
            "la llave foránea del usuario se almacena como nula (actor = null). "
            "Los registros son inmutables y de solo lectura."
        ),
    ),
    retrieve=extend_schema(
        tags=["Auditoría"],
        summary="Consultar detalle de un registro de auditoría",
        description=(
            "Obtiene el detalle completo de un registro de auditoría, incluyendo el diccionario JSON de cambios "
            "(`changes`) que refleja los valores anteriores y nuevos para cada campo modificado."
        ),
    ),
)
class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet inmutable de solo lectura para inspeccionar las pistas de auditoría del sistema.
    """

    queryset = AuditLog.objects.select_related("actor", "content_type").all()
    filterset_class = AuditLogFilter
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    search_fields = [
        "object_repr",
        "object_pk",
        "changes_text",
        "actor__full_name",
        "actor__email",
    ]
    ordering_fields = ["timestamp", "action", "id"]
    ordering = ["-timestamp"]
    pagination_class = CustomPageNumberPagination

    def get_serializer_class(self):
        if self.action == "retrieve":
            return AuditLogDetailSerializer
        return AuditLogListSerializer

    @extend_schema(
        tags=["Auditoría"],
        summary="Listar recursos y tablas auditadas",
        description="Retorna el catálogo de tablas y modelos de la base de datos monitoreados por la auditoría.",
        responses={200: AuditResourceSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="resources")
    def resources(self, request):
        data = []
        for model in sorted(auditlog._registry.keys(), key=lambda m: m._meta.model_name):
            try:
                ct = ContentType.objects.get_for_model(model)
                data.append({
                    "resource": model._meta.model_name,
                    "label": str(model._meta.verbose_name),
                    "app": model._meta.app_label,
                    "content_type_id": ct.id,
                })
            except Exception:
                continue
        return Response(data)

    @extend_schema(
        tags=["Auditoría"],
        summary="Listar tipos de acciones de auditoría",
        description="Retorna los tipos de acciones disponibles en el registro (0=Creación, 1=Actualización, 2=Eliminación).",
        responses={200: AuditActionSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="actions")
    def actions(self, request):
        data = [
            {"action": 0, "name": "create", "label": "Creación"},
            {"action": 1, "name": "update", "label": "Actualización"},
            {"action": 2, "name": "delete", "label": "Eliminación"},
            {"action": 3, "name": "access", "label": "Acceso"},
        ]
        return Response(data)


class ArchiveServiceUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "La auditoría archivada no está disponible en este momento."
    default_code = "archive_unavailable"


class ArchiveIntegrityFailed(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "Un archivo del período consultado no superó la verificación de integridad."
    default_code = "archive_integrity_error"


class ArchiveStateConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "La anomalía cambió; vuelva a revisarla."
    default_code = "archive_state_conflict"


def record_archive_event(request, *, action, audited_model, object_pk, object_repr, data):
    """Deja en la auditoría general quién hizo qué sobre el archivo; nunca los registros."""
    address = client_ip(request)
    try:
        ipaddress.ip_address(address)
    except ValueError:
        address = None
    AuditLog.objects.create(
        action=action,
        content_type=ContentType.objects.get_for_model(audited_model),
        object_pk=object_pk,
        object_repr=object_repr,
        actor=request.user,
        actor_email=request.user.email,
        remote_addr=address,
        additional_data=data,
    )


class ArchivedAuditView(APIView):
    """Consulta paginada de auditoría archivada en AuditCompressor.

    Solo lectura. El permiso lo resuelve ApplicationPermission a partir de la
    ruta (audit.<recurso>.view); el superadmin lo tiene siempre. Cada consulta
    autorizada queda registrada como acceso en la auditoría general.
    """

    archive_source: str
    audited_model: type

    def get(self, request):
        query = ArchivedAuditQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        page, page_size = params["page"], params["page_size"]
        try:
            with AuditArchiveClient() as client:
                archived = client.history(
                    self.archive_source,
                    params["start_date"],
                    params["end_date"],
                    limit=page_size,
                    offset=(page - 1) * page_size,
                )
        except ArchiveIntegrityError as exc:
            self._record_access(request, params, "integrity_error")
            raise ArchiveIntegrityFailed() from exc
        except ArchiveUnavailable as exc:
            self._record_access(request, params, "unavailable")
            raise ArchiveServiceUnavailable() from exc
        self._record_access(request, params, "ok", archived.count)

        total_pages = max(1, math.ceil(archived.count / page_size))
        if page > total_pages:
            raise NotFound("Página inválida.")
        return Response(self._page(request, archived, page, page_size, total_pages))

    @staticmethod
    def _page(request, archived, page, page_size, total_pages):
        url = request.build_absolute_uri()
        first_number = (page - 1) * page_size + 1
        previous = None
        if page > 1:
            previous = (
                remove_query_param(url, "page") if page == 2
                else replace_query_param(url, "page", page - 1)
            )
        return {
            "current_page": page,
            "total_pages": total_pages,
            "page_size": page_size,
            "total_items": archived.count,
            "next": replace_query_param(url, "page", page + 1) if page < total_pages else None,
            "previous": previous,
            "results": [
                {"item_number": number, **row}
                for number, row in enumerate(archived.results, start=first_number)
            ],
        }

    def _record_access(self, request, params, outcome, total_items=None):
        start, end = params["start_date"].isoformat(), params["end_date"].isoformat()
        record_archive_event(
            request,
            action=LogEntry.Action.ACCESS,
            audited_model=self.audited_model,
            object_pk=self.archive_source,
            object_repr=f"Consulta de auditoría archivada {start} → {end}",
            data={
                "archive_source": self.archive_source,
                "start_date": start,
                "end_date": end,
                "page": params["page"],
                "page_size": params["page_size"],
                "outcome": outcome,
                "total_items": total_items,
            },
        )


_ARCHIVED_SCHEMA = {
    "tags": ["Auditoría"],
    "parameters": [ArchivedAuditQuerySerializer],
    "responses": {200: ArchivedAuditPageSerializer},
}


@extend_schema(
    summary="Consultar auditoría general archivada",
    description=(
        "Registros de auditoría general ya archivados en AuditCompressor para el período "
        "[start_date, end_date) en días completos de la zona de la institución, combinando "
        "todos los archivos del período. Los registros con late_addition=true llegaron "
        "después como anomalía y se comprimieron por decisión del usuario. Requiere el "
        "permiso audit.archived-logs.view. Cada consulta queda registrada en la auditoría."
    ),
    **_ARCHIVED_SCHEMA,
)
class ArchivedAuditLogView(ArchivedAuditView):
    archive_source = "auditlog"
    audited_model = LogEntry


@extend_schema(
    summary="Consultar eventos de superadmin archivados",
    description=(
        "Eventos de seguridad del superadmin ya archivados en AuditCompressor para el "
        "período [start_date, end_date) en días completos de la zona de la institución. "
        "Requiere el permiso audit.archived-superadmin-events.view. Cada consulta queda "
        "registrada en la auditoría."
    ),
    **_ARCHIVED_SCHEMA,
)
class ArchivedSuperadminEventView(ArchivedAuditView):
    archive_source = "superadmin_events"
    audited_model = SuperadminAuditEvent


# Fuente de AuditCompressor → (consulta de sus registros en la base, serializer).
ANOMALY_SOURCES = {
    "auditlog": (
        lambda: AuditLog.objects.select_related("actor", "content_type"),
        AuditLogListSerializer,
    ),
    "superadmin_events": (lambda: SuperadminAuditEvent.objects.all(), SuperadminEventSerializer),
}
_SNAPSHOT_ID = re.compile(r"^(\d{8}T\d{6}Z)_(\d{8}T\d{6}Z)$")


def snapshot_bounds(snapshot_id):
    """Inicio y fin UTC de un snapshot a partir de su identificador."""
    match = _SNAPSHOT_ID.fullmatch(snapshot_id)
    if not match:
        raise NotFound("Identificador de semestre inválido.")
    return tuple(
        dt.datetime.strptime(part, "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc)
        for part in match.groups()
    )


def anomaly_records(source, snapshot_id):
    """Registros que siguen en PostgreSQL dentro de un semestre (consulta indexada)."""
    if source not in ANOMALY_SOURCES:
        raise NotFound("Fuente de auditoría desconocida.")
    start, end = snapshot_bounds(snapshot_id)
    queryset, _ = ANOMALY_SOURCES[source]
    return queryset().filter(timestamp__gte=start, timestamp__lt=end)


@extend_schema(
    tags=["Auditoría"],
    summary="Listar anomalías de archivado",
    description=(
        "Semestres ya comprimidos que tienen registros en la base de datos, probablemente "
        "insertados de forma manual. Solo cuenta registros: no descarga archivos. Requiere "
        "audit.archive-anomalies.view."
    ),
    responses={200: ArchiveAnomalySerializer(many=True)},
)
class ArchiveAnomalyListView(APIView):
    permission_classes = [ArchiveAnomalyPermission]

    def get(self, request):
        anomalies = []
        try:
            with AuditArchiveClient() as client:
                for source in ANOMALY_SOURCES:
                    for snapshot in client.closed_snapshots(source):
                        records = anomaly_records(source, snapshot["snapshot_id"]).count()
                        if records:
                            anomalies.append({**snapshot, "source": source, "records": records})
        except ArchiveUnavailable as exc:
            raise ArchiveServiceUnavailable() from exc
        return Response(anomalies)


@extend_schema(
    tags=["Auditoría"],
    summary="Ver los registros de una anomalía de archivado",
    description=(
        "Registros de la base de datos dentro de un semestre ya comprimido, para revisarlos "
        "antes de decidir. Paginado. Requiere audit.archive-anomalies.view."
    ),
)
class ArchiveAnomalyRecordsView(APIView):
    permission_classes = [ArchiveAnomalyPermission]

    def get(self, request, source, snapshot_id):
        records = anomaly_records(source, snapshot_id).order_by("timestamp", "pk")
        paginator = CustomPageNumberPagination()
        page = paginator.paginate_queryset(records, request, view=self)
        _, serializer_class = ANOMALY_SOURCES[source]
        return paginator.get_paginated_response(serializer_class(page, many=True).data)


@extend_schema(
    tags=["Auditoría"],
    summary="Resolver una anomalía de archivado",
    description=(
        "compress: comprime los registros nuevos dentro del semestre (los ya archivados se "
        "descartan y se conserva la versión archivada). delete: los elimina sin archivar. "
        "expected_rows debe ser la cantidad revisada; si cambió, no se ejecuta nada (409). "
        "Requiere audit.archive-anomalies.resolve. La decisión queda en la auditoría."
    ),
    request=ResolveArchiveAnomalySerializer,
)
class ResolveArchiveAnomalyView(APIView):
    permission_classes = [ArchiveAnomalyPermission]

    def post(self, request):
        body = ResolveArchiveAnomalySerializer(data=request.data)
        body.is_valid(raise_exception=True)
        params = body.validated_data
        try:
            with AuditArchiveClient() as client:
                result = client.resolve_leftovers(
                    params["source"],
                    params["snapshot_id"],
                    params["action"],
                    params["expected_rows"],
                )
        except ArchiveConflict as exc:
            raise ArchiveStateConflict(str(exc)) from exc
        except ArchiveIntegrityError as exc:
            raise ArchiveIntegrityFailed() from exc
        except ArchiveUnavailable as exc:
            raise ArchiveServiceUnavailable() from exc

        compress = params["action"] == "compress"
        record_archive_event(
            request,
            action=LogEntry.Action.UPDATE if compress else LogEntry.Action.DELETE,
            audited_model=LogEntry if params["source"] == "auditlog" else SuperadminAuditEvent,
            object_pk=params["snapshot_id"],
            object_repr=(
                f"Anomalía de archivado {params['source']} {params['snapshot_id']}: "
                f"{'comprimida' if compress else 'eliminada'}"
            ),
            data={**params, **result},
        )
        return Response(result)
