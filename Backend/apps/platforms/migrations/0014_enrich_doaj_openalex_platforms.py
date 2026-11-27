"""Complete the DOAJ and OpenAlex platform records.

The values in this migration were checked against the providers' official
pages on 2026-11-26.  Both platforms cover every discipline and language, so
their catalogue classifications use every active local option.  Images remain
intentionally absent and both records remain unvalidated drafts.

Sources:
* https://doaj.org/about/
* https://doaj.org/docs/widgets/
* https://doaj.org/docs/oai-pmh/
* https://openalex.org/transparency
* https://help.openalex.org/data/sources/
* https://help.openalex.org/api/filtering/
"""

from datetime import date, datetime, timezone

from django.db import migrations


RESEARCHED_AT = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)


def _restore_named(model, name, user_id):
    value = model.objects.filter(name__iexact=name).first()
    if value is None:
        return model.objects.create(name=name, created_by_id=user_id)
    model.objects.filter(pk=value.pk).update(
        deleted_at=None,
        deleted_by_id=None,
        delete_explanation=None,
    )
    return value


def _active_relation(
    model,
    *,
    user_id,
    manual=True,
    derived=False,
    **lookup,
):
    relation = model.objects.filter(**lookup).first()
    values = {
        "deleted_at": None,
        "deleted_by_id": None,
        "delete_explanation": None,
        "is_manual": manual,
        "is_derived": derived,
    }
    if relation is None:
        return model.objects.create(
            **lookup,
            created_by_id=user_id,
            **values,
        )
    model.objects.filter(pk=relation.pk).update(**values)
    return relation


def _retire_support(model, *, platform_id, institution_name, user_id):
    model.objects.filter(
        platform_id=platform_id,
        institution__name__iexact=institution_name,
        deleted_at__isnull=True,
    ).update(
        is_manual=False,
        is_derived=False,
        deleted_at=RESEARCHED_AT,
        deleted_by_id=user_id,
        delete_explanation="Entidad responsable reemplazada por su nombre vigente.",
    )


def _syntax(model, *, name, values, user_id):
    syntax = model.objects.filter(name__iexact=name).first()
    restored = {
        **values,
        "deleted_at": None,
        "deleted_by_id": None,
        "delete_explanation": None,
    }
    if syntax is None:
        return model.objects.create(
            name=name,
            created_by_id=user_id,
            **restored,
        )
    model.objects.filter(pk=syntax.pk).update(**restored)
    return syntax


