from auditlog.context import disable_auditlog

from .permissions import PUBLIC_ACCOUNT_PATHS
from .session_security import (
    SESSION_IP,
    SESSION_USER_AGENT,
    client_ip,
    make_private_no_store,
    user_agent,
)


class AuditDisableForPublicMiddleware:
    """
    Deshabilita el registro de auditoría (django-auditlog) para los
    endpoints públicos que no requieren autenticación.

    Esto evita que operaciones como login, registro y recuperación de
    contraseña generen entradas en la bitácora, ya que en esos flujos
    el usuario aún no está autenticado y no existe un «actor» válido.

    Las rutas cubiertas son las declaradas en PUBLIC_ACCOUNT_PATHS
    del módulo de permisos:
        - /api/accounts/auth/csrf/
        - /api/accounts/auth/login/
        - /api/accounts/register/
        - /api/accounts/password/forgot/
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info.rstrip("/") + "/"
        if path in PUBLIC_ACCOUNT_PATHS:
            with disable_auditlog():
                return self.get_response(request)
        return self.get_response(request)


class SessionSecurityMiddleware:
    """Record context changes without treating mobile IP changes as a lockout."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        session = getattr(request, "session", None)
        if user and user.is_authenticated and session and session.session_key:
            current_ip = client_ip(request)
            current_agent = user_agent(request)
            previous_ip = session.get(SESSION_IP)
            previous_agent = session.get(SESSION_USER_AGENT)
            changed = (
                (previous_ip and previous_ip != current_ip)
                or (previous_agent and previous_agent != current_agent)
            )
            if previous_ip != current_ip:
                session[SESSION_IP] = current_ip
            if previous_agent != current_agent:
                session[SESSION_USER_AGENT] = current_agent
            if changed and user.is_superadmin:
                from .security import audit_superadmin

                audit_superadmin(
                    "session_context_changed",
                    actor=user,
                    target=user,
                    details={
                        "ip_changed": previous_ip != current_ip,
                        "user_agent_changed": previous_agent != current_agent,
                    },
                )
        response = self.get_response(request)
        if request.path_info.startswith("/api/accounts/auth/"):
            make_private_no_store(response)
        return response
