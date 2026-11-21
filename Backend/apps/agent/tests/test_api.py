from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.account.models import User
from apps.catalog.models import (
    AcademicProgram,
    KnowledgeArea,
    Language,
    MaterialType,
    SharedAcademicProgramKnowledgeArea,
)
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
    ValidSintaxis,
)

from ..views import SNAPSHOT_CACHE_KEY


class AgentPublicSnapshotTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.system = User.objects.get(code=0)
        cls.area = KnowledgeArea.objects.create(
            name="Inteligencia Artificial Agente",
            created_by=cls.system,
        )
        cls.program = AcademicProgram.objects.create(
            name="Ingeniería de Sistemas Agente",
            created_by=cls.system,
        )
        SharedAcademicProgramKnowledgeArea.objects.create(
            academic_program=cls.program,
            knowledge_area=cls.area,
            created_by=cls.system,
        )
        cls.language = Language.objects.get(abbreviation="es")
        cls.material = MaterialType.objects.get(name__iexact="Artículo de revista")
        cls.syntax = ValidSintaxis.objects.create(
            name="Sintaxis Agente",
            booleans=["AND", "OR"],
            parenthesis=True,
            fields={"title": "ti({})", "year": "py({})"},
            created_by=cls.system,
        )
        cls.platform = Platform.objects.create(
            name="Plataforma pública Agente",
            status=Platform.Status.PUBLICADO,
            valid_sintaxis=cls.syntax,
            created_by=cls.system,
        )
        SharedPlatformLanguage.objects.create(
            platform=cls.platform,
            language=cls.language,
            created_by=cls.system,
        )
        cls.draft_platform = Platform.objects.create(
            name="Plataforma borrador Agente",
            status=Platform.Status.BORRADOR,
            created_by=cls.system,
        )
        cls.journal = cls._create_public_journal("Revista pública Agente", "1000-0001")
        cls.unvalidated_journal = Journal.objects.create(
            title="Revista no validada Agente",
            issn="1000-0002",
            active=True,
            publication_date="2024-01-01",
            created_by=cls.system,
        )

    @classmethod
    def _create_public_journal(cls, title, issn):
        journal = Journal.objects.create(
            title=title,
            issn=issn,
            active=True,
            validated_at=timezone.now(),
            publication_date="2024-01-01",
            created_by=cls.system,
        )
        SharedJournalAcademicProgram.objects.create(
            journal=journal,
            academic_program=cls.program,
            created_by=cls.system,
        )
        SharedJournalLanguage.objects.create(
            journal=journal,
            language=cls.language,
            created_by=cls.system,
        )
        SharedJournalMaterialType.objects.create(
            journal=journal,
            material_type=cls.material,
            created_by=cls.system,
        )
        SharedJournalPlatform.objects.create(
            journal=journal,
            platform=cls.platform,
            created_by=cls.system,
        )
        return journal

    def setUp(self):
        cache.delete(SNAPSHOT_CACHE_KEY)

    def test_snapshot_is_anonymous_read_only_and_exposes_only_public_data(self):
        response = self.client.get("/api/agent/v1/snapshot/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["schema_version"], 1)
        self.assertIn("public", response["Cache-Control"])
        self.assertTrue(response["ETag"])
        # Las migraciones también siembran una plataforma pública DOAJ.
        platforms = {item["id"]: item for item in response.data["plataformas"]}
        self.assertIn(self.platform.id, platforms)
        self.assertNotIn(self.draft_platform.id, platforms)
        self.assertEqual(
            [item["id"] for item in response.data["revistas"]],
            [self.journal.id],
        )
        self.assertEqual(
            response.data["revistas"][0]["programas"],
            [self.program.id],
        )
        self.assertEqual(response.data["revistas"][0]["idiomas"], ["es"])
        self.assertEqual(
            response.data["revistas"][0]["tipos_documento"],
            ["articulo de revista"],
        )
        self.assertEqual(platforms[self.platform.id]["idioma_principal"], "es")
        self.assertEqual(
            platforms[self.platform.id]["valid_sintaxis"]["fields"]["title"],
            "ti({})",
        )
        self.assertEqual(
            self.client.post("/api/agent/v1/snapshot/", {}, format="json").status_code,
            405,
        )

    def test_snapshot_supports_etag_without_requerying_database(self):
        initial = self.client.get("/api/agent/v1/snapshot/")
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(
                "/api/agent/v1/snapshot/",
                HTTP_IF_NONE_MATCH=initial["ETag"],
            )
        self.assertEqual(response.status_code, 304)
        self.assertEqual(len(queries), 0)

    def test_snapshot_query_count_is_constant_when_journals_grow(self):
        with CaptureQueriesContext(connection) as single_queries:
            first = self.client.get("/api/agent/v1/snapshot/")
        self.assertEqual(first.status_code, 200)
        self.assertLessEqual(len(single_queries), 12)

        self._create_public_journal("Segunda revista pública Agente", "1000-0003")
        cache.delete(SNAPSHOT_CACHE_KEY)
        with CaptureQueriesContext(connection) as multiple_queries:
            second = self.client.get("/api/agent/v1/snapshot/")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(len(second.data["revistas"]), 2)
        self.assertEqual(len(multiple_queries), len(single_queries))

