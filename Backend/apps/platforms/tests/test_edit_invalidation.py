"""Editar una plataforma publicada la devuelve a BORRADOR (misma regla que Journal)."""

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.account.models import User
from apps.core.testing import satisfy_superadmin_mfa
from apps.platforms import services
from apps.platforms.models import LinkCheckLog, Platform


class PlatformEditInvalidationTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="edicion-plataforma@test.local",
            password="Contrasena-Fuerte-2026",
            full_name="Edición plataforma",
            is_superadmin=True,
        )

    def setUp(self):
        self.client.force_authenticate(self.user)
        satisfy_superadmin_mfa(self.client)

    def platform(self, status):
        validated = status == Platform.Status.PUBLICADO
        platform = Platform.objects.create(
            name=f"Edición {status}",
            status=status,
            validated_by=self.user if validated else None,
            validated_at=timezone.now() if validated else None,
            created_by=self.user,
        )
        LinkCheckLog.objects.create(
            platform=platform,
            url="https://8.8.8.8/edicion",
            is_active=True,
            last_check=timezone.now(),
            created_by=self.user,
        )
        return platform

    def patch(self, platform, data):
        response = self.client.patch(f"/api/platforms/{platform.pk}/", data, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        platform.refresh_from_db()
        return response

    def test_editing_any_field_of_a_published_platform_returns_it_to_draft(self):
        platform = self.platform(Platform.Status.PUBLICADO)

        response = self.patch(platform, {"name": "Edición renombrada"})

        self.assertEqual(response.data["status"], Platform.Status.BORRADOR)
        self.assertEqual(platform.status, Platform.Status.BORRADOR)
        self.assertIsNone(platform.validated_by)
        self.assertIsNone(platform.validated_at)

    def test_new_public_url_returns_to_draft_and_must_be_verified_again(self):
        platform = self.platform(Platform.Status.PUBLICADO)

        self.patch(platform, {"public_url": "https://8.8.4.4/nueva"})

        self.assertEqual(platform.status, Platform.Status.BORRADOR)
        current = services.latest_platform_link_log(platform)
        self.assertEqual(current.url, "https://8.8.4.4/nueva")
        self.assertFalse(services.link_is_serving(current))

    def test_draft_and_obsolete_platforms_keep_their_status(self):
        for status in (Platform.Status.BORRADOR, Platform.Status.OBSOLETO):
            with self.subTest(status=status):
                platform = self.platform(status)

                self.patch(platform, {"name": f"Edición {status} renombrada"})

                self.assertEqual(platform.status, status)
