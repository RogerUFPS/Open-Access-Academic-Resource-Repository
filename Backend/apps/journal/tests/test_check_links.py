"""POST /api/journals/{id}/check-links/ y estado de verificación de las asociaciones."""

from unittest.mock import patch

from rest_framework.test import APITestCase

from apps.account.models import User
from apps.core.testing import satisfy_superadmin_mfa
from apps.journal import models
from apps.platforms.models import LinkCheckLog, Platform

CHECK_PERMISSION = {"platforms": {"platforms": {"check_link": True}}}
DOWN_URLS = {"https://8.8.8.8/caida/revista"}


def fake_check(url):
    """Responde 500 para las URLs caídas y 200 para el resto, sin red."""
    return (500, False) if url in DOWN_URLS else (200, True)


@patch("apps.platforms.services._perform_link_check", side_effect=fake_check)
@patch("apps.platforms.notifications.enqueue_pending_link_failure_notification")
class JournalCheckLinksTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            email="verificar-revista@test.local",
            password="Contrasena-Fuerte-2026",
            full_name="Verificar revista",
            is_superadmin=True,
        )
        cls.journal = models.Journal.objects.create(
            issn="7070-0001", title="Revista a verificar", created_by=cls.admin,
        )
        cls.serving = cls.associate("sirve", "https://8.8.8.8/sirve/revista")
        cls.down = cls.associate("caida", "https://8.8.8.8/caida/revista")
        cls.draft = cls.associate(
            "borrador", "https://8.8.8.8/borrador/revista", status=Platform.Status.BORRADOR,
        )
        cls.without_url = cls.associate("sin-url", None)

    @classmethod
    def associate(cls, name, journal_url, status=Platform.Status.PUBLICADO):
        platform = Platform.objects.create(name=f"Verificar {name}", status=status, created_by=cls.admin)
        LinkCheckLog.objects.create(
            platform=platform, url=f"https://8.8.8.8/{name}", created_by=cls.admin,
        )
        relation = models.SharedJournalPlatform.objects.create(
            journal=cls.journal, platform=platform, created_by=cls.admin,
        )
        if journal_url:
            LinkCheckLog.objects.create(
                platform=platform, journal_platform=relation, url=journal_url, created_by=cls.admin,
            )
        return relation

    def login(self, user):
        self.client.force_authenticate(user)
        satisfy_superadmin_mfa(self.client)

    def check_links(self):
        return self.client.post(f"/api/journals/{self.journal.pk}/check-links/")

    def by_relation(self, response):
        return {item["relation_id"]: item for item in response.data["platforms"]}

    def test_verifies_every_association_and_reports_which_ones_serve(self, enqueue, perform):
        self.login(self.admin)

        response = self.check_links()

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["publishable"])
        items = self.by_relation(response)
        self.assertEqual(set(items), {
            self.serving.pk, self.down.pk, self.draft.pk, self.without_url.pk,
        })
        self.assertEqual(
            (items[self.serving.pk]["public_url_status"], items[self.serving.pk]["journal_url_status"]),
            ("available", "available"),
        )
        self.assertTrue(items[self.serving.pk]["is_serving"])
        self.assertEqual(items[self.down.pk]["journal_url_status"], "unavailable")
        self.assertFalse(items[self.down.pk]["is_serving"])
        # Ambas URLs sirven, pero la plataforma no está publicada.
        self.assertEqual(items[self.draft.pk]["journal_url_status"], "available")
        self.assertFalse(items[self.draft.pk]["is_serving"])
        # Sin URL de la revista no hay nada que verificar.
        self.assertIsNone(items[self.without_url.pk]["journal_url_status"])
        self.assertFalse(items[self.without_url.pk]["is_serving"])
        enqueue.assert_called_once()

    def test_uses_the_shared_counter_and_history(self, enqueue, perform):
        self.login(self.admin)

        self.check_links()
        self.check_links()

        current = LinkCheckLog.objects.filter(journal_platform=self.down).order_by("-created_at", "-pk").first()
        self.assertEqual(current.fail_count, 2)
        self.assertIsNone(current.check_batch_id)
        # 4 URLs públicas + 3 URLs de revista por ejecución.
        self.assertEqual(perform.call_count, 14)

    def test_not_publishable_when_no_association_serves(self, enqueue, perform):
        self.login(self.admin)
        self.serving.soft_delete(user=self.admin, explanation="Sin la única asociación válida")

        response = self.check_links()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["publishable"])

    def test_requires_link_verification_permission(self, enqueue, perform):
        without = User.objects.create_user(email="sin-verificacion@test.local")
        verifier = User.objects.create_user(email="verificador@test.local", permissions=CHECK_PERMISSION)

        self.login(without)
        self.assertEqual(self.check_links().status_code, 403)

        self.login(verifier)
        self.assertEqual(self.check_links().status_code, 200)

    def test_admin_detail_exposes_the_same_states(self, enqueue, perform):
        self.login(self.admin)
        self.check_links()

        response = self.client.get(f"/api/journals/{self.journal.pk}/")

        self.assertEqual(response.status_code, 200)
        items = {item["relation_id"]: item for item in response.data["platforms"]}
        self.assertTrue(items[self.serving.pk]["is_serving"])
        self.assertEqual(items[self.down.pk]["journal_url_status"], "unavailable")
        self.assertIsNone(items[self.without_url.pk]["journal_url_status"])
