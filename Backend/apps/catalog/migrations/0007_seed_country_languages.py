from django.conf import settings
from django.db import migrations


# Idiomas oficiales o de uso nacional principal de los países incluidos en
# countries.json. Los códigos siguen ISO 639-1 cuando existe; para filipino,
# bereber y las lenguas de señas se utiliza ISO 639-2/3.
LANGUAGES = (
    ("af", "afrikáans"),
    ("sq", "albanés"),
    ("de", "alemán"),
    ("ar", "árabe"),
    ("ber", "bereber"),
    ("ca", "catalán"),
    ("zh", "chino"),
    ("ko", "coreano"),
    ("cs", "checo"),
    ("da", "danés"),
    ("es", "español"),
    ("eu", "euskera"),
    ("fil", "filipino"),
    ("fi", "finés"),
    ("fr", "francés"),
    ("gl", "gallego"),
    ("el", "griego"),
    ("he", "hebreo"),
    ("hi", "hindi"),
    ("id", "indonesio"),
    ("en", "inglés"),
    ("ga", "irlandés"),
    ("it", "italiano"),
    ("ja", "japonés"),
    ("ms", "malayo"),
    ("mi", "maorí"),
    ("nl", "neerlandés"),
    ("no", "noruego"),
    ("nzs", "lengua de señas neozelandesa"),
    ("sfs", "lengua de señas sudafricana"),
    ("fa", "persa"),
    ("ps", "pastún"),
    ("pl", "polaco"),
    ("pt", "portugués"),
    ("rm", "romanche"),
    ("ru", "ruso"),
    ("nso", "sotho septentrional"),
    ("st", "sotho meridional"),
    ("ss", "suazi"),
    ("sv", "sueco"),
    ("sw", "suajili"),
    ("ta", "tamil"),
    ("th", "tailandés"),
    ("tn", "setsuana"),
    ("ts", "tsonga"),
    ("tr", "turco"),
    ("uk", "ucraniano"),
    ("ur", "urdu"),
    ("ve", "venda"),
    ("vi", "vietnamita"),
    ("xh", "xhosa"),
    ("zu", "zulú"),
)


def seed_country_languages(apps, schema_editor):
    User = apps.get_model("account", "User")
    Language = apps.get_model("catalog", "Language")

    user = User.objects.filter(code=0).first()
    if user is None:
        raise RuntimeError(
            "No se puede cargar el catálogo de idiomas: "
            "falta el usuario sistema con code=0."
        )

    for abbreviation, name in LANGUAGES:
        language, created = Language.objects.get_or_create(
            abbreviation=abbreviation,
            defaults={
                "name": name,
                "created_by_id": user.pk,
            },
        )
        if not created and language.name != name:
            Language.objects.filter(pk=language.pk).update(name=name)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0006_seed_ufps_catalog_data"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(seed_country_languages, migrations.RunPython.noop),
    ]
