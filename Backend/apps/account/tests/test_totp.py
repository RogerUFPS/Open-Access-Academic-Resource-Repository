from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.account.security import totp_code, verify_totp

# Base32 of the RFC 6238 SHA-1 test key "12345678901234567890".
RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


class TotpTests(SimpleTestCase):
    def test_matches_rfc_6238_test_vectors(self):
        # RFC 6238, Appendix B (last 6 digits of the 8-digit values).
        self.assertEqual(totp_code(RFC_SECRET, 59), "287082")
        self.assertEqual(totp_code(RFC_SECRET, 1111111109), "081804")
        self.assertEqual(totp_code(RFC_SECRET, 2000000000), "279037")

    def test_accepts_unpadded_lowercase_and_spaced_secrets(self):
        self.assertEqual(totp_code(RFC_SECRET.lower(), 59), "287082")
        self.assertEqual(totp_code("GEZD GNBV GY3T QOJQ GEZD GNBV GY3T QOJQ", 59), "287082")

    @patch("apps.account.security._secret", return_value=RFC_SECRET)
    @patch("apps.account.security.time.time", return_value=59)
    def test_verify_accepts_authenticator_code_with_clock_drift(self, *_mocks):
        user = SimpleNamespace()
        self.assertTrue(verify_totp(user, "287082"))
        self.assertTrue(verify_totp(user, totp_code(RFC_SECRET, 89)))  # next 30 s window
        self.assertFalse(verify_totp(user, "000000"))
