"""Add publisher countries required by the researched DOAJ journals."""

from django.db import migrations


COUNTRIES = (
    ("AM", "armenia"),
    ("BD", "bangladés"),
    ("BG", "bulgaria"),
    ("CR", "costa rica"),
    ("EC", "ecuador"),
    ("ET", "etiopía"),
    ("GA", "gabón"),
    ("HK", "hong kong"),
    ("HN", "honduras"),
    ("HR", "croacia"),
    ("HU", "hungría"),
    ("IQ", "irak"),
    ("IR", "irán"),
    ("JO", "jordania"),
    ("KZ", "kazajistán"),
    ("LK", "sri lanka"),
    ("LT", "lituania"),
    ("LY", "libia"),
    ("ME", "montenegro"),
    ("MK", "macedonia del norte"),
    ("PE", "perú"),
    ("PY", "paraguay"),
    ("RO", "rumania"),
    ("RS", "serbia"),
    ("SI", "eslovenia"),
    ("SK", "eslovaquia"),
    ("SN", "senegal"),
    ("SV", "el salvador"),
    ("TW", "taiwán"),
    ("VE", "venezuela"),
    ("YE", "yemen"),
)


def _emoji_flag(code):
    return "".join(chr(127397 + ord(character)) for character in code)


def seed_doaj_countries(apps, schema_editor):
    User = apps.get_model("account", "User")
    Country = apps.get_model("catalog", "Country")
    user = User.objects.filter(code=0).first()
    if user is None:
        raise RuntimeError(
            "No se pueden completar los países DOAJ: falta el usuario code=0."
        )
    for abbreviation, name in COUNTRIES:
        country = Country.objects.filter(
            abbreviation__iexact=abbreviation
        ).first()
        values = {
            "name": name,
            "emoji_flag": _emoji_flag(abbreviation),
            "deleted_at": None,
            "deleted_by_id": None,
            "delete_explanation": None,
        }
        if country is None:
            Country.objects.create(
                abbreviation=abbreviation,
                created_by_id=user.pk,
                **values,
            )
        else:
            Country.objects.filter(pk=country.pk).update(**values)


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0008_seed_countries"),
    ]

    operations = [
        migrations.RunPython(
            seed_doaj_countries,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
