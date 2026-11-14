import time
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.account.models import User


class SessionHardeningTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_superuser(
            email="security-session@example.org",
            password="Security-session-password-927",
            full_name="Seguridad de sesión",
        )

    def authenticated_client(self, *, mfa_satisfied=False, recently_verified=False):
        client = APIClient()
        client.force_authenticate(self.user)
        session = client.session
        session["superadmin_mfa_satisfied"] = mfa_satisfied
        session["password_verified_at"] = int(time.time())
        session["session_started_at"] = "2026-11-13T12:00:00+00:00"
        session["session_ip"] = "127.0.0.1"
        session["session_user_agent"] = "test-client"
        if recently_verified:
            session["mfa_verified_at"] = int(time.time())
        session.save()
        return client

    def test_login_is_throttled_by_account_and_ip(self):
        client = APIClient()
        csrf = client.get("/api/accounts/auth/csrf/").cookies["csrftoken"].value
        responses = []
        for _ in range(6):
            response = client.post(
                "/api/accounts/auth/login/",
                {"email": "unknown@example.org", "password": "invalid-password"},
                format="json",
                HTTP_X_CSRFTOKEN=csrf,
            )
            responses.append(response)
            if response.status_code == 429:
                break

        throttled = responses[-1]
        self.assertEqual(throttled.status_code, 429)
        self.assertIn("Retry-After", throttled)

    def test_mfa_enrollment_uses_post_and_is_never_cached(self):
        client = self.authenticated_client()

        self.assertEqual(
            client.get("/api/accounts/auth/mfa/enroll/").status_code,
            405,
        )
        response = client.post("/api/accounts/auth/mfa/enroll/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("secret", response.data)
        self.assertIn("otpauth_uri", response.data)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["Pragma"], "no-cache")

    @patch("apps.account.views.verify_totp", return_value=True)
    def test_mfa_confirmation_rotates_session_cookie(self, verify_totp):
        client = self.authenticated_client()
        enrollment = client.post("/api/accounts/auth/mfa/enroll/")
        self.assertEqual(enrollment.status_code, 200)
        old_key = client.cookies["sessionid"].value

        response = client.post(
            "/api/accounts/auth/mfa/enroll/confirm/",
            {"code": "123456"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(client.cookies["sessionid"].value, old_key)
        self.user.refresh_from_db()
        self.assertTrue(self.user.mfa_enabled)
        self.assertEqual(self.user.session_key, client.cookies["sessionid"].value)
        verify_totp.assert_called_once()

    def test_session_metadata_is_private_and_not_cached(self):
        client = self.authenticated_client(mfa_satisfied=True, recently_verified=True)
        response = client.get("/api/accounts/auth/session/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["ip_address"], "127.0.0.1")
        self.assertTrue(response.data["recent_authentication"])
        self.assertIn("no-store", response["Cache-Control"])

    def test_critical_action_requires_recent_mfa(self):
        client = self.authenticated_client(mfa_satisfied=True)
        response = client.post(
            "/api/accounts/superadmin/accounts/",
            {"email": "new-superadmin@example.org"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "recent_authentication_required")
