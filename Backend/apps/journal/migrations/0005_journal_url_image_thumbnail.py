from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("journal", "0004_journal_knowledge_area_origin"),
    ]

    operations = [
        migrations.AddField(
            model_name="journal",
            name="url_image_thumbnail",
            field=models.URLField(
                blank=True,
                help_text="URL de la miniatura optimizada de la imagen.",
                max_length=500,
                null=True,
            ),
        ),
    ]
