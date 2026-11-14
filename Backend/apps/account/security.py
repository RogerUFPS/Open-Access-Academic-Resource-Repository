import base64
import hashlib
import hmac
import struct
import time

from django.conf import settings
from apps.core.utils.crypto import decrypt_api_key, encrypt_api_key


def audit_superadmin(action, *, actor=None, target=None, details=None):
    from .models import SuperadminAuditEvent

    SuperadminAuditEvent.objects.create(
        actor=actor,
        actor_email=actor.email if actor else "",
        action=action,
        target=target,
        target_email=target.email if target else "",
        details=details or {},
    )


def _secret(user):
    return decrypt_api_key(user.mfa_secret)


def _totp_key(secret):
    # RFC 6238 / authenticator apps use the Base32-decoded bytes as the HMAC key.
    normalized = secret.replace(" ", "").upper()
    return base64.b32decode(normalized + "=" * (-len(normalized) % 8))


def totp_code(secret, at=None):
    counter = int((at or time.time()) // 30)
    digest = hmac.new(_totp_key(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{number % 1_000_000:06d}"


def verify_totp(user, code):
    secret = _secret(user)
    if not secret or not code or len(code) != 6 or not code.isdigit():
        return False
    now = time.time()
    return any(hmac.compare_digest(totp_code(secret, now + shift * 30), code)
               for shift in (-1, 0, 1))


def new_totp_secret():
    return base64.b32encode(__import__("secrets").token_bytes(20)).decode().rstrip("=")


def encrypt_totp_secret(secret):
    return encrypt_api_key(secret)


def enrollment_uri(user, secret):
    from urllib.parse import quote
    label = quote(f"{settings.DEFAULT_FROM_EMAIL}:{user.email}")
    issuer = quote("Biblioteca")
    return f"otpauth://totp/{label}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"
