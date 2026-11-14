from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def copy_existing_keys(apps, schema_editor):
    LinkCheckRun = apps.get_model("platforms", "LinkCheckRun")
    LinkCheckRequest = apps.get_model("platforms", "LinkCheckRequest")
    for run in LinkCheckRun.objects.exclude(idempotency_key__isnull=True).iterator():
        LinkCheckRequest.objects.get_or_create(
            requested_by_id=run.requested_by_id,
            idempotency_key=run.idempotency_key,
            defaults={"mode": run.mode, "run_id": run.pk},
        )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("platforms", "0010_linkchecklog_latest_indexes"),
    ]

    operations = [
        migrations.CreateModel(
            name="LinkCheckRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("idempotency_key", models.CharField(max_length=255)),
                ("mode", models.CharField(choices=[("all", "Total"), ("failed", "Reintentos")], max_length=10)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("requested_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="requests", to="platforms.linkcheckrun")),
            ],
        ),
        migrations.AddConstraint(
            model_name="linkcheckrequest",
            constraint=models.UniqueConstraint(fields=("requested_by", "idempotency_key"), name="unique_link_check_request_key_per_user"),
        ),
        migrations.RunPython(copy_existing_keys, migrations.RunPython.noop),
    ]
