from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("platforms", "0009_platform_url_image_thumbnail"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="linkchecklog",
            index=models.Index(
                condition=models.Q(journal_platform__isnull=True),
                fields=["platform", "-created_at", "-id"],
                name="link_log_platform_latest",
            ),
        ),
        migrations.AddIndex(
            model_name="linkchecklog",
            index=models.Index(
                condition=models.Q(journal_platform__isnull=False),
                fields=["journal_platform", "-created_at", "-id"],
                name="link_log_journal_latest",
            ),
        ),
    ]
