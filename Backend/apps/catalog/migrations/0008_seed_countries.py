from django.conf import settings
from django.db import migrations


# Adaptación de countries.json al modelo Country. Los campos del archivo que
# no existen en el modelo (capital, región, población y moneda) se omiten.
COUNTRIES = (
    ("AF", "afganistán"),
    ("AL", "albania"),
    ("DZ", "argelia"),
    ("AR", "argentina"),
    ("AU", "australia"),
    ("AT", "austria"),
    ("BE", "bélgica"),
    ("BR", "brasil"),
    ("CA", "canadá"),
    ("CL", "chile"),
    ("CN", "china"),
    ("CO", "colombia"),
    ("CZ", "república checa"),
    ("DK", "dinamarca"),
    ("EG", "egipto"),
    ("FI", "finlandia"),
    ("FR", "francia"),
    ("DE", "alemania"),
    ("GR", "grecia"),
    ("IN", "india"),
    ("ID", "indonesia"),
    ("IE", "irlanda"),
    ("IL", "israel"),
    ("IT", "italia"),
    ("JP", "japón"),
    ("KE", "kenia"),
    ("MY", "malasia"),
    ("MX", "méxico"),
    ("NL", "países bajos"),
    ("NZ", "nueva zelanda"),
    ("NG", "nigeria"),
    ("NO", "noruega"),
    ("PK", "pakistán"),
    ("PH", "filipinas"),
    ("PL", "polonia"),
    ("PT", "portugal"),
    ("RU", "rusia"),
    ("SA", "arabia saudita"),
    ("SG", "singapur"),
    ("ZA", "sudáfrica"),
    ("KR", "corea del sur"),
    ("ES", "españa"),
    ("SE", "suecia"),
    ("CH", "suiza"),
    ("TH", "tailandia"),
    ("TR", "turquía"),
    ("UA", "ucrania"),
    ("AE", "emiratos árabes unidos"),
    ("GB", "reino unido"),
    ("US", "estados unidos"),
    ("VN", "vietnam"),
)


def emoji_flag(country_code):
    return "".join(chr(127397 + ord(character)) for character in country_code)


def seed_countries(apps, schema_editor):
    User = apps.get_model("account", "User")
    Country = apps.get_model("catalog", "Country")

    user = User.objects.filter(code=0).first()
    if user is None:
        raise RuntimeError(
            "No se puede cargar el catálogo de países: "
            "falta el usuario sistema con code=0."
        )

    for abbreviation, name in COUNTRIES:
        country, created = Country.objects.get_or_create(
            abbreviation=abbreviation,
            defaults={
                "name": name,
                "emoji_flag": emoji_flag(abbreviation),
                "created_by_id": user.pk,
            },
        )
        flag = emoji_flag(abbreviation)
        if not created and (country.name != name or country.emoji_flag != flag):
            Country.objects.filter(pk=country.pk).update(
                name=name,
                emoji_flag=flag,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0007_seed_country_languages"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(seed_countries, migrations.RunPython.noop),
    ]
