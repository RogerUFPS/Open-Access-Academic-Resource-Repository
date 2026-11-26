import ipaddress
import math

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
from .archive_client import ArchiveIntegrityError, ArchiveUnavailable, AuditArchiveClient
from .filters import AuditLogFilter
from .models import AuditLog
from .serializers import (
    ArchivedAuditPageSerializer,
    ArchivedAuditQuerySerializer,
    AuditActionSerializer,
    AuditLogDetailSerializer,
    AuditLogListSerializer,
    AuditResourceSerializer,
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
        """Registra quién consultó qué período; nunca los registros devueltos."""
        address = client_ip(request)
        try:
            ipaddress.ip_address(address)
        except ValueError:
            address = None
        start, end = params["start_date"].isoformat(), params["end_date"].isoformat()
        AuditLog.objects.create(
            action=LogEntry.Action.ACCESS,
            content_type=ContentType.objects.get_for_model(self.audited_model),
            object_pk=self.archive_source,
            object_repr=f"Consulta de auditoría archivada {start} → {end}",
            actor=request.user,
            actor_email=request.user.email,
            remote_addr=address,
            additional_data={
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
        "[start_date, end_date) en días UTC, combinando todos los archivos del período. "
        "Requiere el permiso audit.archived-logs.view. Cada consulta queda registrada "
        "como acceso en la auditoría general."
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
        "período [start_date, end_date) en días UTC. Requiere el permiso "
        "audit.archived-superadmin-events.view. Cada consulta queda registrada como "
        "acceso en la auditoría general."
    ),
    **_ARCHIVED_SCHEMA,
)
class ArchivedSuperadminEventView(ArchivedAuditView):
    archive_source = "superadmin_events"
    audited_model = SuperadminAuditEvent
