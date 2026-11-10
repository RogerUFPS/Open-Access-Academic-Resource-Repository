import logging
from html import escape
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from kombu.exceptions import OperationalError

from apps.account import email
from apps.account.models import User
from apps.account.permissions import has_permission

from . import models, services

logger = logging.getLogger(__name__)
EMAIL_LINK_LIMIT = 10
EMAIL_MARK_BATCH_SIZE = 1000
RECIPIENT_QUERY_CHUNK_SIZE = 200


def failure_recipients():
    addresses = set()
    for user in User.objects.filter(is_active=True).prefetch_related("presets").iterator(
        chunk_size=RECIPIENT_QUERY_CHUNK_SIZE,
    ):
        if not has_permission(user, "platforms", "platforms", "check_link"):
            continue
        address = (user.email or "").strip()
        try:
            validate_email(address)
        except ValidationError:
            continue
        addresses.add(address)
    return sorted(addresses)


def affected_links_url():
    configured = settings.LINK_FAILURE_FRONTEND_URL.strip()
    if not configured:
        return None
    try:
        parts = urlsplit(configured)
    except ValueError:
        logger.error("LINK_FAILURE_FRONTEND_URL no tiene un formato válido")
        return None
    if parts.scheme not in {"http", "https"} or not parts.netloc or parts.username:
        logger.error("LINK_FAILURE_FRONTEND_URL no es una URL absoluta HTTP(S) válida")
        return None
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    params.update(current="true", failure_confirmed="true")
    return urlunsplit(parts._replace(query=urlencode(params)))


def failure_summary_html(logs, total):
    rows = []
    for log in logs:
        relation = log.journal_platform
        kind = "Journal" if relation else "Platform"
        journal = f" — {escape(relation.journal.title)}" if relation else ""
        checked = timezone.localtime(log.last_check).isoformat()
        rows.append(
            f"<li>{escape(log.platform.name)} — {kind}{journal}<br>"
            f"{escape(log.url)}<br>Última comprobación: {escape(checked)}; "
            f"fallos consecutivos: {log.fail_count}</li>"
        )
    remaining = total - len(rows)
    html = f"<p>Se detectaron {total} enlaces con fallos confirmados.</p><ul>{''.join(rows)}</ul>"
    if remaining:
        html += f"<p>{remaining} enlaces adicionales no se muestran en este correo.</p>"
    url = affected_links_url()
    if url:
        html += f'<p><a href="{escape(url, quote=True)}">Revisar enlaces afectados</a></p>'
    else:
        html += (
            "<p>Revisar enlaces afectados: ingrese al módulo administrativo de alertas. "
            "El acceso directo al listado filtrado está pendiente de configuración.</p>"
        )
    return html


def pending_failure_notifications():
    """Incidentes vigentes sin notificar y listos para el resumen compartido."""
    return services.confirmed_link_failures().filter(
        failure_notified_at__isnull=True,
    ).filter(
        Q(check_batch__isnull=True) | Q(check_batch__run__finished_at__isnull=False),
    )


def enqueue_pending_link_failure_notification():
    """Solicita un resumen tras el commit de una operación manual completa.

    El chequeo de candidatos también ocurre después del commit. No se envía
    correo aquí ni se convierte un fallo del broker en un fallo del checker.
    """
    def publish_if_pending():
        if not pending_failure_notifications().exists():
            return
        # Importación diferida: tasks utiliza el notificador de este módulo.
        from .tasks import notify_link_failures

        try:
            notify_link_failures.delay()
        except OperationalError:
            logger.warning(
                "No se pudo encolar el resumen de enlaces; los incidentes siguen pendientes",
            )

    transaction.on_commit(publish_if_pending, robust=True)


def notify_confirmed_failures():
    recipients = failure_recipients()
    if not recipients:
        logger.info("Notificación de enlaces omitida: no hay destinatarios habilitados")
        return 0
    with transaction.atomic():
        # Orden estable de locks compartido con el checker/registro de URL.
        # Releer candidatos después de bloquear evita notificar historia o
        # repetir alertas cuando varios callbacks se ejecutan simultáneamente.
        # Un callback de otra ronda no debe adelantar los resultados parciales
        # de una ronda que todavía tiene workers procesando lotes.
        ready = pending_failure_notifications()
        platform_ids = list(
            ready
            .order_by("platform_id").values_list("platform_id", flat=True).distinct()
        )
        if not platform_ids:
            return 0
        list(models.Platform.objects.filter(pk__in=platform_ids).order_by("pk").select_for_update())
        candidates = ready.filter(platform_id__in=platform_ids)
        ids = list(candidates.order_by("-last_check", "-pk").values_list("pk", flat=True))
        total = len(ids)
        if not total:
            return 0
        preview = list(models.LinkCheckLog.all_objects.filter(pk__in=ids[:EMAIL_LINK_LIMIT]).select_related(
            "platform", "journal_platform__journal",
        ).order_by("-last_check", "-pk")[:EMAIL_LINK_LIMIT])
        # Solo el correo conserva locks durante I/O. Los requests del checker
        # siempre se realizan fuera de transacciones. El rollback mantiene los
        # candidatos pendientes si Resend falla.
        email.send_email(
            settings.DEFAULT_FROM_EMAIL,
            f"Alerta: {total} enlaces con fallos confirmados",
            failure_summary_html(preview, total),
            bcc=recipients,
        )
        # Marcar exactamente el conjunto incluido, incluso los no visibles.
        notified_at = timezone.now()
        for offset in range(0, total, EMAIL_MARK_BATCH_SIZE):
            models.LinkCheckLog.objects.filter(
                pk__in=ids[offset:offset + EMAIL_MARK_BATCH_SIZE],
            ).update(failure_notified_at=notified_at)
        logger.info("Notificación agrupada enviada: links=%s", total)
        return total
