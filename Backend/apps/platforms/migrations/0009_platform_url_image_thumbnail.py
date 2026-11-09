from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "platforms",
            "0008_linkcheckrun_dispatch_idempotency",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="platform",
            name="url_image_thumbnail",
            field=models.URLField(
                blank=True,
                help_text="URL de la miniatura optimizada de la imagen.",
                max_length=500,
                null=True,
            ),
        ),
    ]
