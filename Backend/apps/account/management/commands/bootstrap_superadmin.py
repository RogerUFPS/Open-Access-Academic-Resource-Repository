import secrets
from html import escape

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone

from apps.account.email import EmailDeliveryError, login_link_html, send_email
from apps.account.models import SuperadminBootstrapState, User
from apps.account.security import audit_superadmin


class Command(BaseCommand):
    help = "Create the initial superadmin from SUPERADMIN_EMAIL, once per database."

    def handle(self, *_args, **_options):
        email = (getattr(settings, "SUPERADMIN_EMAIL", "") or "").strip().lower()
        if connection.vendor != "postgresql":
            raise CommandError("Superadmin bootstrap requires PostgreSQL advisory locks.")

        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(731942118204)")
                state, _ = SuperadminBootstrapState.objects.get_or_create(pk=1)
                if state.completed_at:
                    self.stdout.write("Superadmin bootstrap was already completed; skipped.")
                    return
                if User.all_objects.filter(is_superadmin=True).exists():
                    state.completed_at = timezone.now()
                    state.save(update_fields=["completed_at"])
                    self.stdout.write("A superadmin already exists; bootstrap skipped.")
                    return
                if not email:
                    raise CommandError(
                        "SUPERADMIN_EMAIL is required on the first backend startup."
                    )
                try:
                    validate_email(email)
                except ValidationError as error:
                    raise CommandError(
                        "SUPERADMIN_EMAIL must contain a valid email address."
                    ) from error
                existing = User.all_objects.filter(email__iexact=email).first()
                if existing:
                    raise CommandError(
                        "SUPERADMIN_EMAIL belongs to an existing non-superadmin account; "
                        "refusing to promote it."
                    )
                password = secrets.token_urlsafe(24)
                user = User.objects.create_user(
                    email=email,
                    password=password,
                    is_superadmin=True,
                    force_password_change=True,
                    full_name="Superadmin",
                )
                try:
                    send_email(
                        email,
                        "Credenciales iniciales de superadmin",
                        "<p>Tu contraseña temporal es:</p>"
                        f"<p><strong>{escape(password)}</strong></p>"
                        "<p>Al iniciar sesión deberás cambiarla y configurar MFA.</p>"
                        f"{login_link_html()}",
                    )
                except EmailDeliveryError as error:
                    raise CommandError(str(error)) from error
                audit_superadmin("bootstrap_created", target=user)
                state.completed_at = timezone.now()
                state.save(update_fields=["completed_at"])
        except CommandError:
            raise
        self.stdout.write(self.style.SUCCESS(f"Initial superadmin created for {email}."))
