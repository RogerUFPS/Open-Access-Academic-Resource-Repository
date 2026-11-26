from django.contrib.sessions.backends.db import SessionStore
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.account.models import SessionTermination, User
from apps.account.security import audit_superadmin


class Command(BaseCommand):
    help = (
        "Reset MFA for the sole active superadmin after support has verified "
        "their identity."
    )

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="Email of the active superadmin.")
        parser.add_argument(
            "--operator",
            help="Name or internal identifier of the support operator performing the reset.",
        )
        parser.add_argument(
            "--reason",
            help="Brief explanation of the verified recovery request.",
        )

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        operator = (options.get("operator") or "").strip()
        reason = (options.get("reason") or "").strip()

        if not operator:
            operator = input("Operador responsable (nombre o identificador): ").strip()
        if not reason:
            reason = input("Explicación y método de verificación de identidad: ").strip()
        if len(operator) < 2:
            raise CommandError("Debes indicar quién realiza la recuperación.")
        if len(reason) < 20:
            raise CommandError("La explicación debe tener al menos 20 caracteres.")
        if len(reason) > 1000:
            raise CommandError("La explicación no puede superar los 1000 caracteres.")

        confirmation = input(
            f"Escribe el correo exacto del superadmin para confirmar ({email}): "
        ).strip().lower()
        if confirmation != email:
            raise CommandError("La confirmación no coincide; no se modificó ninguna cuenta.")

        with transaction.atomic():
            active_admins = list(
                User.all_objects.select_for_update()
                .filter(is_superadmin=True, is_active=True)
                .order_by("pk")
            )
            if len(active_admins) != 1:
                raise CommandError(
                    "El reset requiere exactamente un superadmin activo; "
                    f"se encontraron {len(active_admins)}. No se modificó ninguna cuenta."
                )

            admin = active_admins[0]
            if admin.email.lower() != email:
                raise CommandError(
                    "El correo indicado no corresponde al único superadmin activo."
                )
            if not admin.mfa_enabled and not admin.mfa_secret and not admin.session_key:
                raise CommandError("La MFA de esta cuenta ya está restablecida.")

            old_session_key = admin.session_key
            if old_session_key:
                SessionTermination.record(
                    admin,
                    old_session_key,
                    reason=SessionTermination.Reason.CREDENTIALS_RESET,
                )
                SessionStore(session_key=old_session_key).delete()

            admin.mfa_secret = ""
            admin.mfa_enabled = False
            admin.session_key = None
            admin.save(update_fields=["mfa_secret", "mfa_enabled", "session_key"])
            audit_superadmin(
                "mfa_recovery_operator_reset",
                target=admin,
                details={
                    "operator": operator,
                    "reason": reason,
                    "sessions_revoked": bool(old_session_key),
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"MFA restablecida para {admin.email}. El usuario debe iniciar sesión "
                "y registrar un nuevo autenticador."
            )
        )
