from datetime import date

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.account.models import User
from apps.catalog.models import (
    AcademicProgram,
    Country,
    Editorial,
    KnowledgeArea,
    Language,
    MaterialType,
)
from apps.platforms.models import Platform

from apps.journal import models


class JournalFilterTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            code=0,
            full_name="Sistema filtros Journal",
            email="journal-filters@test.local",
            is_superadmin=True,
        )
        cls.editorial = Editorial.objects.create(
            name="Editorial filtros",
            created_by=cls.user,
        )
        cls.language = Language.objects.create(
            name="Idioma filtros",
            abbreviation="jf",
            created_by=cls.user,
        )
        cls.country = Country.objects.create(
            name="País filtros",
            abbreviation="jf",
            emoji_flag="🏳️",
            created_by=cls.user,
        )
        cls.knowledge_area = KnowledgeArea.objects.create(
            name="Área filtros",
            created_by=cls.user,
        )
        cls.material_type = MaterialType.objects.create(
            name="Material filtros",
            created_by=cls.user,
        )
        cls.academic_program = AcademicProgram.objects.create(
            name="Programa filtros",
            created_by=cls.user,
        )
        cls.license = models.License.objects.create(
            name="Licencia filtros",
            created_by=cls.user,
        )
        cls.published_platform = Platform.objects.create(
            name="Plataforma publicada filtros",
            status=Platform.Status.PUBLICADO,
            created_by=cls.user,
        )
        cls.draft_platform = Platform.objects.create(
            name="Plataforma borrador filtros",
            status=Platform.Status.BORRADOR,
            created_by=cls.user,
        )

        cls.public_journal = models.Journal.objects.create(
            issn="1111-1111",
            title="Alpha Journal",
            editorial=cls.editorial,
            has_apc=False,
            active=True,
            publication_date=date(2020, 1, 15),
            validated_by=cls.user,
            validated_at=timezone.now(),
            created_by=cls.user,
        )
        cls.inactive_journal = models.Journal.objects.create(
            issn="2222-2222",
            title="Beta Journal",
            editorial=cls.editorial,
            has_apc=True,
            active=False,
            publication_date=date(2024, 6, 1),
            created_by=cls.user,
        )

        relation_specs = (
            (models.SharedJournalLanguage, "language", cls.language),
            (models.SharedJournalCountry, "country", cls.country),
            (models.SharedJournalKnowledgeArea, "knowledge_area", cls.knowledge_area),
            (models.SharedJournalMaterialType, "material_type", cls.material_type),
            (
                models.SharedJournalAcademicProgram,
                "academic_program",
                cls.academic_program,
            ),
        )
        for through_model, field_name, related in relation_specs:
            origin = (
                {"is_derived": True}
                if through_model is models.SharedJournalKnowledgeArea
                else {}
            )
            through_model.objects.create(
                journal=cls.public_journal,
                created_by=cls.user,
                **{field_name: related},
                **origin,
            )

        cls.platform_link = models.SharedJournalPlatform.objects.create(
            journal=cls.public_journal,
            platform=cls.published_platform,
            created_by=cls.user,
        )
        models.SharedJournalLicense.objects.create(
            journal=cls.public_journal,
            license=cls.license,
            created_by=cls.user,
        )
        models.SharedJournalPlatform.objects.create(
            journal=cls.inactive_journal,
            platform=cls.draft_platform,
            created_by=cls.user,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    @staticmethod
    def _ids(response):
        return [item["id"] for item in response.data["results"]]

    def test_admin_filters_active_true_and_false(self):
        active = self.client.get("/api/journals/?active=true")
        inactive = self.client.get("/api/journals/?active=false")

        self.assertEqual(active.status_code, 200)
        self.assertEqual(self._ids(active), [self.public_journal.pk])
        self.assertEqual(inactive.status_code, 200)
        self.assertEqual(self._ids(inactive), [self.inactive_journal.pk])

    def test_admin_status_filter_separates_pending_and_deactivated_with_pagination(self):
        another_pending = models.Journal.objects.create(
            issn="3333-3333",
            title="Gamma Journal",
            active=False,
            created_by=self.user,
        )
        deactivated = models.Journal.objects.create(
            issn="4444-4444",
            title="Delta Journal",
            active=False,
            validated_by=self.user,
            validated_at=timezone.now(),
            created_by=self.user,
        )

        first_page = self.client.get(
            "/api/journals/",
            {"status": "pending", "page_size": 1, "page": 1},
        )
        second_page = self.client.get(
            "/api/journals/",
            {"status": "pending", "page_size": 1, "page": 2},
        )
        deactivated_page = self.client.get(
            "/api/journals/",
            {"status": "deactivated"},
        )

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(first_page.data["total_items"], 2)
        self.assertEqual(first_page.data["total_pages"], 2)
        self.assertEqual(second_page.status_code, 200)
        self.assertEqual(deactivated_page.status_code, 200)
        self.assertEqual(
            self._ids(first_page) + self._ids(second_page),
            [self.inactive_journal.pk, another_pending.pk],
        )
        self.assertEqual(self._ids(deactivated_page), [deactivated.pk])

    def test_admin_status_filter_combines_with_existing_active_filter(self):
        response = self.client.get(
            "/api/journals/",
            {"active": "true", "status": "pending"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_items"], 0)

    def test_public_journal_relations_are_prefetched_per_page(self):
        models.Journal.objects.create(
            issn="5555-5555",
            title="Second Public Journal",
            active=True,
            validated_by=self.user,
            validated_at=timezone.now(),
            created_by=self.user,
        )

        with CaptureQueriesContext(connection) as one_item_queries:
            one_item_response = self.client.get(
                "/api/journals/public/",
                {"page_size": 1},
            )
        with CaptureQueriesContext(connection) as two_item_queries:
            two_item_response = self.client.get(
                "/api/journals/public/",
                {"page_size": 2},
            )

        self.assertEqual(one_item_response.status_code, 200)
        self.assertEqual(two_item_response.status_code, 200)
        self.assertEqual(len(one_item_queries), len(two_item_queries))

    def test_public_journal_list_has_shared_cache_policy_for_anonymous_requests(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/journals/public/")
        self.assertEqual(response.status_code, 200)
        cache_control = response.headers["Cache-Control"]
        self.assertIn("public", cache_control)
        self.assertIn("max-age=0", cache_control)
        self.assertIn("s-maxage=300", cache_control)

    def test_public_journal_list_is_not_shared_cached_for_authenticated_requests(self):
        response = self.client.get("/api/journals/public/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("s-maxage=300", response.headers.get("Cache-Control", ""))

    def test_admin_supports_common_relational_filters(self):
        params = {
            "issn": "11111111",
            "title": "alpha",
            "editorial": self.editorial.pk,
            "language": self.language.pk,
            "country": self.country.pk,
            "knowledge_area": self.knowledge_area.pk,
            "material_type": self.material_type.pk,
            "academic_program": self.academic_program.pk,
            "platform": self.published_platform.pk,
            "license": self.license.pk,
            "has_apc": "false",
            "publication_date_from": "2020-01-01",
            "publication_date_to": "2020-12-31",
        }

        response = self.client.get("/api/journals/", params)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._ids(response), [self.public_journal.pk])

    def test_public_relational_filters_return_the_expected_journal(self):
        filters = {
            "editorial": self.editorial.pk,
            "language": self.language.pk,
            "country": self.country.pk,
            "knowledge_area": self.knowledge_area.pk,
            "material_type": self.material_type.pk,
            "academic_program": self.academic_program.pk,
            "platform": self.published_platform.pk,
            "license": self.license.pk,
        }

        for parameter, value in filters.items():
            with self.subTest(parameter=parameter):
                response = self.client.get(
                    "/api/journals/public/",
                    {parameter: value},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self._ids(response), [self.public_journal.pk])

    def test_public_scalar_and_date_filters_can_be_combined(self):
        response = self.client.get(
            "/api/journals/public/",
            {
                "issn": "11111111",
                "title": "alpha",
                "has_apc": "false",
                "publication_date_from": "2020-01-01",
                "publication_date_to": "2020-12-31",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._ids(response), [self.public_journal.pk])

    def test_public_platform_filter_ignores_non_published_platforms(self):
        self.inactive_journal.active = True
        self.inactive_journal.validated_by = self.user
        self.inactive_journal.validated_at = self.public_journal.validated_at
        self.inactive_journal.save(
            update_fields=["active", "validated_by", "validated_at"]
        )

        response = self.client.get(
            "/api/journals/public/",
            {"platform": self.draft_platform.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._ids(response), [])

    def test_soft_deleted_relation_does_not_influence_filter(self):
        self.platform_link.soft_delete(
            user=self.user,
            explanation="Validar filtros con Soft Delete",
        )

        response = self.client.get(
            "/api/journals/public/",
            {"platform": self.published_platform.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._ids(response), [])

    def test_soft_deleted_editorial_does_not_influence_admin_filter(self):
        self.editorial.soft_delete(
            user=self.user,
            explanation="Validar editorial eliminada",
        )

        response = self.client.get(
            "/api/journals/",
            {"editorial": self.editorial.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._ids(response), [])

    def test_relational_joins_do_not_duplicate_results(self):
        response = self.client.get(
            "/api/journals/public/",
            {
                "language": self.language.pk,
                "country": self.country.pk,
                "academic_program": self.academic_program.pk,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._ids(response), [self.public_journal.pk])

    def test_invalid_filter_values_return_bad_request(self):
        for params in (
            {"country": "invalid"},
            {"publication_date_from": "not-a-date"},
        ):
            with self.subTest(params=params):
                response = self.client.get("/api/journals/public/", params)
                self.assertEqual(response.status_code, 400)

    def test_search_ordering_and_pagination_apply_to_filtered_queryset(self):
        response = self.client.get(
            "/api/journals/",
            {
                "search": "Journal",
                "active": "true",
                "ordering": "-publication_date",
                "page_size": 1,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["page_size"], 1)
        self.assertEqual(self._ids(response), [self.public_journal.pk])
