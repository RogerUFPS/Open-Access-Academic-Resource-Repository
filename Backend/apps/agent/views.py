from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import defaultdict

from django.conf import settings
from django.core.cache import cache
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import (
    AcademicProgram,
    KnowledgeArea,
    Language,
    MaterialType,
    SharedAcademicProgramKnowledgeArea,
)
from apps.core.viewsets import PublicReadCacheMixin
from apps.journal.models import (
    Journal,
    SharedJournalAcademicProgram,
    SharedJournalLanguage,
    SharedJournalMaterialType,
    SharedJournalPlatform,
)
from apps.platforms.models import (
    Platform,
    SharedPlatformLanguage,
)

from .serializers import AgentSnapshotSerializer


SNAPSHOT_CACHE_KEY = "agent:public-snapshot:v1"


def _normalized_value(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(
        character for character in decomposed
        if not unicodedata.combining(character)
    )
    return " ".join(
        "".join(
            character if character.isalnum() else " "
            for character in without_marks
        ).split()
    )


def _group_relation(rows, parent_key: str, related_key: str):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row[parent_key]].append(row[related_key])
    return grouped


def build_public_snapshot():
    """Construye el contrato compacto con consultas por lotes, nunca por fila."""
    areas = list(KnowledgeArea.objects.order_by("id").values("id", "name"))
    programs = list(AcademicProgram.objects.order_by("id").values("id", "name"))
    program_areas = _group_relation(
        SharedAcademicProgramKnowledgeArea.objects.filter(
            academic_program__deleted_at__isnull=True,
            knowledge_area__deleted_at__isnull=True,
        ).order_by("academic_program_id", "knowledge_area_id").values(
            "academic_program_id", "knowledge_area_id"
        ),
        "academic_program_id",
        "knowledge_area_id",
    )

    languages = list(Language.objects.order_by("id").values("id", "abbreviation"))
    language_by_id = {
        item["id"]: item["abbreviation"].casefold()
        for item in languages
    }
    material_types = list(MaterialType.objects.order_by("id").values("id", "name"))
    material_type_by_id = {
        item["id"]: _normalized_value(item["name"])
        for item in material_types
    }

    platform_rows = list(
        Platform.objects.filter(status=Platform.Status.PUBLICADO)
        .select_related("valid_sintaxis")
        .order_by("id")
    )
    platform_ids = [platform.id for platform in platform_rows]
    platform_languages = _group_relation(
        SharedPlatformLanguage.objects.filter(
            platform_id__in=platform_ids,
            language__deleted_at__isnull=True,
        ).order_by("platform_id", "language_id").values(
            "platform_id", "language_id"
        ),
        "platform_id",
        "language_id",
    )

    journal_rows = list(
        Journal.objects.filter(active=True, validated_at__isnull=False)
        .order_by("id")
        .values("id", "title", "publication_date")
    )
    journal_ids = [journal["id"] for journal in journal_rows]
    relation_filter = {"journal_id__in": journal_ids}
    journal_programs = _group_relation(
        SharedJournalAcademicProgram.objects.filter(
            **relation_filter,
            academic_program__deleted_at__isnull=True,
        ).order_by("journal_id", "academic_program_id").values(
            "journal_id", "academic_program_id"
        ),
        "journal_id",
        "academic_program_id",
    )
    journal_platforms = _group_relation(
        SharedJournalPlatform.objects.filter(
            **relation_filter,
            platform_id__in=platform_ids,
        ).order_by("journal_id", "platform_id").values(
            "journal_id", "platform_id"
        ),
        "journal_id",
        "platform_id",
    )
    journal_languages = _group_relation(
        SharedJournalLanguage.objects.filter(
            **relation_filter,
            language__deleted_at__isnull=True,
        ).order_by("journal_id", "language_id").values(
            "journal_id", "language_id"
        ),
        "journal_id",
        "language_id",
    )
    journal_material_types = _group_relation(
        SharedJournalMaterialType.objects.filter(
            **relation_filter,
            material_type__deleted_at__isnull=True,
        ).order_by("journal_id", "material_type_id").values(
            "journal_id", "material_type_id"
        ),
        "journal_id",
        "material_type_id",
    )

    language_values = sorted({value for value in language_by_id.values() if value})
    material_values = sorted({value for value in material_type_by_id.values() if value})
    payload = {
        "schema_version": 1,
        "programas": [
            {
                "id": item["id"],
                "nombre": item["name"],
                "areas": program_areas[item["id"]],
            }
            for item in programs
        ],
        "areas": [
            {"id": item["id"], "nombre": item["name"]}
            for item in areas
        ],
        "filtros": [
            {
                "id": 1,
                "clave": "idioma",
                "nombre": "Idioma",
                "tipo": "lista",
                "valores_validos": language_values,
                "formato": None,
            },
            {
                "id": 2,
                "clave": "tipo_documento",
                "nombre": "Tipo de documento",
                "tipo": "lista",
                "valores_validos": material_values,
                "formato": None,
            },
            {
                "id": 3,
                "clave": "fecha_publicacion",
                "nombre": "Fecha de publicación",
                "tipo": "rango_anios",
                "valores_validos": None,
                "formato": "AAAA-AAAA",
            },
        ],
        "plataformas": [],
        "revistas": [],
    }
    for platform in platform_rows:
        platform_language_values = [
            language_by_id[language_id]
            for language_id in platform_languages[platform.id]
            if language_id in language_by_id
        ]
        syntax = platform.valid_sintaxis
        payload["plataformas"].append({
            "id": platform.id,
            "nombre": platform.name,
            "idiomas": platform_language_values,
            # El modelo actual no registra cuál idioma es predominante.
            "idioma_principal": (
                platform_language_values[0]
                if len(platform_language_values) == 1
                else None
            ),
            "valid_sintaxis": (
                {
                    "booleans": syntax.booleans,
                    "parenthesis": syntax.parenthesis,
                    "fields": syntax.fields,
                }
                if syntax is not None else None
            ),
        })
    for journal in journal_rows:
        journal_id = journal["id"]
        payload["revistas"].append({
            "id": journal_id,
            "titulo": journal["title"],
            "programas": journal_programs[journal_id],
            "plataformas": journal_platforms[journal_id],
            "idiomas": [
                language_by_id[language_id]
                for language_id in journal_languages[journal_id]
                if language_id in language_by_id
            ],
            "tipos_documento": [
                material_type_by_id[material_type_id]
                for material_type_id in journal_material_types[journal_id]
                if material_type_id in material_type_by_id
            ],
            "fecha_publicacion": journal["publication_date"],
        })
    return payload


def cached_public_snapshot():
    cached = cache.get(SNAPSHOT_CACHE_KEY)
    if cached is not None:
        return cached
    payload = build_public_snapshot()
    serialized = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    result = (payload, f'"{hashlib.sha256(serialized).hexdigest()}"')
    cache.set(
        SNAPSHOT_CACHE_KEY,
        result,
        timeout=getattr(settings, "AGENT_SNAPSHOT_CACHE_SECONDS", 300),
    )
    return result


class AgentSnapshotView(PublicReadCacheMixin, APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Obtener el catálogo compacto del agente",
        description=(
            "Devuelve exclusivamente registros públicos y vigentes en un contrato "
            "compacto para el agente. Admite validación condicional mediante ETag."
        ),
        responses={200: AgentSnapshotSerializer, 304: None},
        tags=["Agente - Público"],
    )
    def get(self, request):
        payload, etag = cached_public_snapshot()
        if request.headers.get("If-None-Match") == etag:
            return Response(status=304, headers={"ETag": etag})
        return Response(payload, headers={"ETag": etag})

