"""Consultas constantes y contrato del listado administrativo de revistas."""

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.account.models import User
from apps.catalog.models import (
    AcademicProgram,
    Country,
    KnowledgeArea,
    Language,
    MaterialType,
)
from apps.journal import models, serializers, views
from apps.platforms.models import LinkCheckLog, Platform


class JournalAdminQueryTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="journal-query@example.org", is_superadmin=True)
        cls.language = Language.objects.create(name="Idioma rendimiento Journal", abbreviation="qj", created_by=cls.user)
        cls.country = Country.objects.create(
            name="País rendimiento Journal", abbreviation="qj", emoji_flag="🏳️", created_by=cls.user,
        )
        cls.area = KnowledgeArea.objects.create(name="Área rendimiento Journal", created_by=cls.user)
        cls.material = MaterialType.objects.create(name="Material rendimiento Journal", created_by=cls.user)
        cls.program = AcademicProgram.objects.create(name="Programa rendimiento Journal", created_by=cls.user)
        cls.license_z = models.License.objects.create(name="Z licencia rendimiento", created_by=cls.user)
        cls.license_a = models.License.objects.create(name="A licencia rendimiento", created_by=cls.user)
        cls.platforms = [
            Platform.objects.create(name="A rendimiento Journal", status=Platform.Status.PUBLICADO, created_by=cls.user),
            Platform.objects.create(name="Z rendimiento Journal", created_by=cls.user),
        ]
        for platform in cls.platforms:
            for suffix in ("old", "current"):
                LinkCheckLog.objects.create(
                    platform=platform, url=f"https://example.org/platform/{platform.pk}/{suffix}", created_by=cls.user,
                )
        related = {
            "languages": cls.language, "countries": cls.country,
            "material_types": cls.material, "academic_programs": cls.program,
        }
        cls.journal_ids = []
        for index in range(10):
            journal = models.Journal.objects.create(
                issn=f"9000-{index:04}", title=f"Rendimiento Journal {index:02}", created_by=cls.user,
            )
            cls.journal_ids.append(journal.pk)
            for config in serializers.JOURNAL_RELATION_CONFIG:
                if config.data_field in {"platforms", "licenses"}:
                    continue
                config.through_model.objects.create(
                    journal=journal, **{config.relation_field: related[config.data_field]}, created_by=cls.user,
                )
            models.SharedJournalKnowledgeArea.objects.create(
                journal=journal, knowledge_area=cls.area, is_manual=True, is_derived=index % 2 == 0,
                created_by=cls.user,
            )
            for license in (cls.license_z, cls.license_a):
                models.SharedJournalLicense.objects.create(journal=journal, license=license, created_by=cls.user)
            for platform in cls.platforms:
                link = models.SharedJournalPlatform.objects.create(journal=journal, platform=platform, created_by=cls.user)
                for suffix in ("old", "current"):
                    LinkCheckLog.objects.create(
                        platform=platform, journal_platform=link,
                        url=f"https://example.org/journal/{journal.pk}/{platform.pk}/{suffix}", created_by=cls.user,
                    )

    def setUp(self):
        self.client.force_authenticate(self.user)

    def test_admin_list_query_count_does_not_grow_per_journal(self):
        with CaptureQueriesContext(connection) as single:
            one = self.client.get("/api/journals/", {"page_size": 1, "ordering": "title"})
        with CaptureQueriesContext(connection) as multiple:
            ten = self.client.get("/api/journals/", {"page_size": 10, "ordering": "title"})
        self.assertEqual(one.status_code, 200)
        self.assertEqual(ten.status_code, 200)
        self.assertEqual(len(one.data["results"]), 1)
        self.assertEqual(len(ten.data["results"]), 10)
        self.assertEqual(len(single), len(multiple))
        for row in ten.data["results"]:
            self.assertEqual(row["languages"], [self.language.pk])
            self.assertEqual(row["licenses"], [self.license_a.pk, self.license_z.pk])
            self.assertEqual(len(row["platforms"]), 2)
            for link in row["platforms"]:
                self.assertTrue(link["public_url"].endswith("/current"))
                self.assertTrue(link["journal_url"].endswith("/current"))
                self.assertIn("relation_id", link)

    def test_prefetched_list_keeps_representation_and_soft_delete_rules(self):
        first = models.Journal.objects.get(pk=self.journal_ids[0])
        deleted_area = KnowledgeArea.objects.create(
            name="Área eliminada rendimiento Journal", created_by=self.user, deleted_at=timezone.now(),
        )
        models.SharedJournalKnowledgeArea.objects.create(
            journal=first, knowledge_area=deleted_area, is_manual=True, created_by=self.user,
        )
        models.SharedJournalLicense.objects.filter(journal=first, license=self.license_z).update(deleted_at=timezone.now())
        models.SharedJournalLanguage.objects.filter(journal=first).update(deleted_at=timezone.now())
        models.Journal.objects.filter(pk=self.journal_ids[-1]).update(deleted_at=timezone.now())
        response = self.client.get("/api/journals/", {"page_size": 10, "ordering": "title"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_items"], 9)
        for row in response.data["results"]:
            expected = serializers.JournalSerializer(models.Journal.objects.get(pk=row["id"])).data
            self.assertEqual({key: value for key, value in row.items() if key != "item_number"}, expected)
        row = next(row for row in response.data["results"] if row["id"] == first.pk)
        self.assertEqual(row["languages"], [])
        self.assertEqual(row["licenses"], [self.license_a.pk])
        self.assertEqual([area["id"] for area in row["knowledge_areas"]], [self.area.pk])

    def test_empty_prefetched_relations_do_not_fall_back_to_per_row_queries(self):
        journal = models.Journal.objects.create(issn="9001-0000", title="Rendimiento Journal vacío", created_by=self.user)
        loaded = views._with_admin_relations(views._with_platform_urls(models.Journal.objects.filter(pk=journal.pk))).get()
        with self.assertNumQueries(0):
            data = serializers.JournalSerializer(loaded).data
        for field in ("languages", "countries", "material_types", "academic_programs", "knowledge_areas", "platforms", "licenses"):
            self.assertEqual(data[field], [])

    def test_relational_filter_and_update_keep_their_contract_after_a_list(self):
        journal_id = self.journal_ids[0]
        listed = self.client.get("/api/journals/", {"platform": self.platforms[0].pk, "page_size": 10})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.data["total_items"], 10)
        updated = self.client.patch(f"/api/journals/{journal_id}/", {"languages": []}, format="json")
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["languages"], [])
        detail = self.client.get(f"/api/journals/{journal_id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["languages"], [])
        filtered = self.client.get("/api/journals/", {"language": self.language.pk, "page_size": 10})
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.data["total_items"], 9)
        self.assertNotIn(journal_id, {row["id"] for row in filtered.data["results"]})
