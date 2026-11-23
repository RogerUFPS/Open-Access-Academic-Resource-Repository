"""Ensure that the harvested DOAJ platform is never auto-published."""

from django.db import migrations


def keep_doaj_draft(apps, schema_editor):
    Platform = apps.get_model("platforms", "Platform")
    Platform.objects.filter(name__iexact="DOAJ").update(
        status="borrador",
        validated_by_id=None,
        validated_at=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("harvesting", "0010_seed_colombian_doaj_journals"),
        ("platforms", "0012_seed_openalex_platform"),
    ]

    operations = [
        migrations.RunPython(
            keep_doaj_draft,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
