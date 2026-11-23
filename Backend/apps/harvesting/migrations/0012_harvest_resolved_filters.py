from django.db import migrations, models


def preserve_provider_queries(apps, schema_editor):
    Harvest = apps.get_model("harvesting", "Harvest")
    alias = schema_editor.connection.alias
    # Before this migration, selections already contained provider text values.
    # Preserve them verbatim; never derive a new query for an in-flight cursor.
    Harvest.objects.using(alias).update(resolved_filters=models.F("selection_filters"))


class Migration(migrations.Migration):
    dependencies = [
        ("harvesting", "0011_harvestsourcerecord_harvest_filter_key_and_more"),
        ("catalog", "0008_seed_countries"),
    ]
    operations = [
        migrations.AddField(
            model_name="harvest", name="resolved_filters",
            field=models.JSONField(default=dict, blank=True),
        ),
        migrations.RunPython(preserve_provider_queries, migrations.RunPython.noop),
    ]
