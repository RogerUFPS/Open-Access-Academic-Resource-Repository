"""Security metadata and rotation helpers for authenticated sessions."""

import time

from django.conf import settings
from django.utils import timezone
from django.utils.cache import patch_cache_control

PASSWORD_VERIFIED_AT = "password_verified_at"
MFA_VERIFIED_AT = "mfa_verified_at"
SESSION_STARTED_AT = "session_started_at"
SESSION_IP = "session_ip"
SESSION_USER_AGENT = "session_user_agent"
MFA_ENROLLMENT_STARTED_AT = "mfa_enrollment_started_at"


def client_ip(request):
    forwarded = [
        part.strip()
        for part in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")
        if part.strip()
    ]
    proxy_count = getattr(settings, "NUM_PROXIES", 0)
    if forwarded and proxy_count and len(forwarded) >= proxy_count:
        return forwarded[-proxy_count][:64]
    return request.META.get("REMOTE_ADDR", "")[:64]


def user_agent(request):
    return request.META.get("HTTP_USER_AGENT", "")[:255]


def initialize_session_security(request):
    now = int(time.time())
    request.session[PASSWORD_VERIFIED_AT] = now
    request.session[SESSION_STARTED_AT] = timezone.now().isoformat()
    request.session[SESSION_IP] = client_ip(request)
    request.session[SESSION_USER_AGENT] = user_agent(request)


def mark_mfa_verified(request):
    request.session[MFA_VERIFIED_AT] = int(time.time())


def rotate_authenticated_session(request, user):
    """Rotate the bearer credential while preserving authenticated state."""
    request.session.cycle_key()
    request.session.save()
    user.session_key = request.session.session_key
    user.save(update_fields=["session_key"])


def has_recent_authentication(request):
    key = MFA_VERIFIED_AT if request.user.is_superadmin else PASSWORD_VERIFIED_AT
    verified_at = request.session.get(key)
    return (
        isinstance(verified_at, int)
        and int(time.time()) - verified_at <= settings.RECENT_AUTH_AGE
    )


def session_metadata(request):
    key = MFA_VERIFIED_AT if request.user.is_superadmin else PASSWORD_VERIFIED_AT
    remaining = settings.RECENT_AUTH_AGE - (
        int(time.time()) - request.session.get(key, 0)
    )
    return {
        "started_at": request.session.get(SESSION_STARTED_AT),
        "expires_at": request.session.get_expiry_date().isoformat(),
        "ip_address": request.session.get(SESSION_IP, ""),
        "user_agent": request.session.get(SESSION_USER_AGENT, ""),
        "recent_authentication": has_recent_authentication(request),
        "recent_authentication_expires_in": max(
            0, min(settings.RECENT_AUTH_AGE, remaining)
        ),
    }


def make_private_no_store(response):
    patch_cache_control(response, private=True, no_store=True, max_age=0)
    response["Pragma"] = "no-cache"
    return response
