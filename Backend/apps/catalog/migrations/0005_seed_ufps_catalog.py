from django.conf import settings
from django.db import migrations


AREAS = (
    "004 ciencia de la computación",
    "006.312 minería de datos",
    "070.4 periodismo",
    "300 ciencias sociales",
    "302.2 comunicación",
    "303.6 conflictos sociales",
    "307 comunidades",
    "330 economía",
    "334 cooperativas",
    "340 derecho",
    "342 derecho constitucional y administrativo",
    "361.3 trabajo social",
    "370 educación",
    "370.71 formación de docentes",
    "371.3 métodos de enseñanza y estudio",
    "371.33 medios educativos (tecnología educativa)",
    "372.21 educación preescolar",
    "378 educación superior",
    "382 comercio internacional",
    "500 ciencias naturales y matemáticas",
    "507.1 enseñanza y educación en ciencias naturales",
    "510 matemáticas",
    "510.7 estudio y enseñanza de las matemáticas",
    "519.5 estadística (matemáticas estadísticas)",
    "540 química y ciencias afines",
    "551 geología, hidrología y meteorología",
    "551.48 hidrología",
    "570 ciencias de la vida y biología",
    "572 bioquímica",
    "610 medicina y salud",
    "610.73 enfermería",
    "613.62 salud e higiene ocupacional",
    "615 farmacología y terapéutica",
    "620.11 ingeniería de materiales",
    "621 física aplicada",
    "621.381 electrónica",
    "621.8 ingeniería de máquinas",
    "622 minería y operaciones relacionadas",
    "624 ingeniería civil",
    "624.1 ingeniería estructural y subterránea",
    "627 ingeniería hidráulica",
    "628 ingeniería sanitaria y municipal",
    "630 agricultura y tecnologías relacionadas",
    "636 producción animal",
    "657 contabilidad",
    "658 gerencia general",
    "658.049 gerencia internacional",
    "658.15 gerencia financiera",
    "658.382 salud y seguridad del personal",
    "658.421 emprendimiento y creación de empresas",
    "658.5 gerencia de la producción",
    "658.7 gerencia de materiales y logística",
    "660 ingeniería química y tecnologías relacionadas",
    "660.6 biotecnología",
    "664 tecnología de alimentos",
    "670 manufactura",
    "690 edificios",
    "720 arquitectura",
)