def enrich_platforms(apps, schema_editor):
    User = apps.get_model("account", "User")
    AcademicProgram = apps.get_model("catalog", "AcademicProgram")
    Country = apps.get_model("catalog", "Country")
    Institution = apps.get_model("catalog", "Institution")
    Language = apps.get_model("catalog", "Language")
    MaterialType = apps.get_model("catalog", "MaterialType")
    ProgramArea = apps.get_model(
        "catalog", "SharedAcademicProgramKnowledgeArea"
    )
    Platform = apps.get_model("platforms", "Platform")
    ValidSintaxis = apps.get_model("platforms", "ValidSintaxis")
    PlatformProgram = apps.get_model(
        "platforms", "SharedPlatformAcademicProgram"
    )
    PlatformArea = apps.get_model(
        "platforms", "SharedPlatformKnowledgeArea"
    )
    PlatformCountry = apps.get_model("platforms", "SharedPlatformCountry")
    PlatformLanguage = apps.get_model("platforms", "SharedPlatformLanguage")
    PlatformMaterial = apps.get_model(
        "platforms", "SharedPlatformMaterialType"
    )
    PlatformSupport = apps.get_model("platforms", "SharedPlatformSupport")

    user = User.objects.filter(code=0).first()
    if user is None:
        raise RuntimeError(
            "No se pueden completar las plataformas: falta el usuario code=0."
        )

    doaj = Platform.objects.filter(name__iexact="DOAJ").first()
    openalex = Platform.objects.filter(name__iexact="OpenAlex").first()
    if doaj is None or openalex is None:
        raise RuntimeError(
            "No se pueden completar las plataformas: faltan DOAJ u OpenAlex."
        )

    denmark = Country.objects.filter(abbreviation__iexact="DK").first()
    united_states = Country.objects.filter(abbreviation__iexact="US").first()
    journal_type = MaterialType.objects.filter(name__iexact="revista").first()
    if denmark is None or united_states is None or journal_type is None:
        raise RuntimeError(
            "No se pueden completar las plataformas: faltan Dinamarca, "
            "Estados Unidos o el tipo Revista."
        )

    doaj_foundation = _restore_named(
        Institution,
        "DOAJ Foundation",
        user.pk,
    )
    openalex_organization = _restore_named(
        Institution,
        "OpenAlex",
        user.pk,
    )

    doaj_syntax = _syntax(
        ValidSintaxis,
        name="DOAJ search",
        user_id=user.pk,
        values={
            "booleans": ["AND", "OR"],
            "parenthesis": False,
            "fields": {
                "title": "bibjson.title:{}",
                "subject": "index.classification:{}",
                "issn": "index.issn.exact:{}",
                "language": "index.language:{}",
            },
        },
    )
    openalex_syntax = _syntax(
        ValidSintaxis,
        name="OpenAlex API",
        user_id=user.pk,
        values={
            "booleans": ["AND", "OR", "NOT"],
            "parenthesis": True,
            "fields": {
                "title": "search={}",
                "subject": "filter=topics.id:{}",
                "issn": "filter=issn:{}",
            },
        },
    )

    Platform.objects.filter(pk=doaj.pk).update(
        status="borrador",
        base_api_url="https://doaj.org/oai",
        is_harvestable=True,
        start_period=date(2003, 1, 1),
        finish_period=None,
        requires_registration=False,
        has_access_text=True,
        valid_sintaxis_id=doaj_syntax.pk,
        validated_by_id=None,
        validated_at=None,
        deleted_at=None,
        deleted_by_id=None,
        delete_explanation=None,
        updated_by_id=user.pk,
        updated_at=RESEARCHED_AT,
    )
    Platform.objects.filter(pk=openalex.pk).update(
        status="borrador",
        base_api_url="https://api.openalex.org",
        is_harvestable=True,
        start_period=date(2022, 1, 3),
        finish_period=None,
        requires_registration=False,
        has_access_text=True,
        valid_sintaxis_id=openalex_syntax.pk,
        validated_by_id=None,
        validated_at=None,
        deleted_at=None,
        deleted_by_id=None,
        delete_explanation=None,
        updated_by_id=user.pk,
        updated_at=RESEARCHED_AT,
    )

    _retire_support(
        PlatformSupport,
        platform_id=openalex.pk,
        institution_name="OurResearch",
        user_id=user.pk,
    )
    for platform, institution, country in (
        (doaj, doaj_foundation, denmark),
        (openalex, openalex_organization, united_states),
    ):
        _active_relation(
            PlatformSupport,
            user_id=user.pk,
            platform_id=platform.pk,
            institution_id=institution.pk,
        )
        _active_relation(
            PlatformCountry,
            user_id=user.pk,
            platform_id=platform.pk,
            country_id=country.pk,
        )
        _active_relation(
            PlatformMaterial,
            user_id=user.pk,
            platform_id=platform.pk,
            material_type_id=journal_type.pk,
        )

        # Both official descriptions are global and multidisciplinary. Link
        # every active local language/program choice as an explicit platform
        # classification. Areas stay derived from those programs, matching
        # the normal platform-classification service.
        for language_id in Language.objects.filter(
            deleted_at__isnull=True
        ).values_list("pk", flat=True):
            _active_relation(
                PlatformLanguage,
                user_id=user.pk,
                platform_id=platform.pk,
                language_id=language_id,
            )
        for program_id in AcademicProgram.objects.filter(
            deleted_at__isnull=True
        ).values_list("pk", flat=True):
            _active_relation(
                PlatformProgram,
                user_id=user.pk,
                platform_id=platform.pk,
                academic_program_id=program_id,
            )
        for area_id in ProgramArea.objects.filter(
            academic_program__deleted_at__isnull=True,
            knowledge_area__deleted_at__isnull=True,
        ).values_list("knowledge_area_id", flat=True).distinct():
            _active_relation(
                PlatformArea,
                user_id=user.pk,
                manual=False,
                derived=True,
                platform_id=platform.pk,
                knowledge_area_id=area_id,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("harvesting", "0013_enrich_doaj_journals"),
        ("platforms", "0013_keep_doaj_platform_draft"),
    ]

    operations = [
        migrations.RunPython(
            enrich_platforms,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
