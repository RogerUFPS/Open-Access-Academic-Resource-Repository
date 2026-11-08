from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("platforms", "0007_linkcheckbatch_linkchecklog_failure_notified_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="linkcheckrun",
            name="idempotency_key",
            field=models.CharField(blank=True, max_length=255, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="linkcheckrun",
            name="dispatch_task_id",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddConstraint(
            model_name="linkcheckrun",
            constraint=models.UniqueConstraint(
                condition=models.Q(finished_at__isnull=True),
                fields=("mode",),
                name="unique_active_link_check_run_per_mode",
            ),
        ),
    ]
