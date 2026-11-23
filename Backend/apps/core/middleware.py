import time

from django.conf import settings

SESSION_RENEWED_AT_KEY = "_session_renewed_at"


class ThrottledSessionRenewalMiddleware:
    """
    Renueva la expiración por inactividad de la sesión con frecuencia limitada.

    Sustituye a ``SESSION_SAVE_EVERY_REQUEST=True``, que escribía la sesión en
    la base de datos en cada petición. Aquí la sesión solo se marca como
    modificada (y ``SessionMiddleware`` la guarda) cuando pasaron al menos
    ``SESSION_RENEWAL_INTERVAL`` segundos desde la última renovación.

    Efecto: la sesión vence entre ``SESSION_COOKIE_AGE - intervalo`` y
    ``SESSION_COOKIE_AGE`` segundos después de la última actividad; nunca
    más tarde que antes. Cierre de sesión, sesión reemplazada e invalidación
    de credenciales siguen borrando la sesión en la base y no cambian.

    Debe ubicarse después de ``SessionMiddleware`` en ``MIDDLEWARE``.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        session = getattr(request, "session", None)
        # Solo se renuevan sesiones usadas por la petición y no vacías:
        # tras un logout (flush) la sesión queda vacía y no debe recrearse.
        if session is None or not session.accessed or session.is_empty():
            return response

        now = int(time.time())
        interval = getattr(settings, "SESSION_RENEWAL_INTERVAL", 0)
        renewed_at = session.get(SESSION_RENEWED_AT_KEY)
        if (
            session.modified
            or not isinstance(renewed_at, int)
            or now - renewed_at >= interval
        ):
            session[SESSION_RENEWED_AT_KEY] = now
        return response
