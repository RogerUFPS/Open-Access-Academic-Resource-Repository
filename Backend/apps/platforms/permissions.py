from apps.account.permissions import ApplicationPermission


class LinkVerificationPermission(ApplicationPermission):
    """Asocia las acciones propias al permiso existente de verificación.

    ApplicationPermission conserva las comprobaciones de autenticación,
    cambio de contraseña y permisos efectivos, incluidos presets/superadmin.
    """

    @staticmethod
    def _operation(method, tail):
        if method == "POST" and tail and tail[-1] in {
            "check-links", "check-links-async", "check-failed-links",
        }:
            return "check_link"
        return ApplicationPermission._operation(method, tail)