PROGRAMS = (
    ("administración de empresas", ("658 gerencia general",)),
    ("arquitectura", ("720 arquitectura", "690 edificios")),
    ("comercio internacional", ("382 comercio internacional", "330 economía")),
    ("comunicación social", ("302.2 comunicación", "070.4 periodismo")),
    ("contaduría pública", ("657 contabilidad",)),
    ("derecho", ("340 derecho",)),
    ("enfermería", ("610.73 enfermería",)),
    (
        "ingeniería agroindustrial",
        ("664 tecnología de alimentos", "630 agricultura y tecnologías relacionadas"),
    ),
    (
        "ingeniería agronómica",
        ("630 agricultura y tecnologías relacionadas", "500 ciencias naturales y matemáticas"),
    ),
    (
        "ingeniería ambiental",
        ("628 ingeniería sanitaria y municipal", "500 ciencias naturales y matemáticas"),
    ),
    (
        "ingeniería biotecnológica",
        (
            "660.6 biotecnología",
            "500 ciencias naturales y matemáticas",
            "630 agricultura y tecnologías relacionadas",
        ),
    ),
    ("ingeniería civil", ("624 ingeniería civil",)),
    (
        "ingeniería de minas",
        (
            "622 minería y operaciones relacionadas",
            "500 ciencias naturales y matemáticas",
            "551 geología, hidrología y meteorología",
        ),
    ),
    (
        "ingeniería de sistemas",
        ("004 ciencia de la computación", "500 ciencias naturales y matemáticas"),
    ),
    ("ingeniería electromecánica", ("621 física aplicada",)),
    (
        "ingeniería electrónica",
        ("621.381 electrónica", "500 ciencias naturales y matemáticas"),
    ),
    (
        "ingeniería industrial",
        (
            "658.5 gerencia de la producción",
            "658.15 gerencia financiera",
            "620.11 ingeniería de materiales",
        ),
    ),
    ("ingeniería mecánica", ("621.8 ingeniería de máquinas",)),
    (
        "licenciatura en matemáticas",
        ("370.71 formación de docentes", "510 matemáticas"),
    ),
    (
        "licenciatura en ciencias naturales y educación ambiental",
        ("370.71 formación de docentes", "500 ciencias naturales y matemáticas"),
    ),
    (
        "licenciatura en educación infantil",
        ("372.21 educación preescolar", "300 ciencias sociales"),
    ),
    (
        "licenciatura en educación comunitaria",
        ("370.71 formación de docentes", "307 comunidades"),
    ),
    (
        "química industrial",
        ("540 química y ciencias afines", "660 ingeniería química y tecnologías relacionadas"),
    ),
    ("seguridad y salud en el trabajo", ("613.62 salud e higiene ocupacional",)),
    ("trabajo social", ("361.3 trabajo social",)),
    ("zootecnia", ("636 producción animal",)),
    ("administración financiera", ("658.15 gerencia financiera",)),
    ("tecnología en obras civiles", ("624 ingeniería civil",)),
    ("tecnología en construcciones civiles", ("690 edificios",)),
    (
        "tecnología en procesos industriales",
        ("670 manufactura", "658 gerencia general"),
    ),
    (
        "tecnología en regencia de farmacia",
        ("615 farmacología y terapéutica", "572 bioquímica"),
    ),
    (
        "tecnología en analítica de datos",
        (
            "006.312 minería de datos",
            "510 matemáticas",
            "519.5 estadística (matemáticas estadísticas)",
        ),
    ),
    (
        "especialización en educación, emprendimiento y economía solidaria",
        (
            "370 educación",
            "658.421 emprendimiento y creación de empresas",
            "334 cooperativas",
        ),
    ),
    (
        "especialización en educación mediada por las tecnologías de la información y la comunicación",
        (
            "371.33 medios educativos (tecnología educativa)",
            "004 ciencia de la computación",
        ),
    ),
    ("especialización en estructuras", ("624.1 ingeniería estructural y subterránea",)),
    (
        "especialización en gerencia y auditoría de la calidad en salud (en convenio)",
        ("658 gerencia general", "610 medicina y salud"),
    ),
    (
        "especialización en gestión de la seguridad y la salud en el trabajo (en convenio)",
        ("658.382 salud y seguridad del personal", "610 medicina y salud"),
    ),
    ("especialización en práctica pedagógica", ("371.3 métodos de enseñanza y estudio",)),
    (
        "especialización en educación para la atención a la población afectada por el conflicto armado y en problemática fronteriza",
        ("370 educación", "303.6 conflictos sociales"),
    ),
    (
        "especialización en logística y negocios internacionales",
        ("658.7 gerencia de materiales y logística", "330 economía"),
    ),
    ("maestría en ciencias biológicas", ("570 ciencias de la vida y biología",)),
    (
        "maestría en educación matemática",
        ("510.7 estudio y enseñanza de las matemáticas", "371.3 métodos de enseñanza y estudio"),
    ),
    ("maestría en gerencia de empresas", ("658 gerencia general",)),
    ("maestría en práctica pedagógica", ("371.3 métodos de enseñanza y estudio",)),
    (
        "maestría en estudios sociales y educación para la paz",
        ("370 educación", "300 ciencias sociales"),
    ),
    (
        "maestría en ingeniería de recursos hidráulicos",
        ("627 ingeniería hidráulica", "551.48 hidrología"),
    ),
    (
        "maestría en tecnologías de la información y la comunicación (tic) aplicadas a la educación",
        (
            "371.33 medios educativos (tecnología educativa)",
            "004 ciencia de la computación",
        ),
    ),
    (
        "maestría en negocios internacionales",
        ("658.049 gerencia internacional", "382 comercio internacional"),
    ),
    (
        "maestría en derecho público: gobierno, justicia y derechos humanos",
        ("342 derecho constitucional y administrativo",),
    ),
    (
        "maestría en transformación digital",
        ("004 ciencia de la computación", "658 gerencia general"),
    ),
    ("diplomado en docencia y didáctica", ("371.3 métodos de enseñanza y estudio",)),
    (
        "diplomado en didáctica de las ciencias en educación superior",
        ("378 educación superior", "507.1 enseñanza y educación en ciencias naturales"),
    ),
)


def seed_ufps_catalog(apps, schema_editor):
    User = apps.get_model("account", "User")
    KnowledgeArea = apps.get_model("catalog", "KnowledgeArea")
    AcademicProgram = apps.get_model("catalog", "AcademicProgram")
    Relation = apps.get_model("catalog", "SharedAcademicProgramKnowledgeArea")

    user = User.objects.filter(code=0).first()
    if user is None:
        if User.objects.exists():
            raise RuntimeError(
                "No se puede cargar el catálogo UFPS: falta el usuario sistema con code=0."
            )
        user = User(
            code=0,
            full_name="Sistema",
            email="sistema@local.dev",
        )
        user.set_unusable_password()
        user.save()

    areas = {}
    for name in AREAS:
        area, _ = KnowledgeArea.objects.get_or_create(
            name=name,
            defaults={"created_by_id": user.pk},
        )
        areas[name] = area

    for name, area_names in PROGRAMS:
        program, _ = AcademicProgram.objects.get_or_create(
            name=name,
            defaults={"created_by_id": user.pk},
        )
        for area_name in area_names:
            Relation.objects.get_or_create(
                academic_program_id=program.pk,
                knowledge_area_id=areas[area_name].pk,
                defaults={"created_by_id": user.pk},
            )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0004_alter_sharedacademicprogramknowledgearea_options"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(seed_ufps_catalog, migrations.RunPython.noop),
    ]
