import logging
import uuid
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import serializers as drf_serializers
from rest_framework.decorators import (
    action,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework import status, viewsets
from rest_framework.response import Response

from apps.core.viewsets import AuditableViewSet, get_acting_user
from apps.journal.models import Journal
from apps.journal.serializers import JournalSerializer
from . import filters, models, serializers
from . import services

logger = logging.getLogger(__name__)
HARVEST_REQUEST_LEASE = timedelta(minutes=5)


def _claim_harvest_request(idempotency_key, operation):
    """Claim a key, replay its result, or report an in-flight request."""
    token = uuid.uuid4()
    try:
        # The savepoint keeps a uniqueness race from poisoning an enclosing
        # request/test transaction before we read the winning record.
        with transaction.atomic():
            request = models.HarvestRunRequest.objects.create(
                idempotency_key=idempotency_key,
                operation=operation,
                processing_token=token,
            )
        return request, token, "claimed"
    except IntegrityError:
        pass

    with transaction.atomic():
        request = models.HarvestRunRequest.objects.select_for_update().get(
            idempotency_key=idempotency_key,
        )
        if request.operation != operation:
            return request, None, "conflict"
        if request.state == models.HarvestRunRequest.State.COMPLETED:
            return request, None, "completed"
        if request.updated_at > timezone.now() - HARVEST_REQUEST_LEASE:
            return request, None, "processing"
        # Reclaiming is safe: schedule occurrence uniqueness and worker
        # checkpoints independently make run_scheduled_harvests repeatable.
        request.processing_token = token
        request.updated_at = timezone.now()
        request.save(update_fields=["processing_token", "updated_at"])
        return request, token, "reclaimed"


def _release_harvest_request(request_record, token):
    if request_record is not None:
        models.HarvestRunRequest.objects.filter(
            pk=request_record.pk,
            processing_token=token,
            state=models.HarvestRunRequest.State.PROCESSING,
        ).delete()


def _complete_harvest_request(request_record, token, response_status, response_body):
    if request_record is None:
        return True
    return models.HarvestRunRequest.objects.filter(
        pk=request_record.pk,
        processing_token=token,
        state=models.HarvestRunRequest.State.PROCESSING,
    ).update(
        state=models.HarvestRunRequest.State.COMPLETED,
        response_status=response_status,
        response_body=response_body,
        completed_at=timezone.now(),
    ) == 1


@extend_schema_view(
    list=extend_schema(
        summary="Listar programaciones de cosecha",
        tags=["Cosecha - Programaciones"],
    ),
    retrieve=extend_schema(
        summary="Consultar programación de cosecha",
        tags=["Cosecha - Programaciones"],
    ),
    create=extend_schema(
        summary="Crear programación de cosecha",
        tags=["Cosecha - Programaciones"],
    ),
    update=extend_schema(
        summary="Actualizar programación de cosecha",
        tags=["Cosecha - Programaciones"],
    ),
    partial_update=extend_schema(
        summary="Actualizar parcialmente programación de cosecha",
        tags=["Cosecha - Programaciones"],
    ),
    destroy=extend_schema(
        summary="Desactivar programación de cosecha",
        description=(
            "No necesita cuerpo si la programación puede eliminarse "
            "permanentemente. Si tiene registros dependientes, se debe enviar "
            "`delete_explanation` para archivarla."
        ),
        request=inline_serializer(
            name="ScheduleDeleteRequest",
            fields={
                "delete_explanation": drf_serializers.CharField(
                    required=False,
                    allow_blank=False,
                    max_length=500,
                ),
            },
        ),
        tags=["Cosecha - Programaciones"],
    ),
    restore=extend_schema(
        summary="Restaurar programación de cosecha",
        request=None,
        tags=["Cosecha - Programaciones"],
    ),
)
class ScheduleViewSet(AuditableViewSet):
    queryset = models.Schedule.objects.prefetch_related("platforms").all()
    serializer_class = serializers.ScheduleSerializer
    filterset_class = filters.ScheduleFilter
    search_fields = ["platforms__name"]
    ordering_fields = ["created_at", "start_date"]
    ordering = ["-created_at"]

    @extend_schema(
        summary="Procesar cosechas programadas vencidas",
        description=(
            "Evalúa las programaciones vencidas y encola sus cosechas para "
            "procesamiento asíncrono. Idempotency-Key permite que los reintentos "
            "reciban exactamente el resultado original sin repetir el despacho."
        ),
        request=None,
        parameters=[OpenApiParameter(
            name="Idempotency-Key",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.HEADER,
            description="Opcional, hasta 255 caracteres. Debe reutilizarse al reintentar.",
        )],
        responses={
            200: serializers.HarvestSerializer(many=True),
            202: serializers.HarvestSerializer(many=True),
            400: serializers.HarvestQueueErrorSerializer,
            425: serializers.HarvestQueueErrorSerializer,
            503: serializers.HarvestQueueErrorSerializer,
        },
        tags=["Cosecha - Programaciones"],
    )
    @action(detail=False, methods=["post"], url_path="run-due",authentication_classes=[],
    permission_classes=[AllowAny])
    def run_due(self, request):
        idempotency_key = request.headers.get("Idempotency-Key", "").strip() or None
        if idempotency_key and len(idempotency_key) > 255:
            return Response(
                {"detail": "Idempotency-Key no puede superar 255 caracteres."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request_record = token = None
        if idempotency_key:
            request_record, token, claim_state = _claim_harvest_request(
                idempotency_key,
                "run_due",
            )
            if claim_state not in {"claimed", "reclaimed"}:
                if claim_state == "conflict":
                    return Response(
                        {"detail": "Idempotency-Key ya fue usada para otra operación."},
                        status=status.HTTP_409_CONFLICT,
                    )
                if claim_state == "completed":
                    return Response(
                        request_record.response_body,
                        status=request_record.response_status,
                    )
                response = Response(
                    {"detail": "La solicitud con esta Idempotency-Key sigue en proceso."},
                    status=status.HTTP_425_TOO_EARLY,
                )
                response["Retry-After"] = "5"
                return response

        try:
            harvests = services.run_scheduled_harvests()
        except Exception as exc:
            _release_harvest_request(request_record, token)
            logger.exception("No se pudieron encolar las cosechas vencidas.")
            return Response(
                {"detail": f"No se pudieron encolar las cosechas: {exc}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        response_status = status.HTTP_202_ACCEPTED if harvests else status.HTTP_200_OK
        response_body = serializers.HarvestSerializer(harvests, many=True).data
        if not _complete_harvest_request(
            request_record, token, response_status, response_body,
        ):
            logger.error("Se perdió el lease idempotente de run-due: key=%s", idempotency_key)
            return Response(
                {"detail": "No se pudo persistir el resultado idempotente."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(response_body, status=response_status)


class ScheduleEventViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = models.ScheduleEvent.objects.select_related("schedule").prefetch_related(
        "harvests",
    )
    serializer_class = serializers.ScheduleEventSerializer
    filterset_fields = ["schedule", "state"]
    ordering_fields = ["scheduled_for", "started_at", "finished_at"]
    ordering = ["-scheduled_for"]


class HarvestViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = models.Harvest.objects.select_related(
        "platform",
        "schedule",
        "event",
    ).all()
    serializer_class = serializers.HarvestSerializer
    filterset_class = filters.HarvestFilter
    search_fields = ["platform__name"]
    ordering_fields = ["created_at", "started_at", "finished_at", "records_added"]
    ordering = ["-created_at"]

    @extend_schema(
        summary="Listar revistas agregadas por una cosecha",
        description=(
            "Devuelve las revistas nuevas creadas por esta ejecución. "
            "Las revistas actualizadas no se incluyen."
        ),
        request=None,
        responses={200: JournalSerializer(many=True)},
        tags=["Cosecha - Ejecuciones"],
    )
    @action(detail=True, methods=["get"], url_path="journals")
    def journals(self, request, pk=None):
        harvest = self.get_object()
        journals = Journal.all_objects.filter(
            harvest_records__harvest=harvest,
            harvest_records__result=models.HarvestJournal.Result.ADDED,
        ).distinct().order_by("title", "pk")
        page = self.paginate_queryset(journals)
        if page is not None:
            return self.get_paginated_response(
                JournalSerializer(page, many=True).data,
            )
        return Response(JournalSerializer(journals, many=True).data)

    @extend_schema(
        summary="Pausar una cosecha",
        description=(
            "Solicita detener la cosecha después del registro que procesa el "
            "worker. Una cosecha pendiente se pausa inmediatamente."
        ),
        request=None,
        responses={200: serializers.HarvestSerializer, 202: serializers.HarvestSerializer},
        tags=["Cosecha - Ejecuciones"],
    )
    @action(detail=True, methods=["post"], url_path="pause")
    def pause(self, request, pk=None):
        with transaction.atomic():
            harvest = get_object_or_404(
                self.get_queryset().select_for_update(of=("self",)),
                pk=pk,
            )
            if harvest.state == models.Harvest.State.PENDING:
                harvest.state = models.Harvest.State.PAUSED
            elif harvest.state == models.Harvest.State.RUNNING:
                harvest.state = models.Harvest.State.PAUSING
            else:
                return Response(
                    {"detail": f"No se puede pausar una cosecha en estado '{harvest.state}'."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            harvest.updated_by = get_acting_user(request)
            harvest.updated_at = timezone.now()
            harvest.save(update_fields=["state", "updated_by", "updated_at"])

        response_status = (
            status.HTTP_202_ACCEPTED
            if harvest.state == models.Harvest.State.PAUSING
            else status.HTTP_200_OK
        )
        return Response(serializers.HarvestSerializer(harvest).data, status=response_status)

    @extend_schema(
        summary="Reanudar una cosecha pausada",
        description=(
            "Encola la continuación desde el checkpoint guardado en el Harvest. "
            "Idempotency-Key permite repetir con seguridad si se pierde la respuesta."
        ),
        request=None,
        parameters=[OpenApiParameter(
            name="Idempotency-Key",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.HEADER,
            description="Opcional, hasta 255 caracteres. Debe reutilizarse al reintentar.",
        )],
        responses={
            202: serializers.HarvestSerializer,
            400: serializers.HarvestQueueErrorSerializer,
            409: serializers.HarvestQueueErrorSerializer,
            425: serializers.HarvestQueueErrorSerializer,
            503: serializers.HarvestQueueErrorSerializer,
        },
        tags=["Cosecha - Ejecuciones"],
    )
    @action(detail=True, methods=["post"], url_path="resume")
    def resume(self, request, pk=None):
        idempotency_key = request.headers.get("Idempotency-Key", "").strip() or None
        if idempotency_key and len(idempotency_key) > 255:
            return Response(
                {"detail": "Idempotency-Key no puede superar 255 caracteres."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request_record = token = None
        claim_state = "claimed"
        if idempotency_key:
            request_record, token, claim_state = _claim_harvest_request(
                idempotency_key,
                f"resume:{pk}",
            )
            if claim_state == "conflict":
                return Response(
                    {"detail": "Idempotency-Key ya fue usada para otra operación."},
                    status=status.HTTP_409_CONFLICT,
                )
            if claim_state == "completed":
                return Response(
                    request_record.response_body,
                    status=request_record.response_status,
                )
            if claim_state == "processing":
                response = Response(
                    {"detail": "La solicitud con esta Idempotency-Key sigue en proceso."},
                    status=status.HTTP_425_TOO_EARLY,
                )
                response["Retry-After"] = "5"
                return response

        with transaction.atomic():
            harvest = get_object_or_404(
                self.get_queryset().select_for_update(of=("self",)),
                pk=pk,
            )
            if (
                harvest.state == models.Harvest.State.PENDING
                and claim_state == "reclaimed"
            ):
                # The previous process died after changing state but before
                # persisting a response. Re-dispatching the same checkpoint is safe.
                pass
            elif harvest.state != models.Harvest.State.PAUSED:
                _release_harvest_request(request_record, token)
                return Response(
                    {
                        "detail": (
                            "Solo se pueden reanudar cosechas en estado "
                            f"'{models.Harvest.State.PAUSED}'."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            harvest.state = models.Harvest.State.PENDING
            harvest.error_message = None
            harvest.updated_by = get_acting_user(request)
            harvest.updated_at = timezone.now()
            harvest.save(
                update_fields=[
                    "state",
                    "error_message",
                    "updated_by",
                    "updated_at",
                ]
            )

        try:
            harvest = services.dispatch_harvest_to_worker(harvest)
        except Exception as exc:
            logger.exception("Error al reanudar la cosecha #%s", harvest.pk)
            with transaction.atomic():
                harvest = models.Harvest.objects.select_for_update().get(pk=harvest.pk)
                if harvest.state == models.Harvest.State.PENDING:
                    harvest.state = models.Harvest.State.PAUSED
                    harvest.save(update_fields=["state"])
                    _release_harvest_request(request_record, token)
                else:
                    # A worker may have consumed a broker-confirmation-ambiguous
                    # message already. Its state/checkpoint is stronger evidence
                    # than the publisher exception, so report the accepted run.
                    response_body = serializers.HarvestSerializer(harvest).data
                    if _complete_harvest_request(
                        request_record,
                        token,
                        status.HTTP_202_ACCEPTED,
                        response_body,
                    ):
                        return Response(response_body, status=status.HTTP_202_ACCEPTED)
            return Response(
                {
                    "detail": f"Error al encolar la cosecha: {exc}",
                    "harvest": serializers.HarvestSerializer(harvest).data,
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        response_body = serializers.HarvestSerializer(harvest).data
        if not _complete_harvest_request(
            request_record,
            token,
            status.HTTP_202_ACCEPTED,
            response_body,
        ):
            return Response(
                {"detail": "No se pudo persistir el resultado idempotente."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(response_body, status=status.HTTP_202_ACCEPTED)
