from django.conf import settings
from django.db import migrations


CATALOG_DATA = {
    "institutions": [
        {
            "name": "Universidad Francisco de Paula Santander"
        },
        {
            "name": "Universidad Francisco de Paula Santander Ocaña"
        },
        {
            "name": "Universidad de Pamplona"
        },
        {
            "name": "Universidad Industrial de Santander"
        },
        {
            "name": "Universidad de Santander"
        },
        {
            "name": "Universidad Autónoma de Bucaramanga"
        },
        {
            "name": "Universidad Simón Bolívar"
        },
        {
            "name": "Universidad Libre"
        },
        {
            "name": "Universidad Santo Tomás"
        },
        {
            "name": "Universidad Cooperativa de Colombia"
        },
        {
            "name": "Universidad Antonio Nariño"
        },
        {
            "name": "Fundación Universidad de Bogotá Jorge Tadeo Lozano"
        },
        {
            "name": "Universidad Nacional de Colombia"
        },
        {
            "name": "Universidad Nacional Abierta y a Distancia"
        },
        {
            "name": "Universidad de los Andes"
        },
        {
            "name": "Pontificia Universidad Javeriana"
        },
        {
            "name": "Universidad del Rosario"
        },
        {
            "name": "Universidad Externado de Colombia"
        },
        {
            "name": "Universidad de Antioquia"
        },
        {
            "name": "Universidad del Valle"
        },
        {
            "name": "Universidad del Norte"
        },
        {
            "name": "Universidad EAFIT"
        },
        {
            "name": "Universidad Pontificia Bolivariana"
        },
        {
            "name": "Universidad Distrital Francisco José de Caldas"
        },
        {
            "name": "Universidad Pedagógica y Tecnológica de Colombia"
        },
        {
            "name": "Universidad de Cartagena"
        },
        {
            "name": "Universidad del Magdalena"
        },
        {
            "name": "Universidad de Los Andes (Venezuela)"
        },
        {
            "name": "Universidad Nacional Experimental del Táchira"
        },
        {
            "name": "Universidad Central de Venezuela"
        },
        {
            "name": "Universidad Nacional Autónoma de México"
        },
        {
            "name": "Universidad de Buenos Aires"
        },
        {
            "name": "Universidad de São Paulo"
        },
        {
            "name": "Ministerio de Educación Nacional"
        },
        {
            "name": "Ministerio de Ciencia, Tecnología e Innovación"
        },
        {
            "name": "Instituto Colombiano para la Evaluación de la Educación"
        },
        {
            "name": "Instituto Colombiano de Normas Técnicas y Certificación"
        },
        {
            "name": "Departamento Administrativo Nacional de Estadística"
        },
        {
            "name": "Servicio Nacional de Aprendizaje"
        },
        {
            "name": "Biblioteca Nacional de Colombia"
        },
        {
            "name": "Banco de la República"
        },
        {
            "name": "Instituto Geográfico Agustín Codazzi"
        },
        {
            "name": "Servicio Geológico Colombiano"
        },
        {
            "name": "Instituto de Hidrología, Meteorología y Estudios Ambientales"
        },
        {
            "name": "Organización de las Naciones Unidas para la Educación, la Ciencia y la Cultura"
        },
        {
            "name": "Comisión Económica para América Latina y el Caribe"
        },
        {
            "name": "Organización Mundial de la Salud"
        },
        {
            "name": "Organización de las Naciones Unidas para la Alimentación y la Agricultura"
        },
        {
            "name": "Banco Interamericano de Desarrollo"
        },
        {
            "name": "Banco Mundial"
        },
        {
            "name": "Institute of Electrical and Electronics Engineers"
        },
        {
            "name": "Association for Computing Machinery"
        },
        {
            "name": "International Organization for Standardization"
        },
        {
            "name": "American Society of Civil Engineers"
        },
        {
            "name": "American Society of Mechanical Engineers"
        }
    ],
    "languages": [
        {
            "abbreviation": "es",
            "name": "Español"
        },
        {
            "abbreviation": "en",
            "name": "Inglés"
        },
        {
            "abbreviation": "pt",
            "name": "Portugués"
        },
        {
            "abbreviation": "fr",
            "name": "Francés"
        },
        {
            "abbreviation": "de",
            "name": "Alemán"
        },
        {
            "abbreviation": "it",
            "name": "Italiano"
        },
        {
            "abbreviation": "la",
            "name": "Latín"
        },
        {
            "abbreviation": "ca",
            "name": "Catalán"
        },
        {
            "abbreviation": "nl",
            "name": "Neerlandés"
        },
        {
            "abbreviation": "sv",
            "name": "Sueco"
        },
        {
            "abbreviation": "ru",
            "name": "Ruso"
        },
        {
            "abbreviation": "zh",
            "name": "Chino"
        },
        {
            "abbreviation": "ja",
            "name": "Japonés"
        },
        {
            "abbreviation": "ko",
            "name": "Coreano"
        },
        {
            "abbreviation": "ar",
            "name": "Árabe"
        },
        {
            "abbreviation": "he",
            "name": "Hebreo"
        },
        {
            "abbreviation": "el",
            "name": "Griego"
        },
        {
            "abbreviation": "pl",
            "name": "Polaco"
        },
        {
            "abbreviation": "tr",
            "name": "Turco"
        },
        {
            "abbreviation": "hi",
            "name": "Hindi"
        }
    ],
    "countries": [
        {
            "name": "Colombia",
            "abbreviation": "CO",
            "emoji_flag": "🇨🇴"
        },
        {
            "name": "Venezuela",
            "abbreviation": "VE",
            "emoji_flag": "🇻🇪"
        },
        {
            "name": "Ecuador",
            "abbreviation": "EC",
            "emoji_flag": "🇪🇨"
        },
        {
            "name": "Perú",
            "abbreviation": "PE",
            "emoji_flag": "🇵🇪"
        },
        {
            "name": "Brasil",
            "abbreviation": "BR",
            "emoji_flag": "🇧🇷"
        },
        {
            "name": "Argentina",
            "abbreviation": "AR",
            "emoji_flag": "🇦🇷"
        },
        {
            "name": "Chile",
            "abbreviation": "CL",
            "emoji_flag": "🇨🇱"
        },
        {
            "name": "Bolivia",
            "abbreviation": "BO",
            "emoji_flag": "🇧🇴"
        },
        {
            "name": "Uruguay",
            "abbreviation": "UY",
            "emoji_flag": "🇺🇾"
        },
        {
            "name": "Paraguay",
            "abbreviation": "PY",
            "emoji_flag": "🇵🇾"
        },
        {
            "name": "Panamá",
            "abbreviation": "PA",
            "emoji_flag": "🇵🇦"
        },
        {
            "name": "Costa Rica",
            "abbreviation": "CR",
            "emoji_flag": "🇨🇷"
        },
        {
            "name": "Guatemala",
            "abbreviation": "GT",
            "emoji_flag": "🇬🇹"
        },
        {
            "name": "Honduras",
            "abbreviation": "HN",
            "emoji_flag": "🇭🇳"
        },
        {
            "name": "El Salvador",
            "abbreviation": "SV",
            "emoji_flag": "🇸🇻"
        },
        {
            "name": "Nicaragua",
            "abbreviation": "NI",
            "emoji_flag": "🇳🇮"
        },
        {
            "name": "Cuba",
            "abbreviation": "CU",
            "emoji_flag": "🇨🇺"
        },
        {
            "name": "República Dominicana",
            "abbreviation": "DO",
            "emoji_flag": "🇩🇴"
        },
        {
            "name": "México",
            "abbreviation": "MX",
            "emoji_flag": "🇲🇽"
        },
        {
            "name": "Estados Unidos",
            "abbreviation": "US",
            "emoji_flag": "🇺🇸"
        },
        {
            "name": "Canadá",
            "abbreviation": "CA",
            "emoji_flag": "🇨🇦"
        },
        {
            "name": "España",
            "abbreviation": "ES",
            "emoji_flag": "🇪🇸"
        },
        {
            "name": "Portugal",
            "abbreviation": "PT",
            "emoji_flag": "🇵🇹"
        },
        {
            "name": "Francia",
            "abbreviation": "FR",
            "emoji_flag": "🇫🇷"
        },
        {
            "name": "Alemania",
            "abbreviation": "DE",
            "emoji_flag": "🇩🇪"
        },
        {
            "name": "Italia",
            "abbreviation": "IT",
            "emoji_flag": "🇮🇹"
        },
        {
            "name": "Reino Unido",
            "abbreviation": "GB",
            "emoji_flag": "🇬🇧"
        },
        {
            "name": "Países Bajos",
            "abbreviation": "NL",
            "emoji_flag": "🇳🇱"
        },
        {
            "name": "Bélgica",
            "abbreviation": "BE",
            "emoji_flag": "🇧🇪"
        },
        {
            "name": "Suiza",
            "abbreviation": "CH",
            "emoji_flag": "🇨🇭"
        },
        {
            "name": "Austria",
            "abbreviation": "AT",
            "emoji_flag": "🇦🇹"
        },
        {
            "name": "Suecia",
            "abbreviation": "SE",
            "emoji_flag": "🇸🇪"
        },
        {
            "name": "Irlanda",
            "abbreviation": "IE",
            "emoji_flag": "🇮🇪"
        },
        {
            "name": "Rusia",
            "abbreviation": "RU",
            "emoji_flag": "🇷🇺"
        },
        {
            "name": "China",
            "abbreviation": "CN",
            "emoji_flag": "🇨🇳"
        },
        {
            "name": "Japón",
            "abbreviation": "JP",
            "emoji_flag": "🇯🇵"
        },
        {
            "name": "India",
            "abbreviation": "IN",
            "emoji_flag": "🇮🇳"
        },
        {
            "name": "Corea del Sur",
            "abbreviation": "KR",
            "emoji_flag": "🇰🇷"
        },
        {
            "name": "Australia",
            "abbreviation": "AU",
            "emoji_flag": "🇦🇺"
        },
        {
            "name": "Israel",
            "abbreviation": "IL",
            "emoji_flag": "🇮🇱"
        },
        {
            "name": "Sudáfrica",
            "abbreviation": "ZA",
            "emoji_flag": "🇿🇦"
        }
    ],
    "material-types": [
        {
            "name": "Libro"
        },
        {
            "name": "Libro electrónico"
        },
        {
            "name": "Libro de texto"
        },
        {
            "name": "Obra de referencia"
        },
        {
            "name": "Diccionario"
        },
        {
            "name": "Enciclopedia"
        },
        {
            "name": "Manual"
        },
        {
            "name": "Guía"
        },
        {
            "name": "Folleto"
        },
        {
            "name": "Publicación seriada"
        },
        {
            "name": "Revista"
        },
        {
            "name": "Artículo de revista"
        },
        {
            "name": "Periódico"
        },
        {
            "name": "Trabajo de grado"
        },
        {
            "name": "Trabajo de grado de especialización"
        },
        {
            "name": "Tesis de maestría"
        },
        {
            "name": "Tesis doctoral"
        },
        {
            "name": "Informe de pasantía"
        },
        {
            "name": "Informe técnico"
        },
        {
            "name": "Memorias de evento académico"
        },
        {
            "name": "Ponencia"
        },
        {
            "name": "Norma técnica"
        },
        {
            "name": "Mapa"
        },
        {
            "name": "Plano"
        },
        {
            "name": "Material audiovisual"
        },
        {
            "name": "CD-ROM"
        },
        {
            "name": "DVD"
        },
        {
            "name": "Base de datos"
        },
        {
            "name": "Material cartográfico"
        }
    ],
    "editorials": [
        {
            "name": "McGraw-Hill"
        },
        {
            "name": "McGraw-Hill Interamericana"
        },
        {
            "name": "Pearson Educación"
        },
        {
            "name": "Prentice Hall"
        },
        {
            "name": "Addison-Wesley"
        },
        {
            "name": "Cengage Learning"
        },
        {
            "name": "Thomson Learning"
        },
        {
            "name": "Wiley"
        },
        {
            "name": "Elsevier"
        },
        {
            "name": "Springer"
        },
        {
            "name": "Oxford University Press"
        },
        {
            "name": "Cambridge University Press"
        },
        {
            "name": "Taylor & Francis"
        },
        {
            "name": "CRC Press"
        },
        {
            "name": "Routledge"
        },
        {
            "name": "SAGE Publications"
        },
        {
            "name": "Academic Press"
        },
        {
            "name": "MIT Press"
        },
        {
            "name": "W. H. Freeman"
        },
        {
            "name": "Brooks/Cole"
        },
        {
            "name": "Wadsworth"
        },
        {
            "name": "South-Western"
        },
        {
            "name": "O'Reilly Media"
        },
        {
            "name": "Apress"
        },
        {
            "name": "Packt Publishing"
        },
        {
            "name": "Manning Publications"
        },
        {
            "name": "Morgan Kaufmann"
        },
        {
            "name": "IEEE Press"
        },
        {
            "name": "Harvard Business Review Press"
        },
        {
            "name": "Kogan Page"
        },
        {
            "name": "Schaum"
        },
        {
            "name": "Alfaomega"
        },
        {
            "name": "Alfaomega Colombiana"
        },
        {
            "name": "Limusa"
        },
        {
            "name": "Reverté"
        },
        {
            "name": "Paraninfo"
        },
        {
            "name": "Marcombo"
        },
        {
            "name": "Díaz de Santos"
        },
        {
            "name": "Anaya Multimedia"
        },
        {
            "name": "Ra-Ma"
        },
        {
            "name": "Ediciones Pirámide"
        },
        {
            "name": "ESIC Editorial"
        },
        {
            "name": "Editorial Trillas"
        },
        {
            "name": "Grupo Editorial Patria"
        },
        {
            "name": "Compañía Editorial Continental"
        },
        {
            "name": "Fondo de Cultura Económica"
        },
        {
            "name": "Siglo XXI Editores"
        },
        {
            "name": "Alianza Editorial"
        },
        {
            "name": "Ariel"
        },
        {
            "name": "Planeta"
        },
        {
            "name": "Penguin Random House"
        },
        {
            "name": "Anagrama"
        },
        {
            "name": "Tecnos"
        },
        {
            "name": "Trotta"
        },
        {
            "name": "Gedisa"
        },
        {
            "name": "Paidós"
        },
        {
            "name": "Graó"
        },
        {
            "name": "Narcea"
        },
        {
            "name": "Ediciones Morata"
        },
        {
            "name": "Editorial Síntesis"
        },
        {
            "name": "Santillana"
        },
        {
            "name": "Editorial Norma"
        },
        {
            "name": "Editorial Océano"
        },
        {
            "name": "Ecoe Ediciones"
        },
        {
            "name": "Ediciones de la U"
        },
        {
            "name": "Editorial Temis"
        },
        {
            "name": "Legis"
        },
        {
            "name": "Siglo del Hombre Editores"
        },
        {
            "name": "Cooperativa Editorial Magisterio"
        },
        {
            "name": "Panamericana Editorial"
        },
        {
            "name": "Editorial Kimpres"
        },
        {
            "name": "Editorial Universidad Nacional de Colombia"
        },
        {
            "name": "Editorial Universidad del Rosario"
        },
        {
            "name": "Ediciones Uniandes"
        },
        {
            "name": "Editorial Pontificia Universidad Javeriana"
        },
        {
            "name": "Editorial Universidad de Antioquia"
        },
        {
            "name": "Editorial Universidad del Norte"
        },
        {
            "name": "Fondo Editorial Universidad EAFIT"
        },
        {
            "name": "Ediciones UIS"
        },
        {
            "name": "Editorial Universidad Pontificia Bolivariana"
        },
        {
            "name": "Universidad Externado de Colombia"
        },
        {
            "name": "Editorial Universidad Santo Tomás"
        },
        {
            "name": "Editorial Universidad Cooperativa de Colombia"
        },
        {
            "name": "Editorial Universidad de Pamplona"
        },
        {
            "name": "Editorial Universidad Libre"
        },
        {
            "name": "Instituto Colombiano de Normas Técnicas y Certificación"
        },
        {
            "name": "Universidad Francisco de Paula Santander"
        }
    ]
}

MODEL_NAMES = {
    "institutions": "Institution",
    "languages": "Language",
    "countries": "Country",
    "material-types": "MaterialType",
    "editorials": "Editorial",
}


def seed_catalog_data(apps, schema_editor):
    User = apps.get_model("account", "User")
    user = User.objects.filter(code=0).first()
    if user is None:
        raise RuntimeError(
            "No se puede cargar el cat?logo UFPS: falta el usuario sistema con code=0."
        )

    for collection, records in CATALOG_DATA.items():
        model_name = MODEL_NAMES.get(collection)
        if model_name is None:
            raise RuntimeError(f"Colecci?n de cat?logo no soportada: {collection}")
        model = apps.get_model("catalog", model_name)
        for record in records:
            values = {key: value.strip() if isinstance(value, str) else value for key, value in record.items()}
            if "name" in values:
                values["name"] = values["name"].lower()
            lookup = {"abbreviation": values["abbreviation"]} if "abbreviation" in values else {"name": values["name"]}
            defaults = {key: value for key, value in values.items() if key not in lookup}
            defaults["created_by_id"] = user.pk
            model.objects.get_or_create(**lookup, defaults=defaults)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0005_seed_ufps_catalog"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(seed_catalog_data, migrations.RunPython.noop),
    ]
