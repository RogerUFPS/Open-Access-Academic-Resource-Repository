"""Tasks del monitor sobre la app Celery y la cola predeterminada existentes."""

import logging

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.utils import (
    InterfaceError,
    OperationalError as DatabaseOperationalError,
    ProgrammingError,
)
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.account.email import EmailDeliveryError

from . import models, services
from .notifications import notify_confirmed_failures

logger = logging.getLogger(__name__)
TASK_RETRIES = 5


@shared_task(
    bind=True, autoretry_for=(Exception,), retry_backoff=True,
    retry_jitter=True, max_retries=TASK_RETRIES,
    name="apps.platforms.dispatch_link_checks",
)
def dispatch_link_checks(self, run_id):
    # La planificación es corta y solo usa DB; nunca realiza HTTP.
    with transaction.atomic():
        run = models.LinkCheckRun.objects.select_for_update().get(pk=run_id)
        logger.info("Inicio de ronda de enlaces: run=%s mode=%s", run.pk, run.mode)
        if not run.planned:
            queryset = (
                services.pending_link_retries() if run.mode == "failed"
                else services.current_link_logs()
            )
            batch_size = settings.LINK_CHECK_BATCH_SIZE
            ids = []
            total = 0
            for log_id in queryset.order_by("pk").values_list("pk", flat=True).iterator(
                chunk_size=batch_size,
            ):
                ids.append(log_id)
                total += 1
                if len(ids) == batch_size:
                    models.LinkCheckBatch.objects.create(run=run, link_ids=ids)
                    ids = []
            if ids:
                models.LinkCheckBatch.objects.create(run=run, link_ids=ids)
            run.planned = True
            run.save(update_fields=["planned"])
            logger.info(
                "Ronda de enlaces planificada: run=%s mode=%s links=%s batches=%s",
                run.pk, run.mode, total, run.batches.count(),
            )
    # Republicar tras un fallo del broker es seguro: IDs de eventos y lotes
    # completados impiden repetir la misma comprobación automática.
    for batch_id in run.batches.filter(completed_at__isnull=True).values_list(
        "pk", flat=True,
    ).iterator():
        check_link_batch.delay(batch_id)
    complete_link_run(run_id)


def complete_link_run(run_id):
    with transaction.atomic():
        run = models.LinkCheckRun.objects.select_for_update().get(pk=run_id)
        if not run.planned or run.batches.filter(completed_at__isnull=True).exists():
            return
        if run.finished_at is None:
            run.finished_at = timezone.now()
            run.save(update_fields=["finished_at"])
        # También se reencola al redeliver el último lote. El envío es idempotente
        # frente a workers simultáneos y consulta estado persistente vigente.
        transaction.on_commit(notify_link_failures.delay)


@shared_task(
    bind=True, autoretry_for=(Exception,), retry_backoff=True,
    retry_jitter=True, max_retries=TASK_RETRIES,
    name="apps.platforms.check_link_batch",
)
def check_link_batch(self, batch_id):
    batch = models.LinkCheckBatch.objects.select_related("run__requested_by").get(pk=batch_id)
    if batch.completed_at is None:
        logs = models.LinkCheckLog.objects.filter(pk__in=batch.link_ids).select_related(
            "platform", "journal_platform__journal",
        ).order_by("pk")
        unexpected = False
        for log in logs:
            try:
                # Revalidar justo antes del request: URLs y contextos pueden
                # haber cambiado desde que el coordinador creó el lote.
                eligible = (
                    services.pending_link_retries() if batch.run.mode == "failed"
                    else services.current_link_logs()
                )
                if not eligible.filter(pk=log.pk).exists():
                    continue
                services.check_link_context(
                    platform=log.platform, journal_platform=log.journal_platform,
                    user=batch.run.requested_by, expected_log_id=log.pk,
                    check_batch_id=batch.pk,
                )
            except (ValidationError, models.Platform.DoesNotExist):
                logger.info("Contexto de enlace ya no elegible: log=%s", log.pk)
            except Exception:
                unexpected = True
                logger.exception("Error comprobando enlace: batch=%s log=%s", batch_id, log.pk)
        if unexpected:
            # Los ya comprobados tienen otro ID vigente y se omiten al repetir.
            raise RuntimeError("El lote contiene comprobaciones pendientes por errores inesperados.")
        models.LinkCheckBatch.objects.filter(pk=batch_id, completed_at__isnull=True).update(
            completed_at=timezone.now(),
        )
    complete_link_run(batch.run_id)


@shared_task(
    bind=True, autoretry_for=(EmailDeliveryError,), retry_backoff=True,
    retry_jitter=True, max_retries=TASK_RETRIES,
    name="apps.platforms.notify_link_failures",
)
def notify_link_failures(self):
    try:
        return notify_confirmed_failures()
    except EmailDeliveryError:
        logger.warning("Falló el envío del resumen de enlaces; las marcas siguen pendientes")
        raise
    except (DatabaseOperationalError, InterfaceError, ProgrammingError) as exc:
        # InvalidCursorName llega envuelto por Django como ProgrammingError.
        # No reintentar otros errores de programación (p. ej. columnas ausentes).
        sqlstate = getattr(exc.__cause__, "sqlstate", None)
        if isinstance(exc, ProgrammingError) and sqlstate != "34000":
            raise
        logger.warning(
            "Falló la base de datos del resumen de enlaces; se solicita reintento: "
            "error_type=%s sqlstate=%s retry=%s",
            type(exc).__name__, sqlstate, self.request.retries,
        )
        raise self.retry(exc=exc, countdown=min(2 ** self.request.retries, 60))
