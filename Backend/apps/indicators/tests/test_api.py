from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.account.models import User
from apps.catalog.models import KnowledgeArea
from apps.journal.models import Journal, SharedJournalKnowledgeArea


class IndicatorsApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="indicators@example.org",
            password="test-password",
            permissions={
                "indicators": {
                    "indicators": {
                        "view": True,
                    },
                },
            },
        )
        cls.area = KnowledgeArea.objects.create(
            name="Ciencias de datos",
            created_by=cls.user,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_returns_unified_indicators(self):
        now = timezone.now()
        published = Journal.objects.create(
            issn="1234-5678",
            title="Publicada",
            active=True,
            validated_at=now,
            created_by=self.user,
        )
        SharedJournalKnowledgeArea.objects.create(
            journal=published,
            knowledge_area=self.area,
            is_manual=True,
            created_by=self.user,
        )
        Journal.objects.create(
            issn="8765-4321",
            title="Pendiente",
            active=False,
            created_by=self.user,
        )

        response = self.client.get("/api/indicators/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["published_journals"], 1)
        self.assertEqual(response.data["published_journals_this_month"], 1)
        self.assertEqual(response.data["pending_journals"], 1)
        self.assertEqual(response.data["journals_by_knowledge_area"], [{
            "id": self.area.pk,
            "name": self.area.name,
            "journals": 1,
        }])
        self.assertEqual(len(response.data["publications_by_month"]), 12)

    def test_requires_indicator_permission(self):
        self.user.is_superadmin = False
        self.user.permissions = {}
        self.user.save(update_fields=["is_superadmin", "permissions"])

        response = self.client.get("/api/indicators/")

        self.assertEqual(response.status_code, 403)
