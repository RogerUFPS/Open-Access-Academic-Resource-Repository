import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("harvesting", "0008_harvestjournal_quantity_guard"),
    ]

    operations = [
        migrations.CreateModel(
            name="HarvestRunRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("idempotency_key", models.CharField(max_length=255, unique=True)),
                ("operation", models.CharField(default="run_due", max_length=255)),
                ("state", models.CharField(choices=[("processing", "PROCESSING"), ("completed", "COMPLETED")], default="processing", max_length=20)),
                ("processing_token", models.UUIDField(default=uuid.uuid4, editable=False)),
                ("response_status", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("response_body", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
            ],
        ),
    ]
