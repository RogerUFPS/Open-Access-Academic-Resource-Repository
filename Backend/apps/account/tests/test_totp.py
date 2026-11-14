from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.account.security import totp_code, verify_totp


class TotpRfc6238Tests(SimpleTestCase):
    # RFC 6238 Appendix B, SHA-1 key "12345678901234567890".
    SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"

    def test_rfc6238_sha1_vector_uses_decoded_base32_key(self):
        self.assertEqual(totp_code(self.SECRET, at=59), "287082")

    def test_verification_accepts_unpadded_lowercase_base32(self):
        user = SimpleNamespace(mfa_secret="configured")
        with (
            patch("apps.account.security._secret", return_value=self.SECRET.lower()),
            patch("apps.account.security.time.time", return_value=59),
        ):
            self.assertTrue(verify_totp(user, "287082"))

    def test_invalid_base32_secret_is_rejected(self):
        with self.assertRaises(ValueError):
            totp_code("not a valid secret!", at=59)
