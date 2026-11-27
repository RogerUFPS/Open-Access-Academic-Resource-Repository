from apps.account.permissions import ApplicationPermission


class ArchiveAnomalyPermission(ApplicationPermission):
    """Responder una anomalía exige audit.archive-anomalies.resolve.

    ApplicationPermission conserva sesión, MFA, cambio de contraseña y permisos
    efectivos (incluidos presets y superadmin); solo se nombra la acción propia.
    """

    @staticmethod
    def _operation(method, tail):
        if method == "POST" and tail and tail[-1] == "resolve":
            return "resolve"
        return ApplicationPermission._operation(method, tail)
