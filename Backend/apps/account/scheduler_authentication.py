import hmac

from django.conf import settings
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .models import User


class SchedulerTokenAuthentication(BaseAuthentication):
    """Authenticate scheduler calls as a configured, least-privilege user."""

    keyword = b"bearer"

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts or parts[0].lower() != self.keyword:
            return None
        if len(parts) != 2:
            raise AuthenticationFailed("Invalid scheduler authorization header.")

        configured_token = settings.SCHEDULER_API_TOKEN
        supplied_token = parts[1].decode("utf-8", errors="replace")
        if not configured_token or not hmac.compare_digest(supplied_token, configured_token):
            raise AuthenticationFailed("Invalid scheduler credentials.")

        try:
            user_id = int(settings.SCHEDULER_SERVICE_USER_ID)
        except (TypeError, ValueError):
            raise AuthenticationFailed("Scheduler service account is not configured.")

        try:
            user = User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            raise AuthenticationFailed("Scheduler service account is unavailable.")

        permission = (
            user.effective_permissions()
            .get("platforms", {})
            .get("platforms", {})
            .get("check_link", False)
        )
        if user.is_superadmin or not permission:
            raise AuthenticationFailed(
                "Scheduler service account must have check_link access."
            )
        return user, "scheduler"

    def authenticate_header(self, request):
        return "Bearer"
