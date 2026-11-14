"""Regression tests for constant-query account listings."""

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from apps.account.models import AccessPreset, User
from apps.account.views import ArchivedUsersView, UsersView


class UserListQueryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            email="account-query-admin@example.org",
            password="Account-query-admin-927",
            is_superadmin=True,
        )
        cls.preset = AccessPreset.objects.create(
            name="Preset rendimiento cuentas",
            permissions={"accounts": {"users": {"view": True}}},
            created_by=cls.admin,
        )
        for index in range(5):
            user = User.objects.create_user(
                email=f"account-query-{index}@example.org",
                permissions={"catalog": {"languages": {"view": True}}},
                created_by=cls.admin,
            )
            user.presets.add(cls.preset)

    def setUp(self):
        self.request_factory = APIRequestFactory()

    def test_active_users_use_two_queries_with_prefetched_presets(self):
        with self.assertNumQueries(2):
            response = UsersView().get(
                self.request_factory.get("/api/accounts/users/")
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), User.objects.count())
        row = next(item for item in response.data if item["email"] == "account-query-0@example.org")
        self.assertEqual(row["presets"], [self.preset.pk])
        self.assertTrue(
            row["effective_permissions"]["accounts"]["users"]["view"]
        )

    def test_archived_users_use_two_queries_with_prefetched_presets(self):
        archived = User.objects.get(email="account-query-0@example.org")
        archived.soft_delete(self.admin, "Prueba de consultas")

        with self.assertNumQueries(2):
            response = ArchivedUsersView().get(
                self.request_factory.get("/api/accounts/users/archived/")
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["presets"], [self.preset.pk])
        self.assertTrue(
            response.data[0]["effective_permissions"]["accounts"]["users"]["view"]
        )
