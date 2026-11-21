"""Register OpenAlex as an initial harvestable platform.

The backend already contains an OpenAlex harvester for the ``sources`` API.
This migration supplies the platform record and the catalogue relationships
required by the publication workflow.  The image is intentionally omitted,
so a clean installation leaves OpenAlex as an unvalidated draft whose only
publication blocker is ``url_image``.

The public site and Sources API were checked on 2026-11-21.  The public site
answered HTTP 403 (a reachable, access-restricted resource) and the journal
Sources query answered HTTP 200.
"""

from datetime import date, datetime, timezone

from django.db import migrations


CHECKED_AT = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
OPENALEX_PUBLIC_URL = "https://openalex.org"
OPENALEX_API_URL = "https://api.openalex.org"


def _active_relation(model, *, user_id, defaults=None, **lookup):
    relation = model.objects.filter(**lookup).first()
    values = {
        "deleted_at": None,
        "deleted_by_id": None,
        "delete_explanation": None,
        "is_manual": True,
        "is_derived": False,
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


def seed_openalex_platform(apps, schema_editor):
    User = apps.get_model("account", "User")
    Country = apps.get_model("catalog", "Country")
    Institution = apps.get_model("catalog", "Institution")
    Language = apps.get_model("catalog", "Language")
    MaterialType = apps.get_model("catalog", "MaterialType")
    Platform = apps.get_model("platforms", "Platform")
    ValidSintaxis = apps.get_model("platforms", "ValidSintaxis")
    LinkCheckLog = apps.get_model("platforms", "LinkCheckLog")
    SharedPlatformSupport = apps.get_model(
        "platforms", "SharedPlatformSupport"
    )
    SharedPlatformCountry = apps.get_model(
        "platforms", "SharedPlatformCountry"
    )
    SharedPlatformLanguage = apps.get_model(
        "platforms", "SharedPlatformLanguage"
    )
    SharedPlatformMaterialType = apps.get_model(
        "platforms", "SharedPlatformMaterialType"
    )

    user = User.objects.filter(code=0).first()
    if user is None:
        raise RuntimeError(
            "No se puede registrar OpenAlex: falta el usuario sistema con code=0."
        )

    country = Country.objects.filter(abbreviation__iexact="US").first()
    language = Language.objects.filter(abbreviation__iexact="en").first()
    material_type = MaterialType.objects.filter(name__iexact="revista").first()
    if country is None or language is None or material_type is None:
        raise RuntimeError(
            "No se puede registrar OpenAlex: faltan Estados Unidos, inglés "
            "o el tipo de material Revista."
        )

    institution = Institution.objects.filter(name__iexact="OurResearch").first()
    if institution is None:
        institution = Institution.objects.create(
            name="ourresearch",
            created_by_id=user.pk,
        )
    else:
        Institution.objects.filter(pk=institution.pk).update(
            deleted_at=None,
            deleted_by_id=None,
            delete_explanation=None,
        )

    syntax = ValidSintaxis.objects.filter(name__iexact="OpenAlex API").first()
    syntax_values = {
        "booleans": ["AND", "OR", "NOT"],
        "parenthesis": False,
        "fields": {
            "title": "display_name.search:{}",
            "issn": "issn:{}",
        },
        "deleted_at": None,
        "deleted_by_id": None,
        "delete_explanation": None,
    }
    if syntax is None:
        syntax = ValidSintaxis.objects.create(
            name="openalex api",
            created_by_id=user.pk,
            **syntax_values,
        )
    else:
        ValidSintaxis.objects.filter(pk=syntax.pk).update(**syntax_values)

    platform = Platform.objects.filter(name__iexact="OpenAlex").first()
    created = platform is None
    platform_values = {
        "base_api_url": OPENALEX_API_URL,
        "is_harvestable": True,
        "requires_registration": False,
        "has_access_text": True,
        "valid_sintaxis_id": syntax.pk,
        "deleted_at": None,
        "deleted_by_id": None,
        "delete_explanation": None,
    }
    if created:
        platform = Platform.objects.create(
            name="openalex",
            status="borrador",
            start_period=date(2026, 11, 21),
            url_image=None,
            url_image_thumbnail=None,
            validated_by_id=None,
            validated_at=None,
            created_by_id=user.pk,
            **platform_values,
        )
    else:
        # Preserve any image, validation or lifecycle decision already made by
        # an administrator; this migration only completes harvesting metadata.
        Platform.objects.filter(pk=platform.pk).update(**platform_values)
        platform.refresh_from_db()

    _active_relation(
        SharedPlatformSupport,
        user_id=user.pk,
        platform_id=platform.pk,
        institution_id=institution.pk,
    )
    _active_relation(
        SharedPlatformCountry,
        user_id=user.pk,
        platform_id=platform.pk,
        country_id=country.pk,
    )
    _active_relation(
        SharedPlatformLanguage,
        user_id=user.pk,
        platform_id=platform.pk,
        language_id=language.pk,
    )
    _active_relation(
        SharedPlatformMaterialType,
        user_id=user.pk,
        platform_id=platform.pk,
        material_type_id=material_type.pk,
    )

    # LinkCheckLog is an event history.  Add the verified public URL only when
    # it is not already the current event, avoiding duplicate migration data.
    latest_link = (
        LinkCheckLog.objects.filter(
            platform_id=platform.pk,
            journal_platform_id__isnull=True,
        )
        .order_by("-created_at", "-pk")
        .first()
    )
    if latest_link is None or latest_link.url != OPENALEX_PUBLIC_URL:
        latest_link = LinkCheckLog.objects.create(
            platform_id=platform.pk,
            journal_platform_id=None,
            url=OPENALEX_PUBLIC_URL,
            fail_count=0,
            http_status_code=403,
            is_active=True,
            last_check=CHECKED_AT,
            created_by_id=user.pk,
        )
        LinkCheckLog.objects.filter(pk=latest_link.pk).update(
            created_at=CHECKED_AT,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0005_single_superadmin_handoff"),
        ("catalog", "0008_seed_countries"),
        ("platforms", "0011_linkcheckrequest"),
    ]

    operations = [
        migrations.RunPython(
            seed_openalex_platform,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
