"""Regresiones de consultas y contrato del listado administrativo."""

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.account.models import User
from apps.catalog.models import (
    AcademicProgram,
    Country,
    Institution,
    KnowledgeArea,
    Language,
    MaterialType,
)
from apps.platforms import classification, models, serializers, views


class PlatformAdminQueryTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="platform-query@example.org", is_superadmin=True)
        cls.institution = Institution.objects.create(name="Institución rendimiento Platform", created_by=cls.user)
        cls.language = Language.objects.create(
            name="Idioma rendimiento Platform", abbreviation="qp", created_by=cls.user,
        )
        cls.country = Country.objects.create(
            name="País rendimiento Platform", abbreviation="qp", emoji_flag="🏳️", created_by=cls.user,
        )
        cls.area = KnowledgeArea.objects.create(name="Área rendimiento Platform", created_by=cls.user)
        cls.material = MaterialType.objects.create(name="Material rendimiento Platform", created_by=cls.user)
        cls.program = AcademicProgram.objects.create(name="Programa rendimiento Platform", created_by=cls.user)
        related = {
            "institutions": cls.institution, "languages": cls.language, "countries": cls.country,
            "material_types": cls.material, "academic_programs": cls.program,
        }
        cls.platform_ids = []
        for index in range(10):
            platform = models.Platform.objects.create(name=f"Rendimiento Platform {index:02}", created_by=cls.user)
            cls.platform_ids.append(platform.pk)
            for field, through, relation in classification.MANUAL_SECTION_SPECS:
                through.objects.create(
                    platform=platform, **{relation: related[field]},
                    is_manual=True, is_derived=index % 2 == 0, created_by=cls.user,
                )
            models.SharedPlatformKnowledgeArea.objects.create(
                platform=platform, knowledge_area=cls.area, is_manual=False, is_derived=True,
                created_by=cls.user,
            )
            for suffix in ("old", "current"):
                models.LinkCheckLog.objects.create(
                    platform=platform, url=f"https://example.org/platform/{index}/{suffix}", created_by=cls.user,
                )

    def setUp(self):
        self.client.force_authenticate(self.user)

    def test_admin_list_query_count_does_not_grow_per_platform(self):
        with CaptureQueriesContext(connection) as single:
            one = self.client.get("/api/platforms/", {"page_size": 1, "ordering": "name"})
        with CaptureQueriesContext(connection) as multiple:
            ten = self.client.get("/api/platforms/", {"page_size": 10, "ordering": "name"})
        self.assertEqual(one.status_code, 200)
        self.assertEqual(ten.status_code, 200)
        self.assertEqual(len(one.data["results"]), 1)
        self.assertEqual(len(ten.data["results"]), 10)
        self.assertEqual(len(single), len(multiple))
        for row in ten.data["results"]:
            self.assertTrue(row["public_url"].endswith("/current"))
            self.assertEqual(row["knowledge_areas"][0]["id"], self.area.pk)
            self.assertFalse(row["knowledge_areas"][0]["editable"])
            for field, _through, _relation in classification.MANUAL_SECTION_SPECS:
                self.assertEqual(len(row[field]), 1)

    def test_prefetched_list_keeps_representation_and_soft_delete_rules(self):
        first = models.Platform.objects.get(pk=self.platform_ids[0])
        derived = Language.objects.create(name="Idioma derivado rendimiento", abbreviation="qpi", created_by=self.user)
        archived = Language.objects.create(name="Idioma archivado rendimiento", abbreviation="qpd", created_by=self.user)
        models.SharedPlatformLanguage.objects.create(
            platform=first, language=derived, is_manual=False, is_derived=True, created_by=self.user,
        )
        models.SharedPlatformLanguage.objects.create(
            platform=first, language=archived, is_manual=True, created_by=self.user,
            deleted_at=timezone.now(),
        )
        first.deleted_at = timezone.now()
        first.save(update_fields=["deleted_at"])
        response = self.client.get("/api/platforms/", {"page_size": 10, "ordering": "name"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(first.pk, {row["id"] for row in response.data["results"]})
        for row in response.data["results"]:
            expected = serializers.PlatformSerializer(models.Platform.objects.get(pk=row["id"])).data
            self.assertEqual({key: value for key, value in row.items() if key != "item_number"}, expected)

        # Restaurar solo la fila para contrastar también vínculos derivados y eliminados.
        models.Platform.all_objects.filter(pk=first.pk).update(deleted_at=None)
        response = self.client.get("/api/platforms/", {"page_size": 10, "ordering": "name"})
        row = next(row for row in response.data["results"] if row["id"] == first.pk)
        self.assertEqual([item["id"] for item in row["languages"]], [derived.pk, self.language.pk])
        self.assertEqual(row["languages"][0], {
            "id": derived.pk, "name": derived.name,
            "is_manual": False, "is_derived": True, "editable": False,
        })
        self.assertEqual(
            {key: value for key, value in row.items() if key != "item_number"},
            serializers.PlatformSerializer(models.Platform.objects.get(pk=first.pk)).data,
        )

    def test_empty_prefetched_relations_do_not_fall_back_to_per_row_queries(self):
        platform = models.Platform.objects.create(name="Rendimiento Platform vacío", created_by=self.user)
        loaded = views._with_admin_relations(
            views._with_public_link_logs(models.Platform.objects.filter(pk=platform.pk)),
        ).get()
        with self.assertNumQueries(0):
            data = serializers.PlatformSerializer(loaded).data
        self.assertEqual(data["languages"], [])
        self.assertEqual(data["knowledge_areas"], [])
        self.assertIsNone(data["public_url"])

    def test_relational_filter_and_update_keep_their_contract_after_a_list(self):
        platform_id = self.platform_ids[1]
        listed = self.client.get("/api/platforms/", {"language": self.language.pk, "page_size": 10})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.data["total_items"], 10)
        updated = self.client.patch(
            f"/api/platforms/{platform_id}/", {"languages": []}, format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["languages"], [])
        detail = self.client.get(f"/api/platforms/{platform_id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["languages"], [])
        filtered = self.client.get("/api/platforms/", {"language": self.language.pk, "page_size": 10})
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.data["total_items"], 9)
        self.assertNotIn(platform_id, {row["id"] for row in filtered.data["results"]})
