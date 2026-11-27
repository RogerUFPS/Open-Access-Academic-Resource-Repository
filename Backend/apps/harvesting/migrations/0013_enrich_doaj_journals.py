"""Complete the 650 harvested DOAJ journals with researched metadata.

The compressed snapshot records the official-page check for every journal and
the matching DOAJ bibliographic evidence. Images remain intentionally absent,
and this migration never publishes or validates a journal.
"""

import gzip
import hashlib
import json
from datetime import date, datetime
from pathlib import Path

from django.db import migrations


DATA_FILE = (
    Path(__file__).resolve().parent.parent
    / "migration_data"
    / "doaj_journal_enrichment_650.json.gz"
)
DATA_SHA256 = (
    "41adc723cc92bc39abead9cfdb17211e46a042365b89e95e5bed50c63ddff357"
)


def _load_data():
    with gzip.open(DATA_FILE, "rb") as stream:
        payload = stream.read()
    if hashlib.sha256(payload).hexdigest() != DATA_SHA256:
        raise RuntimeError("La investigación DOAJ no coincide con su checksum.")
    data = json.loads(payload)
    rows = data.get("journals", [])
    if len(rows) != 650 or len({row["issn"].upper() for row in rows}) != 650:
        raise RuntimeError("La investigación DOAJ no contiene 650 revistas únicas.")
    return data


def _active_relation(model, *, user_id, defaults=None, **lookup):
    relation = model.objects.filter(**lookup).first()
    values = {
        "deleted_at": None,
        "deleted_by_id": None,
        "delete_explanation": None,
    }
    if defaults:
        values.update(defaults)
    if relation is None:
        return model.objects.create(
            **lookup,
            created_by_id=user_id,
            **values,
        )
    model.objects.filter(pk=relation.pk).update(**values)
    return relation


def enrich_doaj_journals(apps, schema_editor):
    User = apps.get_model("account", "User")
    Country = apps.get_model("catalog", "Country")
    MaterialType = apps.get_model("catalog", "MaterialType")
    AcademicProgram = apps.get_model("catalog", "AcademicProgram")
    ProgramArea = apps.get_model(
        "catalog", "SharedAcademicProgramKnowledgeArea"
    )
    Journal = apps.get_model("journal", "Journal")
    JournalCountry = apps.get_model("journal", "SharedJournalCountry")
    JournalMaterialType = apps.get_model(
        "journal", "SharedJournalMaterialType"
    )
    JournalProgram = apps.get_model(
        "journal", "SharedJournalAcademicProgram"
    )
    JournalArea = apps.get_model("journal", "SharedJournalKnowledgeArea")

    data = _load_data()
    researched_at = datetime.fromisoformat(data["generated_at"])
    user = User.objects.filter(code=0).first()
    if user is None:
        raise RuntimeError(
            "No se puede completar DOAJ: falta el usuario sistema code=0."
        )

    material_type = MaterialType.objects.filter(name__iexact="revista").first()
    if material_type is None:
        raise RuntimeError("No existe el tipo de material 'revista'.")

    for row in data["journals"]:
        journal = Journal.objects.filter(issn__iexact=row["issn"]).first()
        if journal is None:
            raise RuntimeError(
                f"No existe la revista cosechada con ISSN {row['issn']}."
            )

        Journal.objects.filter(pk=journal.pk).update(
            publication_date=date.fromisoformat(row["publication_date"]),
            active=False,
            validated_by_id=None,
            validated_at=None,
            updated_by_id=user.pk,
            updated_at=researched_at,
        )

        for country_code in row["countries"]:
            country = Country.objects.filter(
                abbreviation__iexact=country_code
            ).first()
            if country is None:
                raise RuntimeError(
                    f"No existe el país {country_code!r} de {row['issn']}."
                )
            _active_relation(
                JournalCountry,
                user_id=user.pk,
                journal_id=journal.pk,
                country_id=country.pk,
            )

        _active_relation(
            JournalMaterialType,
            user_id=user.pk,
            journal_id=journal.pk,
            material_type_id=material_type.pk,
        )

        for program_name in row["academic_programs"]:
            program = AcademicProgram.objects.filter(
                name__iexact=program_name
            ).first()
            if program is None:
                raise RuntimeError(
                    f"No existe el programa {program_name!r} de {row['issn']}."
                )
            _active_relation(
                JournalProgram,
                user_id=user.pk,
                journal_id=journal.pk,
                academic_program_id=program.pk,
            )
            area_ids = ProgramArea.objects.filter(
                academic_program_id=program.pk,
                deleted_at__isnull=True,
            ).values_list("knowledge_area_id", flat=True)
            for area_id in area_ids:
                area = JournalArea.objects.filter(
                    journal_id=journal.pk,
                    knowledge_area_id=area_id,
                ).first()
                if area is None:
                    JournalArea.objects.create(
                        journal_id=journal.pk,
                        knowledge_area_id=area_id,
                        is_manual=False,
                        is_derived=True,
                        created_by_id=user.pk,
                    )
                else:
                    JournalArea.objects.filter(pk=area.pk).update(
                        is_derived=True,
                        deleted_at=None,
                        deleted_by_id=None,
                        delete_explanation=None,
                    )


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0005_single_superadmin_handoff"),
        ("catalog", "0009_seed_doaj_countries"),
        ("journal", "0005_journal_url_image_thumbnail"),
        ("harvesting", "0012_harvest_resolved_filters"),
    ]

    operations = [
        migrations.RunPython(
            enrich_doaj_journals,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
