"""Utilidades compartidas para tests sobre la base real del proyecto.

La base de test se crea con TODAS las migraciones, incluidas las semillas:

- ``catalog/0005``: usuario sistema con ``code=0``;
- ``catalog/0006-0008``: instituciones, idiomas y países;
- ``harvesting/0010``: revistas colombianas de DOAJ con sus ``LinkCheckLog``;
- ``account/0004``: trigger que rechaza UPDATE/DELETE/TRUNCATE en
  ``account_superadminauditevent``.

Además, ``ApplicationPermission`` exige MFA al superadmin. Estas utilidades
permiten escribir tests que no dependan de una base vacía.
"""

import time

from django.db import connection

from apps.core.middleware import SESSION_RENEWED_AT_KEY

SYSTEM_USER_CODE = 0
SUPERADMIN_EVENTS_TABLE = "account_superadminauditevent"
SUPERADMIN_TRUNCATE_TRIGGER = "account_superadmin_audit_no_truncate"


def system_user(**updates):
    """Usuario sistema creado por la migración semilla (``code=0``)."""
    from apps.account.models import User

    user = User.objects.get(code=SYSTEM_USER_CODE)
    if updates:
        for field, value in updates.items():
            setattr(user, field, value)
        user.save(update_fields=list(updates))
    return user


def archive_seeded_journals_and_platforms():
    """Archiva (borrado lógico) las revistas y plataformas ya existentes.

    Las semillas cargan 650 revistas DOAJ y las plataformas DOAJ/OpenAlex.
    Llamarlo al inicio de ``setUpTestData``, antes de crear los datos del
    test, para que listados, conteos de consultas y filtros solo vean esos
    datos. Los registros siguen presentes en los listados de archivados:
    esos tests deben filtrar por sus propios datos. Se revierte con la
    transacción del test.
    """
    from django.utils import timezone

    from apps.journal.models import Journal
    from apps.platforms.models import Platform

    now = timezone.now()
    Journal.objects.update(deleted_at=now)
    Platform.objects.update(deleted_at=now)


def satisfy_superadmin_mfa(client):
    """Marca la sesión del cliente de test como MFA completado.

    Debe llamarse una vez por test (en ``setUp``); la marca se conserva aunque
    luego se use ``force_authenticate`` con otro usuario.
    """
    session = client.session
    session["superadmin_mfa_satisfied"] = True
    # Preparar la renovación fuera de las mediciones SQL de la primera petición.
    session[SESSION_RENEWED_AT_KEY] = int(time.time())
    session.save()


class SuperadminEventsFlushMixin:
    """Permite que ``TransactionTestCase`` vacíe la base entre tests.

    El ``flush`` usa TRUNCATE y el trigger de ``account/0004`` lo rechaza
    ("superadmin audit events are append-only"). Solo durante el vaciado se
    desactiva únicamente el trigger de TRUNCATE de esa tabla. Las protecciones
    de UPDATE/DELETE y las FK permanecen activas.
    """

    def _fixture_teardown(self):
        if connection.vendor != "postgresql":
            return super()._fixture_teardown()

        table = connection.ops.quote_name(SUPERADMIN_EVENTS_TABLE)
        trigger = connection.ops.quote_name(SUPERADMIN_TRUNCATE_TRIGGER)
        with connection.cursor() as cursor:
            cursor.execute(f"ALTER TABLE {table} DISABLE TRIGGER {trigger}")
        try:
            super()._fixture_teardown()
        finally:
            with connection.cursor() as cursor:
                cursor.execute(f"ALTER TABLE {table} ENABLE TRIGGER {trigger}")
