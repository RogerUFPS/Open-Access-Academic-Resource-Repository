from datetime import timedelta
from typing import Any, cast
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APITestCase

from apps.account.models import User
from apps.core.storage import StoredImage
from apps.catalog.models import (
    AcademicProgram,
    Country,
    Institution,
    KnowledgeArea,
    Language,
    MaterialType,
)
from apps.platforms import models, services
from apps.journal.models import Journal, SharedJournalPlatform


class PlatformAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.system = User.objects.get(code=0)
        cls.system.is_superadmin = True
        cls.system.save(update_fields=["is_superadmin"])

        cls.institution = Institution.objects.create(
            name="UFPS pruebas Platform",
            created_by=cls.system,
        )

        cls.language = Language.objects.create(
            name="Español pruebas Platform",
            abbreviation="test-es",
            created_by=cls.system,
        )

        cls.country = Country.objects.create(
            name="Colombia pruebas Platform",
            abbreviation="test-co",
            emoji_flag="🇨🇴",
            created_by=cls.system,
        )

        cls.knowledge_area = KnowledgeArea.objects.create(
            name="Ingeniería pruebas Platform",
            created_by=cls.system,
        )

        cls.material_type = MaterialType.objects.create(
            name="Artículos pruebas Platform",
            created_by=cls.system,
        )

        cls.academic_program = AcademicProgram.objects.create(
            name="Ingeniería de Sistemas pruebas Platform",
            created_by=cls.system,
        )

        cls.sintaxis = models.ValidSintaxis.objects.create(
            name="Sintaxis Estandar",
            booleans=["AND", "OR"],
            parenthesis=True,
            fields={"title": "ti"},
            created_by=cls.system,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.system)

    def _get_data(self, response: Any) -> dict[str, Any]:
        """Helper para obtener el payload asegurando el tipado estático."""
        return getattr(response, "data", {})

    def test_similar_syntax_returns_explainable_exact_match(self):
        response = self.client.post(
            "/api/platforms/valid-sintaxis/similar/",
            {
                "booleans": ["AND", "OR"],
                "parenthesis": True,
                "fields": {"title": "ti"},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        result = response.data["results"][0]
        self.assertEqual(result["id"], self.sintaxis.pk)
        self.assertEqual(result["similarity"], 100)
        self.assertEqual(result["different_fields"], [])

    def test_platform_can_be_created_incomplete_as_draft(self):
        response = self.client.post(
            "/api/platforms/",
            {
                "name": "borrador incompleto",
                "public_url": "https://8.8.8.8/draft",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], models.Platform.Status.BORRADOR)

    def _setup_complete_platform(
        self,
        name="Plataforma API Test",
    ):
        platform = models.Platform.objects.create(
            name=name,
            url_image="https://example.org/platform.png",
            is_harvestable=True,
            base_api_url="https://api.test.org",
            valid_sintaxis=self.sintaxis,
            created_by=self.system,
        )

        models.SharedPlatformSupport.objects.create(
            platform=platform,
            institution=self.institution,
            created_by=self.system,
        )

        models.SharedPlatformLanguage.objects.create(
            platform=platform,
            language=self.language,
            created_by=self.system,
        )

        models.SharedPlatformCountry.objects.create(
            platform=platform,
            country=self.country,
            created_by=self.system,
        )

        models.SharedPlatformKnowledgeArea.objects.create(
            platform=platform,
            knowledge_area=self.knowledge_area,
            created_by=self.system,
        )

        models.SharedPlatformMaterialType.objects.create(
            platform=platform,
            material_type=self.material_type,
            created_by=self.system,
        )

        models.SharedPlatformAcademicProgram.objects.create(
            platform=platform,
            academic_program=self.academic_program,
            created_by=self.system,
        )

        # La URL pública pertenece a LinkCheckLog y es requisito
        # para publicar la plataforma.
        models.LinkCheckLog.objects.create(
            platform=platform,
            url="https://www.plataforma-api-test.org",
            fail_count=0,
            http_status_code=200,
            is_active=True,
            last_check=timezone.now(),
            created_by=self.system,
        )

        return platform

    def test_create_platform_endpoint(self):
        """Verifica la creacion administrativa via POST /api/platforms/."""
        response = self.client.post(
            "/api/platforms/",
            {
                "name": "Scopus API Test",
                "public_url": "https://8.8.8.8/scopus",
                "is_harvestable": True,
                "base_api_url": "https://api.scopus.com",
                "api_key": "raw_secret_key",
                "valid_sintaxis": self.sintaxis.pk,
                "institutions": [self.institution.pk],
            },
            format="json",
        )

        data = self._get_data(response)

        self.assertEqual(
            response.status_code,
            201,
        )

        self.assertEqual(
            data["name"],
            "scopus api test",
        )

        self.assertNotIn(
            "encrypted_api_key",
            data,
        )
        self.assertNotIn("api_key", data)
        self.assertEqual(data["public_url"], "https://8.8.8.8/scopus")
        self.assertTrue(data["is_harvestable"])
        platform = models.Platform.objects.get(pk=data["id"])
        self.assertEqual(platform.start_period, timezone.localdate())
        self.assertIsNone(platform.finish_period)
        self.assertFalse(hasattr(platform, "public_url"))
        self.assertTrue(
            models.LinkCheckLog.objects.filter(
                platform=platform,
                journal_platform__isnull=True,
                url="https://8.8.8.8/scopus",
            ).exists()
        )

    @patch("apps.core.viewsets.upload_image")
    def test_upload_image_action_sets_permanent_url(self, upload_image):
        platform = models.Platform.objects.create(
            name="Plataforma con imagen",
            created_by=self.system,
        )
        upload_image.return_value = StoredImage(
            key="platforms/logo.png",
            url="http://localhost:9000/imagenes/platforms/logo.png",
            content_type="image/png",
            size=40,
            thumbnail_key="platforms/logo.thumbnail.webp",
            thumbnail_url="http://localhost:9000/imagenes/platforms/logo.thumbnail.webp",
        )

        response = self.client.post(
            f"/api/platforms/{platform.pk}/image/",
            {
                "image": SimpleUploadedFile(
                    "logo.png",
                    b"\x89PNG\r\n\x1a\n" + (b"\x00" * 32),
                    content_type="image/png",
                )
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["url_image"],
            "http://localhost:9000/imagenes/platforms/logo.png",
        )
        self.assertEqual(
            response.data["url_image_thumbnail"],
            "http://localhost:9000/imagenes/platforms/logo.thumbnail.webp",
        )

        platform.refresh_from_db()
        self.assertEqual(
            platform.url_image,
            "http://localhost:9000/imagenes/platforms/logo.png",
        )
        self.assertEqual(platform.updated_by_id, self.system.pk)

    def test_changing_platform_image_url_clears_outdated_thumbnail(self):
        platform = models.Platform.objects.create(
            name="Plataforma URL actualizable",
            url_image="https://example.org/old.png",
            url_image_thumbnail="https://example.org/old.thumbnail.webp",
            created_by=self.system,
        )
        response = self.client.patch(
            f"/api/platforms/{platform.pk}/",
            {"url_image": "https://example.org/new.png"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["url_image_thumbnail"])
        platform.refresh_from_db()
        self.assertIsNone(platform.url_image_thumbnail)

    def test_public_platform_relations_are_prefetched_per_page(self):
        first = self._setup_complete_platform("Public query count one")
        second = self._setup_complete_platform("Public query count two")
        services.publish_platform(platform=first, user=self.system)
        services.publish_platform(platform=second, user=self.system)

        with CaptureQueriesContext(connection) as one_item_queries:
            one_item_response = self.client.get(
                "/api/platforms/public/",
                {"page_size": 1},
            )
        with CaptureQueriesContext(connection) as two_item_queries:
            two_item_response = self.client.get(
                "/api/platforms/public/",
                {"page_size": 2},
            )

        self.assertEqual(one_item_response.status_code, 200)
        self.assertEqual(two_item_response.status_code, 200)
        self.assertEqual(len(one_item_queries), len(two_item_queries))

    def test_public_platform_list_has_shared_cache_policy_for_anonymous_requests(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/platforms/public/")
        self.assertEqual(response.status_code, 200)
        cache_control = response.headers["Cache-Control"]
        self.assertIn("public", cache_control)
        self.assertIn("max-age=0", cache_control)
        self.assertIn("s-maxage=300", cache_control)

    def test_public_platform_list_is_not_shared_cached_for_authenticated_requests(self):
        response = self.client.get("/api/platforms/public/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("s-maxage=300", response.headers.get("Cache-Control", ""))

    @patch("apps.core.viewsets.delete_image_by_url")
    def test_delete_image_action_clears_url(self, delete_image_by_url):
        platform = models.Platform.objects.create(
            name="Plataforma sin imagen",
            url_image="http://localhost:9000/imagenes/platforms/logo.png",
            created_by=self.system,
        )

        response = self.client.delete(
            f"/api/platforms/{platform.pk}/image/",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["url_image"])

        platform.refresh_from_db()
        self.assertIsNone(platform.url_image)
        delete_image_by_url.assert_called_once_with(
            "http://localhost:9000/imagenes/platforms/logo.png"
        )

    def test_create_platform_defaults_to_not_harvestable(self):
        response = self.client.post(
            "/api/platforms/",
            {
                "name": "Referencia por defecto",
                "public_url": "https://8.8.8.8/reference-default",
            },
            format="json",
        )
        data = self._get_data(response)

        self.assertEqual(response.status_code, 201)
        self.assertFalse(data["is_harvestable"])
        self.assertFalse(
            models.Platform.objects.get(pk=data["id"]).is_harvestable
        )

    def test_api_rejects_manual_lifecycle_dates(self):
        response = self.client.post(
            "/api/platforms/",
            {
                "name": "Fechas manuales",
                "public_url": "https://8.8.8.8/manual-dates",
                "start_period": "2000-01-01",
                "finish_period": "2001-01-01",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("start_period", response.data)
        self.assertIn("finish_period", response.data)

    def test_create_platform_accepts_explicit_not_harvestable(self):
        response = self.client.post(
            "/api/platforms/",
            {
                "name": "Referencia explícita",
                "is_harvestable": False,
                "public_url": "https://8.8.8.8/reference-explicit",
            },
            format="json",
        )
        data = self._get_data(response)

        self.assertEqual(response.status_code, 201)
        self.assertFalse(data["is_harvestable"])

    def test_publish_action_endpoint(self):
        """Verifica la accion POST /api/platforms/{id}/publish/."""
        platform = self._setup_complete_platform()

        response = self.client.post(
            f"/api/platforms/{platform.pk}/publish/"
        )

        data = self._get_data(response)

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            data["status"],
            models.Platform.Status.PUBLICADO,
        )

    def test_restore_action_resets_status_to_draft(self):
        """Verifica que restaurar una plataforma por endpoint la devuelva a BORRADOR."""
        platform = self._setup_complete_platform()

        services.publish_platform(
            platform=platform,
            user=self.system,
        )

        platform.soft_delete(
            user=self.system,
            explanation="Eliminando ficha activa",
        )

        response = self.client.post(
            f"/api/platforms/{platform.pk}/restore/"
        )

        data = self._get_data(response)

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            data["status"],
            models.Platform.Status.BORRADOR,
        )

        self.assertIsNone(
            data["validated_by"],
        )

        self.assertIsNone(
            data["validated_at"],
        )
        self.assertIsNone(data["finish_period"])

    def test_public_endpoint_only_lists_published_platforms(self):
        """El endpoint publico solo debe retornar plataformas en estado PUBLICADO."""
        self._setup_complete_platform(
            "Borrador Oculto"
        )

        pub = self._setup_complete_platform(
            "Publica Visible"
        )

        services.publish_platform(
            platform=pub,
            user=self.system,
        )

        response = self.client.get(
            "/api/platforms/public/"
        )

        data = self._get_data(response)

        self.assertEqual(
            response.status_code,
            200,
        )

        results = data["results"]

        self.assertEqual(
            len(results),
            1,
        )

        self.assertEqual(
            results[0]["name"],
            "publica visible",
        )

        self.assertIn(
            "item_number",
            results[0],
        )

    def test_public_filter_by_catalog_relations(self):
        """Verifica los filtros en singular para catalogos en el endpoint publico."""
        pub = self._setup_complete_platform(
            "Publica Filtrable"
        )

        services.publish_platform(
            platform=pub,
            user=self.system,
        )

        response = self.client.get(
            f"/api/platforms/public/?country={self.country.pk}"
        )

        data = self._get_data(response)

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            len(data["results"]),
            1,
        )

        response_empty = self.client.get(
            "/api/platforms/public/?country=99999"
        )

        data_empty = self._get_data(
            response_empty
        )

        self.assertEqual(
            response_empty.status_code,
            200,
        )

        self.assertEqual(
            len(data_empty["results"]),
            0,
        )

    def test_link_history_orders_checks_newest_first_and_pending_last(self):
        platform = models.Platform.objects.create(
            name="Historial ordenado",
            created_by=self.system,
        )
        now = timezone.now()
        oldest = models.LinkCheckLog.objects.create(
            platform=platform,
            url="https://8.8.8.8/oldest",
            http_status_code=500,
            is_active=False,
            fail_count=1,
            last_check=now - timedelta(hours=2),
            created_by=self.system,
        )
        newest = models.LinkCheckLog.objects.create(
            platform=platform,
            url="https://8.8.8.8/newest",
            http_status_code=200,
            is_active=True,
            last_check=now,
            created_by=self.system,
        )
        pending = models.LinkCheckLog.objects.create(
            platform=platform,
            url="https://8.8.8.8/pending",
            created_by=self.system,
        )

        response = self.client.get(
            f"/api/platforms/link-check-logs/?platform={platform.pk}"
            "&page_size=2"
        )
        data = self._get_data(response)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["total_items"], 3)
        self.assertEqual(
            [item["id"] for item in data["results"]],
            [newest.pk, oldest.pk],
        )
        second_page = self.client.get(
            f"/api/platforms/link-check-logs/?platform={platform.pk}"
            "&page_size=2&page=2"
        )
        second_page_data = self._get_data(second_page)
        self.assertEqual(second_page_data["results"][0]["id"], pending.pk)
        self.assertIsNone(second_page_data["results"][0]["last_check"])
        self.assertFalse(second_page_data["results"][0]["is_active"])
        self.assertEqual(
            second_page_data["results"][0]["verification_status"], "unverified"
        )

    def test_link_history_uses_created_at_and_id_as_tiebreakers(self):
        platform = models.Platform.objects.create(
            name="Historial con empate",
            created_by=self.system,
        )
        checked_at = timezone.now()
        first = models.LinkCheckLog.objects.create(
            platform=platform,
            url="https://8.8.8.8/first",
            last_check=checked_at,
            created_by=self.system,
        )
        second = models.LinkCheckLog.objects.create(
            platform=platform,
            url="https://8.8.8.8/second",
            last_check=checked_at,
            created_by=self.system,
        )
        same_created_at = timezone.now() - timedelta(hours=1)
        models.LinkCheckLog.all_objects.filter(
            pk__in=[first.pk, second.pk]
        ).update(created_at=same_created_at)

        response = self.client.get(
            f"/api/platforms/link-check-logs/?platform={platform.pk}"
        )
        data = self._get_data(response)

        self.assertEqual(
            [item["id"] for item in data["results"]],
            [second.pk, first.pk],
        )

    def test_link_history_filters_by_verification_status(self):
        platform = models.Platform.objects.create(
            name="Historial por estado",
            created_by=self.system,
        )
        states = (
            ("unverified", False, None),
            ("available", True, timezone.now()),
            ("unavailable", False, timezone.now()),
        )
        expected_ids = {}
        for state, is_active, last_check in states:
            log = models.LinkCheckLog.objects.create(
                platform=platform,
                url=f"https://8.8.8.8/{state}",
                is_active=is_active,
                last_check=last_check,
                created_by=self.system,
            )
            expected_ids[state] = log.pk

        for state, expected_id in expected_ids.items():
            response = self.client.get(
                f"/api/platforms/link-check-logs/?platform={platform.pk}"
                f"&verification_status={state}"
            )
            data = self._get_data(response)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(data["total_items"], 1)
            self.assertEqual(data["results"][0]["id"], expected_id)
            self.assertEqual(data["results"][0]["verification_status"], state)

    @patch("apps.platforms.services._perform_link_check", return_value=(200, True))
    @patch("apps.platforms.services._validate_safe_http_url")
    def test_successful_check_is_consistent_with_history(
        self,
        _mock_validate,
        _mock_check,
    ):
        platform = models.Platform.objects.create(
            name="Chequeo coherente",
            status=models.Platform.Status.PUBLICADO,
            created_by=self.system,
        )
        response = self.client.post(
            f"/api/platforms/{platform.pk}/check-link/",
            {"url": "https://www.example.org"},
            format="json",
        )
        checked = self._get_data(response)
        history_response = self.client.get(
            f"/api/platforms/link-check-logs/?platform={platform.pk}"
            "&journal_platform__isnull=true"
        )
        history = self._get_data(history_response)["results"][0]
        public_response = self.client.get(
            f"/api/platforms/public/{platform.pk}/"
        )
        link_status = self._get_data(public_response)["link_status"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(history["id"], checked["id"])
        self.assertEqual(history["http_status_code"], 200)
        self.assertTrue(history["is_active"])
        self.assertEqual(history["fail_count"], 0)
        self.assertEqual(history["last_check"], checked["last_check"])
        self.assertEqual(link_status["is_active"], history["is_active"])
        self.assertEqual(link_status["last_check"], history["last_check"])
        self.assertEqual(history["verification_status"], "available")
        self.assertEqual(link_status["verification_status"], "available")

    def test_link_history_can_exclude_journal_urls(self):
        platform = models.Platform.objects.create(
            name="Historial por contexto",
            created_by=self.system,
        )
        journal = Journal.objects.create(
            issn="1234-5678",
            title="Revista contextual",
            created_by=self.system,
        )
        relation = SharedJournalPlatform.objects.create(
            journal=journal,
            platform=platform,
            created_by=self.system,
        )
        general = models.LinkCheckLog.objects.create(
            platform=platform,
            url="https://8.8.8.8/general",
            last_check=timezone.now(),
            created_by=self.system,
        )
        models.LinkCheckLog.objects.create(
            platform=platform,
            journal_platform=relation,
            url="https://8.8.8.8/journal",
            last_check=timezone.now(),
            created_by=self.system,
        )

        response = self.client.get(
            f"/api/platforms/link-check-logs/?platform={platform.pk}"
            "&journal_platform__isnull=true"
        )
        data = self._get_data(response)

        self.assertEqual(data["total_items"], 1)
        self.assertEqual(data["results"][0]["id"], general.pk)
