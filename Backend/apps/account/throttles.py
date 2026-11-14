"""Rate limits for credential and MFA verification endpoints."""

import hashlib
import math
import time

from django.core.cache import cache
from rest_framework.throttling import SimpleRateThrottle

from .session_security import client_ip


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def credential_identity(request, account):
    return _digest(f"{client_ip(request)}:{str(account).strip().lower()}")


def progressive_wait(request, account, scope):
    state = cache.get(f"security-failures:{scope}:{credential_identity(request, account)}") or {}
    return max(0, math.ceil(state.get("blocked_until", 0) - time.time()))


def record_failure(request, account, scope):
    key = f"security-failures:{scope}:{credential_identity(request, account)}"
    state = cache.get(key) or {"attempts": 0}
    attempts = int(state.get("attempts", 0)) + 1
    delay = 0 if attempts < 3 else min(2 ** (attempts - 3), 60)
    cache.set(
        key,
        {"attempts": attempts, "blocked_until": time.time() + delay},
        timeout=60 * 60,
    )


def clear_failures(request, account, scope):
    cache.delete(f"security-failures:{scope}:{credential_identity(request, account)}")


class _EmailIPThrottle(SimpleRateThrottle):
    """Keep account enumeration out of cache keys while limiting IP+account."""

    def get_cache_key(self, request, view):
        email = str(request.data.get("email", "")).strip().lower()
        identity = f"{self.get_ident(request)}:{email}"
        return self.cache_format % {
            "scope": self.scope,
            "ident": _digest(identity),
        }


class LoginBurstThrottle(_EmailIPThrottle):
    scope = "login_burst"


class LoginSustainedThrottle(_EmailIPThrottle):
    scope = "login_sustained"


class PasswordRecoveryThrottle(_EmailIPThrottle):
    scope = "password_recovery"


class _MFAThrottle(SimpleRateThrottle):
    def get_cache_key(self, request, view):
        user_id = getattr(getattr(request, "user", None), "pk", "anonymous")
        identity = f"{self.get_ident(request)}:{user_id}"
        return self.cache_format % {
            "scope": self.scope,
            "ident": _digest(identity),
        }


class MFABurstThrottle(_MFAThrottle):
    scope = "mfa_burst"


class MFASustainedThrottle(_MFAThrottle):
    scope = "mfa_sustained"
